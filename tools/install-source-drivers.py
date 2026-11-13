#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Install built external modules into a source rootfs and run depmod."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def install(root,drivers,kernel):
    root,drivers,kernel=map(Path,(root,drivers,kernel))
    if root.resolve()==Path('/') or not (root/'.mocha-source-rootfs-build').is_file():
        raise ValueError('marked offline source rootfs required')
    release=(kernel/'include/config/kernel.release').read_text().strip()
    report=json.loads((drivers/'modules.json').read_text())
    if report.get('kernelrelease')!=release:raise ValueError('driver and kernel release mismatch')
    dest=root/'usr/lib/modules'/release/'extra';dest.mkdir(parents=True,exist_ok=True)
    for name,expected in report['files'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('invalid module path')
        source=drivers/relative
        if hashlib.sha256(source.read_bytes()).hexdigest()!=expected:raise ValueError('module hash mismatch: '+name)
        shutil.copy2(source,dest/relative.name)
    subprocess.run(['depmod','-b',str(root),release],check=True)
    print('SOURCE_DRIVERS_INSTALLED; physical device validation remains')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','drivers','kernel'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if not hasattr(os,'geteuid') or os.geteuid()!=0:p.error('Linux root required')
    try:install(a.root,a.drivers,a.kernel)
    except (OSError,ValueError,KeyError,json.JSONDecodeError,subprocess.SubprocessError) as exc:p.error(str(exc))


if __name__=='__main__':main()
