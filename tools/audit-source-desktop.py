#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only completeness checks for a *staged* source-built Mocha desktop.

This does not certify that an image is safe to distribute or works on-device.
It deliberately does not mount, format, flash, or modify either input tree.
"""
import argparse
import hashlib
import json
from pathlib import Path

REQUIRED_ROOT = {
    'kernel': 'boot/uImage-desktop',
    'device tree': 'boot/mocha-desktop.dtb',
    'initramfs': 'boot/initramfs.cpio.gz',
    'default login metadata': 'etc/mocha/default-login.json',
    'Niri': 'usr/local/bin/niri',
    'Noctalia': 'usr/local/bin/noctalia',
    'native graphics launcher': 'usr/local/libexec/mocha-native-app',
    'wallpaper launcher': 'usr/local/bin/mpvpaper',
    'wallpaper player': 'usr/local/libexec/mocha-mpvpaper-runtime/mpvpaper',
    'wallpaper player selector': 'usr/local/libexec/mocha-mpvpaper-runtime/select-player-runtime.py',
    'GPU session environment': 'home/mocha/.config/environment.d/70-mocha-gpu.conf',
    'Niri configuration': 'home/mocha/.config/niri/config.kdl',
    'Nyxuri source': 'usr/local/share/mocha/nyxuri/MOCHA-UPSTREAM-COMMIT',
}
WALLPAPER = 'ymcymcymc-vde-cavlc-gop30-1536w-30fps.mp4'
WALLPAPER_SHA256 = '0e6065b0288f9ce6f13028cba16b0da0c09770972dd11855a2423cb900300c71'


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inspect(root, data):
    root, data = Path(root), Path(data)
    if not root.is_dir() or not data.is_dir():
        raise ValueError('APP and UDA staging directories must exist')
    if root.resolve() == data.resolve() or root.resolve() in data.resolve().parents or data.resolve() in root.resolve().parents:
        raise ValueError('APP and UDA staging directories must be separate')
    issues = []
    for label, relative in REQUIRED_ROOT.items():
        path = root / relative
        if not path.is_file() or path.stat().st_size == 0:
            issues.append('missing or empty ' + label + ': ' + relative)
    passwd = root / 'etc/passwd'
    if not passwd.is_file() or not any(line.split(':')[0:3] == ['mocha', 'x', '1000']
                                       for line in passwd.read_text().splitlines()):
        issues.append('missing expected mocha account')
    getty = root / 'etc/systemd/system/getty@tty1.service.d'
    if not getty.is_dir() or not any('--autologin mocha' in p.read_text()
                                     for p in getty.glob('*.conf') if p.is_file()):
        issues.append('missing tty1 desktop autologin')
    enabled = root / 'etc/systemd/system/getty.target.wants/getty@tty1.service'
    if not enabled.is_symlink():
        issues.append('tty1 getty is not enabled')
    wallpapers = [p for p in data.rglob(WALLPAPER) if p.is_file() and not p.is_symlink()]
    if not wallpapers:
        issues.append('missing GOP30 wallpaper')
    elif len(wallpapers) != 1 or sha256(wallpapers[0]) != WALLPAPER_SHA256:
        issues.append('GOP30 wallpaper duplicate or hash mismatch')
    runtime_dir = root / 'usr/local/libexec/mocha-vde-player'
    manifests = list(runtime_dir.glob('*/build-manifest.json')) if runtime_dir.is_dir() else []
    if not manifests:
        issues.append('missing isolated VDE runtime manifest')
    elif len(manifests) != 1:
        issues.append('ambiguous isolated VDE runtime manifests')
    else:
        try:
            directory = manifests[0].parent.resolve()
            manifest = json.loads(manifests[0].read_text())
            records = manifest['runtime_files']
            if not isinstance(records, list) or not records:
                raise ValueError('empty runtime file list')
            expected = {'build-manifest.json'}
            for record in records:
                name = record['path']
                relative = Path(name)
                if relative.is_absolute() or '..' in relative.parts or name in expected:
                    raise ValueError('invalid runtime path')
                expected.add(name)
                path = directory / relative
                if not path.resolve(strict=True).is_relative_to(directory):
                    raise ValueError('runtime path escapes runtime directory')
                if 'symlink' in record:
                    if not path.is_symlink() or path.readlink().as_posix() != record['symlink']:
                        raise ValueError('runtime symlink mismatch')
                elif path.is_symlink() or sha256(path) != record['sha256']:
                    raise ValueError('runtime hash mismatch')
            actual = {str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file() or p.is_symlink()}
            if actual != expected:
                raise ValueError('unmanifested or missing runtime files')
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            issues.append('invalid isolated VDE runtime: ' + str(exc))
    metadata = root / REQUIRED_ROOT['default login metadata']
    if metadata.is_file():
        try:
            login = json.loads(metadata.read_text())
            if login.get('schema') != 1 or login.get('username') != 'mocha':
                raise ValueError('unexpected account')
        except (OSError, ValueError, AttributeError, json.JSONDecodeError):
            issues.append('invalid default login metadata')
    for tree in (root, data):
        for suffix in ('*.gguf', '*.safetensors'):
            if next(tree.rglob(suffix), None) is not None:
                issues.append('model weights present in ' + ('APP' if tree == root else 'UDA'))
    return {'schema': 1, 'checks_passed': not issues, 'ready_to_flash': False,
            'limitations': ['Device boot, graphics, decoding and installer acceptance are not checked',
                            'Privacy and source provenance require independent review'],
            'issues': issues}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = inspect(args.root, args.data)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['checks_passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
