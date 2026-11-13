#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import types
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

    def test_successful_preparation_never_flashes(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(m.sys, 'platform', 'linux'), \
                mock.patch.object(m.shutil, 'which', return_value='/bin/tool'), \
                mock.patch.object(m.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=25*1024**3)), \
                mock.patch.object(m.subprocess, 'run') as run:
            fetch=types.SimpleNamespace(check_environment=mock.Mock(), fetch=mock.Mock())
            desktop=types.SimpleNamespace(fetch=mock.Mock())
            stage=types.SimpleNamespace(stage=mock.Mock())
            board=types.SimpleNamespace(extract=mock.Mock())
            preflight=types.SimpleNamespace(inspect=mock.Mock(return_value={'ready_to_flash':False,'issues':['missing desktop assembler']}))
            with mock.patch.object(m, 'load', side_effect=[fetch,desktop,stage,board,preflight]):
                result=m.main(['--work',str(Path(d)/'new')])
            self.assertEqual(result,2)
            self.assertEqual(run.call_count,12)
            self.assertEqual([Path(call.args[0][1]).name for call in run.call_args_list],
                             ['build-source-kernel.py','build-source-drivers.py','build-source-boot.py','build-source-desktop.py',
                              'build-source-rootfs.py','build-source-ram.py','install-source-desktop-deps.py','install-source-firmware.py',
                              'install-source-drivers.py','build-source-video.py','install-source-desktop.py',
                              'assemble-source-candidate.py'])
            self.assertTrue((Path(d)/'new/source-build-status.json').exists())

if __name__ == '__main__': unittest.main()
