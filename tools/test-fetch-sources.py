#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('fetch_sources', HERE / 'fetch-sources.py')
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.lock = HERE.parent / 'sources.lock.json'
        self.environment = mock.patch.object(fetch, 'check_environment')
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_lock_contains_six_pinned_public_sources(self):
        self.assertEqual(len(fetch.load_lock(self.lock)), 6)

    def test_dirty_destination_rejected_before_git(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(fetch.subprocess, 'run') as run:
            (Path(d) / 'existing').touch()
            with self.assertRaisesRegex(ValueError, 'new or empty'):
                fetch.fetch(self.lock, d)
            run.assert_not_called()

    def test_unknown_repository_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            data = json.loads(self.lock.read_text(encoding='utf-8-sig'))
            data['repositories'][0]['name'] = '../unsafe'
            p = Path(d) / 'lock.json'; p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                fetch.load_lock(p)

    def test_failed_checkout_does_not_reach_later_sources(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(fetch.subprocess, 'run', side_effect=RuntimeError('git failed')) as run:
            with self.assertRaisesRegex(RuntimeError, 'git failed'):
                fetch.fetch(self.lock, Path(d) / 'sources')
            self.assertEqual(run.call_count, 1)

    def test_fetch_checks_every_pinned_commit(self):
        rows = fetch.load_lock(self.lock)
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(fetch.subprocess, 'run') as run, \
                mock.patch.object(fetch.subprocess, 'check_output',
                                  side_effect=[row['commit'] + '\n' for row in rows]):
            fetch.fetch(self.lock, Path(d) / 'sources')
            self.assertEqual(run.call_count, 4 * len(rows))

    def test_mismatched_commit_stops_fetch(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(fetch.subprocess, 'run') as run, \
                mock.patch.object(fetch.subprocess, 'check_output', return_value='0' * 40):
            with self.assertRaisesRegex(RuntimeError, 'commit mismatch'):
                fetch.fetch(self.lock, Path(d) / 'sources')
            self.assertEqual(run.call_count, 4)

    def test_failed_primary_mirror_falls_back_for_each_source(self):
        rows = fetch.load_lock(self.lock)
        def run(command, **kwargs):
            if 'fetch' in command and any(str(value).startswith('https://primary.invalid/') for value in command):
                raise fetch.subprocess.CalledProcessError(128, command)
            return mock.DEFAULT
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(fetch.subprocess, 'run', side_effect=run) as calls, \
                mock.patch.object(fetch.subprocess, 'check_output',
                                  side_effect=[row['commit'] + '\n' for row in rows]):
            fetch.fetch(self.lock, Path(d) / 'sources', 'https://primary.invalid', 'https://fallback.invalid')
            fallback = [call for call in calls.call_args_list
                        if any(str(value).startswith('https://fallback.invalid/') for value in call.args[0])]
            self.assertEqual(len(fallback), len(rows))

    def test_windows_checkout_is_rejected(self):
        self.environment.stop()
        with mock.patch.object(fetch.sys, 'platform', 'win32'):
            with self.assertRaisesRegex(RuntimeError, 'Windows cannot'):
                fetch.check_environment('unused')


if __name__ == '__main__':
    unittest.main()
