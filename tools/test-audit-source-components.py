#!/usr/bin/env python3
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('component_audit',Path(__file__).with_name('audit-source-components.py'))
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)


class ComponentAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        base=Path(self.tmp.name);self.root=base/'app';self.kernel=base/'kernel';self.drivers=base/'drivers'
        for p in (self.root/'boot',self.kernel/'include/config',self.drivers/'audio',self.root/'usr/lib/modules/6.1-test/extra'):
            p.mkdir(parents=True)
        (self.kernel/'include/config/kernel.release').write_text('6.1-test\n')
        for source,target in [('uImage','uImage-desktop'),('mocha.dtb','mocha-desktop.dtb')]:
            (self.kernel/source).write_bytes(source.encode());(self.root/'boot'/target).write_bytes(source.encode())
        files={}
        for name in audit.EXPECTED:
            payload=name.encode();(self.drivers/'audio'/name).write_bytes(payload)
            (self.root/'usr/lib/modules/6.1-test/extra'/name).write_bytes(payload)
            files['audio/'+name]=hashlib.sha256(payload).hexdigest()
        self.manifest={'schema':1,'kernelrelease':'6.1-test','flash_ready':False,'files':files}
        self.save()

    def save(self):
        (self.drivers/'modules.json').write_text(json.dumps(self.manifest))

    def test_matching_files_do_not_mark_image_ready(self):
        result=audit.inspect(self.root,self.kernel,self.drivers)
        self.assertEqual(len(result['verified']),9);self.assertFalse(result['ready_to_flash'])

    def test_changed_module_is_rejected(self):
        (self.root/'usr/lib/modules/6.1-test/extra/mocha_audio_data_pin.ko').write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError,'driver output mismatch'):
            audit.inspect(self.root,self.kernel,self.drivers)

    def test_kernel_mismatch_is_rejected(self):
        (self.root/'boot/uImage-desktop').write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError,'kernel output mismatch'):
            audit.inspect(self.root,self.kernel,self.drivers)

    def test_driver_path_traversal_is_rejected(self):
        key=next(iter(self.manifest['files']));value=self.manifest['files'].pop(key)
        self.manifest['files']['../'+Path(key).name]=value;self.save()
        with self.assertRaisesRegex(ValueError,'invalid or duplicate'):
            audit.inspect(self.root,self.kernel,self.drivers)


if __name__=='__main__':unittest.main()
