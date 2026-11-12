#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Sanitize a builder-created copy of a source-built APP/UDA tree.

This is not a snapshot sanitizer and must never be run against a live system.
The caller must create a separate copy and its explicit marker first.
It prepares an unverified staging tree; it does not create or flash an image.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

MARKER = '.mocha-source-image-copy'
MARKER_CONTENT = {'schema': 1, 'purpose': 'source-image-staging'}
PRIVATE_NAMES = {'authorized_keys', 'known_hosts', 'cookies.sqlite', 'places.sqlite',
                 'key4.db', 'logins.json', 'sessionstore.jsonlz4',
                 'recovery.jsonlz4', 'recovery.baklz4'}
PURGE = ('.mocha-source-rootfs-build', 'root/.ssh', 'home/mocha/.ssh', 'root/.bash_history', 'home/mocha/.bash_history', 'home/mocha/.cache',
         'home/mocha/.local/state', 'root/.config', 'var/log', 'var/crash',
         'var/backups', 'var/cache/apt/archives', 'var/lib/NetworkManager', 'var/lib/bluetooth',
         'var/lib/upower', 'var/lib/dhcp', 'etc/NetworkManager/system-connections',
         'var/lib/systemd/coredump', 'var/lib/dbus/machine-id',
         'var/lib/systemd/random-seed')


def safe_path(base, relative):
    """Reject symlinked ancestors before modifying anything underneath them."""
    path = base
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or '..' in parts:
        raise ValueError('unsafe staging path')
    for part in parts[:-1]:
        path = path / part
        if path.is_symlink():
            raise ValueError('symlinked ancestor in staging tree: ' + relative)
    return path / parts[-1]


def validate(root, data):
    if not root.is_dir() or not data.is_dir() or root.is_symlink() or data.is_symlink():
        raise ValueError('APP and UDA must be real directories')
    root, data = root.resolve(), data.resolve()
    if root == Path('/') or data == Path('/') or root == data or root in data.parents or data in root.parents:
        raise ValueError('APP and UDA must be separate non-root directories')
    marker = root / MARKER
    if marker.is_symlink() or not marker.is_file() or json.loads(marker.read_text()) != MARKER_CONTENT:
        raise ValueError('missing source image staging marker')
    if not (root / 'etc/mocha-internal-debian').is_file():
        raise ValueError('missing Mocha system marker')
    # This tool must never walk into mounts from either staging directory.
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        mount = Path(line.split()[4].replace('\\040', ' ').replace('\\011', '\t').replace('\\134', '\\'))
        if mount == root or root in mount.parents or mount == data or data in mount.parents:
            raise ValueError('staging trees must not contain mount points')
    for rel in (*PURGE, 'etc/passwd', 'etc/shadow', 'etc/machine-id', 'etc/ssh',
                'etc/mocha/default-login.json', 'etc/systemd/system',
                'usr/lib/firmware/brcm', 'home/mocha/.config'):
        safe_path(root, rel)
    for rel in ('etc/machine-id', 'etc/ssh', 'etc/mocha/default-login.json', 'etc/systemd/system'):
        if safe_path(root, rel).is_symlink():
            raise ValueError('refusing symlink at staging target: ' + rel)
    units = safe_path(root, 'etc/systemd/system')
    if units.is_dir() and any(p.is_symlink() for p in units.glob('*.wants')):
        raise ValueError('systemd wants directory cannot be a symlink')
    passwd = safe_path(root, 'etc/passwd')
    shadow = safe_path(root, 'etc/shadow')
    if passwd.is_symlink() or shadow.is_symlink():
        raise ValueError('account files cannot be symlinks')
    accounts = [line.split(':') for line in passwd.read_text().splitlines()]
    humans = [fields for fields in accounts if len(fields) >= 7 and fields[2].isdigit() and 1000 <= int(fields[2]) < 65534]
    if len(humans) != 1 or humans[0][0:4] != ['mocha', 'x', '1000', '1000'] or humans[0][5] != '/home/mocha':
        raise ValueError('unexpected user accounts or home directory')
    shadow_rows = [line.split(':') for line in shadow.read_text().splitlines()]
    if sum(row[0] == 'mocha' for row in shadow_rows) != 1 or sum(row[0] == 'root' for row in shadow_rows) != 1:
        raise ValueError('unexpected shadow accounts')
    if any(p.name != 'wallpapers' for p in data.iterdir()):
        raise ValueError('unexpected top-level UDA content; review before publishing')
    for base in (data, root / 'home/mocha'):
        if not base.is_dir() or base.is_symlink():
            raise ValueError('missing or symlinked content directory')
        for p in base.rglob('*'):
            if p.name.lower() in PRIVATE_NAMES or p.suffix.lower() in ('.gguf', '.safetensors'):
                raise ValueError('private data or model weights present: ' + str(p.relative_to(base)))
            if p.is_file() and p.name.lower().startswith('ymcymcymc') and p.suffix.lower() in ('.mp4','.mkv','.webm') and 'gop30' not in p.name.lower():
                raise ValueError('original high-cost video must not be included')
    brcm = safe_path(root, 'usr/lib/firmware/brcm')
    if brcm.is_symlink():
        raise ValueError('firmware directory cannot be a symlink')
    if brcm.exists() and any(brcm.glob('brcmfmac4354-sdio*.txt')):
        raise ValueError('target-specific Wi-Fi board data must not be bundled')
    if any(units.glob('mocha-oobe*')) or (root/'var/lib/mocha-oobe/pending').exists():
        raise ValueError('OOBE state must not be included')
    return root, data, shadow_rows


