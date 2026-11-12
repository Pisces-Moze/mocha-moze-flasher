#!/usr/bin/env python3
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec=importlib.util.spec_from_file_location('prepare_source',Path(__file__).with_name('prepare-source-distribution.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


@unittest.skipUnless(hasattr(os,'geteuid') and os.geteuid()==0,'Linux root staging-copy test')
class SourcePreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'app';self.data=Path(self.tmp.name)/'uda'
        for p in ('etc/ssh','etc/systemd/system','usr/lib/firmware/brcm','home/mocha/.config','root','var/log'):
            (self.root/p).mkdir(parents=True,exist_ok=True)
        (self.data/'wallpapers').mkdir(parents=True)
        (self.root/module.MARKER).write_text(json.dumps(module.MARKER_CONTENT))
        (self.root/'etc/mocha-internal-debian').touch()
        (self.root/'etc/passwd').write_text('root:x:0:0::/root:/bin/bash\nmocha:x:1000:1000::/home/mocha:/bin/bash\n')
        (self.root/'etc/shadow').write_text('root:secret:1:2\nmocha:secret:1:2\n')
        (self.root/'etc/machine-id').write_text('device-id')
        (self.root/'etc/ssh/ssh_host_ed25519_key').write_text('private')
        (self.root/'home/mocha/.config/keep').write_text('desktop')
        (self.data/'wallpapers/example.webp').write_bytes(b'wallpaper')

    def test_removes_identity_and_preserves_desktop(self):
        with mock.patch.object(module.subprocess,'run',return_value=mock.Mock(stdout='$6$testhash\n')):
            result=module.prepare(self.root,self.data)
        self.assertFalse(result['ready_to_flash'])
        self.assertEqual((self.root/'etc/machine-id').read_text(),'')
        self.assertTrue((self.root/'var/lib/dbus/machine-id').is_symlink())
        self.assertEqual(os.readlink(self.root/'var/lib/dbus/machine-id'),'/etc/machine-id')
        self.assertFalse((self.root/'etc/ssh/ssh_host_ed25519_key').exists())
        self.assertEqual((self.root/'home/mocha/.config/keep').read_text(),'desktop')
        self.assertTrue((self.data/'wallpapers/example.webp').exists())
        self.assertFalse((self.root/module.MARKER).exists())
        self.assertIn('mocha:$6$testhash:',(self.root/'etc/shadow').read_text())

    def test_refuses_private_files_before_modification(self):
        (self.data/'wallpapers/weights.gguf').write_bytes(b'private')
        with self.assertRaisesRegex(ValueError,'private data or model'):
            module.prepare(self.root,self.data)
        self.assertTrue((self.root/'etc/ssh/ssh_host_ed25519_key').exists())

    def test_refuses_symlinked_ancestor(self):
        (self.root/'etc/ssh').rename(self.root/'etc/ssh-original')
        (self.root/'etc/ssh').symlink_to(self.root/'etc/ssh-original')
        with self.assertRaisesRegex(ValueError,'symlink'):
            module.prepare(self.root,self.data)
        self.assertEqual((self.root/'etc/machine-id').read_text(),'device-id')

    def test_requires_explicit_copy_marker(self):
        (self.root/module.MARKER).unlink()
        with self.assertRaisesRegex(ValueError,'marker'):
            module.prepare(self.root,self.data)


if __name__=='__main__': unittest.main()
