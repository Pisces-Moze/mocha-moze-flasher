#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec=importlib.util.spec_from_file_location('source_dist',Path(__file__).with_name('build-source-distribution.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class SourcePackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.stage=self.base/'stage';self.stage.mkdir();self.out=self.base/'out'
        (self.stage/'source-stage.json').write_text(json.dumps({'schema':1,'stage':'source-desktop-copy','ready_to_flash':False}))
        self.inputs={}
        for name,content in {'loader':b'ANDROID!x','lnx':b'ANDROID!y','ram_kernel':bytes.fromhex('27051956'),
                             'ram_dtb':bytes.fromhex('d00dfeed'),'installer':b'ram'}.items():
            path=self.base/name;path.write_bytes(content);self.inputs[name]=path
        self.builder=mock.Mock();self.audit=mock.Mock();self.audit.inspect.return_value={'checks_passed':True,'issues':[]}

    def call_validate(self):
        with mock.patch.object(module,'load',side_effect=[self.builder,self.audit]), \
             mock.patch.object(module.shutil,'disk_usage',return_value=mock.Mock(free=20*1024**3)):
            return module.validate(self.stage,self.out,self.inputs)

    def test_checks_ram_capture_and_desktop_before_output(self):
        self.call_validate()
        self.builder.check_installer_wifi_capture.assert_called_once_with(self.inputs['installer'])
        self.audit.inspect.assert_called_once_with(self.stage.resolve()/'APP',self.stage.resolve()/'DATA')
        self.assertFalse(self.out.exists())

    def test_rejects_false_claim_of_ready_to_flash(self):
        (self.stage/'source-stage.json').write_text(json.dumps({'schema':1,'stage':'source-desktop-copy','ready_to_flash':True}))
        with self.assertRaisesRegex(ValueError,'unexpected source stage report'):self.call_validate()
        self.assertFalse(self.out.exists())

    def test_rejects_wrong_kernel_before_output(self):
        self.inputs['ram_kernel'].write_bytes(b'bad image')
        with self.assertRaisesRegex(ValueError,'invalid ram_kernel'):self.call_validate()
        self.assertFalse(self.out.exists())

    def test_audit_failure_stops_packaging(self):
        self.audit.inspect.return_value={'checks_passed':False,'issues':['broken wallpaper']}
        with self.assertRaisesRegex(ValueError,'broken wallpaper'):self.call_validate()
        self.assertFalse(self.out.exists())


if __name__=='__main__': unittest.main()
