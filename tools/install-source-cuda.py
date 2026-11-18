#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Install the previously device-tested open CUDA runtime into an offline image."""
import argparse
import hashlib
from pathlib import Path
import shutil
import tarfile

ARCHIVE_SHA256 = 'd03de8fe6562eee6b41c603a786d21db995d86a008e682a8d0ca7bdf7d8375c8'
RUNTIME = '/opt/mocha-cuda-runtime'
RUNNERS = ('mocha-cuda-runtime-run', 'mocha-cuda-runtime-selftest')


def install(root, archive, sources):
    root = root.resolve()
    if root == Path('/') or not (root/'.mocha-source-rootfs-build').is_file():
        raise ValueError('marked offline source rootfs required')
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != ARCHIVE_SHA256:
            raise ValueError('unexpected CUDA runtime archive hash')
    target = root / RUNTIME.lstrip('/')
    target.mkdir(parents=True)
    with tarfile.open(archive, 'r:gz') as bundle:
        bundle.extractall(target, filter='data')
    # The pinned archive stores runtime-smoke with mode 0644.
    for executable in ('probe-runtime-api', 'runtime-smoke'):
        (target/'bin'/executable).chmod(0o755)
    commands = root/'usr/local/bin'
    commands.mkdir(parents=True, exist_ok=True)
    for name in RUNNERS:
        launcher = (sources/name).read_text()
        launcher = launcher.replace('/srv/mocha-data/codex-debian-desktop/cuda-runtime-current', RUNTIME)
        path = commands/name
        path.write_text(launcher)
        path.chmod(0o755)
    for name, target_name in zip(('mocha-cuda-run', 'mocha-cuda-selftest'), RUNNERS):
        (commands/name).symlink_to(target_name)
    docs = root/'usr/share/doc/mocha-cuda-runtime'
    docs.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sources/'GDEV-LICENSE.txt', docs)
    shutil.copy2(sources/'README.md', docs/'README.md')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'archive', 'sources'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    install(args.root, args.archive, args.sources)


if __name__ == '__main__':
    main()
