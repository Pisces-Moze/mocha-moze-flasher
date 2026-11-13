#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build a read-only RAM installer from the generated Debian rootfs."""
import argparse
import base64
import os
from pathlib import Path
import shlex
import subprocess
import tempfile


def build(root,debian,output,work,qemu):
    root,debian,output,work,qemu=map(lambda p:Path(p).resolve(),(root,debian,output,work,qemu))
    if output.exists() or work.exists():raise ValueError('output and work must be new')
    here=Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='mocha-ram-build-') as temp:
        folder=Path(temp)
        key=folder/'placeholder.pub'
        kind=b'ssh-ed25519';pub=bytes(32)
        blob=len(kind).to_bytes(4,'big')+kind+len(pub).to_bytes(4,'big')+pub
        key.write_text('ssh-ed25519 '+base64.b64encode(blob).decode()+' placeholder\n')
        # The temporary key generated here is stripped from the final RAM image.
        shim=folder/'dropbearkey'
        shim.write_text('#!/bin/sh\nexec '+shlex.quote(str(qemu))+' -L '+shlex.quote(str(root))+' '+
                        shlex.quote(str(root/'usr/bin/dropbearkey'))+' "$@"\n')
        shim.chmod(0o755)
        env=dict(os.environ,PATH=str(folder)+os.pathsep+os.environ.get('PATH',''))
        base=Path(temp)/'maintenance.cpio.gz'
        subprocess.run(['bash',str(debian/'tools/build-initramfs.sh'),str(root),str(key),str(base),'install'],env=env,check=True)
        subprocess.run(['bash',str(here/'build-distribution-ram.sh'),str(base),str(work),str(output)],check=True)
    print('SOURCE_RAM_INSTALLER_BUILT; device verification required')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','debian','output','work','qemu'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if not hasattr(os,'geteuid') or os.geteuid()!=0:p.error('Linux root required')
    try:build(a.root,a.debian,a.output,a.work,a.qemu)
    except (OSError,ValueError,subprocess.SubprocessError) as exc:p.error(str(exc))


if __name__=='__main__':main()
