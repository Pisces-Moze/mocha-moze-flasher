#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compare staged boot files and external modules with source build outputs.

This read-only check does not establish source provenance or device usability.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

EXPECTED = {'mocha_miui_backlight.ko', 'snd-soc-rt5670.ko', 'mocha_rt5671_board.ko',
            'mocha_audio_i2s_probe.ko', 'mocha_audio_runtime_card.ko',
            'mocha_audio_data_pin.ko', 'mocha_miui_tfa98xx.ko'}


def digest(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def regular(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('missing or symlinked file: '+str(path))
    return path


def inspect(root, kernel, drivers):
    root,kernel,drivers=map(Path,(root,kernel,drivers))
    if any(p.is_symlink() or not p.is_dir() for p in (root,kernel,drivers)):
        raise ValueError('root, kernel and drivers must be real directories')
    kernelrelease=regular(kernel/'include/config/kernel.release').read_text().strip()
    if not re.fullmatch(r'[A-Za-z0-9._+-]+',kernelrelease):
        raise ValueError('invalid kernel release')
    result={'schema':1,'kernelrelease':kernelrelease,'verified':[],'ready_to_flash':False}
    for source,target in [('uImage','boot/uImage-desktop'),('mocha.dtb','boot/mocha-desktop.dtb')]:
        src=regular(kernel/source);dst=regular(root/target)
        if digest(src)!=digest(dst): raise ValueError('kernel output mismatch: '+target)
        result['verified'].append(target)
    manifest=json.loads(regular(drivers/'modules.json').read_text())
    if manifest.get('schema')!=1 or manifest.get('kernelrelease')!=kernelrelease or manifest.get('flash_ready') is not False:
        raise ValueError('unexpected driver manifest')
    records=manifest.get('files')
    if not isinstance(records,dict) or len(records)!=len(EXPECTED):raise ValueError('unexpected driver module count')
    names=set()
    for name,expected in records.items():
        rel=Path(name)
        if rel.is_absolute() or '..' in rel.parts or rel.name not in EXPECTED or rel.name in names:
            raise ValueError('invalid or duplicate driver module path')
        if not isinstance(expected,str) or not re.fullmatch(r'[0-9a-f]{64}',expected):
            raise ValueError('invalid driver hash')
        src=regular(drivers/rel)
        if not src.resolve().is_relative_to(drivers.resolve()):raise ValueError('driver path escapes build tree')
        target=regular(root/'usr/lib/modules'/kernelrelease/'extra'/rel.name)
        if digest(src)!=expected or digest(target)!=expected:
            raise ValueError('driver output mismatch: '+rel.name)
        names.add(rel.name);result['verified'].append(str(target.relative_to(root)))
    if names!=EXPECTED:raise ValueError('missing driver modules')
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True,type=Path);p.add_argument('--kernel',required=True,type=Path)
    p.add_argument('--drivers',required=True,type=Path);a=p.parse_args(argv)
    try:result=inspect(a.root,a.kernel,a.drivers)
    except (OSError,ValueError,TypeError,json.JSONDecodeError) as exc:p.error(str(exc))
    print(json.dumps(result,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
