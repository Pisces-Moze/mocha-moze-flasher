#!/usr/bin/env python3
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('source_audit', Path(__file__).with_name('audit-source-desktop.py'))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'app'
        self.data = Path(self.tmp.name) / 'uda'
        self.root.mkdir(); self.data.mkdir()

    def populate(self):
        for path in audit.REQUIRED_ROOT.values():
            file = self.root / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('present')
        (self.root / audit.REQUIRED_ROOT['default login metadata']).write_text('{"schema":1,"username":"mocha"}')
        (self.root / 'etc/passwd').write_text('mocha:x:1000:1000::/home/mocha:/bin/bash\n')
        getty = self.root / 'etc/systemd/system/getty@tty1.service.d'
        getty.mkdir(parents=True)
        (getty / 'mocha.conf').write_text('ExecStart=/sbin/agetty --autologin mocha\n')
        wants = self.root / 'etc/systemd/system/getty.target.wants'
        wants.mkdir(parents=True)
        try:
            (wants / 'getty@tty1.service').symlink_to('/usr/lib/systemd/system/getty@.service')
        except OSError:
            self.skipTest('creating a symlink requires privileges on this Windows host')
        (self.data / audit.WALLPAPER).write_bytes(b'wallpaper')
        audit.WALLPAPER_SHA256 = hashlib.sha256(b'wallpaper').hexdigest()
        runtime = self.root / 'usr/local/libexec/mocha-vde-player/abc'
        runtime.mkdir(parents=True)
        (runtime / 'player').write_bytes(b'player')
        (runtime / 'build-manifest.json').write_text(json.dumps({'runtime_files': [
            {'path': 'player', 'sha256': hashlib.sha256(b'player').hexdigest()}]}))
        return runtime

    def test_incomplete_tree_is_not_flash_ready(self):
        result = audit.inspect(self.root, self.data)
        self.assertFalse(result['checks_passed'])
        self.assertFalse(result['ready_to_flash'])
        self.assertTrue(any('default login' in issue for issue in result['issues']))

    def test_complete_tree_is_still_not_flash_ready(self):
        self.populate()
        result = audit.inspect(self.root, self.data)
        self.assertTrue(result['checks_passed'], result['issues'])
        self.assertFalse(result['ready_to_flash'])

    def test_changed_runtime_is_rejected(self):
        runtime = self.populate()
        (runtime / 'player').write_bytes(b'tampered')
        self.assertTrue(any('runtime hash mismatch' in i for i in audit.inspect(self.root, self.data)['issues']))

    def test_model_and_bad_wallpaper_are_rejected(self):
        self.populate()
        (self.data / audit.WALLPAPER).write_bytes(b'wrong')
        (self.root / 'weights.gguf').write_bytes(b'model')
        issues = audit.inspect(self.root, self.data)['issues']
        self.assertTrue(any('wallpaper duplicate or hash' in i for i in issues))
        self.assertTrue(any('model weights' in i for i in issues))

    def test_runtime_cannot_escape_manifest_directory(self):
        runtime = self.populate()
        (runtime / 'build-manifest.json').write_text(json.dumps({'runtime_files': [
            {'path': '../outside', 'sha256': '0' * 64}]}))
        self.assertTrue(any('invalid runtime path' in i for i in audit.inspect(self.root, self.data)['issues']))

    def test_nested_roots_are_rejected(self):
        with self.assertRaises(ValueError):
            audit.inspect(self.root, self.root)


if __name__ == '__main__':
    unittest.main()