def prepare(root, data):
    root, data, rows = validate(Path(root), Path(data))
    # Perform all validation, including the password generator, before cleanup.
    password = subprocess.run(['openssl', 'passwd', '-6', '-stdin'], input='mocha\n',
                              text=True, capture_output=True, check=True).stdout.strip()
    if not password.startswith('$6$'):
        raise RuntimeError('could not generate default password hash')
    for rel in PURGE:
        p = safe_path(root, rel)
        if p.is_symlink() or p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)
    for rel in ('var/log', 'var/crash', 'var/backups', 'var/lib/NetworkManager',
                'var/lib/bluetooth', 'var/lib/upower', 'var/lib/dhcp',
                'etc/NetworkManager/system-connections', 'var/lib/systemd/coredump',
                'var/cache/apt/archives/partial'):
        safe_path(root, rel).mkdir(parents=True, exist_ok=True)
    ssh = safe_path(root, 'etc/ssh')
    if ssh.is_symlink(): raise ValueError('SSH directory cannot be a symlink')
    for p in ssh.glob('ssh_host_*'):
        if p.is_file() or p.is_symlink(): p.unlink()
    for p in (root/'etc/systemd/system').glob('*.wants'):
        if p.is_symlink(): raise ValueError('systemd wants directory cannot be a symlink')
        for name in ('ssh.service','sshd.service','ssh.socket','sshd.socket'):
            link = p/name
            if link.is_symlink() or link.is_file(): link.unlink()
    machine_id = safe_path(root, 'etc/machine-id')
    if machine_id.is_symlink(): raise ValueError('machine-id cannot be a symlink')
    machine_id.write_text('')
    dbus_id = safe_path(root, 'var/lib/dbus/machine-id')
    dbus_id.parent.mkdir(parents=True, exist_ok=True)
    dbus_id.symlink_to('/etc/machine-id')
    for row in rows:
        if row[0] == 'root': row[1] = '!'
        if row[0] == 'mocha': row[1] = password
    shadow = safe_path(root, 'etc/shadow')
    shadow.write_text('\n'.join(':'.join(row) for row in rows)+'\n')
    shadow.chmod(0o640)
    identity = safe_path(root, 'etc/mocha/default-login.json')
    if identity.is_symlink(): raise ValueError('login metadata cannot be a symlink')
    identity.parent.mkdir(parents=True, exist_ok=True)
    identity.write_text(json.dumps({'schema':1,'username':'mocha','password':'default-change-immediately'})+'\n')
    (root/MARKER).unlink()
    return {'schema':1, 'source_copy_prepared':True, 'ready_to_flash':False,
            'required': ['privacy review', 'image assembly', 'device acceptance']}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--data',type=Path,required=True)
    args=parser.parse_args(argv)
    if os.geteuid()!=0: parser.error('Linux root is required to preserve ownership')
    try:
        print(json.dumps(prepare(args.root,args.data),indent=2))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    return 0


if __name__=='__main__': raise SystemExit(main())
