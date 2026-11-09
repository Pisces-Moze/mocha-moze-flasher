#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Stage verified Mocha Bluetooth and speaker assets for a source build.

This copies a conservative fixed list into a new build directory; it never
updates a device, generates NVRAM, or treats MIUI GPU blobs as Nouveau firmware.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request

AUDIO = ('tfa9890.config', 'tfa9890_boot.patch', 'tfa9890_rom.patch',
         'tfa9890_left.speaker', 'tfa9890_right.speaker',
         'tfa9890_left_music.eq', 'tfa9890_right_music.eq',
         'tfa9890_left_music.preset', 'tfa9890_right_music.preset')
MAPPING = {'miui-system/etc/firmware/BCM4350C0.hcd': 'brcm/BCM4350C0.hcd',
           **{'miui-system/etc/firmware/' + x: 'mocha/' + x for x in AUDIO}}
DEBIAN = 'https://sources.debian.org/data/non-free-firmware/f/firmware-nonfree/20250410-2/'
WIFI_ASSETS = {
    'cypress/cyfmac4354-sdio.bin': ('brcm/brcmfmac4354-sdio.bin',
        'f6b4164c50c4406573f3671d50c2d19b370ed079035a7d76a38535e244ae41d8', 601704),
    'LICENCE.cypress': ('licenses/LICENCE.cypress',
        'ae0db6cc4db33941148df0f67de53e76a77b1b5a46b3165edb7040aa2750015f', 8914),
}


def stage(source, output, fetch_wifi=False):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists() or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('output must be new and separate from the firmware checkout')
    data = json.loads((source / 'manifest.json').read_text(encoding='utf-8-sig'))
    rows = data.get('files', [])
    records = {}
    for row in rows:
        name = row.get('path')
        if name in MAPPING:
            if name in records:
                raise ValueError('duplicate firmware manifest entry')
            records[name] = row
    if set(records) != set(MAPPING):
        raise ValueError('firmware manifest is missing required entries')
    for name, row in records.items():
        path = source / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source):
            raise ValueError('firmware source is missing or unsafe: ' + name)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if path.stat().st_size != row.get('bytes') or digest != row.get('sha256'):
            raise ValueError('firmware checksum mismatch: ' + name)
    downloaded = {}
    if fetch_wifi:
        for name, (dest, expected, size) in WIFI_ASSETS.items():
            with urllib.request.urlopen(DEBIAN + name, timeout=60) as response:
                content = response.read(size + 1)
            if len(content) != size or hashlib.sha256(content).hexdigest() != expected:
                raise ValueError('upstream Wi-Fi asset checksum mismatch: ' + name)
            downloaded[dest] = content
    output.mkdir(parents=True, mode=0o700)
    for name, dest in MAPPING.items():
        target = output / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    for dest, content in downloaded.items():
        target = output / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    missing = ['per-device wifi board data', 'nouveau gk20a firmware']
    if not fetch_wifi:
        missing.insert(0, 'wifi firmware')
    (output / 'staged-firmware.json').write_text(json.dumps({
        'schema': 1, 'files': {**{MAPPING[k]: v['sha256'] for k, v in records.items()},
                              **{dest: hashlib.sha256(content).hexdigest() for dest, content in downloaded.items()}},
        'complete': False,
        'missing': missing
    }, indent=2) + '\n')
    print('FIRMWARE_PARTIALLY_STAGED: ' + ', '.join(missing) + ' still required')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--fetch-wifi', action='store_true', help='download and hash-check the tested Debian Wi-Fi firmware and its licence')
    a = p.parse_args()
    stage(a.source, a.output, a.fetch_wifi)


if __name__ == '__main__':
    main()
