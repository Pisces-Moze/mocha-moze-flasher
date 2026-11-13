#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Install previously staged public firmware into a source-built rootfs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil


def install(root,firmware):
    root,firmware=Path(root),Path(firmware)
    if root.resolve()==Path('/') or not (root/'.mocha-source-rootfs-build').is_file():
        raise ValueError('marked offline source rootfs required')
    report=json.loads((firmware/'staged-firmware.json').read_text())
    if report.get('schema')!=1:raise ValueError('invalid staged firmware')
    for name,expected in report['files'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('invalid firmware path')
        if relative.name.startswith('brcmfmac4354-sdio') and relative.suffix=='.txt':
            raise ValueError('device-specific Wi-Fi board data must not be bundled')
        src=firmware/relative
        if hashlib.sha256(src.read_bytes()).hexdigest()!=expected:raise ValueError('firmware hash mismatch: '+name)
        dst=(root/'usr/share/doc/mocha-firmware' if relative.parts[0]=='licenses' else root/'usr/lib/firmware')/relative
        dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    print('SOURCE_FIRMWARE_INSTALLED; target Wi-Fi board data is captured during installation')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--firmware',type=Path,required=True)
    a=p.parse_args()
    if not hasattr(os,'geteuid') or os.geteuid()!=0:p.error('Linux root required')
    try:install(a.root,a.firmware)
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as exc:p.error(str(exc))


if __name__=='__main__':main()
