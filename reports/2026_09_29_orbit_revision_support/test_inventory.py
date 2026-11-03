import unittest
from datetime import UTC, datetime
from types import SimpleNamespace

from inventory import epoch_ns, select


class InventoryTests(unittest.TestCase):
    def test_causal_and_age_cutoffs(self):
        refs = [SimpleNamespace(collected_utc_ns=t, sha256=str(t)) for t in (10, 20, 30)]
        self.assertEqual(select(refs, 20).collected_utc_ns, 10)
        self.assertEqual(select(refs, 20, False).collected_utc_ns, 20)
        self.assertIsNone(select(refs, 10))

    def test_epoch_fraction(self):
        line = " " * 18 + "26001.50000000"
        self.assertEqual(
            epoch_ns(line), int(datetime(2026, 1, 1, 12, tzinfo=UTC).timestamp()) * 10**9
        )


if __name__ == "__main__":
    unittest.main()
