#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Rebuild the accepted r6 desktop image with the data-backed home layout."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

from stage_home import stage_home


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path, help='verified r6 image directory')
    parser.add_argument('raw', type=Path, help='raw, decompressed r6 APP image')
    parser.add_argument('output', type=Path, help='new output directory')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('builder', repo/'tools/build-distribution.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    base = json.loads((args.base/'bundle.json').read_text())
    if base['version'] != 'source-candidate-20261118-r6' or builder.digest(args.raw) != base['app_raw_sha256']:
        raise ValueError('r6 base image does not match its manifest')
    for filename, entry in base['files'].items():
        if filename != 'APP.img.xz' and builder.digest(args.base/filename) != entry['sha256']:
            raise ValueError('r6 bundle member does not match its manifest: ' + filename)
    output = args.output.resolve()
    output.mkdir(mode=0o700)
    work = output/'private-work'
    data = work/'DATA'
    data.mkdir(parents=True)
    image = output/'image'
    image.mkdir()
    subprocess.run(['tar', '--extract', '--xz', '--numeric-owner', '--same-permissions', '--xattrs', '--acls',
                    '--file', str(args.base/'DATA.tar.xz'), '--directory', str(data)], check=True)
    raw = work/'APP.img'
    subprocess.run(['cp', '--sparse=always', '--reflink=auto', str(args.raw), str(raw)], check=True)
    root = work/'mount'
    root.mkdir()
    subprocess.run(['mount', '-o', 'loop', str(raw), str(root)], check=True)
    try:
        stage_home(root, data)
        speaker = root/'usr/local/libexec/mocha-speaker-hardware'
        original = speaker.read_text()
        old = "control(side + ' Spk Digital Volume', '219')  # -18 dB hardware ceiling"
        if original.count(old) != 1:
            raise ValueError('unexpected r6 speaker volume setting')
        speaker.write_text(original.replace(old, "control(side + ' Spk Digital Volume', '231')  # -12 dB hardware ceiling"))
        (root/'opt/mocha-cuda-runtime/bin/runtime-smoke').chmod(0o755)
        assert not any((root/'home').iterdir())
        home = data/'home/mocha'
        assert home.stat().st_uid == 1000
        assert (home/'.config/niri/config.kdl').is_file()
    finally:
        subprocess.run(['umount', str(root)], check=True)
    root.rmdir()
    subprocess.run(['e2fsck', '-fn', str(raw)], check=True)
    with (image/'APP.img.xz').open('wb') as stream:
        subprocess.run(['xz', '-T2', '-3', '-c', str(raw)], stdout=stream, check=True)
    inputs = SimpleNamespace(version='source-candidate-20261120-r7', loader=args.base/'loader.img',
                             ram_kernel=args.base/'uImage', ram_dtb=args.base/'mocha.dtb',
                             installer=args.base/'installer.cpio.gz', lnx=args.base/'LNX.img')
    builder.finish_candidate(inputs, repo, output, builder.digest(raw),
                             sum(p.stat().st_size for p in data.rglob('*') if not p.is_symlink() and p.is_file()))


if __name__ == '__main__':
    main()
