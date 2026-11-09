#!/usr/bin/env python3
import importlib.util,io,tarfile,tempfile,unittest
from pathlib import Path
p=Path(__file__).with_name('fetch-desktop-upstream.py');spec=importlib.util.spec_from_file_location('desktop_fetch',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class DesktopFetchTests(unittest.TestCase):
 def test_rejects_archive_path_escape(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);archive=root/'bad.tar.xz'
   with tarfile.open(archive,'w:xz') as t:
    x=tarfile.TarInfo('vendor/../../outside');x.size=1;t.addfile(x,io.BytesIO(b'x'))
   with self.assertRaisesRegex(ValueError,'unsafe vendor'):m.extract_vendor(archive,root/'out')
   self.assertFalse((root/'outside').exists())
 def test_rejects_archive_symlink(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);archive=root/'bad.tar.xz'
   with tarfile.open(archive,'w:xz') as t:
    x=tarfile.TarInfo('vendor/link');x.type=tarfile.SYMTYPE;x.linkname='/etc';t.addfile(x)
   with self.assertRaisesRegex(ValueError,'unsafe vendor'):m.extract_vendor(archive,root/'out')
 def test_existing_output_stops_before_network(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);src=root/'src';src.mkdir();out=root/'out';out.mkdir();(out/'keep').touch()
   with self.assertRaises(ValueError):m.fetch(src,out,root/'missing.json')
   self.assertTrue((out/'keep').exists())
if __name__=='__main__':unittest.main()
