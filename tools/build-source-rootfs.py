#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build a Debian ARM rootfs with PRoot, without mounting host filesystems."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

BASE='systemd-sysv,openssh-server,dropbear-bin,busybox-static,kmod,udev,iproute2,iputils-ping,ca-certificates,network-manager,sudo'


def build(root,kernel,debian,proot,qemu,mirror):
    root,kernel,debian,proot,qemu=map(lambda p:Path(p).resolve(),(root,kernel,debian,proot,qemu))
    if root.exists():raise ValueError('rootfs output already exists')
    if not mirror.startswith('https://'):raise ValueError('Debian mirror must use HTTPS')
    subprocess.run(['debootstrap','--foreign','--arch=armhf','--variant=minbase',
                    '--include='+BASE,'trixie',str(root),mirror],check=True)
    env=dict(os.environ,PROOT_NO_SECCOMP='1',DEBOOTSTRAP_DIR='/debootstrap',DEBIAN_FRONTEND='noninteractive')
    cmd=[str(proot),'-r',str(root),'-q',str(qemu),'-b','/dev','-b','/etc/resolv.conf','-w','/']
    subprocess.run(cmd+['/bin/sh','/debootstrap/debootstrap','--second-stage'],env=env,check=True)
    (root/'etc/apt/sources.list').write_text('deb '+mirror+' trixie main\n')
    (root/'etc/hostname').write_text('mocha\n')
    (root/'etc/hosts').write_text('127.0.0.1 localhost\n127.0.1.1 mocha\n')
    (root/'etc/fstab').write_text('LABEL=mocha-debian / ext4 defaults 0 1\nLABEL=mocha-data /srv/mocha-data ext4 defaults,nofail 0 2\n')
    (root/'etc/mocha-internal-debian').touch()
    (root/'srv/mocha-data').mkdir(parents=True,exist_ok=True)
    subprocess.run(cmd+['/usr/sbin/useradd','-m','-s','/bin/bash','mocha'],env=env,check=True)
    groups={line.split(':',1)[0] for line in (root/'etc/group').read_text().splitlines()}
    selected=[name for name in ('sudo','audio','video','input','render') if name in groups]
    if selected:subprocess.run(cmd+['/usr/sbin/usermod','-aG',','.join(selected),'mocha'],env=env,check=True)
    subprocess.run(cmd+['/usr/sbin/chpasswd'],input='mocha:mocha\n',text=True,env=env,check=True)
    release=(kernel/'include/config/kernel.release').read_text().strip()
    (root/'boot').mkdir(exist_ok=True)
    for src,dst in (('uImage','uImage-desktop'),('mocha.dtb','mocha-desktop.dtb')):
        shutil.copy2(kernel/src,root/'boot'/dst)
    modules=root/'usr/lib/modules'/release
    shutil.copytree(kernel/'modules/lib/modules'/release,modules,symlinks=True)
    if (modules/'build').is_symlink():(modules/'build').unlink()
    subprocess.run(['depmod','-b',str(root),release],check=True)
    # The emmc initramfs does not embed this placeholder public key.
    with tempfile.NamedTemporaryFile() as key:
        subprocess.run(['bash',str(debian/'tools/build-initramfs.sh'),str(root),key.name,
                        str(root/'boot/initramfs.cpio.gz'),'emmc'],check=True)
    for service in ('NetworkManager.service',):
        wants=root/'etc/systemd/system/multi-user.target.wants';wants.mkdir(parents=True,exist_ok=True)
        (wants/service).symlink_to('/usr/lib/systemd/system/'+service)
    (root/'.mocha-source-rootfs-build').touch()
    print('SOURCE_ROOTFS_BUILT; desktop and firmware remain')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','kernel','debian','proot','qemu'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--mirror',default='https://mirrors.tuna.tsinghua.edu.cn/debian')
    a=p.parse_args()
    if not hasattr(os,'geteuid') or os.geteuid()!=0:p.error('Linux root required')
    try:build(a.root,a.kernel,a.debian,a.proot,a.qemu,a.mirror)
    except (OSError,ValueError,subprocess.SubprocessError) as exc:p.error(str(exc))


if __name__=='__main__':main()
