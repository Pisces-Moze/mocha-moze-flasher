#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build Mocha external audio/backlight modules against the pinned kernel."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

EXPECTED = {'mocha_miui_backlight.ko', 'snd-soc-rt5670.ko', 'mocha_rt5671_board.ko',
            'mocha_audio_i2s_probe.ko', 'mocha_audio_runtime_card.ko',
            'mocha_audio_data_pin.ko', 'mocha_miui_tfa98xx.ko'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--kernel',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--jobs',type=int,default=2)
    p.add_argument('--lock',type=Path,default=Path(__file__).resolve().parents[1]/'sources.lock.json')
    a=p.parse_args(argv)
    if sys.platform!='linux':p.error('Linux is required')
    if not 1<=a.jobs<=32:p.error('jobs must be between 1 and 32')
    source=a.workspace.resolve();kernel=a.kernel.resolve();out=a.output.resolve()
    if out.exists() or out.is_relative_to(source) or source.is_relative_to(out) or out.is_relative_to(kernel) or kernel.is_relative_to(out):
        p.error('output must be new and separate from source and kernel')
    if not out.parent.is_dir():p.error('output parent must exist')
    required=('git','bash','make','arm-linux-gnueabihf-gcc','patch','modinfo','sha256sum')
    missing=[x for x in required if shutil.which(x) is None]
    if missing:p.error('missing build tools: '+', '.join(missing))
    if not (kernel/'Module.symvers').is_file() or not (kernel/'SHA256SUMS').is_file():
        p.error('completed kernel output is required')
    spec=importlib.util.spec_from_file_location('source_preflight',Path(__file__).with_name('preflight-source-build.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    issues=module.source_checks(a.lock,source)
    if issues:p.error('; '.join(issues))
    subprocess.run(['sha256sum','-c','SHA256SUMS'],cwd=kernel,check=True)
    release=(kernel/'include/config/kernel.release').read_text().strip()
    if not release:p.error('kernel release is missing')
    repo=source/'mocha-moze-drivers';kernel_source=source/'mocha-moze-linux'
    if not (repo/'tools/build-backlight.sh').is_file() or not (repo/'audio/build-bringup.sh').is_file():
        p.error('pinned driver build scripts are missing')
    out.mkdir(mode=0o700);scratch=out/'backlight-src';(scratch/'tools').mkdir(parents=True)
    shutil.copytree(repo/'backlight',scratch/'backlight')
    shutil.copy2(repo/'tools/build-backlight.sh',scratch/'tools/build-backlight.sh')
    env=os.environ.copy();env['JOBS']=str(a.jobs)
    subprocess.run(['bash',str(scratch/'tools/build-backlight.sh'),str(kernel_source),str(kernel)],env=env,check=True)
    subprocess.run(['sh',str(repo/'audio/build-bringup.sh'),str(kernel_source),str(kernel),str(out/'audio')],env=env,check=True)
    modules=list(out.rglob('*.ko')); names={x.name for x in modules}
    if names!=EXPECTED or len(modules)!=len(EXPECTED):raise RuntimeError('unexpected external module set')
    records={}
    for path in modules:
        vermagic=subprocess.check_output(['modinfo','-F','vermagic',str(path)],text=True).strip()
        if not vermagic or vermagic.split()[0]!=release:raise RuntimeError('module release mismatch: '+path.name)
        records[str(path.relative_to(out))]=hashlib.sha256(path.read_bytes()).hexdigest()
    (out/'modules.json').write_text(json.dumps({'schema':1,'kernelrelease':release,'files':records,'flash_ready':False},indent=2)+'\n')
    print('DRIVER_MODULES_BUILT; complete system assembly and device testing remain required')
    return 0

if __name__=='__main__':sys.exit(main())
