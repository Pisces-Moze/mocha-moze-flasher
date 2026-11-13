#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Install Debian desktop dependencies into a marked, offline ARM rootfs.

The caller provides a working PRoot/QEMU and configured Debian mirror.
This stage does not build Niri/Noctalia, assemble an image, or access a tablet.
"""
import argparse
import os
from pathlib import Path
import subprocess

PACKAGES = '''
locales sudo dbus dbus-daemon dbus-user-session polkitd seatd libseat1 libinput10 libdrm2
libgbm1 libegl1 libgles2 libwayland-client0 libwayland-cursor0 libwayland-egl1
libxkbcommon0 libudev1 libpango-1.0-0 libpangocairo-1.0-0 libcairo2
libfontconfig1 libfreetype6 libglib2.0-0t64 libsecret-1-0 libsodium23
libpipewire-0.3-0t64 libwireplumber-0.5-0 libqalculate23 libpam0g libxml2
libical3t64 libtomlplusplus3t64 libmd4c0 libwebp7 libwebpdemux2 libjxl0.11
libsndfile1 libsdbus-c++2 libdisplay-info2 librsvg2-2 network-manager bluez
pipewire wireplumber pipewire-pulse pipewire-alsa libspa-0.2-bluetooth alsa-utils firefox-esr mpv
ffmpeg gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-gl
gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav
python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1 gir1.2-gstreamer-1.0 fcitx5 fcitx5-pinyin fcitx5-frontend-gtk3
fonts-noto-core fonts-noto-cjk fonts-noto-color-emoji fonts-dejavu-core
xdg-desktop-portal xdg-desktop-portal-gtk xdg-utils upower brightnessctl
xwayland foot curl ca-certificates socat slurp wf-recorder inotify-tools grim wtype wl-clipboard playerctl
'''.split()


def install(root, proot, qemu):
    root,proot,qemu=map(Path,(root,proot,qemu))
    if root.is_symlink() or not root.is_dir() or root.resolve()==Path('/'):
        raise ValueError('root must be a separate real directory')
    root=root.resolve()
    for rel in ('etc','usr','usr/bin','usr/sbin'):
        if (root/rel).is_symlink():raise ValueError('symlinked rootfs directory: '+rel)
    marker=root/'.mocha-source-rootfs-build'
    if marker.is_symlink() or not marker.is_file():
        raise ValueError('missing source rootfs build marker')
    for rel in ('etc/mocha-internal-debian','usr/bin/apt-get','usr/bin/dpkg'):
        if not (root/rel).is_file():raise ValueError('incomplete rootfs: '+rel)
    if not proot.is_file() or not os.access(proot,os.X_OK) or not qemu.is_file() or not os.access(qemu,os.X_OK):
        raise ValueError('working PRoot and QEMU executables are required')
    policy=root/'usr/sbin/policy-rc.d'
    if policy.parent.is_symlink() or policy.is_symlink():
        raise ValueError('refusing to overwrite existing service policy')
    policy.parent.mkdir(parents=True,exist_ok=True)
    if policy.exists():
        if policy.read_text()!='#!/bin/sh\nexit 101\n':raise ValueError('refusing to overwrite existing service policy')
    else:
        with policy.open('x',encoding='ascii') as stream:stream.write('#!/bin/sh\nexit 101\n')
        policy.chmod(0o755)
    env=dict(os.environ,PROOT_NO_SECCOMP='1',DEBIAN_FRONTEND='noninteractive')
    prefix=[str(proot.resolve()),'-r',str(root),'-q',str(qemu.resolve()),'-b','/dev',
            '-b','/etc/resolv.conf','-w','/']
    def check_dpkg():
        result=subprocess.run(prefix+['/usr/bin/dpkg','--audit'],env=env,check=True,
                              capture_output=True,text=True)
        if result.stdout.strip():raise RuntimeError('rootfs dpkg audit reports unfinished packages')
    try:
        apt=prefix+['/usr/bin/apt-get','-o','APT::Sandbox::User=root']
        subprocess.run(apt+['update'],env=env,check=True)
        # A cross-architecture second stage can leave D-Bus or its dependencies
        # unpacked but not configured. Repair that state before installing UI.
        subprocess.run(apt+['-y','-f','install'],env=env,check=True)
        subprocess.run(prefix+['/usr/bin/dpkg','--configure','-a'],env=env,check=True)
        check_dpkg()
        subprocess.run(apt+['-y','--no-install-recommends','install',*PACKAGES],env=env,check=True)
        check_dpkg()
        subprocess.run(prefix+['/usr/bin/apt-get','check'],env=env,check=True)
    finally:
        policy.unlink(missing_ok=True)
    print('DESKTOP_DEPENDENCIES_INSTALLED; desktop build and image acceptance remain')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--proot',type=Path,required=True)
    p.add_argument('--qemu',type=Path,required=True)
    a=p.parse_args(argv)
    if not hasattr(os,'geteuid') or os.geteuid()!=0:p.error('Linux root required')
    try:install(a.root,a.proot,a.qemu)
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:p.error(str(exc))
    return 0


if __name__=='__main__':raise SystemExit(main())
