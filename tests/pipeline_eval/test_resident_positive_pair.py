from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from reports.ALGO08.v3 import resident_positive_pair as pair


class PassivePhysicalTests(unittest.TestCase):
    def test_cold_metadata_does_not_authorize_a_payload(self):
        with TemporaryDirectory() as root:
            directory = Path(root)
            (directory / "manifest.json").write_text("invalid JSON")
            (directory / "iq-000000.ci16.zst").write_bytes(b"sample")
            (directory / "windows-000000.jsonl").write_text("test")

            def sample(paths):
                warm = all(name != "manifest.json" for _, name, _ in paths)
                return dict(unavailable={}, members=len(paths), observed_members=len(paths),
                            cached_pages=len(paths) if warm else 0, observed_file_pages=len(paths))

            with patch.object(pair, "BULK", directory):
                observed = pair.official(dict(path=root, manifest_digest="unused"), sample)
            self.assertFalse(observed["admitted"])
            self.assertFalse(observed["manifest_verified"])
            self.assertEqual(observed["data"]["payload"]["bytes"], 6)

    def test_bound_manifest_still_requires_every_payload_page(self):
        with TemporaryDirectory() as root:
            directory = Path(root)
            data = json.dumps(dict(window_count=64, chunks=[
                dict(payload_relative_path="iq-000000.ci16.zst", compressed_bytes=6, compressed_sha256="payload-digest",
                     index_relative_path="windows-000000.jsonl", index_bytes=4, index_sha256="index-digest")])).encode()
            (directory / "manifest.json").write_bytes(data)

            def sample(paths):
                warm = all(not name.endswith(".zst") for _, name, _ in paths)
                return dict(unavailable={}, members=len(paths), observed_members=len(paths),
                            cached_pages=len(paths) if warm else 0, observed_file_pages=len(paths))

            with patch.object(pair, "BULK", directory):
                observed = pair.official(dict(path=root, manifest_digest=sha256(data).hexdigest()), sample)
            self.assertTrue(observed["manifest_verified"])
            self.assertFalse(observed["admitted"])
            self.assertEqual(observed["data"]["payload"]["bound_members"][0]["sha256"], "payload-digest")
