import os
from pathlib import Path
import sys
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from ds30_0049_saved_crossover import ARCHIVE, admit_released_detector, inventory_hook, reject_waveforms
from ds30_0049_saved_crossover_score import effects, retained_native_support
from integrated_original_batch import tagged_bytes


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

    def test_conditional_effects_include_interaction(self):
        values = {"installed-installed": 2., "installed-successor": 5.,
                  "successor-installed": 3., "successor-successor": 10.}
        self.assertEqual(effects(values), dict(raw_diagonal_delta=8., receiver_with_installed_solver=3.,
                                              receiver_with_successor_solver=7., solver_with_installed_receiver=1.,
                                              solver_with_successor_receiver=5., interaction=4.))

    def test_native_support_keeps_distinct_empty_and_retained_lanes(self):
        def candidate(frequency):
            return dict(fractional_margin=2, candidate_rank=0, passed_fractional_margin_gate=True,
                        fractional_tracking_cfo_hz=frequency, integer_epoch_sample=3, fractional_epoch_offset_samples=.5)

        def packet(early, late):
            return dict(source=dict(session_id="signed", probes=[
                dict(receiver_id=0, valid_start_counter=3, candidates=early),
                dict(receiver_id=1, valid_start_counter=7, candidates=late),
            ]))

        def owner(receiver, counter):
            return [tagged_bytes(f"signed:{receiver}:{counter}".encode()), "1234", "curve"]

        packets = dict(installed=packet([candidate(8.)], [candidate(3.)]), successor=packet([], [candidate(5.)]))
        result = retained_native_support(packets, [owner(0, 3), owner(1, 7)], [owner(1, 7)])
        self.assertEqual(result["matched_lanes"], 2)
        self.assertEqual(result["support"]["lost"]["states"], {"accepted_to_empty": 1})
        self.assertEqual(result["support"]["shared"]["median_abs_cfo_delta_hz"], 2.)
