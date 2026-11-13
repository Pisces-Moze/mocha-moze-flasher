#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('desktop_build',Path(__file__).with_name('build-source-desktop.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class CopyTests(unittest.TestCase):
    def test_nested_target_is_source_not_build_cache(self):
        source=Path('/tmp/niri')
        self.assertIn('target',module.ignored_source_entries(source,source,['target','src']))
        self.assertNotIn('target',module.ignored_source_entries(source,source/'vendor/cc/src',['target','lib.rs']))


if __name__=='__main__':unittest.main()
