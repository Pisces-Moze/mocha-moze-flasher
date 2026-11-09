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
import time
import http.client
import urllib.error
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
GPU_FILES = {
    'fecs_data.bin': (1920, 'a1a383cf91b5893328d99fff7b5a6dbf2d55763c002824d0990d611503276c5e'),
    'fecs_inst.bin': (15356, '5f75f4cf6f806e280678a6a1abdb511cf91064ed31a018b15d0c9ef104328f8f'),
    'gpccs_data.bin': (1800, '2b38205c1b188454028cdf5dbb0d4dd08e53cc47fa40e93223fb86f99c3d4918'),
    'gpccs_inst.bin': (8171, '69e88f65d33c34db0f5b0f6b9edd3e2d666be8a9a7fc059751d7a7d1a9ccff56'),
    'sw_bundle_init.bin': (6696, '0403f73727b523bbbfe9cda9349ebfccfa8089e2975e3092c0263227565d055f'),
    'sw_ctx.bin': (4464, '7c8fc16631fe2ecde8aa5e09e1c9d4fcd78628a771f0520c592469d9690798a9'),
    'sw_method_init.bin': (10304, 'f7d2f2e92055c56a0a6b582de727562eb43d512ebf2d95d4ac374676dacd3259'),
    'sw_nonctx.bin': (1360, '8d190e7c8ddbd3e756ad6ef6014b86d65070b9930eaa8de8249d154d1b893f40'),
}
GPU_ASSETS = {
    **{'nvidia/gk20a/' + name: ('nvidia/gk20a/' + name, sha, size)
       for name, (size, sha) in GPU_FILES.items()},
    'LICENCE.nvidia': ('licenses/LICENCE.nvidia',
        'bc5225a57f49c5249dcf238e4ae6437811677a2a8a7f579c3d839e058653ee44', 6212),
}


def download(name, size):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(DEBIAN + name, timeout=45) as response:
                return response.read(size + 1)
        except (OSError, urllib.error.URLError, http.client.HTTPException):
            if attempt == 2:
                raise
            time.sleep(1 + attempt * 2)


def stage(source, output, fetch_wifi=False, fetch_gpu=False):
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
    for label, assets in (('Wi-Fi', WIFI_ASSETS if fetch_wifi else {}),
                          ('GPU', GPU_ASSETS if fetch_gpu else {})):
        for name, (dest, expected, size) in assets.items():
            content = download(name, size)
            if len(content) != size or hashlib.sha256(content).hexdigest() != expected:
                raise ValueError('upstream ' + label + ' asset checksum mismatch: ' + name)
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
    missing = ['per-device wifi board data']
    if not fetch_wifi:
        missing.insert(0, 'wifi firmware')
    if not fetch_gpu:
        missing.append('nouveau gk20a firmware')
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
    p.add_argument('--fetch-gpu', action='store_true', help='download and hash-check the tested Debian GK20A firmware and its licence')
    a = p.parse_args()
    stage(a.source, a.output, a.fetch_wifi, a.fetch_gpu)


if __name__ == '__main__':
    main()
