#!/usr/bin/env python3
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

spec=importlib.util.spec_from_file_location('assemble',Path(__file__).with_name('assemble-source-candidate.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);base=Path(self.tmp.name)
        self.args=SimpleNamespace(output=base/'output',version='test')
        for name in ('root','data','kernel','drivers','speaker_source'):
            path=base/name;path.mkdir();setattr(self.args,name,path)
        for name in ('loader','ram_kernel','ram_dtb','installer','lnx'):
            path=base/name;path.write_bytes(b'fixture');setattr(self.args,name,path)

    def test_stages_then_packages_with_component_gate(self):
        with mock.patch.object(module.subprocess,'run') as run:result=module.assemble(self.args)
        self.assertEqual(run.call_count,2)
        first,second=[call.args[0] for call in run.call_args_list]
        self.assertTrue(first[1].endswith('stage-source-distribution.py'))
        self.assertIn('--kernel',first);self.assertIn('--drivers',first)
        self.assertTrue(second[1].endswith('build-source-distribution.py'))
        self.assertIn('--require-component-match',second)
        self.assertIn('--speaker-source',first);self.assertIn('--require-speaker',second)
        self.assertFalse(result['ready_to_flash'])

    def test_missing_input_fails_before_output(self):
        self.args.installer.unlink()
        with mock.patch.object(module.subprocess,'run') as run:
            with self.assertRaisesRegex(ValueError,'missing boot input'):module.assemble(self.args)
        self.assertFalse(self.args.output.exists());run.assert_not_called()


if __name__=='__main__':unittest.main()
