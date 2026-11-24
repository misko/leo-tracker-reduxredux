"""Integrity and ordered primitive record tests for the portable orbit index."""

from hashlib import sha256
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from portable_orbit_index import PortableSourceIndex, decode, load_index, write_index


def pin(value):
    return "sha256:"+sha256(value).hexdigest()


VERSIONS = {"sgp4_version": "test", "source_sha256": {"implementation": "version-a"}}
BODY = pin(b"Original signed text")
EPOCHS = (1_768_004_540_047_623_105, -182_049_799_000)
NUMBERS = (45678, 424242)


class PortableIndexTests(unittest.TestCase):
    def export(self, root):
        source = SimpleNamespace(bodies={BODY: SimpleNamespace(
            names=("from", "original"), satellite_numbers=NUMBERS, epochs=EPOCHS)})
        path = Path(root)/"orbits.bin"
        return path, write_index(path, source, VERSIONS)

    def test_record_bytes_preserve_order_and_signed_epochs(self):
        with TemporaryDirectory() as root:
            path, receipt = self.export(root)
            index, audit = load_index(path, receipt["sha256"], VERSIONS)
            self.assertIsNone(audit["fallback"])
            self.assertEqual(audit["read_bytes"], receipt["bytes"])
            count, rows = index.rows(BODY)
            self.assertEqual(count, 2)
            self.assertEqual(list(rows), list(zip(NUMBERS, EPOCHS, strict=True)))
            self.assertIsNone(index.rows(pin(b"another verified source")))
            self.assertLess(audit["artifact_peak_bytes"], 4096)

    def test_mismatch_in_external_pin_or_implementation_falls_through(self):
        with TemporaryDirectory() as root:
            path, receipt = self.export(root)
            self.assertIsNone(load_index(path, pin(b"wrong pin"), VERSIONS)[0])
            self.assertIsNone(load_index(path, receipt["sha256"], {"sgp4_version": "new"})[0])
            modified = bytearray(path.read_bytes())
            modified[-1] ^= 0x80
            path.write_bytes(modified)
            loaded, audit = load_index(path, receipt["sha256"], VERSIONS)
            self.assertIsNone(loaded)
            self.assertIn("external SHA-256", audit["fallback"])

    def test_rejects_bad_layout_even_at_expected_digest(self):
        with TemporaryDirectory() as root:
            path, _ = self.export(root)
            data = path.read_bytes()
            for value in (b"", data[:-1], data+b"trailing"):
                with self.assertRaises(ValueError):
                    decode(value, pin(value), VERSIONS)

    def test_does_not_block_on_or_follow_a_non_artifact(self):
        with TemporaryDirectory() as root:
            directory = Path(root)
            path, receipt = self.export(root)
            (directory/"symlink").symlink_to(path)
            os.mkfifo(directory/"fifo")
            for name in ("symlink", "fifo", "missing"):
                artifact, audit = load_index(directory/name, receipt["sha256"], VERSIONS)
                self.assertIsNone(artifact)
                self.assertIsNotNone(audit["fallback"])

    def test_attach_checks_original_count_id_and_same_pair_epoch(self):
        index = PortableSourceIndex(None)
        strict = [SimpleNamespace(name=f"actual-{number}", satellite_number=number,
                                  first_line=f"line1-{number}", second_line=f"line2-{number}")
                  for number in NUMBERS]
        packed = list(zip(NUMBERS, EPOCHS, strict=True))
        build = lambda *fields: fields
        self.assertIsNone(index.attach(build, strict, 3, packed))
        self.assertIsNone(index.attach(build, strict[::-1], 2, packed))
        self.assertEqual(index.pairs, {})
        attached = index.attach(build, strict, 2, packed)
        self.assertEqual(attached, (tuple(row.name for row in strict), NUMBERS,
                                    tuple((row.first_line, row.second_line) for row in strict), EPOCHS))
        previous = dict(index.pairs)
        bad = [packed[0], (NUMBERS[1], EPOCHS[1]+1)]
        self.assertIsNone(index.attach(build, strict, 2, bad))
        self.assertEqual(index.pairs, previous)


if __name__ == "__main__":
    unittest.main()
