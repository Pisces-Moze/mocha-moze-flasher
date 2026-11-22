#!/usr/bin/env python3
"""Build a portable Windows GUI with fastboot and its dependencies."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--platform-tools', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--usb-drivers', type=Path,
                    help='Directory containing matching signed Windows INF packages')
args = parser.parse_args()
if args.usb_drivers and not any(args.usb_drivers.rglob('*.inf')):
    parser.error('--usb-drivers must contain at least one INF')
tools = Path(__file__).resolve().parent
platform_tools = args.platform_tools.resolve()
files = ('fastboot.exe', 'AdbWinApi.dll', 'AdbWinUsbApi.dll', 'libwinpthread-1.dll', 'NOTICE.txt')
with tempfile.TemporaryDirectory(prefix='mocha-flasher-build-') as temporary:
    work = Path(temporary)
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--windowed', '--uac-admin',
               '--name', 'Mocha-Flasher', '--hidden-import', 'flash-distribution',
               '--distpath', str(args.output.resolve()), '--workpath', str(work/'work'),
               '--specpath', str(work), '--paths', str(tools)]
    if args.usb_drivers:
        command += ['--add-data', f'{args.usb_drivers.resolve()}:usb-drivers']
    for name in files:
        source = platform_tools/name
        if not source.is_file():
            parser.error(f'Missing platform-tools file: {source}')
        command += ['--add-data', f'{source}{":"}platform-tools']
    subprocess.run(command+[str(tools/'mocha-flasher-gui.py')], check=True)
