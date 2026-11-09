#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

p = Path(__file__).with_name('build-source-kernel.py')
spec = importlib.util.spec_from_file_location('source_kernel', p)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class BuildSafety(unittest.TestCase):
    def test_windows_is_rejected_before_tools_or_build(self):
        with mock.patch.object(m.sys, 'platform', 'win32'), mock.patch.object(m.subprocess, 'run') as run:
            with self.assertRaises(SystemExit):
                m.main(['--workspace', 'source', '--output', 'output'])
            run.assert_not_called()

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(m.sys, 'platform', 'linux'), mock.patch.object(m.subprocess, 'run') as run:
            output = Path(d) / 'existing'; output.mkdir(); (output / 'keep').write_text('sentinel')
            with self.assertRaises(SystemExit):
                m.main(['--workspace', d, '--output', str(output)])
            self.assertEqual((output / 'keep').read_text(), 'sentinel')
            run.assert_not_called()

if __name__ == '__main__': unittest.main()
