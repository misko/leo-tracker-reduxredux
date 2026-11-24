from itertools import combinations
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from ds30_owner_support_four import bounds, compare_group, digest, encoded, owner_map, peaks


class FourReceiptOwnerTest(TestCase):
    def test_sharp_bounds_exhaustively_for_small_rosters(self):
        population = set(range(6))
        for n in range(7):
            for k in range(7):
                pool = set(range(k))
                scores = [len(set(subset) & pool) for subset in combinations(population, n)]
                self.assertEqual(bounds(6, k, n), [min(scores), max(scores)])
        with self.assertRaises(ValueError):
            bounds(2, 1, 3)

    def test_passing_peak_and_margin_ties_follow_original(self):
        probe = dict(receiver_id=0, channel=6, edge="lower", actual_rf_hz=10, valid_start_counter=7)
        probe["candidates"] = [
            dict(passed_fractional_margin_gate=passed, fractional_margin=margin,
                 candidate_rank=rank, fractional_tracking_cfo_hz=cfo)
            for passed, margin, rank, cfo in [(False, 9, 0, 99), (True, 1, 1, 11), (True, 1, 0, 7)]
        ]
        native = {"source": {"session_id": "fast", "probes": [probe]}}
        (lane,) = peaks(native).values()
        self.assertEqual((lane.stream, lane.cfo), ("RX1/CH6", 7))
        native["source"]["probes"].append(probe)
        with self.assertRaises(ValueError):
            peaks(native)

    def test_cfo_pool_remains_distinct_from_retained_owner(self):
        old, new = ({str(i): SimpleNamespace(signature=(i,), cfo=cfo) for i, cfo in enumerate(values)}
                    for values in [(0, 30, None, 50), (4, 31, 2, None)])
        a, b = ({key for key, row in lanes.items() if row.cfo is not None} for lanes in (old, new))
        new_owners = {"0": ("1", "left"), "1": ("2", "left"), "2": ("3", "right")}
        exact_rows = [["0", "1", "left"], ["3", "1", "left"]]
        authority = dict(associated_points=2, owner_sha256=digest(encoded({"0": "1", "3": "1"})))
        exact_owners = owner_map(exact_rows, authority, a)
        exact = compare_group(old, new, set(old), a, b, exact_owners, new_owners, 2)
        unknown = compare_group(old, new, set(old), a, b, None, new_owners, 2)
        self.assertEqual(exact["owners"]["retained_cfo"]["median_abs_hz"], 4)
        self.assertEqual(unknown["owners"]["matched"], [1, 2])
        self.assertEqual(unknown["owners"]["retained_median_abs_hz_bounds"], [1, 4])
        self.assertEqual(unknown["owners"]["successor_owner_without_installed_factor"], 1)
        self.assertEqual(unknown["owners"]["successor_owner_also_installed_accepted"]["median_abs_hz"], 2.5)
