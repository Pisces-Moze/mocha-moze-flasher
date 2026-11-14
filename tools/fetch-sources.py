#!/usr/bin/env python3
"""Fetch pinned public source repositories without touching existing checkouts."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

EXPECTED = {'mocha-moze-boot', 'mocha-moze-linux', 'mocha-moze-drivers',
            'mocha-moze-desktop', 'mocha-moze-debian', 'mocha-moze-firmware-private'}


def check_environment(destination):
    if sys.platform != 'linux':
        raise RuntimeError('Fetch on Linux/WSL using a Linux filesystem; Windows cannot check out kernel paths such as aux.c')
    parent = Path(destination).resolve()
    while not parent.exists():
        parent = parent.parent
    filesystem = subprocess.check_output(['stat', '-f', '-c', '%T', str(parent)], text=True).strip()
    if filesystem in {'9p', 'drvfs', 'fuseblk', 'ntfs', 'ntfs3'}:
        raise RuntimeError('Use the WSL Linux filesystem (e.g. ~/mocha-sources), not a Windows-mounted drive')


def load_lock(path):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    rows = data.get('repositories')
    if data.get('schema') != 1 or not isinstance(rows, list) or len(rows) != len(EXPECTED):
        raise ValueError('Invalid source lock')
    if {x.get('name') for x in rows} != EXPECTED:
        raise ValueError('Source lock must contain exactly the six public repositories')
    for row in rows:
        if not re.fullmatch(r'[0-9a-f]{40}', row.get('commit', '')):
            raise ValueError('Invalid source commit')
    return rows


def fetch(lock, destination, git_mirror=None, git_mirror_fallback=None):
    rows = load_lock(lock)
    check_environment(destination)
    destination = Path(destination).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Source destination must be new or empty')
    destination.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env['GIT_TERMINAL_PROMPT'] = '0'
    for row in rows:
        name, commit = row['name'], row['commit']
        target = destination / name
        mirrors = [value for value in (git_mirror, git_mirror_fallback) if value] or ['https://github.com']
        if any(not value.startswith('https://') for value in mirrors):
            raise ValueError('Git mirror must use HTTPS')
        urls = [f'{value.rstrip("/")}/Pisces-Moze/{name}.git' for value in mirrors]
        print(f'Fetching {name} at {commit}', flush=True)
        subprocess.run(['git', 'init', str(target)], check=True, env=env)
        subprocess.run(['git', '-C', str(target), 'remote', 'add', 'origin', urls[0]], check=True, env=env)
        for index,url in enumerate(urls):
            try:
                subprocess.run(['git', '-C', str(target), 'fetch', '--depth=1', url, commit], check=True, env=env, timeout=1200)
                break
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                if index == len(urls)-1: raise
                print(f'Mirror failed for {name}; trying the next mirror', flush=True)
        subprocess.run(['git', '-C', str(target), 'checkout', '--detach', 'FETCH_HEAD'], check=True, env=env)
        actual = subprocess.check_output(['git', '-C', str(target), 'rev-parse', 'HEAD'], text=True, env=env).strip()
        if actual != commit:
            raise RuntimeError(f'Source commit mismatch for {name}')
    print('SOURCES_FETCHED: build and firmware prerequisites are still required', flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dest', required=True, type=Path)
    p.add_argument('--lock', type=Path, default=Path(__file__).resolve().parents[1] / 'sources.lock.json')
    p.add_argument('--git-mirror', help='HTTPS prefix for GitHub, e.g. https://ghproxy.net/https://github.com')
    p.add_argument('--git-mirror-fallback', help='Optional second HTTPS GitHub mirror prefix')
    a = p.parse_args()
    fetch(a.lock, a.dest, a.git_mirror, a.git_mirror_fallback)


if __name__ == '__main__':
    main()
