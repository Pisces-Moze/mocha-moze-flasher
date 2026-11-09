#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build and package pinned RAM/eMMC U-Boot images without flashing."""
import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--jobs', type=int, default=2)
    p.add_argument('--lock', type=Path, default=Path(__file__).resolve().parents[1]/'sources.lock.json')
    a = p.parse_args(argv)
    if sys.platform != 'linux': p.error('Linux is required for the U-Boot build')
    if not 1 <= a.jobs <= 32: p.error('jobs must be between 1 and 32')
    source = a.workspace.resolve(); out = a.output.resolve()
    if out.exists() or out.is_relative_to(source) or source.is_relative_to(out):
        p.error('output must be new and separate from the source workspace')
    if not out.parent.is_dir() or shutil.disk_usage(out.parent).free < 5*1024**3:
        p.error('an existing output parent with 5 GiB free is required')
    required = ('git','bash','make','python3','arm-linux-gnueabihf-gcc','bc','bison','flex','sha256sum')
    missing = [x for x in required if shutil.which(x) is None]
    if missing: p.error('missing build tools: ' + ', '.join(missing))
    spec = importlib.util.spec_from_file_location('source_preflight', Path(__file__).with_name('preflight-source-build.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    issues = module.source_checks(a.lock, source)
    if issues: p.error('; '.join(issues))
    boot = source/'mocha-moze-boot'; script = boot/'tools/build.sh'; pack = boot/'tools/pack-android.py'
    if not script.is_file() or not pack.is_file(): p.error('pinned U-Boot scripts are missing')
    out.mkdir(mode=0o700)
    env=os.environ.copy();env['JOBS']=str(a.jobs);env['GIT_TERMINAL_PROMPT']='0'
    for mode in ('ram','emmc'):
        target=out/mode
        subprocess.run(['bash',str(script),str(target),mode],check=True,env=env)
        subprocess.run(['sha256sum','-c','SHA256SUMS'],cwd=target,check=True)
        subprocess.run([sys.executable,str(pack),str(target/'u-boot-dtb.bin'),
                        str(target/'u-boot'),str(target/'boot.img')],check=True)
    print('BOOT_IMAGES_BUILT; device validation and complete system assembly still required')
    return 0

if __name__ == '__main__': sys.exit(main())
