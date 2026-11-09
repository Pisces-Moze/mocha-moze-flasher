#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile,unittest
from unittest import mock
p=Path(__file__).with_name('build-source-drivers.py');spec=importlib.util.spec_from_file_location('drivers',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Safety(unittest.TestCase):
 def test_existing_output_is_preserved(self):
  with tempfile.TemporaryDirectory() as d, mock.patch.object(m.sys,'platform','linux'), mock.patch.object(m.subprocess,'run') as run:
   root=Path(d);src=root/'src';src.mkdir();kernel=root/'kernel';kernel.mkdir();out=root/'out';out.mkdir();(out/'keep').touch()
   with self.assertRaises(SystemExit):m.main(['--workspace',str(src),'--kernel',str(kernel),'--output',str(out)])
   self.assertTrue((out/'keep').exists());run.assert_not_called()
 def test_incomplete_kernel_never_builds(self):
  with tempfile.TemporaryDirectory() as d, mock.patch.object(m.sys,'platform','linux'), mock.patch.object(m.shutil,'which',return_value='/bin/tool'), mock.patch.object(m.subprocess,'run') as run:
   root=Path(d);src=root/'src';src.mkdir();kernel=root/'kernel';kernel.mkdir();out=root/'out'
   with self.assertRaises(SystemExit):m.main(['--workspace',str(src),'--kernel',str(kernel),'--output',str(out)])
   self.assertFalse(out.exists());run.assert_not_called()
if __name__=='__main__':unittest.main()
