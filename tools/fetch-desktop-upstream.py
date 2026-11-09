#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Fetch pinned Niri and Noctalia sources and Niri's verified vendor archive."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import urllib.request


def extract_vendor(archive, destination):
    with tarfile.open(archive,'r:xz') as tar:
        for item in tar:
            path=PurePosixPath(item.name)
            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0]!='vendor' or not (item.isfile() or item.isdir()):
                raise ValueError('unsafe vendor archive entry')
        tar.extractall(destination,filter='data')


def fetch(workspace, output, lock, vendor_file=None, git_mirror=None):
    workspace, output = Path(workspace).resolve(), Path(output).resolve()
    if output.exists() or output.is_relative_to(workspace) or workspace.is_relative_to(output):
        raise ValueError('output must be new and separate from the source workspace')
    desktop = workspace/'mocha-moze-desktop'
    if not (desktop/'Cargo.lock').is_file() or not (desktop/'config/cargo-armhf.toml').is_file():
        raise ValueError('pinned Mocha desktop checkout is missing')
    data=json.loads(Path(lock).read_text(encoding='utf-8-sig'))
    expected={'niri':('https://github.com/niri-wm/niri.git','8ed0da44d974c32c6877d2f4630c314da0717ecb'),
              'noctalia':('https://github.com/noctalia-dev/noctalia.git','6ef43e2bf2f3d5b4205ec72a72e34a2ab76ce3b4')}
    if data.get('schema')!=1:raise ValueError('invalid desktop source lock')
    for name,(url,commit) in expected.items():
        row=data.get(name,{})
        if row.get('repository')!=url or row.get('commit')!=commit:raise ValueError('unexpected upstream source lock')
    vendor=data.get('niri_vendor',{})
    if vendor.get('url')!='https://github.com/niri-wm/niri/releases/download/v26.04/niri-26.04-vendored-dependencies.tar.xz' or vendor.get('bytes')!=40263284 or vendor.get('sha256')!='407c525cd78710e72455c48741756857ca47dc32910a42f82cd40992a34beed6':
        raise ValueError('unexpected Niri vendor lock')
    env=os.environ.copy();env['GIT_TERMINAL_PROMPT']='0'
    if git_mirror is not None:
        prefix=git_mirror.rstrip('/')+'/'
        if not prefix.startswith('https://'):
            raise ValueError('Git mirror must use HTTPS')
        fetch_urls={name:prefix+url.removeprefix('https://github.com/') for name,(url,_) in expected.items()}
    else:
        fetch_urls={name:url for name,(url,_) in expected.items()}
    output.mkdir(mode=0o700)
    for name,(url,commit) in expected.items():
        dest=output/name
        subprocess.run(['git','init',str(dest)],check=True,env=env)
        subprocess.run(['git','-C',str(dest),'remote','add','origin',fetch_urls[name]],check=True,env=env)
        subprocess.run(['git','-C',str(dest),'fetch','--depth=1','origin',commit],check=True,env=env,timeout=1800)
        subprocess.run(['git','-C',str(dest),'checkout','--detach','FETCH_HEAD'],check=True,env=env)
        actual=subprocess.check_output(['git','-C',str(dest),'rev-parse','HEAD'],text=True,env=env).strip()
        if actual!=commit:raise ValueError('upstream commit mismatch: '+name)
    if (output/'niri/Cargo.lock').read_bytes()!=(desktop/'Cargo.lock').read_bytes():
        raise ValueError('Niri Cargo.lock does not match Mocha desktop')
    if (output/'noctalia/VERSION').read_text().strip()!='5.2.1':raise ValueError('unexpected Noctalia version')
    archive=output/'niri-vendor.tar.xz'
    if vendor_file is not None:shutil.copyfile(vendor_file,archive)
    else:
        with urllib.request.urlopen(vendor['url'],timeout=90) as response, archive.open('xb') as target:
            shutil.copyfileobj(response,target,length=1024*1024)
    with archive.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    if archive.stat().st_size!=vendor['bytes'] or digest!=vendor['sha256']:raise ValueError('Niri vendor archive hash mismatch')
    extract_vendor(archive,output/'niri')
    config=output/'niri/.cargo/config.toml';config.parent.mkdir(exist_ok=True)
    shutil.copy2(desktop/'config/cargo-armhf.toml',config)
    if not (output/'niri/vendor/smithay/.cargo-checksum.json').is_file():raise ValueError('Smithay vendor metadata missing')
    print('DESKTOP_UPSTREAM_FETCHED; source build and device validation remain required')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--lock',type=Path,default=Path(__file__).resolve().parents[1]/'desktop-upstream.lock.json')
    p.add_argument('--vendor-file',type=Path,help='optional previously downloaded vendor archive')
    p.add_argument('--git-mirror',help='HTTPS prefix for GitHub Git smart HTTP, e.g. https://ghproxy.net/https://github.com')
    a=p.parse_args();fetch(a.workspace,a.output,a.lock,a.vendor_file,a.git_mirror)

if __name__=='__main__':main()
