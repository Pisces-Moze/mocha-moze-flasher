#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Install built desktop components and pinned Nyxuri into an offline rootfs.

The hardware video player, firmware and kernel are separate build stages.
This command does not start a desktop or access a tablet.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

NYXURI='ebafe03c9bdf1291eeb83d0f8c368d40a63ccdfd'
def install(root,data,components,adapter,upstream,proot,qemu,video):
    root,data,components,adapter,upstream,proot,qemu,video=map(Path,(root,data,components,adapter,upstream,proot,qemu,video))
    if root.resolve()==Path('/') or not (root/'.mocha-source-rootfs-build').is_file():
        raise ValueError('marked offline source rootfs required')
    groups={line.split(':',1)[0] for line in (root/'etc/group').read_text().splitlines()}
    selected=[name for name in ('sudo','audio','video','input','render') if name in groups]
    if selected:
        subprocess.run([str(proot),'-r',str(root),'-q',str(qemu),'-b','/dev','-w','/',
                        '/usr/sbin/usermod','-aG',','.join(selected),'mocha'],
                       env=dict(os.environ,PROOT_NO_SECCOMP='1'),check=True)
    extras={'wtype':'wtype','wl-copy':'wl-clipboard','playerctl':'playerctl'}
    missing=sorted({package for command,package in extras.items() if not (root/'usr/bin'/command).exists()})
    if missing:
        subprocess.run([str(proot),'-r',str(root),'-q',str(qemu),'-b','/dev','-b','/etc/resolv.conf',
                        '-w','/','/usr/bin/apt-get','-o','APT::Sandbox::User=root','-y',
                        '--no-install-recommends','install',*missing],
                       env=dict(os.environ,PROOT_NO_SECCOMP='1',DEBIAN_FRONTEND='noninteractive'),check=True)
    for component in ('niri','noctalia','mesa/stage'):
        if not (components/component).is_dir():raise ValueError('missing built component: '+component)
    actual=subprocess.check_output(['git','-C',str(upstream/'nyxuri'),'rev-parse','HEAD'],text=True).strip()
    if actual!=NYXURI:raise ValueError('unexpected Nyxuri revision')
    for name in ('niri','noctalia','mesa/stage'):
        shutil.copytree(components/name,root,dirs_exist_ok=True,symlinks=True)
    libexec=root/'usr/local/libexec';libexec.mkdir(parents=True,exist_ok=True)
    bin_dir=root/'usr/local/bin';bin_dir.mkdir(parents=True,exist_ok=True)
    for name in ('mocha-native-app','mocha-session-exec','mocha-buttons.py','mocha-touch-key-lights.py','mocha-touch-keyboard.py'):
        shutil.copy2(adapter/'tablet'/name,libexec/name);(libexec/name).chmod(0o755)
    for name in ('mocha-input-method','mocha-keyboard','mocha-touch-nav'):
        shutil.copy2(adapter/'tablet'/name,bin_dir/name);(bin_dir/name).chmod(0o755)
    appdir=root/'usr/local/share/applications';appdir.mkdir(parents=True,exist_ok=True)
    for name in ('mocha-keyboard.desktop','mocha-input-method.desktop'):
        shutil.copy2(adapter/'tablet'/name,appdir/name)
    release=libexec/'mocha-tablet-release/mesa';(release/'lib').mkdir(parents=True,exist_ok=True)
    for link,target in ((release/'lib/arm-linux-gnueabihf','/opt/mocha-mesa-candidate/lib/arm-linux-gnueabihf'),
                        (release/'dri','/opt/mocha-mesa-candidate/lib/arm-linux-gnueabihf/dri'),
                        (libexec/'mocha-tablet-current','/usr/local/libexec/mocha-tablet-release')):
        if not link.is_symlink():link.symlink_to(target)
    root_cmd=[str(proot),'-r',str(root),'-q',str(qemu),'-b','/dev',
              '-b',str(adapter.resolve())+':/opt/mocha-desktop-src',
              '-b',str(video.resolve())+':/opt/mocha-video','-w','/','/usr/bin/python3']
    root_env=dict(os.environ,PROOT_NO_SECCOMP='1')
    subprocess.run(root_cmd+['/opt/mocha-desktop-src/tools/install-mpvpaper-runtime.py',
                            '--binary','/opt/mocha-video/mpvpaper/build/mpvpaper',
                            '--holder','/opt/mocha-video/mpvpaper/build/mpvpaper-holder',
                            '--decoder-runtime','/opt/mocha-video/runtime',
                            '--backup-dir','/tmp/mocha-install-backups'],env=root_env,check=True)
    share=root/'usr/local/share/mocha';share.mkdir(parents=True,exist_ok=True)
    nyx=share/'nyxuri'
    shutil.copytree(upstream/'nyxuri',nyx,ignore=shutil.ignore_patterns('.git'),symlinks=True)
    (nyx/'MOCHA-UPSTREAM-COMMIT').write_text(NYXURI+'\n')
    plugins=share/'nyxuri-official-plugins/official-plugins-main'
    shutil.copytree(upstream/'official-plugins',plugins,ignore=shutil.ignore_patterns('.git'),symlinks=True)
    plugin=plugins/'mpvpaper'
    patch=adapter/'patches/vde/0007-noctalia-fullscreen-decoder-release.patch'
    subprocess.run(['patch','--batch','--forward','-p1','-i',str(patch.resolve())],cwd=plugin,check=True)
    home=root/'home/mocha';home.mkdir(parents=True,exist_ok=True)
    os.chown(home,1000,1000)
    graphics='''export MESA_LOADER_DRIVER_OVERRIDE=tegra
export MESA_DRI_DRIVER_OVERRIDE=tegra
export LD_LIBRARY_PATH=/opt/mocha-mesa-candidate/lib/arm-linux-gnueabihf
export LIBGL_DRIVERS_PATH=/opt/mocha-mesa-candidate/lib/arm-linux-gnueabihf/dri
export GBM_BACKENDS_PATH=/opt/mocha-mesa-candidate/lib/arm-linux-gnueabihf/gbm
export MOCHA_DOCK_LINEAR_ICONS=1
export GTK_IM_MODULE=fcitx5
export QT_IM_MODULE=fcitx
export XMODIFIERS=@im=fcitx
export SDL_IM_MODULE=fcitx
'''
    profile=home/'.profile';original=profile.read_text() if profile.exists() else ''
    if '# Mocha graphical session' not in original:
        profile.write_text(original+'\n# Mocha graphical session\n'+graphics+
                           'if [ "$(tty)" = /dev/tty1 ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then\n'
                           '  export XDG_SESSION_TYPE=wayland\n  exec /usr/local/bin/niri --session\nfi\n')
    envdir=home/'.config/environment.d';envdir.mkdir(parents=True,exist_ok=True)
    (envdir/'70-mocha-gpu.conf').write_text(graphics.replace('export ',''))
    system=root/'etc/systemd/system';system.mkdir(parents=True,exist_ok=True)
    modules=root/'etc/modules-load.d';modules.mkdir(parents=True,exist_ok=True)
    (modules/'mocha-input.conf').write_text('uhid\nuinput\n')
    hardware='''[Unit]
Description=Mocha GPU and backlight before desktop
After=local-fs.target systemd-udev-trigger.service
Before=getty@tty1.service
[Service]
Type=oneshot
ExecStart=/sbin/modprobe nouveau
ExecStart=/sbin/modprobe mocha_miui_backlight
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
'''
    (system/'mocha-desktop-hardware.service').write_text(hardware)
    for name in ('mocha-backlight-access.service','mocha-touch-key-lights.service'):
        shutil.copy2(adapter/'tablet'/name,system/name)
    system_wants=system/'multi-user.target.wants';system_wants.mkdir(exist_ok=True)
    for name in ('mocha-desktop-hardware.service','mocha-backlight-access.service','mocha-touch-key-lights.service'):
        link=system_wants/name
        if not link.is_symlink():link.symlink_to('../'+name)
    bluetooth=system/'bluetooth.target.wants';bluetooth.mkdir(exist_ok=True)
    if not (bluetooth/'bluetooth.service').is_symlink():
        (bluetooth/'bluetooth.service').symlink_to('/usr/lib/systemd/system/bluetooth.service')
    getty_wants=system/'getty.target.wants';getty_wants.mkdir(exist_ok=True)
    if not (getty_wants/'getty@tty1.service').is_symlink():
        (getty_wants/'getty@tty1.service').symlink_to('/usr/lib/systemd/system/getty@.service')
    getty=system/'getty@tty1.service.d';getty.mkdir(exist_ok=True)
    (getty/'mocha.conf').write_text('[Unit]\nRequires=mocha-desktop-hardware.service\nAfter=mocha-desktop-hardware.service\n'
                                    '[Service]\nExecStart=\nExecStart=-/sbin/agetty --autologin mocha --noreset --noclear %I linux\n')
    pictures=home/'Pictures';pictures.mkdir(exist_ok=True)
    wallpapers=data/'wallpapers';wallpapers.mkdir(parents=True,exist_ok=True);os.chown(wallpapers,1000,1000)
    link=pictures/'Wallpapers'
    if not link.exists() and not link.is_symlink():link.symlink_to('/srv/mocha-data/wallpapers')
    shutil.copy2(adapter/'assets/wallpapers/ymcymcymc-vde-cavlc-gop30-1536w-30fps.mp4',wallpapers)
    env=dict(os.environ,PROOT_NO_SECCOMP='1',HOME='/home/mocha',PATH='/usr/local/bin:/usr/bin:/bin',
             XDG_CONFIG_HOME='/home/mocha/.config')
    cmd=[str(proot),'-r',str(root),'-q',str(qemu),'-i','1000:1000','-b','/dev',
         '-b',str(adapter.resolve())+':/opt/mocha-desktop-src',
         '-b',str(data.resolve())+':/srv/mocha-data','-w','/home/mocha','/usr/bin/python3']
    subprocess.run(cmd+['/opt/mocha-desktop-src/tools/install-nyxuri.py','--source','/usr/local/share/mocha/nyxuri',
                        '--adapter','/opt/mocha-desktop-src','--offline'],env=env,check=True)
    subprocess.run(['python3',str(adapter/'tools/install-nyxuri-wallpaper-bridge.py'),
                    '--config',str(home/'.config/noctalia'),'--plugin',str(plugin),
                    '--patches',str(adapter/'patches/vde'),'--backup',str(root/'tmp/mocha-wallpaper-bridge-backup')],check=True)
    fcitx=home/'.config/fcitx5';fcitx.mkdir(parents=True,exist_ok=True)
    shutil.copy2(adapter/'tablet/fcitx5-profile',fcitx/'profile')
    shutil.copy2(adapter/'tablet/fcitx5-config',fcitx/'config')
    units=home/'.config/systemd/user';units.mkdir(parents=True,exist_ok=True)
    wants=units/'graphical-session.target.wants';wants.mkdir(exist_ok=True)
    for name in ('mocha-buttons.service','mocha-input-method.service','mocha-keyboard.service'):
        shutil.copy2(adapter/'tablet'/name,units/name)
        link=wants/name
        if not link.is_symlink():link.symlink_to('../'+name)
    for p in [home,*home.rglob('*')]:os.chown(p,1000,1000,follow_symlinks=False)
    print('SOURCE_DESKTOP_CONFIGURED; boot integration and device validation remain')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','data','components','adapter','upstream','proot','qemu','video'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if not hasattr(os,'geteuid') or os.geteuid()!=0:p.error('Linux root required')
    try:install(a.root,a.data,a.components,a.adapter,a.upstream,a.proot,a.qemu,a.video)
    except (OSError,ValueError,subprocess.SubprocessError) as exc:p.error(str(exc))


if __name__=='__main__':main()
