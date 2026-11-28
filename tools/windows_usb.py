"""Discover Mocha's Windows USB instances and repair matching signed drivers."""
import base64
import ctypes
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def powershell(script, timeout):
    return subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
        capture_output=True, timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW,
        text=True, encoding='utf-8', errors='replace',
    )


def devices():
    script = r"""
[Console]::OutputEncoding=[Text.Encoding]::UTF8
Get-PnpDevice -PresentOnly | Where-Object InstanceId -Match '^(USB\\VID_(?:18D1|2717)&PID_D00D|USB\\VID_1D6B&PID_0104)' |
ForEach-Object {
  $id=$_.InstanceId
  $props=Get-PnpDeviceProperty -InstanceId $id -KeyName @('DEVPKEY_Device_HardwareIds','DEVPKEY_Device_CompatibleIds','DEVPKEY_Device_Parent') -ErrorAction SilentlyContinue
  [pscustomobject]@{id=$id;name=$_.FriendlyName;status=$_.Status;
    hardware=@(($props | Where-Object KeyName -eq 'DEVPKEY_Device_HardwareIds').Data);
    compatible=@(($props | Where-Object KeyName -eq 'DEVPKEY_Device_CompatibleIds').Data);
    parent=($props | Where-Object KeyName -eq 'DEVPKEY_Device_Parent').Data}
} | ConvertTo-Json -Compress
"""
    result = powershell(script, 12)
    if result.returncode:
        return []
    data = json.loads(result.stdout or '[]')
    return data if isinstance(data, list) else [data]


def matching_drivers(device):
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'usb-drivers'
    ids = {value.upper() for value in device['hardware'] + device['compatible'] if value}
    for path in sorted(root.rglob('*.inf')):
        raw = path.read_bytes()
        source = raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig',
                            errors='replace')
        models = {field.strip().upper() for line in source.splitlines()
                  for field in line.split(';', 1)[0].split(',')[1:]}
        if ids & models:
            yield path


def pnp(*args):
    if ctypes.windll.shell32.IsUserAnAdmin():
        return subprocess.run(
            ['pnputil.exe', *map(str, args)], timeout=75,
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
        ).returncode

    def quote(arg):
        return "'" + str(arg).replace("'", "''") + "'"

    # Driver staging uses Windows signature and ranking enforcement.
    command_line = subprocess.list2cmdline([str(arg) for arg in args])
    return powershell(
        "$p=Start-Process -FilePath pnputil.exe -ArgumentList " + quote(command_line)
        + " -Verb RunAs -WindowStyle Hidden -Wait -PassThru; if (!$p) { exit 1 }; exit $p.ExitCode",
        75,
    ).returncode


def bind_fastboot(driver, instance):
    hardware_id = instance.rsplit('\\', 1)[0]
    script = r"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class MochaDriver {
  [DllImport("newdev.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  public static extern bool UpdateDriverForPlugAndPlayDevices(
    IntPtr window, string hardwareId, string inf, uint flags, out bool reboot);
}
"@
$reboot=$false
if (![MochaDriver]::UpdateDriverForPlugAndPlayDevices(
    [IntPtr]::Zero, 'HARDWARE_ID', 'INF_PATH', 5, [ref]$reboot)) { exit 1 }
if ($reboot) { exit 2 }
"""
    script = script.replace('HARDWARE_ID', hardware_id).replace(
        'INF_PATH', str(driver).replace("'", "''"))
    if ctypes.windll.shell32.IsUserAnAdmin():
        return powershell(script, 75).returncode
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    return powershell(
        " $p=Start-Process powershell.exe -ArgumentList "
        f"'-NoProfile -NonInteractive -EncodedCommand {encoded}'"
        " -Verb RunAs -WindowStyle Hidden -Wait -PassThru; if (!$p) { exit 1 }; exit $p.ExitCode",
        75,
    ).returncode


def repair_usb(stage):
    if os.name != 'nt':
        return
    try:
        candidates = []
        for device in devices():
            instance = device['id'].upper()
            if stage == 'fastboot' and re.fullmatch(r'USB\\VID_(?:18D1|2717)&PID_D00D\\[^\\]+', instance):
                candidates.append(device)
            elif (stage == 'rndis' and instance.startswith(r'USB\VID_1D6B&PID_0104&MI_')
                  and (device.get('parent') or '').upper().endswith(r'\MOCHA-RAM-BRINGUP')):
                candidates.append(device)
        if len(candidates) != 1:
            print('Windows did not identify one Mocha USB interface to repair.', flush=True)
            return
        device = candidates[0]
        print(f"Windows USB: {device['name'] or stage} ({device['status']}).", flush=True)
        drivers = list(matching_drivers(device))
        inf = Path(os.environ['WINDIR']) / 'INF'
        if stage == 'rndis' and any('MS_COMP_RNDIS' in value.upper()
                                    for value in device['compatible'] if value):
            drivers.append(inf / 'netrndis.inf')
        if stage == 'fastboot' and any('MS_COMP_WINUSB' in value.upper()
                                       for value in device['compatible'] if value):
            drivers.append(inf / 'winusb.inf')
        driver = next((path for path in drivers if path.is_file()), None)
        if driver:
            if stage == 'fastboot' and drivers and driver == drivers[0] and driver != inf / 'winusb.inf':
                code = bind_fastboot(driver, device['id'])
            else:
                code = pnp('/add-driver', driver, '/install')
            print(f'Windows driver repair exited with code {code}.', flush=True)
            if stage == 'fastboot' and code == 2:
                print('Windows needs to re-enumerate the device. Unplug and reconnect the USB cable while the tablet stays in RAM Fastboot.', flush=True)
        elif stage == 'fastboot' and device['status'] == 'OK' and 'bootloader' in (device['name'] or '').lower():
            code = pnp('/restart-device', device['id'])
            print(f'Windows USB device restart exited with code {code}.', flush=True)
        else:
            print('No matching signed driver available for automatic repair. Select the appropriate driver in Device Manager.', flush=True)
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        print(f'USB repair could not finish: {error}', flush=True)
