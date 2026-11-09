#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only prerequisites check for the unfinished source-to-image pipeline.

This is not a flashing command, does not access the tablet or the network, and
never grants permission to flash. Source checkouts and firmware are inspected
locally only. A passing dependency check is not evidence of a working image.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

REPOS = frozenset(('mocha-moze-boot', 'mocha-moze-linux', 'mocha-moze-drivers',
                   'mocha-moze-desktop', 'mocha-moze-debian',
                   'mocha-moze-firmware-private'))
TOOLS = ('git', 'python3', 'bash', 'make', 'bc', 'bison', 'flex',
         'arm-linux-gnueabihf-gcc', 'arm-linux-gnueabihf-g++',
         'arm-linux-gnueabihf-readelf', 'dtc', 'mkimage', 'debootstrap',
         'qemu-arm-static', 'rsync', 'cpio', 'gzip', 'xz', 'tar', 'openssl',
         'pkg-config', 'meson', 'ninja', 'cmake', 'rustc', 'cargo',
         'dpkg-query', 'truncate', 'mkfs.ext4', 'e2fsck')
# Reference files consumed by the Mocha runtime, not proof of support for all
# board revisions. The caller supplies their own staged firmware directory.
FIRMWARE = {
    'wifi firmware': 'brcm/brcmfmac4354-sdio.bin',
    'wifi board data': 'brcm/brcmfmac4354-sdio.nvidia,mocha.txt',
    'bluetooth firmware': 'brcm/BCM4350C0.hcd',
}
MIN_BYTES = 20 * 1024**3


def source_checks(lock_path, workspace):
    problems = []
    try:
        lock = json.loads(lock_path.read_text(encoding='utf-8-sig'))
        if not isinstance(lock, dict):
            raise ValueError('invalid lock schema')
        rows = lock.get('repositories')
        if lock.get('schema') != 1 or not isinstance(rows, list):
            raise ValueError('invalid lock schema')
        names = [row.get('name') for row in rows if isinstance(row, dict)]
        if len(names) != len(REPOS) or set(names) != REPOS:
            raise ValueError('lock must contain the six expected repositories exactly once')
        for row in rows:
            if not re.fullmatch(r'[0-9a-f]{40}', row.get('commit', '')):
                raise ValueError('invalid locked commit')
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return ['source lock invalid or unavailable: ' + str(exc)]
    for row in rows:
        name = row['name']
        directory = workspace / name
        if not directory.is_dir():
            problems.append('missing source checkout: ' + name)
            continue
        try:
            actual = subprocess.run(['git', '-C', str(directory), 'rev-parse', 'HEAD'],
                                    check=True, text=True, capture_output=True, timeout=20).stdout.strip()
            dirty = subprocess.run(['git', '-C', str(directory), 'status', '--porcelain',
                                    '--untracked-files=all'], check=True, text=True,
                                   capture_output=True, timeout=30).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            problems.append('cannot inspect source checkout: ' + name)
            continue
        if actual != row['commit']:
            problems.append('source commit does not match lock: ' + name)
        if dirty:
            problems.append('source checkout has modifications or untracked files: ' + name)
    return problems


def firmware_checks(root):
    if root is None or not root.is_dir():
        return ['firmware staging directory not supplied or unavailable']
    missing = []
    for label, relative in FIRMWARE.items():
        if not (root / relative).is_file():
            missing.append('missing staged ' + label)
    for name in ('fecs_inst.bin', 'fecs_data.bin', 'gpccs_inst.bin', 'gpccs_data.bin',
                 'sw_bundle_init.bin', 'sw_method_init.bin', 'sw_nonctx.bin', 'sw_ctx.bin'):
        if not (root / 'nvidia' / 'gk20a' / name).is_file():
            missing.append('missing staged GK20A microcode: ' + name)
    for name in ('tfa9890.config', 'tfa9890_boot.patch', 'tfa9890_rom.patch',
                 'tfa9890_left.speaker', 'tfa9890_right.speaker',
                 'tfa9890_left_music.eq', 'tfa9890_right_music.eq',
                 'tfa9890_left_music.preset', 'tfa9890_right_music.preset'):
        if not (root / 'mocha' / name).is_file():
            missing.append('missing staged TFA9890 speaker asset: ' + name)
    return missing


def inspect(lock, workspace, firmware, output_parent):
    issues = []
    if platform.system() != 'Linux':
        issues.append('Linux build environment required; Windows Fastboot is a separate stage')
    elif not hasattr(os, 'geteuid') or os.geteuid() != 0:
        issues.append('Linux root is required for the existing rootfs and image build')
    issues.extend('missing tool: ' + name for name in TOOLS if shutil.which(name) is None)
    try:
        if shutil.disk_usage(output_parent).free < MIN_BYTES:
            issues.append('less than 20 GiB free in the build filesystem')
    except OSError:
        issues.append('cannot inspect free space for build output')
    issues.extend(source_checks(lock, workspace))
    issues.extend(firmware_checks(firmware))
    # This is a hard stop, not an optional warning: the published tree does not
    # contain a complete, validated source-to-desktop image assembler yet.
    issues.append('source-to-desktop image assembly is not implemented or validated; '
                  'the existing builder requires an offline APP/UDA snapshot')
    return {'schema': 1, 'ready_to_build_from_sources': False,
            'ready_to_flash': False, 'issues': issues}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True,
                        help='directory containing the six pinned source checkouts')
    parser.add_argument('--firmware-dir', type=Path,
                        help='user-provided staged Linux firmware root (never uploaded)')
    parser.add_argument('--output-parent', type=Path, required=True,
                        help='existing build filesystem used to check available space')
    parser.add_argument('--lock', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'sources.lock.json')
    args = parser.parse_args(argv)
    result = inspect(args.lock, args.workspace, args.firmware_dir, args.output_parent)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2


if __name__ == '__main__':
    sys.exit(main())
