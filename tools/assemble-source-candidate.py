#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Stage a preassembled source desktop, match drivers and package a candidate.

This does not compile the desktop, connect to a device, or mark a release as
verified. Inputs are explicit until the source desktop assembler is complete.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def assemble(args):
    output=args.output.resolve()
    if output.exists() or not output.parent.is_dir():raise ValueError('output must be new with an existing parent')
    for name in ('root','data','kernel','drivers'):
        value=getattr(args,name)
        if value.is_symlink() or not value.is_dir():raise ValueError(name+' must be a real directory')
        src=value.resolve()
        if src==Path('/') or output in src.parents or src in output.parents or src==output:
            raise ValueError('output must be disjoint from '+name)
    for name in ('loader','ram_kernel','ram_dtb','installer','lnx'):
        value=getattr(args,name)
        if value.is_symlink() or not value.is_file() or value.stat().st_size==0:
            raise ValueError('missing boot input: '+name)
    here=Path(__file__).resolve().parent
    output.mkdir(mode=0o700)
    staged=output/'stage';bundle=output/'bundle'
    subprocess.run([sys.executable,str(here/'stage-source-distribution.py'),
                    '--root',str(args.root.resolve()),'--data',str(args.data.resolve()),
                    '--kernel',str(args.kernel.resolve()),'--drivers',str(args.drivers.resolve()),
                    '--output',str(staged)],check=True)
    cmd=[sys.executable,str(here/'build-source-distribution.py'),
         '--stage',str(staged),'--output',str(bundle),'--require-component-match',
         '--version',args.version]
    for name in ('loader','ram_kernel','ram_dtb','installer','lnx'):
        cmd.extend(['--'+name.replace('_','-'),str(getattr(args,name).resolve())])
    subprocess.run(cmd,check=True)
    result={'schema':1,'bundle':str(bundle),'ready_to_flash':False,
            'remaining':['desktop build automation','privacy review','device acceptance']}
    (output/'assembly-status.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','data','kernel','drivers','loader','ram-kernel','ram-dtb','installer','lnx','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--version',default='source-candidate')
    a=p.parse_args(argv)
    if not hasattr(os,'geteuid') or os.geteuid()!=0:p.error('Linux root required')
    try:print(json.dumps(assemble(a),indent=2))
    except (OSError,ValueError,subprocess.SubprocessError) as exc:p.error(str(exc))
    return 0


if __name__=='__main__':raise SystemExit(main())
