#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Fetch sources, build a candidate system, and report readiness.

This builder never accesses or flashes a tablet. It returns nonzero while the
generated candidate still requires physical device acceptance.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True,
                        help='new Linux-filesystem directory for sources and build outputs')
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--git-mirror', help='HTTPS GitHub mirror prefix')
    parser.add_argument('--git-mirror-fallback', help='Optional second HTTPS GitHub mirror prefix')
    parser.add_argument('--mesa-archive',type=Path,help='optional previously downloaded Mesa source archive')
    parser.add_argument('--mesa-url',help='optional HTTPS Mesa source mirror')
    parser.add_argument('--debian-mirror',default='https://mirrors.tuna.tsinghua.edu.cn/debian')
    parser.add_argument('--proot',type=Path,help='PRoot executable')
    parser.add_argument('--qemu',type=Path,help='qemu-arm executable')
    parser.add_argument('--device-root', type=Path,
                        help='optional inspected offline device root or private copy for Wi-Fi board data')
    args = parser.parse_args(argv)
    if sys.platform != 'linux':
        parser.error('use Linux or WSL on a Linux filesystem')
    if not 1 <= args.jobs <= 32:
        parser.error('jobs must be between 1 and 32')
    work = args.work.resolve()
    if work.exists():
        parser.error('work directory must not exist')
    if not work.parent.is_dir():
        parser.error('work parent must already exist')
    if args.device_root is not None:
        device_root = args.device_root.resolve()
        if not device_root.is_dir():
            parser.error('device root must be an existing inspected offline directory')
        if work.is_relative_to(device_root) or device_root.is_relative_to(work):
            parser.error('work and device root must be separate')
    required = ('git', 'bash', 'make', 'arm-linux-gnueabihf-gcc', 'dtc',
                'mkimage', 'bc', 'bison', 'flex', 'sha256sum', 'stat', 'patch', 'modinfo',
                'cargo','rustc','meson','ninja','arm-linux-gnueabihf-strip','debootstrap','cpio','depmod','rsync')
    missing = [name for name in required if shutil.which(name) is None]
    if missing:
        parser.error('missing tools: ' + ', '.join(missing))
    proot=args.proot or (Path(shutil.which('proot')) if shutil.which('proot') else None)
    qemu=args.qemu or (Path(shutil.which('qemu-arm')) if shutil.which('qemu-arm') else None)
    if proot is None or qemu is None:parser.error('PRoot and qemu-arm are required')
    if shutil.disk_usage(work.parent).free < 20 * 1024**3:
        parser.error('at least 20 GiB free is required')
    fetch = load('fetch_sources', 'fetch-sources.py')
    desktop = load('desktop_upstream', 'fetch-desktop-upstream.py')
    stage = load('stage_firmware', 'stage-public-firmware.py')
    board = load('extract_board_data', 'extract-board-data.py')
    preflight = load('source_preflight', 'preflight-source-build.py')
    fetch.check_environment(work)
    work.mkdir(mode=0o700)
    lock = Path(__file__).resolve().parents[1] / 'sources.lock.json'
    sources, firmware, kernel = work/'sources', work/'firmware', work/'kernel'
    fetch.fetch(lock, sources, args.git_mirror, args.git_mirror_fallback)
    desktop.fetch(sources, work/'desktop-upstream',
                  Path(__file__).resolve().parents[1]/'desktop-upstream.lock.json',
                  git_mirror=args.git_mirror, git_mirror_fallback=args.git_mirror_fallback)
    stage.stage(sources/'mocha-moze-firmware-private', firmware, fetch_wifi=True, fetch_gpu=True)
    if args.device_root is not None:
        board.extract(args.device_root, firmware)
    subprocess.run([sys.executable, str(Path(__file__).with_name('build-source-kernel.py')),
                    '--workspace', str(sources), '--output', str(kernel), '--jobs', str(args.jobs),
                    '--lock', str(lock)], check=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name('build-source-drivers.py')),
                    '--workspace', str(sources), '--kernel', str(kernel), '--output', str(work/'drivers'),
                    '--jobs', str(args.jobs), '--lock', str(lock)], check=True)
    boot_cmd=[sys.executable, str(Path(__file__).with_name('build-source-boot.py')),
              '--workspace', str(sources), '--output', str(work/'boot'), '--jobs', str(args.jobs),
              '--lock', str(lock)]
    if args.git_mirror:boot_cmd+=['--git-mirror',args.git_mirror]
    subprocess.run(boot_cmd,check=True)
    desktop_cmd=[sys.executable,str(Path(__file__).with_name('build-source-desktop.py')),
                 '--workspace',str(sources),'--upstream',str(work/'desktop-upstream'),
                 '--output',str(work/'desktop-build'),'--jobs',str(args.jobs)]
    if args.mesa_archive is not None:desktop_cmd+=['--mesa-archive',str(args.mesa_archive.resolve())]
    if args.mesa_url is not None:desktop_cmd+=['--mesa-url',args.mesa_url]
    subprocess.run(desktop_cmd,check=True)
    tools=Path(__file__).resolve().parent
    root=work/'rootfs';data=work/'data';video=work/'video-build'
    adapter=sources/'mocha-moze-desktop';debian=sources/'mocha-moze-debian'
    subprocess.run([sys.executable,str(tools/'build-source-rootfs.py'),'--root',str(root),
                    '--kernel',str(kernel),'--debian',str(debian),'--proot',str(proot),
                    '--qemu',str(qemu),'--mirror',args.debian_mirror],check=True)
    ram=work/'installer.cpio.gz'
    subprocess.run([sys.executable,str(tools/'build-source-ram.py'),'--root',str(root),'--debian',str(debian),
                    '--output',str(ram),'--work',str(work/'ram-build'),'--qemu',str(qemu)],check=True)
    subprocess.run([sys.executable,str(tools/'install-source-desktop-deps.py'),'--root',str(root),
                    '--proot',str(proot),'--qemu',str(qemu)],check=True)
    subprocess.run([sys.executable,str(tools/'install-source-firmware.py'),'--root',str(root),
                    '--firmware',str(firmware)],check=True)
    subprocess.run([sys.executable,str(tools/'install-source-drivers.py'),'--root',str(root),
                    '--drivers',str(work/'drivers'),'--kernel',str(kernel)],check=True)
    video_cmd=[sys.executable,str(tools/'build-source-video.py'),'--adapter',str(adapter),
               '--out',str(video),'--jobs',str(min(args.jobs,4)),'--debian-mirror',args.debian_mirror]
    if args.git_mirror:video_cmd+=['--github-mirror',args.git_mirror]
    if args.git_mirror_fallback:video_cmd+=['--github-mirror-fallback',args.git_mirror_fallback]
    subprocess.run(video_cmd,check=True)
    data.mkdir()
    subprocess.run([sys.executable,str(tools/'install-source-desktop.py'),'--root',str(root),
                    '--data',str(data),'--components',str(work/'desktop-build'),'--adapter',str(adapter),
                    '--upstream',str(work/'desktop-upstream'),'--proot',str(proot),'--qemu',str(qemu),
                    '--video',str(video)],check=True)
    subprocess.run([sys.executable,str(tools/'assemble-source-candidate.py'),'--root',str(root),
                    '--data',str(data),'--kernel',str(kernel),'--drivers',str(work/'drivers'),
                    '--speaker-source',str(sources/'mocha-moze-drivers'),
                    '--loader',str(work/'boot/ram/boot.img'),'--ram-kernel',str(kernel/'uImage'),
                    '--ram-dtb',str(kernel/'mocha.dtb'),'--installer',str(ram),
                    '--lnx',str(work/'boot/emmc/boot.img'),'--output',str(work/'candidate')],check=True)
    result = preflight.inspect(lock, sources, firmware, work)
    result['issues']=[issue for issue in result.get('issues',[]) if not issue.startswith('source-to-desktop image assembly is not implemented')]
    result['candidate_bundle']=str(work/'candidate/bundle')
    result['source_components_built']=True
    result['issues'].append('candidate has not passed physical-device acceptance')
    (work/'source-build-status.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get('ready_to_flash') is not False:
        raise RuntimeError('incomplete source builder must never mark an image flash-ready')
    return 2


if __name__ == '__main__':
    sys.exit(main())
