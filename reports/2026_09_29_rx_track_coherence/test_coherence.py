import copy
import unittest

import numpy as np
from coherence import analyze, describe, match, select


def track(name, rx, offset=0, start=0):
    t = np.arange(20.0) + start
    y = -1200 * t + 3 * t**2 + offset
    return {
        "track_id": name,
        "receiver_id": rx,
        "channel": 1,
        "rf_hz": 10710000000,
        "times_s": t.tolist(),
        "measured_hz": y.tolist(),
        "training_mask": (np.arange(20) % 3 != 0).tolist(),
        "visits": (np.arange(20) + start).tolist(),
    }


class Tests(unittest.TestCase):
    def test_timestamp_visit_matching_and_ambiguity(self):
        a, b = track("a", 0), track("b", 1)
        b["times_s"][0] += 0.0005
        b["visits"][1] = 999
        i, j, amb = match(a, b)
        self.assertEqual(len(i), 19)
        self.assertEqual(amb, 0)
        self.assertEqual(i.tolist(), j.tolist())
        b["times_s"][2] = b["times_s"][3]
        b["visits"][2] = b["visits"][3]
        i, j, amb = match(a, b)
        self.assertEqual(amb, 2)
        self.assertNotIn(3, i)

    def test_known_offset_and_held_controls(self):
        a, b = track("a", 0, offset=250), track("b", 1)
        result = analyze({"session_id": "toy", "tracks": [a, b]})
        p = result["pairs"][0]
        self.assertTrue(p["selected"])
        self.assertEqual(p["offset_hz"], 250)
        e = p["evaluation"]
        self.assertTrue(e["held_shape_pass"])
        self.assertEqual(e["held_median_abs_hz"], 0)
        self.assertGreater(e["narrow_minus_broad_nats"], 0)
        self.assertGreater(e["actual_minus_reversed_nats"], 0)

    def test_held_changes_do_not_change_pair_selection(self):
        a, b = track("a", 0, 250), track("b", 1)
        original = analyze({"session_id": "toy", "tracks": [a, b]})["pairs"][0]
        for i, training in enumerate(b["training_mask"]):
            if not training:
                b["measured_hz"][i] += 500
        changed = analyze({"session_id": "toy", "tracks": [a, b]})["pairs"][0]
        for field in (
            "selected",
            "offset_hz",
            "training_mean_log_density",
            "margins_nats_per_observation",
        ):
            self.assertEqual(original[field], changed[field])
        self.assertFalse(changed["evaluation"]["held_shape_pass"])
        self.assertEqual(changed["evaluation"]["held_median_abs_hz"], 500)

    def test_ambiguous_track_ties_remain_unselected(self):
        a, b, c = track("a", 0), track("b", 1), track("c", 1)
        result = analyze({"session_id": "toy", "tracks": [a, b, c]})
        self.assertFalse(any(p["selected"] for p in result["pairs"]))

    def test_reciprocal_best_prevents_track_reuse(self):
        pairs = []
        for a in ("a", "b"):
            p = describe(track(a, 0), track("x", 1))
            p["training_mean_log_density"] = -5 if a == "a" else -6
            pairs.append(p)
        selected = select(pairs)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["rx0"], "a")

    def test_shared_offset_transfer_excludes_target_and_held(self):
        tracks = []
        for k in range(3):
            tracks += [track(f"a{k}", 0, 250, start=k * 100), track(f"b{k}", 1, start=k * 100)]
        result = analyze({"session_id": "toy", "tracks": tracks})
        chosen = [p for p in result["pairs"] if p["selected"]]
        self.assertEqual(len(chosen), 3)
        for p in chosen:
            e = p["evaluation"]
            self.assertEqual(e["donor_count"], 2)
            self.assertEqual(e["donor_offset_hz"], 250)
            self.assertTrue(e["donor_held_shape_pass"])
        changed = copy.deepcopy(tracks)
        changed[0]["measured_hz"] = (np.asarray(changed[0]["measured_hz"]) + 1000).tolist()
        out = analyze({"session_id": "toy", "tracks": changed})
        target = next(p for p in out["pairs"] if p["selected"] and p["rx0"] == "a0")
        self.assertEqual(target["offset_hz"], 1250)
        self.assertEqual(target["evaluation"]["donor_offset_hz"], 250)
        self.assertFalse(target["evaluation"]["donor_held_shape_pass"])

    def test_sparse_training_and_held_unavailability(self):
        a, b = track("a", 0), track("b", 1)
        a["training_mask"] = b["training_mask"] = [True] * 20
        result = analyze({"session_id": "toy", "tracks": [a, b]})["pairs"][0]
        self.assertTrue(result["selected"])
        self.assertFalse(result["evaluation"]["held_available"])
        a["training_mask"] = b["training_mask"] = [True] * 4 + [False] * 16
        result = analyze({"session_id": "toy", "tracks": [a, b]})["pairs"][0]
        self.assertFalse(result["eligible"])
        self.assertFalse(result["selected"])


if __name__ == "__main__":
    unittest.main()
