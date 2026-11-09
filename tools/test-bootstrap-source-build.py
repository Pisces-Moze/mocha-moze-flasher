#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('bootstrap', Path(__file__).with_name('bootstrap-source-build.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class BootstrapTests(unittest.TestCase):
    def test_non_linux_never_fetches(self):
        with mock.patch.object(m.sys, 'platform', 'win32'), mock.patch.object(m, 'load') as load:
            with self.assertRaises(SystemExit): m.main(['--work', 'unused'])
            load.assert_not_called()

    def test_existing_directory_never_modified(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(m.sys, 'platform', 'linux'), mock.patch.object(m, 'load') as load:
            p=Path(d)/'work';p.mkdir();(p/'sentinel').write_text('keep')
            with self.assertRaises(SystemExit): m.main(['--work', str(p)])
            self.assertEqual((p/'sentinel').read_text(),'keep')
            load.assert_not_called()

    def test_missing_tool_stops_before_fetch(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(m.sys, 'platform', 'linux'), \
                mock.patch.object(m.shutil, 'which', return_value=None), mock.patch.object(m, 'load') as load:
            with self.assertRaises(SystemExit):m.main(['--work', str(Path(d)/'new')])
            load.assert_not_called()
            self.assertFalse((Path(d)/'new').exists())

if __name__ == '__main__': unittest.main()
