#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec=importlib.util.spec_from_file_location('source_stage',Path(__file__).with_name('stage-source-distribution.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class StageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.parent=Path(self.tmp.name);self.root=self.parent/'root';self.data=self.parent/'data';self.out=self.parent/'out'
        (self.root/'etc').mkdir(parents=True);(self.root/'etc/mocha-internal-debian').touch();self.data.mkdir()

    def test_refuses_output_inside_source_before_copy(self):
        with mock.patch.object(module.subprocess,'run') as run:
            with self.assertRaisesRegex(ValueError,'disjoint'):
                module.stage(self.root,self.data,self.root/'output')
            run.assert_not_called()

    def test_copy_then_prepare_then_audit_remains_unverified(self):
        with mock.patch.object(module.shutil,'which',return_value='/usr/bin/rsync'), \
             mock.patch.object(module.shutil,'disk_usage',return_value=mock.Mock(free=8*1024**3)), \
             mock.patch.object(module.subprocess,'run') as run:
            result=module.stage(self.root,self.data,self.out)
        commands=[call.args[0] for call in run.call_args_list]
        self.assertEqual(len(commands),4)
        self.assertEqual(commands[0][0],'rsync');self.assertEqual(commands[1][0],'rsync')
        self.assertTrue(commands[2][1].endswith('prepare-source-distribution.py'))
        self.assertTrue(commands[3][1].endswith('audit-source-desktop.py'))
        self.assertFalse(result['ready_to_flash'])
        self.assertTrue((self.out/'source-stage.json').is_file())


if __name__=='__main__': unittest.main()
