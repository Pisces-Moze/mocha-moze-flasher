#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build the pinned kernel stage. Does not assemble or flash a system."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--jobs', type=int, default=4)
    p.add_argument('--lock', type=Path, default=Path(__file__).resolve().parents[1] / 'sources.lock.json')
    a = p.parse_args(argv)
    if sys.platform != 'linux':
        p.error('Linux is required for the kernel build')
    if not 1 <= a.jobs <= 32:
        p.error('jobs must be between 1 and 32')
    if a.output.exists():
        p.error('output must be a new directory')
    parent = a.output.resolve().parent
    if not parent.is_dir():
        p.error('output parent must exist')
    if shutil.disk_usage(parent).free < 10 * 1024**3:
        p.error('at least 10 GiB free is required')
    required = ('git', 'bash', 'make', 'arm-linux-gnueabihf-gcc', 'dtc',
                'mkimage', 'bc', 'bison', 'flex', 'sha256sum')
    missing = [x for x in required if shutil.which(x) is None]
    if missing:
        p.error('missing build tools: ' + ', '.join(missing))
    spec = importlib.util.spec_from_file_location('source_preflight', Path(__file__).with_name('preflight-source-build.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    issues = module.source_checks(a.lock, a.workspace.resolve())
    if issues:
        p.error('; '.join(issues))
    source = a.workspace.resolve() / 'mocha-moze-linux'
    script = source / 'moze/tools/build.sh'
    if not script.is_file():
        p.error('pinned kernel build script is missing')
    out = a.output.resolve()
    if out.is_relative_to(a.workspace.resolve()) or a.workspace.resolve().is_relative_to(out):
        p.error('output and source workspace must be separate')
    out.mkdir(mode=0o700)
    env = os.environ.copy(); env['JOBS'] = str(a.jobs)
    subprocess.run(['bash', str(script), 'native-runtime', str(out)], env=env, check=True)
    subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=out, check=True)
    (out/'source-build.json').write_text(json.dumps({'schema': 1, 'stage': 'kernel',
        'profile': 'native-runtime', 'flash_ready': False}, indent=2) + '\n')
    print('KERNEL_BUILD_VERIFIED; desktop assembly and device validation are still required')
    return 0


if __name__ == '__main__':
    sys.exit(main())
