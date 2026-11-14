#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build FFmpeg Request, MPV and mpvpaper with explicit source archives."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request


def build(adapter,out,ffmpeg,mpv,mpvpaper,sysroot,pkgconfig,cross,jobs,debian_mirror,github_mirror,github_mirror_fallback=None):
    adapter,out=(Path(adapter).resolve(),Path(out).resolve())
    if not 1<=jobs<=4:raise ValueError('jobs must be between 1 and 4')
    if out.exists():raise ValueError('output must be new')
    out.mkdir(mode=0o700)
    archives=out/'archives';archives.mkdir()
    sources=[('ffmpeg-7.1.5.tar.xz',ffmpeg,'https://ffmpeg.org/releases/ffmpeg-7.1.5.tar.xz'),
             ('mpv-0.40.0.tar.gz',mpv,'https://github.com/mpv-player/mpv/archive/refs/tags/v0.40.0.tar.gz'),
             ('mpvpaper-1.9.tar.gz',mpvpaper,'https://github.com/GhostNaN/mpvpaper/archive/refs/tags/1.9.tar.gz')]
    fetched=[]
    for name,provided,url in sources:
        path=archives/name
        if provided is not None:shutil.copyfile(provided,path)
        else:
            urls=[url]
            if url.startswith('https://github.com/'):
                mirrors=[v for v in (github_mirror,github_mirror_fallback) if v]
                if mirrors:urls=[v.rstrip('/')+'/'+url.removeprefix('https://github.com/') for v in mirrors]
            for index,source in enumerate(urls):
                try:
                    with urllib.request.urlopen(source,timeout=120) as src,path.open('wb') as dst:shutil.copyfileobj(src,dst)
                    break
                except (OSError,TimeoutError):
                    path.unlink(missing_ok=True)
                    if index==len(urls)-1:raise
                    print('Video source download failed; trying the next mirror',flush=True)
        fetched.append(path)
    ffmpeg,mpv,mpvpaper=fetched
    if sysroot is None:
        deps=out/'deps';deps.mkdir();sysroot=deps/'sysroot'
        packages=['libplacebo-dev:armhf','libplacebo349:armhf','libass-dev:armhf','libass9:armhf',
                  'libvulkan-dev:armhf','libvulkan1:armhf','libunibreak-dev:armhf','libunibreak6:armhf',
                  'libxxhash-dev:armhf','libxxhash0:armhf']
        (deps/'lists/partial').mkdir(parents=True);(deps/'archives/partial').mkdir(parents=True)
        source=deps/'sources.list';source.write_text('deb [arch=armhf signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] '+debian_mirror+' trixie main\n')
        options=['-o','Dir::Etc::sourcelist='+str(source),'-o','Dir::Etc::sourceparts=-',
                 '-o','Dir::State::lists='+str(deps/'lists'),'-o','APT::Architecture=armhf',
                 '-o','APT::Architectures=armhf','-o','Dir::State::status=/dev/null',
                 '-o','Dir::Cache::archives='+str(deps/'archives')]
        subprocess.run(['apt-get',*options,'update'],check=True)
        subprocess.run(['apt-get',*options,'download',*packages],cwd=deps,check=True)
        for package in deps.glob('*.deb'):subprocess.run(['dpkg-deb','-x',str(package),str(sysroot)],check=True)
        for pc in sysroot.rglob('*.pc'):
            pc.write_text(pc.read_text().replace('prefix=/usr','prefix='+str(sysroot/'usr')))
    else:sysroot=Path(sysroot)
    cross=Path(cross) if cross else adapter/'noctalia-armhf-cross.ini'
    patches=adapter/'patches/vde';ff=out/'ffmpeg';player=out/'mpv';wall=out/'mpvpaper'
    commands=[
        [sys.executable,str(adapter/'tools/build-vde-ffmpeg.py'),'--archive',str(ffmpeg),'--patches',str(patches),'--destination',str(ff),'--jobs',str(min(jobs,4))],
        [sys.executable,str(adapter/'tools/build-vde-mpv.py'),'--archive',str(mpv),'--patches',str(patches),'--destination',str(player),'--ffmpeg-prefix',str(ff/'runtime'),'--deps-sysroot',str(sysroot),'--cross-file',str(cross)],
    ]
    for cmd in commands:subprocess.run(cmd,check=True)
    if pkgconfig is None:
        pkgconfig=out/'pkgconfig';pkgconfig.mkdir()
        (pkgconfig/'mpv.pc').write_text('prefix='+str(ff/'runtime')+'\nlibdir=${prefix}/lib\nincludedir=${prefix}/include\n'
                                       'Name: mpv\nDescription: Mocha MPV\nVersion: 0.40.0\nLibs: -L${libdir} -lmpv\nCflags: -I${includedir}\n')
    subprocess.run([sys.executable,str(adapter/'tools/build-mpvpaper-fullscreen.py'),'--archive',str(mpvpaper),
                    '--patch',str(patches/'0004-mpvpaper-focused-fullscreen-release.patch'),
                    '--destination',str(wall),'--mpv-pkgconfig',str(pkgconfig),'--cross-file',str(cross)],check=True)
    ff_info=json.loads((ff/'build.json').read_text());mpv_info=json.loads((player/'build.json').read_text())
    prefix=ff/'runtime';runtime=out/'runtime';runtime.mkdir();records=[]
    for folder in ('bin','lib'):
        (runtime/folder).mkdir()
        for src in sorted((prefix/folder).iterdir()):
            if not (src.is_file() or src.is_symlink()) or (folder=='lib' and '.so' not in src.name):continue
            rel=str(src.relative_to(prefix));dst=runtime/rel
            if src.is_symlink():
                dst.symlink_to(src.readlink());records.append({'path':rel,'symlink':str(src.readlink())})
            else:
                with src.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
                if sha!=mpv_info['files'][rel]:raise ValueError('runtime hash mismatch: '+rel)
                if rel.startswith(('lib/libav','lib/libsw')) and sha!=ff_info['files'][rel]:raise ValueError('FFmpeg hash mismatch: '+rel)
                shutil.copy2(src,dst);records.append({'path':rel,'sha256':sha,'size':src.stat().st_size})
    manifest={'ffmpeg':ff_info,'mpv':mpv_info,'runtime_files':records,'installed_globally':False}
    (runtime/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('SOURCE_VIDEO_BUILT; device hardware decoding is not yet validated')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('adapter','out'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('ffmpeg','mpv','mpvpaper','sysroot','pkgconfig','cross'):p.add_argument('--'+name,type=Path)
    p.add_argument('--debian-mirror',default='https://mirrors.tuna.tsinghua.edu.cn/debian')
    p.add_argument('--github-mirror')
    p.add_argument('--github-mirror-fallback')
    p.add_argument('--jobs',type=int,default=2);a=p.parse_args()
    try:build(a.adapter,a.out,a.ffmpeg,a.mpv,a.mpvpaper,a.sysroot,a.pkgconfig,a.cross,a.jobs,a.debian_mirror,a.github_mirror,a.github_mirror_fallback)
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:p.error(str(exc))


if __name__=='__main__':main()
