#!/usr/bin/env python3
import hashlib, importlib.util, io, json, tempfile, unittest
from pathlib import Path
from unittest import mock
p = Path(__file__).with_name('stage-public-firmware.py')
spec = importlib.util.spec_from_file_location('stage_fw', p)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class StagingTests(unittest.TestCase):
    def fixture(self, root):
        source = root/'source'; source.mkdir(); rows=[]
        for index, name in enumerate(m.MAPPING):
            path=source/name; path.parent.mkdir(parents=True,exist_ok=True)
            data=('asset-'+str(index)).encode(); path.write_bytes(data)
            rows.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        (source/'manifest.json').write_text(json.dumps({'files':rows}))
        return source

    def test_stage_verified_subset_and_mark_incomplete(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=self.fixture(root);out=root/'output';m.stage(source,out)
            self.assertTrue((out/'brcm/BCM4350C0.hcd').is_file())
            self.assertFalse(json.loads((out/'staged-firmware.json').read_text())['complete'])

    def test_tampering_fails_before_creating_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=self.fixture(root);out=root/'output'
            (source/next(iter(m.MAPPING))).write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):m.stage(source,out)
            self.assertFalse(out.exists())

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=self.fixture(root);out=root/'output';out.mkdir();(out/'keep').touch()
            with self.assertRaises(ValueError):m.stage(source,out)
            self.assertTrue((out/'keep').exists())

    def test_bad_download_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=self.fixture(root);out=root/'output'
            with mock.patch.object(m.urllib.request, 'urlopen', return_value=io.BytesIO(b'wrong')):
                with self.assertRaisesRegex(ValueError, 'upstream Wi-Fi asset checksum mismatch'):
                    m.stage(source,out,fetch_wifi=True)
            self.assertFalse(out.exists())

if __name__ == '__main__': unittest.main()
