#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build the source-pinned Niri, Noctalia and Mesa desktop components.

This builds ARM binaries but does not install them into a rootfs or flash a
device. Run fetch-desktop-upstream.py first and use a Linux cross-build host.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

MESA_URL='https://archive.mesa3d.org/mesa-25.0.7.tar.xz'
MESA_SHA256='592272df3cf01e85e7db300c449df5061092574d099da275d19e97ef0510f8a6'


def ignored_source_entries(source,directory,entries):
    excluded={'.git'}
    if Path(directory)==source:excluded.update(('target','build-moze-armhf'))
    return excluded.intersection(entries)


def build(workspace,upstream,output,jobs=4,mesa_archive=None,mesa_url=MESA_URL):
    workspace,upstream,output=map(lambda p:Path(p).resolve(),(workspace,upstream,output))
    if output.exists() or not output.parent.is_dir():raise ValueError('output must be a new directory')
    desktop=workspace/'mocha-moze-desktop'
    for name in ('niri','noctalia'):
        if not (upstream/name).is_dir():raise ValueError('missing upstream '+name)
    for name in ('build-niri.sh','build-noctalia.sh','build-mesa.sh'):
        if not (desktop/'tools'/name).is_file():raise ValueError('missing desktop build script '+name)
    if not 1<=jobs<=32:raise ValueError('jobs must be between 1 and 32')
    output.mkdir(mode=0o700)
    archive=output/'mesa.tar.xz'
    if mesa_archive is None:
        if not mesa_url.startswith('https://'):raise ValueError('Mesa URL must use HTTPS')
        with urllib.request.urlopen(mesa_url,timeout=120) as src,archive.open('xb') as dst:shutil.copyfileobj(src,dst)
    else:shutil.copyfile(mesa_archive,archive)
    with archive.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    if sha!=MESA_SHA256:raise ValueError('Mesa source archive hash mismatch')
    sources=output/'sources';sources.mkdir()
    for name in ('niri','noctalia'):
        source=upstream/name
        def ignore(directory, entries):
            return ignored_source_entries(source,directory,entries)
        shutil.copytree(source,sources/name,symlinks=True,ignore=ignore)
    mesa=sources/'mesa';mesa.mkdir()
    with tarfile.open(archive,'r:xz') as t:
        t.extractall(mesa,filter='data')
    dirs=list(mesa.iterdir())
    if len(dirs)!=1 or not (dirs[0]/'VERSION').is_file():raise ValueError('unexpected Mesa archive layout')
    env=dict(os.environ,JOBS=str(jobs),MOCHA_TEGRA_EXPLICIT_FENCE='1',
             MOCHA_WALLPAPER_VISIBILITY='1',MOCHA_TABLET_GESTURES='1')
    subprocess.run(['bash',str(desktop/'tools/build-niri.sh'),str(sources/'niri')],env=env,check=True)
    subprocess.run(['bash',str(desktop/'tools/build-noctalia.sh'),str(sources/'noctalia'),str(output/'noctalia')],env=env,check=True)
    subprocess.run(['bash',str(desktop/'tools/build-mesa.sh'),str(dirs[0]),str(output/'mesa')],env=env,check=True)
    niri=sources/'niri/target/armv7-unknown-linux-gnueabihf/release/niri'
    bin_dir=output/'niri/usr/local/bin';bin_dir.mkdir(parents=True)
    shutil.copy2(niri,bin_dir/'niri')
    subprocess.run(['arm-linux-gnueabihf-strip','--strip-unneeded',str(bin_dir/'niri')],check=True)
    units=output/'niri/usr/local/lib/systemd/user';units.mkdir(parents=True)
    resources=sources/'niri/resources'
    service=(resources/'niri.service').read_text().replace('ExecStart=niri ','ExecStart=/usr/local/bin/niri ')
    (units/'niri.service').write_text(service)
    shutil.copy2(resources/'niri-shutdown.target',units/'niri-shutdown.target')
    result={'schema':1,'niri':str(bin_dir/'niri'),'noctalia':str(output/'noctalia'),
            'mesa':str(output/'mesa/stage'),'ready_to_flash':False}
    (output/'desktop-build.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2));return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path,required=True);p.add_argument('--upstream',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--jobs',type=int,default=4)
    p.add_argument('--mesa-archive',type=Path);p.add_argument('--mesa-url',default=MESA_URL)
    a=p.parse_args(argv)
    try:build(a.workspace,a.upstream,a.output,a.jobs,a.mesa_archive,a.mesa_url)
    except (OSError,ValueError,subprocess.SubprocessError) as exc:p.error(str(exc))
    return 0


if __name__=='__main__':raise SystemExit(main())
