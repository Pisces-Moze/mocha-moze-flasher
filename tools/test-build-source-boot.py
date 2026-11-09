#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

p = Path(__file__).with_name('build-source-boot.py')
spec = importlib.util.spec_from_file_location('source_boot', p)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class BootBuildSafety(unittest.TestCase):
    def test_windows_never_starts_build(self):
        with mock.patch.object(m.sys,'platform','win32'), mock.patch.object(m.subprocess,'run') as run:
            with self.assertRaises(SystemExit):m.main(['--workspace','source','--output','output'])
            run.assert_not_called()

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(m.sys,'platform','linux'), mock.patch.object(m.subprocess,'run') as run:
            src=Path(d)/'src';src.mkdir();out=Path(d)/'out';out.mkdir();(out/'keep').touch()
            with self.assertRaises(SystemExit):m.main(['--workspace',str(src),'--output',str(out)])
            self.assertTrue((out/'keep').exists());run.assert_not_called()

if __name__ == '__main__':unittest.main()
