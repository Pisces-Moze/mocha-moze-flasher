#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

spec=importlib.util.spec_from_file_location('desktop_deps',Path(__file__).with_name('install-source-desktop-deps.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class DependencyStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        base=Path(self.tmp.name);self.root=base/'root'
        for name in ('etc','usr/bin','usr/sbin'):(self.root/name).mkdir(parents=True,exist_ok=True)
        (self.root/'etc/mocha-internal-debian').touch();(self.root/'.mocha-source-rootfs-build').touch()
        for name in ('apt-get','dpkg'):(self.root/'usr/bin'/name).touch()
        self.proot=base/'proot';self.qemu=base/'qemu'
        for p in (self.proot,self.qemu):p.write_text('fixture');p.chmod(0o755)

    def test_runs_audit_update_install_audit_check_and_removes_policy(self):
        with mock.patch.object(module.os,'access',return_value=True), \
             mock.patch.object(module.subprocess,'run',return_value=SimpleNamespace(stdout='')) as run:
            module.install(self.root,self.proot,self.qemu)
        commands=[call.args[0] for call in run.call_args_list]
        self.assertEqual(len(commands),5)
        self.assertIn('dbus-user-session',commands[2]);self.assertIn('dbus-daemon',commands[2])
        self.assertFalse((self.root/'usr/sbin/policy-rc.d').exists())

    def test_failure_removes_temporary_policy(self):
        with mock.patch.object(module.os,'access',return_value=True), \
             mock.patch.object(module.subprocess,'run',side_effect=subprocess.CalledProcessError(1,'apt')):
            with self.assertRaises(subprocess.CalledProcessError):module.install(self.root,self.proot,self.qemu)
        self.assertFalse((self.root/'usr/sbin/policy-rc.d').exists())

    def test_existing_policy_is_never_replaced(self):
        policy=self.root/'usr/sbin/policy-rc.d';policy.write_text('existing')
        with mock.patch.object(module.os,'access',return_value=True):
            with self.assertRaisesRegex(ValueError,'existing service policy'):module.install(self.root,self.proot,self.qemu)
        self.assertEqual(policy.read_text(),'existing')

    def test_dpkg_audit_output_blocks_install(self):
        with mock.patch.object(module.os,'access',return_value=True), \
             mock.patch.object(module.subprocess,'run',return_value=SimpleNamespace(stdout='unconfigured package')) as run:
            with self.assertRaisesRegex(RuntimeError,'unfinished packages'):module.install(self.root,self.proot,self.qemu)
        self.assertEqual(run.call_count,1);self.assertFalse((self.root/'usr/sbin/policy-rc.d').exists())


if __name__=='__main__':unittest.main()
