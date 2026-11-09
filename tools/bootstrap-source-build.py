#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Fetch pinned sources, stage firmware, build a kernel and report readiness.

This incomplete builder never accesses or flashes a tablet. A nonzero exit is
intentional until the full desktop image assembler is implemented and verified.
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
    required = ('git', 'bash', 'make', 'arm-linux-gnueabihf-gcc', 'dtc',
                'mkimage', 'bc', 'bison', 'flex', 'sha256sum', 'stat')
    missing = [name for name in required if shutil.which(name) is None]
    if missing:
        parser.error('missing tools: ' + ', '.join(missing))
    if shutil.disk_usage(work.parent).free < 20 * 1024**3:
        parser.error('at least 20 GiB free is required')
    fetch = load('fetch_sources', 'fetch-sources.py')
    stage = load('stage_firmware', 'stage-public-firmware.py')
    preflight = load('source_preflight', 'preflight-source-build.py')
    fetch.check_environment(work)
    work.mkdir(mode=0o700)
    lock = Path(__file__).resolve().parents[1] / 'sources.lock.json'
    sources, firmware, kernel = work/'sources', work/'firmware', work/'kernel'
    fetch.fetch(lock, sources)
    stage.stage(sources/'mocha-moze-firmware-private', firmware, fetch_wifi=True, fetch_gpu=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name('build-source-kernel.py')),
                    '--workspace', str(sources), '--output', str(kernel), '--jobs', str(args.jobs),
                    '--lock', str(lock)], check=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name('build-source-boot.py')),
                    '--workspace', str(sources), '--output', str(work/'boot'), '--jobs', str(args.jobs),
                    '--lock', str(lock)], check=True)
    result = preflight.inspect(lock, sources, firmware, work)
    (work/'source-build-status.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get('ready_to_flash') is not False:
        raise RuntimeError('incomplete source builder must never mark an image flash-ready')
    return 2


if __name__ == '__main__':
    sys.exit(main())
