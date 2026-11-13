#!/usr/bin/env python3
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('speaker',Path(__file__).with_name('install-source-speaker.py'))
speaker=importlib.util.module_from_spec(spec);spec.loader.exec_module(speaker)


@unittest.skipUnless(hasattr(os,'geteuid') and os.geteuid()==0,'Linux staging test')
class SpeakerStageTests(unittest.TestCase):
    def test_installs_matching_modules_and_firmware(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);root=base/'root';drivers=base/'drivers';kernel=base/'kernel';source=base/'source'
            for p in (root/'usr/lib/modules/6.1-test/extra',root/'usr/lib/firmware/mocha',drivers,kernel/'include/config',source/'audio'):
                p.mkdir(parents=True,exist_ok=True)
            (root/'.mocha-source-rootfs-build').touch();(kernel/'include/config/kernel.release').write_text('6.1-test\n')
            records={}
            for _,name,_ in speaker.MODULES:
                data=name.encode();(root/'usr/lib/modules/6.1-test/extra'/name).write_bytes(data)
                records['audio/'+name]=hashlib.sha256(data).hexdigest()
            (drivers/'modules.json').write_text(json.dumps({'kernelrelease':'6.1-test','files':records}))
            for i in range(9):(root/'usr/lib/firmware/mocha'/('tfa9890-'+str(i))).write_bytes(b'firmware')
            for name,content in {'mocha-speaker-hardware.service':'ConditionKernelVersion=6.12.111-moze.1-native-vde2\n',
                                 'mocha-speaker-hardware.py':"KERNEL = '6.12.111-moze.1-native-vde2'\nROOT = ROOT / '20261022'\n",
                                 '51-mocha-speakers.conf':'wireplumber', 'mocha-speakers.conf':'alsa'}.items():
                (source/'audio'/name).write_text(content)
            (source/'runtime').mkdir();(source/'gpu').mkdir()
            (source/'runtime/mocha-runtime-policy.py').write_text('runtime')
            (source/'runtime/mocha-runtime-policy.service').write_text('unit')
            (source/'gpu/mocha-native-gpu-policy.sh').write_text('gpu')
            speaker.install(root,drivers,kernel,source)
            manifest=json.loads((root/'usr/local/lib/mocha-audio/6.1-test/source/manifest.json').read_text())
            self.assertEqual(len(manifest['modules']),6);self.assertEqual(len(manifest['firmware']),9)
            self.assertIn('ConditionKernelVersion=6.1-test',(root/'etc/systemd/system/mocha-speaker-hardware.service').read_text())
            self.assertTrue((root/'etc/systemd/system/multi-user.target.wants/mocha-speaker-hardware.service').is_symlink())


if __name__=='__main__':unittest.main()
