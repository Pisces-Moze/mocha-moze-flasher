#!/usr/bin/env python3
import importlib.util,json,tempfile,unittest
from pathlib import Path
p=Path(__file__).with_name('extract-board-data.py');spec=importlib.util.spec_from_file_location('board_data',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
DATA=b'sromrev=11\nboardrev=0x1300\nboardtype=0x1234\nmacaddr=02:11:22:33:44:55\n'
class BoardDataTests(unittest.TestCase):
 def fixture(self,root):
  src=root/'source';src.mkdir();fw=root/'firmware';fw.mkdir();return src,fw
 def test_extract_preserves_data_and_refuses_overwrite(self):
  with tempfile.TemporaryDirectory() as d:
   src,fw=self.fixture(Path(d));p=src/m.CANDIDATES[0];p.parent.mkdir(parents=True);p.write_bytes(DATA)
   m.extract(src,fw);self.assertEqual((fw/m.OUTPUT).read_bytes(),DATA)
   with self.assertRaisesRegex(ValueError,'already exists'):m.extract(src,fw)
 def test_missing_or_conflicting_stops_without_output(self):
  with tempfile.TemporaryDirectory() as d:
   src,fw=self.fixture(Path(d))
   with self.assertRaisesRegex(ValueError,'not found'):m.extract(src,fw)
   for n,data in [(m.CANDIDATES[0],DATA),(m.CANDIDATES[4],DATA+b'foo=1\n')]:
    p=src/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
   with self.assertRaisesRegex(ValueError,'conflicting'):m.extract(src,fw)
   self.assertFalse((fw/m.OUTPUT).exists())
 def test_invalid_file_is_not_accepted(self):
  with tempfile.TemporaryDirectory() as d:
   src,fw=self.fixture(Path(d));p=src/m.CANDIDATES[0];p.parent.mkdir(parents=True);p.write_bytes(b'macaddr=abc\n')
   with self.assertRaisesRegex(ValueError,'not a supported'):m.extract(src,fw)
   self.assertFalse((fw/m.OUTPUT).exists())
 def test_report_does_not_contain_device_identity(self):
  with tempfile.TemporaryDirectory() as d:
   src,fw=self.fixture(Path(d));p=src/m.CANDIDATES[0];p.parent.mkdir(parents=True);p.write_bytes(DATA)
   report=fw/'staged-firmware.json';report.write_text(json.dumps({'schema':1,'missing':['per-device wifi board data'],'complete':False}))
   m.extract(src,fw);text=report.read_text();self.assertNotIn('02:11:22:33:44:55',text)
   self.assertEqual(json.loads(text)['missing'],[])
if __name__=='__main__':unittest.main()
