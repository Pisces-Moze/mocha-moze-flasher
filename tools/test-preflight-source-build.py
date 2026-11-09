#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Preflight checks must never authorize installation or mutate a device."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).with_name('preflight-source-build.py')
spec = importlib.util.spec_from_file_location('source_preflight', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / 'src'; self.work.mkdir()
        self.firmware = self.root / 'firmware'; self.firmware.mkdir()
        self.lock = self.root / 'lock.json'
        self.rows = [{'name': n, 'commit': 'a'*40} for n in sorted(m.REPOS)]
        self.write_lock()

    def write_lock(self):
        self.lock.write_text(json.dumps({'schema': 1, 'repositories': self.rows}), encoding='utf8')

    def populate(self):
        for row in self.rows: (self.work / row['name']).mkdir()
        for relative in m.FIRMWARE.values():
            path = self.firmware / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'x')
        gpu = self.firmware/'nvidia/gk20a'; gpu.mkdir(parents=True)
        for name in ('fecs_inst.bin', 'fecs_data.bin', 'gpccs_inst.bin', 'gpccs_data.bin',
                     'sw_bundle_init.bin', 'sw_method_init.bin', 'sw_nonctx.bin', 'sw_ctx.bin'):
            (gpu/name).write_bytes(b'x')
        audio = self.firmware/'mocha'; audio.mkdir()
        for name in ('tfa9890.config', 'tfa9890_boot.patch', 'tfa9890_rom.patch',
                     'tfa9890_left.speaker', 'tfa9890_right.speaker',
                     'tfa9890_left_music.eq', 'tfa9890_right_music.eq',
                     'tfa9890_left_music.preset', 'tfa9890_right_music.preset'):
            (audio/name).write_bytes(b'x')

    @staticmethod
    def git_run(args, **kwargs):
        if 'rev-parse' in args: return subprocess.CompletedProcess(args, 0, 'a'*40+'\n', '')
        return subprocess.CompletedProcess(args, 0, '', '')

    def test_fully_supplied_materials_still_block_unimplemented_build(self):
        self.populate()
        with mock.patch.object(m.platform, 'system', return_value='Linux'), \
             mock.patch.object(m.os, 'geteuid', return_value=0, create=True), \
             mock.patch.object(m.shutil, 'which', return_value='/bin/tool'), \
             mock.patch.object(m.shutil, 'disk_usage', return_value=type('Disk', (), {'free': m.MIN_BYTES})()), \
             mock.patch.object(m.subprocess, 'run', side_effect=self.git_run) as run:
            result = m.inspect(self.lock, self.work, self.firmware, self.root)
        self.assertFalse(result['ready_to_build_from_sources'])
        self.assertFalse(result['ready_to_flash'])
        self.assertEqual(len(result['issues']), 1)
        self.assertIn('not implemented', result['issues'][0])
        self.assertTrue(all(call.args[0][0] == 'git' for call in run.call_args_list))

    def test_missing_sources_and_firmware_reported(self):
        self.assertEqual(len(m.source_checks(self.lock, self.work)), 6)
        self.assertIn('firmware staging directory not supplied', m.firmware_checks(None)[0])
        missing = m.firmware_checks(self.firmware)
        self.assertEqual(len(missing), len(m.FIRMWARE) + 8 + 9)

    def test_duplicate_repository_and_invalid_hash_rejected(self):
        self.rows[-1] = self.rows[0].copy(); self.write_lock()
        self.assertIn('source lock invalid', m.source_checks(self.lock, self.work)[0])
        self.rows = [{'name': n, 'commit': 'a'*40} for n in sorted(m.REPOS)]
        self.rows[0]['commit'] = '../bad'; self.write_lock()
        self.assertIn('source lock invalid', m.source_checks(self.lock, self.work)[0])

    def test_commit_mismatch_and_dirty_checkout_rejected(self):
        self.populate()
        def bad_git(args, **kwargs):
            if 'rev-parse' in args: return subprocess.CompletedProcess(args, 0, 'b'*40+'\n', '')
            return subprocess.CompletedProcess(args, 0, ' M changed\n', '')
        with mock.patch.object(m.subprocess, 'run', side_effect=bad_git):
            issues = m.source_checks(self.lock, self.work)
        self.assertEqual(sum('commit does not match' in x for x in issues), 6)
        self.assertEqual(sum('modifications or untracked files' in x for x in issues), 6)

    def test_cli_always_returns_blocked_without_assembler(self):
        with mock.patch.object(m, 'inspect', return_value={'ready_to_flash': False, 'issues': ['missing assembler']}):
            self.assertEqual(m.main(['--workspace', str(self.work), '--output-parent', str(self.root)]), 2)


if __name__ == '__main__':
    unittest.main()
