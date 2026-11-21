#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Move the packaged home tree to the data filesystem before creating archives."""
from pathlib import Path
import shutil
import subprocess

HOME_SOURCE = '/srv/mocha-data/home'
HOME_MOUNT = HOME_SOURCE + ' /home none bind,x-systemd.requires-mounts-for=/srv/mocha-data 0 0'


def stage_home(root, data):
    root, data = Path(root), Path(data)
    origin, target = root / 'home', data / 'home'
    fstab = root / 'etc/fstab'
    config = fstab.read_text()
    rows = [line.split() for line in config.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if not any(row[:2] == ['LABEL=mocha-data', '/srv/mocha-data'] for row in rows):
        raise ValueError('missing Mocha data partition in fstab')
    if any(row[1:2] == ['/home'] for row in rows) or target.exists() or target.is_symlink():
        raise ValueError('home has already been staged or a home mount exists')
    if not (origin / 'mocha').is_dir() or origin.is_symlink():
        raise ValueError('missing packaged mocha home directory')
    subprocess.run(['rsync', '-aHAX', '--numeric-ids', str(origin), str(data) + '/'], check=True)
    # These are disposable packaging trees, never the original build or a live root.
    shutil.rmtree(origin)
    origin.mkdir(mode=0o755)
    fstab.write_text(config.rstrip('\n') + '\n' + HOME_MOUNT + '\n')
