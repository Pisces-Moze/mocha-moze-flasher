#!/usr/bin/env python3
"""Build the experimental source candidate using Docker Desktop on Windows."""
import argparse
from datetime import datetime
from pathlib import Path
import subprocess
import sys


def run(command, **kwargs):
    print('+', subprocess.list2cmdline([str(x) for x in command]), flush=True)
    return subprocess.run([str(x) for x in command], **kwargs)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=Path.cwd() / 'source-candidates')
    p.add_argument('--jobs', type=int, default=4)
    p.add_argument('--git-mirror', default='https://ghproxy.net/https://github.com')
    p.add_argument('--git-mirror-fallback', default='https://ghproxy.vip/https://github.com')
    p.add_argument('--debian-image', default='debian:trixie')
    p.add_argument('--debian-mirror', default='https://mirrors.tuna.tsinghua.edu.cn/debian')
    args = p.parse_args()
    if not 1 <= args.jobs <= 32:
        p.error('jobs must be between 1 and 32')
    repo = Path(__file__).resolve().parent.parent
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    name = 'mocha-source-' + stamp
    volume = name + '-work'
    destination = args.output.resolve() / name
    try:
        run(['docker', 'version'], check=True)
        run(['docker', 'build', '-t', 'mocha-source-builder',
             '--build-arg', 'DEBIAN_IMAGE=' + args.debian_image,
             '--build-arg', 'DEBIAN_MIRROR=' + args.debian_mirror, str(repo)], check=True)
        run(['docker', 'volume', 'create', volume], check=True)
        result = run(['docker', 'run', '--name', name, '-v', volume + ':/build',
                      'mocha-source-builder', '--work', '/build/source',
                      '--jobs', str(args.jobs), '--git-mirror', args.git_mirror,
                      '--git-mirror-fallback', args.git_mirror_fallback,
                      '--debian-mirror', args.debian_mirror])
        # The bootstrap exits 2 when it has built a candidate which is not
        # yet approved by physical-device acceptance.
        if result.returncode not in (0, 2):
            print('Build failed. Docker container and volume are retained:', name, volume)
            return result.returncode
        destination.parent.mkdir(parents=True, exist_ok=True)
        run(['docker', 'cp', name + ':/build/source/candidate/bundle', destination], check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print('Build or candidate copy failed:', exc, file=sys.stderr)
        print('Docker container and volume, if created, are retained:', name, volume)
        return 1
    print('Candidate:', destination)
    print('This candidate has not passed device acceptance and will not be flashed automatically.')
    print('Docker container and volume retained:', name, volume)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
