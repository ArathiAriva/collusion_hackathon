import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from results_bundle import unpack


class BundleTests(unittest.TestCase):
    def fixture(self, root, name='results/example.json'):
        archive = root / 'test.tar.gz'
        payload = b'{"status":"stopped"}\n'
        with tarfile.open(archive, 'w:gz') as tar:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
        catalog = root / 'catalog.json'
        catalog.write_text(json.dumps({'bundles': [{
            'id': 'release', 'archive': archive.name,
            'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
            'files': [{'path': name, 'bytes': len(payload),
                       'sha256': hashlib.sha256(payload).hexdigest()}]}]}))
        return catalog, archive

    def test_round_trip_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog, _ = self.fixture(root)
            out = root / 'extracted'
            self.assertEqual(unpack(catalog, out), {'release': 1})
            self.assertEqual(json.loads((out / 'results/example.json').read_text())['status'], 'stopped')
            with self.assertRaises(FileExistsError):
                unpack(catalog, out)

    def test_corrupted_archive_fails_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog, archive = self.fixture(root)
            archive.write_bytes(archive.read_bytes() + b'corrupted')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                unpack(catalog, root / 'extracted')
            self.assertFalse((root / 'extracted').exists())

    def test_path_traversal_fails_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog, _ = self.fixture(root, '../outside.json')
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                unpack(catalog, root / 'extracted')
            self.assertFalse((root / 'outside.json').exists())


if __name__ == '__main__':
    unittest.main()
