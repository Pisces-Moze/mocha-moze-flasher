#!/usr/bin/env python3
"""Build a Mocha source candidate inside an ephemeral QEMU Debian guest."""
import argparse
from datetime import datetime
import functools
import http.server
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import threading
import time


def command(args, **kwargs):
    return subprocess.run([str(x) for x in args], **kwargs)


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, required=True, help='Debian 13 genericcloud amd64 qcow2 with cloud-init')
    p.add_argument('--work', type=Path, default=Path.home() / 'mocha-qemu-builds')
    p.add_argument('--memory', type=int, default=4096, help='guest memory in MiB')
    p.add_argument('--cpus', type=int, default=4)
    p.add_argument('--disk', default='64G', help='maximum size of the sparse guest disk')
    p.add_argument('--git-mirror', default='https://ghproxy.net/https://github.com')
    p.add_argument('--git-mirror-fallback', default='https://ghproxy.vip/https://github.com')
    p.add_argument('--debian-mirror', default='https://mirrors.tuna.tsinghua.edu.cn/debian')
    a = p.parse_args()
    repo = Path(__file__).resolve().parent.parent
    base = a.base.resolve()
    if not base.is_file(): p.error('base image does not exist')
    for executable in ('qemu-system-x86_64', 'qemu-img', 'ssh', 'ssh-keygen', 'scp'):
        if not shutil.which(executable): p.error('missing executable: ' + executable)
    a.work.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(a.work).free < 35 * 1024**3:
        p.error('at least 35 GiB of free host disk space is required')
    work = a.work.resolve() / datetime.now().strftime('build-%Y%m%d-%H%M%S-%f')
    work.mkdir()
    seed = work / 'seed'; seed.mkdir()
    key = work / 'builder-key'
    command(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', key], check=True)
    public_key = key.with_suffix('.pub').read_text().strip()
    (seed / 'meta-data').write_text('instance-id: mocha-build\nlocal-hostname: mocha-builder\n')
    (seed / 'user-data').write_text('#cloud-config\nusers:\n  - name: builder\n    sudo: ALL=(ALL) NOPASSWD:ALL\n'
                                  '    shell: /bin/bash\n    ssh_authorized_keys:\n      - ' + public_key + '\n')
    with tarfile.open(seed / 'flasher.tar.gz', 'w:gz') as archive:
        for item in repo.iterdir():
            if item.name not in ('.git', '__pycache__', 'source-candidates'):
                archive.add(item, arcname=item.name, filter=lambda info: None if '__pycache__' in info.name else info)
    disk = work / 'guest.qcow2'
    command(['qemu-img', 'create', '-f', 'qcow2', '-F', 'qcow2', '-b', base, disk, a.disk], check=True)
    http_port, ssh_port = port(), port()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(seed))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', http_port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    known = work / 'known_hosts'
    ssh_options = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', '-o', 'StrictHostKeyChecking=accept-new',
                   '-o', 'UserKnownHostsFile=' + str(known), '-i', str(key)]
    ssh = ['ssh', *ssh_options, '-p', str(ssh_port), 'builder@127.0.0.1']
    vm = None
    try:
        qemu = ['qemu-system-x86_64', '-accel', 'whpx', '-m', str(a.memory), '-smp', str(a.cpus),
                '-display', 'none', '-serial', 'file:' + str(work / 'serial.log'),
                '-drive', 'file=' + str(disk) + ',if=virtio,format=qcow2',
                '-netdev', 'user,id=net0,hostfwd=tcp:127.0.0.1:' + str(ssh_port) + '-:22',
                '-device', 'virtio-net-pci,netdev=net0',
                '-smbios', 'type=1,serial=ds=nocloud-net;s=http://10.0.2.2:' + str(http_port) + '/']
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        vm = subprocess.Popen(qemu, creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(120):
            if vm.poll() is not None: raise RuntimeError('QEMU exited; verify WHPX and inspect serial.log')
            if command(ssh + ['true'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0: break
            time.sleep(3)
        else: raise RuntimeError('guest SSH did not start; inspect serial.log')
        # Keep build dependencies aligned with the maintained Docker builder.
        dockerfile = (repo / 'Dockerfile').read_text()
        deps = dockerfile.split('apt-get -y --no-install-recommends install \\', 1)[1].split(' && \\', 1)[0]
        packages = ' '.join(deps.replace('\\', ' ').split())
        mirror = shlex.quote(a.debian_mirror)
        build = ('set -eu\n'
                 'sudo cloud-init status --wait\n'
                 'sudo rm -f /etc/apt/sources.list.d/debian.sources\n'
                 "printf 'deb %s trixie main\\ndeb %s trixie-backports main\\n' " + mirror + ' ' + mirror + ' | sudo tee /etc/apt/sources.list >/dev/null\n'
                 'sudo dpkg --add-architecture armhf\nsudo apt-get update\n'
                 'sudo env DEBIAN_FRONTEND=noninteractive apt-get -y --no-install-recommends install ' + packages + '\n'
                 'sudo env DEBIAN_FRONTEND=noninteractive apt-get -y --no-install-recommends -t trixie-backports install rustc cargo libstd-rust-dev:armhf\n'
                 'mkdir -p ~/flasher\ncurl -fsS http://10.0.2.2:' + str(http_port) + '/flasher.tar.gz | tar xz -C ~/flasher\n'
                 'cd ~/flasher\nset +e\nsudo python3 tools/bootstrap-source-build.py --work /home/builder/build --jobs ' + str(a.cpus) +
                 ' --git-mirror ' + shlex.quote(a.git_mirror) + ' --git-mirror-fallback ' + shlex.quote(a.git_mirror_fallback) +
                 ' --debian-mirror ' + mirror + '\nstatus=$?\nset -e\n'
                 '[ "$status" -eq 0 ] || [ "$status" -eq 2 ]\ntest -f /home/builder/build/candidate/bundle/image/bundle.json\n'
                 'sudo chown -R builder:builder /home/builder/build/candidate/bundle\n')
        command(ssh + ['bash', '-s'], input=build, text=True, check=True)
        destination = work / 'bundle'
        command(['scp', *ssh_options, '-P', str(ssh_port), '-r',
                 'builder@127.0.0.1:/home/builder/build/candidate/bundle', destination], check=True)
        print('Candidate saved to', destination)
        print('Device acceptance is still required; no flashing was performed.')
        return 0
    finally:
        if vm is not None and vm.poll() is None:
            command(ssh + ['sudo', 'poweroff'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try: vm.wait(timeout=30)
            except subprocess.TimeoutExpired: vm.terminate(); vm.wait()
        server.shutdown(); server.server_close()
        print('Build workspace retained at', work)


if __name__ == '__main__':
    sys.exit(main())
