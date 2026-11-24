import os
from pathlib import Path
import sys
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from ds30_0049_saved_crossover import ARCHIVE, admit_released_detector, inventory_hook, reject_waveforms


def detector_identity(specification, handoff):
    if (specification["unrelated"] != handoff.qualification
            or specification["detector_sha256"] == handoff.receiver):
        raise ValueError("Expected a qualified raw handoff")
    return handoff.receiver


class SavedCrossoverTest(TestCase):
    def test_stock_saved_packet_only_removes_unequal_detector_rule(self):
        from types import SimpleNamespace

        source = SimpleNamespace(qualification=1, receiver="stock")
        match = dict(unrelated=1, detector_sha256="stock")
        with self.assertRaises(ValueError):
            detector_identity(match, source)
        adapted = admit_released_detector(detector_identity)
        self.assertEqual(adapted(match, source), "stock")
        with self.assertRaises(ValueError):
            adapted(match | {"unrelated": 2}, source)

    def test_saved_inventory_rejects_raw_traversal(self):
        raw = {"recording": "/raw", "session_id": "session", "inventory_sha256": "pin"}
        inventory = {"window_count": 3}
        hook = inventory_hook(raw, inventory)
        self.assertEqual(hook(None, Path("/raw"), verify_windows=False), ("session", "pin", inventory))
        with self.assertRaises(ValueError):
            hook(None, Path("/raw"))
        with self.assertRaises(ValueError):
            hook(None, Path("/other"), verify_windows=False)

    def test_only_the_same_catalogue_can_open_on_backing(self):
        reject_waveforms("open", (str(ARCHIVE / "tle"), "r", os.O_RDONLY))
        for path, flags in ((ARCHIVE / "tle", os.O_WRONLY), (ARCHIVE / "iq.ci16.zst", os.O_RDONLY),
                            (Path("/srv/bulk/unrelated"), os.O_RDONLY)):
            with self.assertRaises(ValueError):
                reject_waveforms("open", (str(path), "r", flags))
