#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Copy, sanitize and audit a source-built desktop without creating an image.

No device is accessed. Output remains an unverified development stage; it is
not an installable image and must not be treated as permission to flash.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def stage(root, data, output, kernel=None, drivers=None):
    root, data, output = Path(root), Path(data), Path(output)
    if root.is_symlink() or data.is_symlink() or not root.is_dir() or not data.is_dir():
        raise ValueError('source APP and UDA must be real directories')
    root, data, output = root.resolve(), data.resolve(), output.resolve()
    if output.exists() or not output.parent.is_dir():
        raise ValueError('output must be new with an existing parent')
    for source in (root, data):
        if source == Path('/') or source == output or source in output.parents or output in source.parents:
            raise ValueError('output must be disjoint from both source trees')
    if root == data or root in data.parents or data in root.parents:
        raise ValueError('APP and UDA source trees must be separate')
    if not (root/'etc/mocha-internal-debian').is_file():
        raise ValueError('source is not a Mocha root filesystem')
    if (kernel is None) != (drivers is None):
        raise ValueError('kernel and drivers must be supplied together')
    if kernel is not None and any(Path(p).is_symlink() or not Path(p).is_dir() for p in (kernel,drivers)):
        raise ValueError('kernel and drivers must be real directories')
    if not shutil.which('rsync'):
        raise ValueError('rsync is required')
    if shutil.disk_usage(output.parent).free < 4*1024**3:
        raise ValueError('at least 4 GiB free is required for staging')
    here=Path(__file__).resolve().parent
    output.mkdir(mode=0o700)
    app, uda = output/'APP', output/'DATA'
    app.mkdir(); uda.mkdir()
    for source,dest in ((root,app),(data,uda)):
        subprocess.run(['rsync','-aHAX','--numeric-ids','--one-file-system',
                        str(source)+'/',str(dest)+'/'],check=True)
    (app/'.mocha-source-image-copy').write_text(json.dumps({'schema':1,'purpose':'source-image-staging'}))
    subprocess.run([sys.executable,str(here/'prepare-source-distribution.py'),
                    '--root',str(app),'--data',str(uda)],check=True)
    subprocess.run([sys.executable,str(here/'audit-source-desktop.py'),
                    '--root',str(app),'--data',str(uda)],check=True)
    if kernel is not None:
        subprocess.run([sys.executable,str(here/'audit-source-components.py'),
                        '--root',str(app),'--kernel',str(Path(kernel).resolve()),
                        '--drivers',str(Path(drivers).resolve())],check=True)
    report={'schema':1,'stage':'source-desktop-copy','ready_to_flash':False,
            'kernel_driver_match':kernel is not None,
            'remaining':['privacy review','image packaging','physical-device acceptance']}
    (output/'source-stage.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--kernel',type=Path,help='matching source kernel output')
    parser.add_argument('--drivers',type=Path,help='matching source external-driver output')
    args=parser.parse_args(argv)
    if not hasattr(os,'geteuid') or os.geteuid()!=0:
        parser.error('Linux root is required for ownership and xattrs')
    try:
        print(json.dumps(stage(args.root,args.data,args.output,args.kernel,args.drivers),indent=2))
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    return 0


if __name__=='__main__': raise SystemExit(main())
