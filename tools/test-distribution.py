#!/usr/bin/env python3
"""Safety boundaries for the new destructive installer; never touches hardware."""
import gzip
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from ram_archive import read_newc,write_newc,regular,personalize

HERE=Path(__file__).resolve().parent


def load(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class ArchiveTests(unittest.TestCase):
    def test_new_bundle_rejects_old_ram_installer(self):
        builder=load('build_distribution_ram_check','build-distribution.py')
        with tempfile.TemporaryDirectory() as directory:
            archive=Path(directory)/'installer.cpio.gz'
            archive.write_bytes(gzip.compress(write_newc([regular('init',b'old init')])))
            with self.assertRaisesRegex(RuntimeError,'lacks target Wi-Fi capture'):
                builder.check_installer_wifi_capture(archive)
            entries=[regular('usr/local/libexec/distribution-ram.py',b'def capture_wifi(args): pass'),
                     regular('usr/local/libexec/extract-board-data.py',b'def extract(a, b): pass')]
            archive.write_bytes(gzip.compress(write_newc(entries)))
            builder.check_installer_wifi_capture(archive)

    @unittest.skipUnless(sys.platform == 'linux','RAM installer requires Linux')
    def test_capture_reads_before_unmount_and_never_writes_the_source(self):
        ram=load('distribution_ram_capture','distribution-ram.py')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); mount=root/'mounted'; mount.mkdir()
            data=mount/'usr/lib/firmware/brcm/brcmfmac4354-sdio.nvidia,mocha.txt'
            data.parent.mkdir(parents=True)
            original=b'sromrev=11\nboardrev=1\nboardtype=2\nmacaddr=02:11:22:33:44:55\n'
            data.write_bytes(original)
            temporary=root/'temporary';temporary.mkdir()
            current={'cid':'device-a','gpt_sha256':'original-gpt'}
            def local_path(value):
                return mount if str(value)=='/mnt/mocha-source-app' else Path(value)
            with mock.patch.object(ram,'WIFI_CAPTURE',root/'capture'), \
                 mock.patch.object(ram,'STATE',root/'state.json'), \
                 mock.patch.object(ram,'Path',side_effect=local_path), \
                 mock.patch.object(ram,'plan',return_value=current), \
                 mock.patch.object(ram.tempfile,'mkdtemp',return_value=str(temporary)), \
                 mock.patch.object(ram,'run') as command:
                ram.capture_wifi(None)
                self.assertEqual(command.call_args_list[0].args[:4],('mount','-t','ext4','-o'))
                self.assertEqual(command.call_args_list[-1].args[0],'umount')
                self.assertEqual(ram.captured_wifi(current).read_bytes(),original)
                self.assertEqual(data.read_bytes(),original)
                self.assertFalse(ram.STATE.exists())

    @unittest.skipUnless(sys.platform == 'linux','RAM installer requires Linux')
    def test_target_wifi_capture_is_bound_to_device_and_original_gpt(self):
        ram=load('distribution_ram_wifi','distribution-ram.py')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); data=root/'brcm/brcmfmac4354-sdio.nvidia,mocha.txt'
            data.parent.mkdir(); data.write_bytes(b'sromrev=11\nboardrev=1\nboardtype=2\n')
            import hashlib
            metadata={'cid':'device-a','gpt_sha256':'original-gpt',
                      'sha256':hashlib.sha256(data.read_bytes()).hexdigest()}
            (root/'device.json').write_text(json.dumps(metadata))
            with mock.patch.object(ram,'WIFI_CAPTURE',root):
                self.assertEqual(ram.captured_wifi(metadata),data)
                with self.assertRaisesRegex(RuntimeError,'another device'):
                    ram.captured_wifi({'cid':'device-b','gpt_sha256':'original-gpt'})
                data.write_bytes(b'tampered')
                with self.assertRaisesRegex(RuntimeError,'verification'):
                    ram.captured_wifi(metadata)

    @unittest.skipUnless(sys.platform == 'linux','RAM installer requires Linux')
    def test_prepare_stops_before_disk_writes_without_target_wifi_data(self):
        ram=load('distribution_ram_prepare','distribution-ram.py')
        current={'cid':'device-a','gpt_sha256':'original-gpt'}
        args=type('Args',(),{'cid':'device-a','gpt_sha256':'original-gpt','erase':'ERASE_APP_UDA'})()
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(ram,'STATE',Path(directory)/'state.json'), \
             mock.patch.object(ram,'plan',return_value=current), \
             mock.patch.object(ram,'captured_wifi',side_effect=RuntimeError('missing')), \
             mock.patch.object(ram,'writable') as writable:
            with self.assertRaisesRegex(RuntimeError,'missing'):ram.prepare(args)
            writable.assert_not_called()
            self.assertFalse(ram.STATE.exists())

    @unittest.skipUnless(sys.platform == 'linux','RAM installer requires Linux')
    def test_prepare_retains_original_gpt_for_wifi_restoration(self):
        ram=load('distribution_ram_state','distribution-ram.py')
        current={'cid':'device-a','gpt_sha256':'original-gpt'}
        args=type('Args',(),{'cid':'device-a','gpt_sha256':'original-gpt','erase':'ERASE_APP_UDA'})()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); disk=root/'disk'; disk.touch(); sysfs=root/'sysfs'; sysfs.mkdir()
            for number,_,start,sectors in ram.layout.NEW:
                node=sysfs/f'mmcblk0p{number}';node.mkdir()
                (node/'start').write_text(str(start));(node/'size').write_text(str(sectors))
            def local_path(value):
                return sysfs if str(value)=='/sys/class/block' else Path(value)
            with mock.patch.object(ram,'STATE',root/'state.json'), \
                 mock.patch.object(ram,'DISK',str(disk)), \
                 mock.patch.object(ram,'Path',side_effect=local_path), \
                 mock.patch.object(ram,'plan',return_value=current), \
                 mock.patch.object(ram,'captured_wifi'), \
                 mock.patch.object(ram,'writable'), mock.patch.object(ram,'readonly'), \
                 mock.patch.object(ram,'run'), \
                 mock.patch.object(ram.layout,'read_gpt',return_value=([(None,[0]*13)],b'unchanged')), \
                 mock.patch.object(ram.layout,'replace_bounds',return_value=b'unchanged'):
                ram.prepare(args)
                state=json.loads(ram.STATE.read_text())
                self.assertEqual(state['phase'],'prepared')
                self.assertEqual(state['source_gpt_sha256'],'original-gpt')

    def test_missing_build_tools_fail_before_subprocess(self):
        builder=load('build_distribution_preflight','build-distribution.py')
        with mock.patch.object(builder.shutil,'which',return_value=None), \
             mock.patch.object(builder.subprocess,'run') as command:
            with self.assertRaisesRegex(RuntimeError,'missing required tools: rsync'):
                builder.check_build_tools()
            command.assert_not_called()

    def test_personalization_preserves_links_and_replaces_key(self):
        entries=[regular('root/.ssh/authorized_keys',b'OLD-DEVELOPER-KEY\n',ino=1),
                 regular('bin/sh',b'busybox',0o120777,2)]
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.gz';target=Path(directory)/'target.gz'
            source.write_bytes(gzip.compress(write_newc(entries)))
            personalize(source,target,b'ssh-ed25519 TEST install\n')
            result=read_newc(gzip.decompress(target.read_bytes()))
            self.assertNotIn(b'OLD-DEVELOPER-KEY',gzip.decompress(target.read_bytes()))
            self.assertEqual(result[0][2],b'ssh-ed25519 TEST install\n')
            self.assertEqual(result[1][0],entries[1][0])
            self.assertEqual(result[1][1][:11],entries[1][1][:11])
            self.assertEqual(result[1][2],entries[1][2])

    def test_escaping_archive_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unsafe'):
            read_newc(write_newc([regular('../etc/shadow',b'x')]))

    def test_candidate_bundle_rejected_before_payload_io(self):
        flash=load('flash_distribution','flash-distribution.py')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'bundle.json').write_text(json.dumps({'schema':1,'device':'xiaomi-mocha-16gb','app_bytes':3*1024**3,'release_state':'candidate'}))
            with self.assertRaisesRegex(ValueError,'acceptance gate'):flash.verify_bundle(root)

    def test_windows_install_entry_does_not_bypass_candidate_gate(self):
        launcher=Path(__file__).with_name('Install-Mocha.cmd').read_text()
        self.assertIn('--install --erase APP_UDA',launcher)
        self.assertNotIn('--allow-candidate',launcher)


