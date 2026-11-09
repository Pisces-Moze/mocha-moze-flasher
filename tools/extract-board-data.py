#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Copy this device's Wi-Fi board data from an inspected offline root.

Never writes the source. Missing or conflicting candidates stop the operation.
The result is device-specific and must not be uploaded or shared.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

CANDIDATES = (
    'usr/lib/firmware/brcm/brcmfmac4354-sdio.nvidia,mocha.txt',
    'lib/firmware/brcm/brcmfmac4354-sdio.nvidia,mocha.txt',
    'system/etc/firmware/nvram.txt',
    'system/vendor/firmware/nvram.txt',
    'vendor/firmware/nvram.txt',
    'etc/firmware/nvram.txt',
    'etc/wifi/nvram.txt',
    'system/etc/wifi/nvram.txt',
)
OUTPUT = 'brcm/brcmfmac4354-sdio.nvidia,mocha.txt'


def extract(source, firmware):
    source, firmware = Path(source).resolve(), Path(firmware).resolve()
    if not source.is_dir() or not firmware.is_dir():
        raise ValueError('source root and firmware staging directory must exist')
    if source == firmware or source.is_relative_to(firmware) or firmware.is_relative_to(source):
        raise ValueError('source and firmware directories must be separate')
    candidates = []
    for rel in CANDIDATES:
        path = source/rel
        if path.is_symlink() or not path.is_file():
            continue
        if not path.resolve().is_relative_to(source):
            raise ValueError('board-data path escapes source root')
        if path.stat().st_size > 128 * 1024:
            raise ValueError('board data exceeds size limit')
        data = path.read_bytes()
        try: text = data.decode('ascii')
        except UnicodeError as exc: raise ValueError('board data must be text') from exc
        if '\x00' in text:
            raise ValueError('board data contains NUL bytes')
        keys = {line.split('=', 1)[0].strip().lower() for line in text.splitlines()
                if '=' in line and not line.lstrip().startswith('#')}
        if not {'sromrev', 'boardrev', 'boardtype'}.issubset(keys):
            raise ValueError('candidate is not a supported Broadcom board-data file')
        candidates.append(data)
    if not candidates:
        raise ValueError('device Wi-Fi board data not found in supported locations')
    if len({hashlib.sha256(x).digest() for x in candidates}) != 1:
        raise ValueError('conflicting board-data candidates; no file was selected')
    target = firmware/OUTPUT
    if target.exists() or target.is_symlink():
        raise ValueError('board-data destination already exists')
    if target.parent.is_symlink() or not target.parent.resolve().is_relative_to(firmware):
        raise ValueError('board-data destination escapes staging directory')
    manifest = firmware/'staged-firmware.json'
    metadata = None
    if manifest.exists():
        if manifest.is_symlink():
            raise ValueError('staging manifest must not be a symlink')
        metadata = json.loads(manifest.read_text(encoding='utf-8'))
        if metadata.get('schema') != 1 or not isinstance(metadata.get('missing'), list):
            raise ValueError('invalid staging manifest')
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(candidates[0]); stream.flush(); os.fsync(stream.fileno())
    if metadata is not None:
        metadata['missing'] = [x for x in metadata['missing'] if x != 'per-device wifi board data']
        # Never include the device-specific bytes or their hash in the report.
        metadata['complete'] = not metadata['missing']
        temporary = manifest.with_name('.staged-firmware.json.tmp')
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(metadata, stream, indent=2); stream.write('\n')
        temporary.replace(manifest)
    print('DEVICE_BOARD_DATA_STAGED; keep the staging directory private')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True, help='read-only offline device system root or private copy')
    p.add_argument('--firmware-dir', type=Path, required=True)
    a = p.parse_args(); extract(a.root, a.firmware_dir)


if __name__ == '__main__': main()
