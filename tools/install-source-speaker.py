#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Stage the Mocha protected stereo speaker service into a source rootfs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

MODULES=[('snd_soc_rt5670','snd-soc-rt5670.ko',[]),
         ('mocha_rt5671_board','mocha_rt5671_board.ko',['register_codec=1']),
         ('mocha_audio_i2s_probe','mocha_audio_i2s_probe.ko',[]),
         ('mocha_audio_data_pin','mocha_audio_data_pin.ko',[]),
         ('mocha_miui_tfa98xx','mocha_miui_tfa98xx.ko',[]),
         ('mocha_audio_runtime_card','mocha_audio_runtime_card.ko',[])]


def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def install(root,drivers,kernel,source):
    root,drivers,kernel,source=map(Path,(root,drivers,kernel,source))
    if root.resolve()==Path('/') or not (root/'.mocha-source-rootfs-build').is_file():
        raise ValueError('marked offline source rootfs required')
    release=(kernel/'include/config/kernel.release').read_text().strip()
    built=json.loads((drivers/'modules.json').read_text())
    if built['kernelrelease']!=release:raise ValueError('kernel and modules do not match')
    extra=root/'usr/lib/modules'/release/'extra'
    fw=root/'usr/lib/firmware/mocha'
    firmware=sorted(fw.glob('tfa9890*'))
    if len(firmware)!=9:raise ValueError('nine speaker firmware files are required')
    audio=source/'audio'
    if not audio.is_dir():raise ValueError('driver source audio directory not found')
    target=root/'usr/local/lib/mocha-audio'/release/'source'
    target.mkdir(parents=True,exist_ok=False)
    manifest={'kernel':release,'modules':[],'firmware':[],'physical_stereo_confirmed':False}
    hashes={Path(name).name:sha for name,sha in built['files'].items()}
    for name,filename,params in MODULES:
        module=extra/filename
        sha=digest(module)
        if hashes.get(filename)!=sha:raise ValueError('speaker module mismatch: '+filename)
        shutil.copy2(module,target/filename)
        manifest['modules'].append({'name':name,'file':filename,'sha256':sha,'parameters':params})
    for path in firmware:manifest['firmware'].append({'file':path.name,'sha256':digest(path)})
    (target/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    service=(audio/'mocha-speaker-hardware.service').read_text().replace('6.12.111-moze.1-native-vde2',release)
    program=(audio/'mocha-speaker-hardware.py').read_text().replace('6.12.111-moze.1-native-vde2',release).replace("/ '20261022'","/ 'source'")
    files={'usr/local/libexec/mocha-speaker-hardware':program,
           'etc/systemd/system/mocha-speaker-hardware.service':service,
           'etc/wireplumber/wireplumber.conf.d/51-mocha-speakers.conf':(audio/'51-mocha-speakers.conf').read_text(),
           'usr/share/alsa-card-profile/mixer/profile-sets/mocha-speakers.conf':(audio/'mocha-speakers.conf').read_text()}
    for name,text in files.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    (root/'usr/local/libexec/mocha-speaker-hardware').chmod(0o755)
    wants=root/'etc/systemd/system/multi-user.target.wants';wants.mkdir(parents=True,exist_ok=True)
    link=wants/'mocha-speaker-hardware.service'
    if not link.is_symlink():link.symlink_to('../mocha-speaker-hardware.service')
    # Include the previously exercised stock-frequency policy with the
    # 1020 MHz CPU / 648 MHz GPU limits used for the prototype tests.
    for src,dst in [('runtime/mocha-runtime-policy.py','usr/local/libexec/mocha-runtime-policy.py'),
                    ('runtime/mocha-runtime-policy.service','etc/systemd/system/mocha-runtime-policy.service'),
                    ('gpu/mocha-native-gpu-policy.sh','usr/local/libexec/mocha-native-gpu-policy.sh')]:
        shutil.copy2(source/src,root/dst)
    (root/'usr/local/libexec/mocha-runtime-policy.py').chmod(0o755)
    (root/'usr/local/libexec/mocha-native-gpu-policy.sh').chmod(0o755)
    gpu_service=root/'etc/systemd/system/mocha-native-gpu-policy.service'
    gpu_service.write_text('[Unit]\nDescription=Mocha stock GPU policy\nAfter=mocha-desktop-hardware.service\n'
                           '[Service]\nType=simple\nExecStart=/usr/local/libexec/mocha-native-gpu-policy.sh\n'
                           'Restart=on-failure\nRestartSec=10\n[Install]\nWantedBy=multi-user.target\n')
    for name in ('mocha-runtime-policy.service','mocha-native-gpu-policy.service'):
        link=wants/name
        if not link.is_symlink():link.symlink_to('../'+name)
    settings=root/'home/mocha/.config/mocha';settings.mkdir(parents=True,exist_ok=True)
    (settings/'runtime.json').write_text(json.dumps({'cpu_max_mhz':1020,'swappiness':80})+'\n')
    (settings/'gpu-max-pstate').write_text('0a\n')
    for path in (settings,settings/'runtime.json',settings/'gpu-max-pstate'):os.chown(path,1000,1000)
    print('SOURCE_SPEAKER_STAGED; real stereo playback requires device validation')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','drivers','kernel','source'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if not hasattr(os,'geteuid') or os.geteuid()!=0:p.error('Linux root required')
    try:install(a.root,a.drivers,a.kernel,a.source)
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as exc:p.error(str(exc))


if __name__=='__main__':main()