@unittest.skipUnless(hasattr(os,'geteuid') and os.geteuid()==0,'Linux root staging-copy test')
class CopyTests(unittest.TestCase):
    def test_sanitization_drops_identity_models_original_and_retains_login_profile(self):
        builder=load('prepare_distribution','prepare-distribution.py')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'APP';data=Path(directory)/'DATA'
            source=Path(directory)/'SOURCE';source.mkdir()
            home=data/'codex-debian-desktop/home/mocha'
            for path in (root/'etc/systemd/system',root/'etc/ssh',root/'usr/local/libexec',
                         home/'.config/fcitx5',home/'.local/share/fcitx5',home/'.local/bin',home/'Pictures/Wallpapers'):
                path.mkdir(parents=True)
            (root/'.mocha-export-copy').write_text('OFFLINE_COPY_NOT_LIVE')
            (root/'etc/mocha-internal-debian').touch()
            (root/'etc/passwd').write_text('root:x:0:0:root:/root:/bin/bash\nmocha:x:1000:1000::/srv/mocha-data/codex-debian-desktop/home/mocha:/bin/bash\n')
            (root/'etc/shadow').write_text('root:SECRET:0:0:99999:7:::\nmocha:SECRET:0:0:99999:7:::\n')
            (root/'etc/fstab').write_text('UUID=old / ext4 defaults 0 1\nUUID=private /srv/mocha-data ext4 defaults 0 2\n')
            (root/'etc/ssh/ssh_host_ed25519_key').write_text('PRIVATE')
            (root/'etc/hostname').write_text('prototype-source-host\n')
            (root/'etc/hosts').write_text('127.0.1.1 prototype-source-host\n')
            (root/'etc/machine-info').write_text('PRETTY_HOSTNAME=prototype-source-host\n')
            (root/'var/lib/upower').mkdir(parents=True)
            (root/'var/lib/upower/history-private-device.dat').write_text('PRIVATE DEVICE')
            old_oobe=root/'var/lib/mocha-oobe';old_oobe.mkdir(parents=True)
            for name in ('request.json','progress.json','handoff-ready.json','complete.json'):
                (old_oobe/name).write_text('old-owner-private-state')
            backups=root/'var/backups/mocha-private';backups.mkdir(parents=True)
            (backups/'shadow.before').write_text('old-owner-secret-password-hash')
            wants=root/'etc/systemd/system/multi-user.target.wants';wants.mkdir()
            (wants/'ssh.service').symlink_to('/lib/systemd/system/ssh.service')
            (wants/'mocha-oobe-session.service').symlink_to('../mocha-oobe-session.service')
            (root/'etc/systemd/system/mocha-oobe-session.service').write_text('old unit')
            gate=root/'etc/systemd/system/getty@tty1.service.d/00-first-run.conf'
            gate.parent.mkdir();gate.write_text('old gate')
            (root/'usr/local/libexec/mocha-oobe-flow').write_text('old code')
            sockets=root/'etc/systemd/system/sockets.target.wants';sockets.mkdir()
            (sockets/'ssh.socket').symlink_to('/lib/systemd/system/ssh.socket')
            prefix=data/'codex-debian-desktop'
            (prefix/'mocha-moze-llm/models').mkdir(parents=True)
            (prefix/'mocha-moze-llm/evidence').mkdir()
            (prefix/'mocha-moze-llm/models/model.bin').write_bytes(b'weight')
            (prefix/'mocha-moze-llm/evidence/run0.txt').write_text('prompt')
            (prefix/'llm-coherent-runtime-20261026/lib').mkdir(parents=True)
            (prefix/'llm-coherent-runtime-20261026/lib/libucuda.so.1.0.0').write_bytes(b'engine')
            setup=prefix/'installed-setup-20261017';setup.mkdir()
            (setup/'bluetooth-scan-private.txt').write_text('PRIVATE DEVICE')
            session_backup=setup/'firefox-session-backup-20261023'
            session_backup.mkdir()
            (session_backup/'sessionstore.jsonlz4').write_bytes(b'PRIVATE SESSION')
            diagnostic_profile=setup/'firefox-render-diagnostic-20261023'
            diagnostic_profile.mkdir()
            (diagnostic_profile/'cookies.sqlite').write_bytes(b'PRIVATE COOKIES')
            (setup/'recovery.jsonlz4').write_bytes(b'PRIVATE RECOVERY')
            (setup/'mocha-qwen-packed-engine').write_bytes(b'engine')
            (setup/'libcuda-desktop-runtime.so.1').write_bytes(b'keep-desktop-driver')
            (home/'.bash_profile').write_text('systemctl --user start niri.service\n')
            (home/'private.txt').write_text('PRIVATE')
            plugin=home/'.config/noctalia/plugin-settings.json';plugin.parent.mkdir(exist_ok=True)
            plugin.write_text(json.dumps({'apiKey':'PRIVATE-API-KEY','nested':{'access_token':'PRIVATE-TOKEN'},'opacity':0.8,'theme':'dark','hasApiKey':True}))
            (home/'Pictures/Wallpapers/ymcymcymc.mp4').write_bytes(b'original')
            (home/'Pictures/Wallpapers/ymcymcymc-gop30.mp4').write_bytes(b'keep')
            (home/'Pictures/Wallpapers/model.gguf').write_bytes(b'weight')
            builder.clean_tree(root,data,source)
            self.assertFalse((root/'usr/local/share/mocha-oobe').exists())
            self.assertTrue((home/'.bash_profile').is_file())
            self.assertFalse((home/'private.txt').exists())
            self.assertEqual(json.loads(plugin.read_text()),{'apiKey':'','nested':{'access_token':''},'opacity':0.8,'theme':'dark','hasApiKey':True})
            self.assertFalse((home/'Pictures/Wallpapers/ymcymcymc.mp4').exists())
            self.assertTrue((home/'Pictures/Wallpapers/ymcymcymc-gop30.mp4').is_file())
            self.assertFalse((home/'Pictures/Wallpapers/model.gguf').exists())
            self.assertFalse((root/'etc/ssh/ssh_host_ed25519_key').exists())
            self.assertNotIn('SECRET',(root/'etc/shadow').read_text())
            self.assertIn('LABEL=mocha-data',(root/'etc/fstab').read_text())
            self.assertFalse((root/'var/lib/mocha-oobe').exists())
            self.assertEqual(list((root/'var/lib/upower').iterdir()),[])
            self.assertFalse((setup/'bluetooth-scan-private.txt').exists())
            self.assertFalse((wants/'mocha-oobe-session.service').is_symlink())
            self.assertFalse((root/'etc/systemd/system/mocha-oobe-session.service').exists())
            self.assertFalse(gate.exists())
            self.assertFalse((root/'usr/local/libexec/mocha-oobe-flow').exists())
            self.assertEqual(list((root/'var/backups').iterdir()),[])
            login=json.loads((root/'etc/mocha/default-login.json').read_text())
            self.assertEqual(login['username'],'mocha')
            shadow=(root/'etc/shadow').read_text().splitlines()
            self.assertTrue(next(x for x in shadow if x.startswith('root:')).startswith('root:!:'))
            password=next(x for x in shadow if x.startswith('mocha:')).split(':')[1]
            self.assertTrue(password.startswith('$6$'))
            check=subprocess.run(['openssl','passwd','-6','-salt',password.split('$')[2],'-stdin'],
                                 input='mocha\n',text=True,capture_output=True,check=True)
            self.assertEqual(check.stdout.strip(),password)
            getty=(root/'etc/systemd/system/getty@tty1.service.d/10-mocha-autologin.conf').read_text()
            self.assertIn('--autologin mocha',getty)
            self.assertTrue((root/'etc/systemd/system/getty.target.wants/getty@tty1.service').is_symlink())
            self.assertFalse((prefix/'mocha-moze-llm').exists())
            self.assertFalse((prefix/'llm-coherent-runtime-20261026').exists())
            self.assertFalse((setup/'mocha-qwen-packed-engine').exists())
            self.assertFalse(session_backup.exists())
            self.assertFalse(diagnostic_profile.exists())
            self.assertFalse((setup/'recovery.jsonlz4').exists())
            self.assertTrue((setup/'libcuda-desktop-runtime.so.1').is_file())
            self.assertEqual((root/'etc/hostname').read_text(),'mocha\n')
            hosts=(root/'etc/hosts').read_text()
            self.assertIn('127.0.1.1 mocha',hosts)
            self.assertNotIn('prototype-source-host',hosts)
            self.assertEqual((root/'etc/machine-info').read_text(),'')
            self.assertFalse((wants/'ssh.service').is_symlink() or (wants/'ssh.service').exists())
            self.assertFalse((sockets/'ssh.socket').is_symlink() or (sockets/'ssh.socket').exists())


if __name__=='__main__':unittest.main()
