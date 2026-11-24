import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from named_hybrid_baseline import INSTALLED_NATIVE, detector_handoff, inventory_check


class NamedHybridInput(TestCase):
    def test_detector_boundary_keeps_verbatim_packet_and_distinct_identity(self):
        original = object()
        scan = SimpleNamespace(PINS={"cancellation-factors.so": INSTALLED_NATIVE}, acquire=original)
        request = dict(session="session", inventory="sha256:inventory", detector="sha256:hybrid", native="sha256:verbatim")
        packet, audit = {}, {}
        with patch("empty_bootstrap.bind_native") as validate, detector_handoff(scan, request, packet, audit):
            with self.assertRaisesRegex(ValueError, "different"):
                scan.acquire("wrong", "sha256:inventory")
            self.assertIs(scan.acquire("session", "sha256:inventory"), packet)
            validate.assert_called_once_with(packet, "session", "sha256:inventory", "hybrid", expected="sha256:verbatim")
            self.assertEqual(scan.PINS["cancellation-factors.so"], "hybrid")
            with self.assertRaisesRegex(ValueError, "different"):
                scan.acquire("session", "sha256:inventory")
        self.assertEqual(scan.PINS["cancellation-factors.so"], INSTALLED_NATIVE)
        self.assertIs(scan.acquire, original)
        self.assertEqual(audit["original_asset"], INSTALLED_NATIVE)

    def test_saved_inventory_does_not_authorize_waveform_or_other_recording(self):
        request = dict(recording="/original/recording", session="original", inventory="signed")
        inventory, audit = {}, []
        port = inventory_check(request, inventory, audit)
        with self.assertRaisesRegex(ValueError, "metadata-only"):
            port(None, request["recording"], verify_windows=True)
        with self.assertRaisesRegex(ValueError, "metadata-only"):
            port(None, "/elsewhere", verify_windows=False)
        self.assertEqual(port(None, request["recording"], verify_windows=False), ("original", "signed", inventory))
        self.assertEqual(audit, ["signed"])
