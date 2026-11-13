#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Package an already staged source desktop as an unverified candidate.

No tablet is accessed. The stage and every boot component must be supplied
explicitly; source compilation and physical acceptance are separate steps.
"""
import argparse
import importlib.util
import json
import lzma
import os
from pathlib import Path
import shutil
import subprocess


def load(name, filename):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(filename))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def validate(stage, output, inputs, require_components=False, require_speaker=False):
    stage,output=Path(stage),Path(output)
    if stage.is_symlink() or not stage.is_dir(): raise ValueError('stage must be a real directory')
    stage,output=stage.resolve(),output.resolve()
    if output.exists() or not output.parent.is_dir() or output in stage.parents or stage in output.parents:
        raise ValueError('output must be new and separate from the staged tree')
    marker=stage/'source-stage.json'
    if marker.is_symlink() or not marker.is_file(): raise ValueError('source stage report missing')
    report=json.loads(marker.read_text())
    if report.get('schema')!=1 or report.get('stage')!='source-desktop-copy' or report.get('ready_to_flash') is not False:
        raise ValueError('unexpected source stage report')
    if require_components and report.get('kernel_driver_match') is not True:
        raise ValueError('kernel and external driver matching was not checked')
    if require_speaker and report.get('speaker_staged') is not True:
        raise ValueError('speaker initialization was not staged')
    for name,path in inputs.items():
        if path.is_symlink() or not path.is_file() or not path.stat().st_size:
            raise ValueError('missing or symlinked boot input: '+name)
        if path.resolve().is_relative_to(output): raise ValueError('boot input is inside output')
    for name in ('loader','lnx'):
        p=inputs[name]
        with p.open('rb') as f: magic=f.read(8)
        if magic!=b'ANDROID!' or p.stat().st_size>8*1024**2:
            raise ValueError(name+' must be an Android boot image under 8 MiB')
    for name,expected in [('ram_kernel',bytes.fromhex('27051956')),('ram_dtb',bytes.fromhex('d00dfeed'))]:
        with inputs[name].open('rb') as f: magic=f.read(4)
        if magic!=expected: raise ValueError('invalid '+name+' magic')
    builder=load('distribution_builder','build-distribution.py')
    builder.check_build_tools()
    builder.check_installer_wifi_capture(inputs['installer'])
    audit=load('source_desktop_audit','audit-source-desktop.py')
    result=audit.inspect(stage/'APP',stage/'DATA')
    if not result['checks_passed']: raise ValueError('desktop audit failed: '+'; '.join(result['issues']))
    if shutil.disk_usage(output.parent).free<10*1024**3: raise ValueError('at least 10 GiB free is required')
    return stage,output,builder


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    for name in ('loader','ram-kernel','ram-dtb','installer','lnx'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--version',default='source-candidate')
    p.add_argument('--require-component-match',action='store_true',
                   help='require staged kernel and driver build outputs to have been compared')
    p.add_argument('--require-speaker',action='store_true',help='require speaker service to be staged')
    a=p.parse_args(argv)
    if not hasattr(os,'geteuid') or os.geteuid()!=0:p.error('Linux root required')
    inputs={name:getattr(a,name) for name in ('loader','ram_kernel','ram_dtb','installer','lnx')}
    try: stage,output,builder=validate(a.stage,a.output,inputs,a.require_component_match,a.require_speaker)
    except (OSError,ValueError,RuntimeError,json.JSONDecodeError) as exc:p.error(str(exc))
    repo=Path(__file__).resolve().parents[1]
    output.mkdir(mode=0o700);work=output/'private-work';work.mkdir(mode=0o700)
    image=output/'image';image.mkdir();data=work/'DATA';data.mkdir()
    subprocess.run(['rsync','-aHAX','--numeric-ids','--one-file-system',str(stage/'DATA')+'/',str(data)+'/'],check=True)
    data_bytes=sum(p.stat().st_size for p in data.rglob('*') if p.is_file() and not p.is_symlink())
    raw=work/'APP.img'
    subprocess.run(['bash',str(repo/'tools/make-app-image.sh'),str(stage/'APP'),str(raw),str(3*1024**3)],check=True)
    raw_sha=builder.digest(raw)
    with raw.open('rb') as source,lzma.open(image/'APP.img.xz','wb',preset=3) as target:
        shutil.copyfileobj(source,target,length=1024*1024)
    builder.finish_candidate(a,repo,output,raw_sha,data_bytes)
    print('SOURCE_CANDIDATE_ONLY: privacy review and device acceptance remain mandatory')
    return 0


if __name__=='__main__': raise SystemExit(main())
