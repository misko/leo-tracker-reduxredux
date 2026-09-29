import copy
import unittest

import numpy as np
from correction import calibrations, correct_document, correct_track


def fixture():
    pairs = []
    for i in range(6):
        t = np.arange(10.0) + 15 * i
        mask = np.arange(10) % 2 == 0
        mean = 10000 - 100 * t + 0.1 * t**2
        delta = 50 + 2 * t
        pairs.append(
            dict(
                rx0=f"a{i}",
                rx1=f"b{i}",
                channel=1,
                rf_hz=10710000000,
                selected=True,
                training=mask.tolist(),
                times_s=t.tolist(),
                rx0_hz=(mean + delta / 2).tolist(),
                rx1_hz=(mean - delta / 2).tolist(),
            )
        )
    return dict(session_id="synthetic", pairs=pairs)


def track(pair, rx):
    return dict(
        track_id=pair[f"rx{rx}"],
        times_s=pair["times_s"],
        measured_hz=pair[f"rx{rx}_hz"],
        channel=pair["channel"],
        rf_hz=pair["rf_hz"],
    )


class Tests(unittest.TestCase):
    def test_recovery_and_common_mode_ambiguity(self):
        s = fixture()
        c = calibrations(s)
        p = s["pairs"][2]
        outputs = {}
        for arm in ("symmetric", "rx0_anchor", "rx1_anchor"):
            ys = [correct_track(track(p, rx), c[p[f"rx{rx}"]], arm)[0] for rx in (0, 1)]
            np.testing.assert_allclose(np.diff(ys[0] - ys[1]), 0, atol=1e-10)
            outputs[arm] = ys
        # All conventions remove relative drift but disagree on common drift.
        diff = outputs["rx0_anchor"][0] - outputs["rx1_anchor"][0]
        np.testing.assert_allclose(np.diff(diff), 2, atol=1e-10)
        np.testing.assert_allclose(c[p["rx0"]]["fit"]["drift_hz_s"], 2)

    def test_held_isolation(self):
        s = fixture()
        changed = copy.deepcopy(s)
        for p in changed["pairs"]:
            for rx in (0, 1):
                for j, training in enumerate(p["training"]):
                    if not training:
                        p[f"rx{rx}_hz"][j] += (rx + 1) * 1e6
        self.assertEqual(calibrations(s), calibrations(changed))

    def test_target_response_exclusion(self):
        s = fixture()
        changed = copy.deepcopy(s)
        p = changed["pairs"][0]
        p["rx0_hz"] = [v + 1234 for v in p["rx0_hz"]]
        p["rx1_hz"] = [v - 1234 for v in p["rx1_hz"]]
        self.assertEqual(calibrations(s)["a0"], calibrations(changed)["a0"])

    def test_swap_symmetry(self):
        s = fixture()
        swapped = copy.deepcopy(s)
        for p in swapped["pairs"]:
            p["rx0"], p["rx1"] = p["rx1"], p["rx0"]
            p["rx0_hz"], p["rx1_hz"] = p["rx1_hz"], p["rx0_hz"]
        a, b = calibrations(s), calibrations(swapped)
        for arm, other in (("symmetric", "symmetric"), ("rx0_anchor", "rx1_anchor")):
            for rx in (0, 1):
                t = track(s["pairs"][0], rx)
                np.testing.assert_allclose(
                    correct_track(t, a[t["track_id"]], arm)[0],
                    correct_track(t, b[t["track_id"]], other)[0],
                )

    def test_zero_fallback_and_preservation(self):
        s = fixture()
        tracks = [track(p, rx) for p in s["pairs"] for rx in (0, 1)]
        tracks.append({**tracks[0], "track_id": "unmatched"})
        d = dict(session_id=s["session_id"], tracks=tracks)
        original = copy.deepcopy(d)
        out, receipts = correct_document(d, s, "none")
        self.assertEqual(d, original)
        self.assertEqual(len(out["tracks"]), len(tracks))
        for a, b in zip(tracks, out["tracks"], strict=True):
            np.testing.assert_array_equal(a["measured_hz"], b["y"])
        c = calibrations(s)["a0"]
        c["fit"]["drift_hz_s"] = 0
        np.testing.assert_array_equal(
            correct_track(tracks[0], c, "symmetric")[0], tracks[0]["measured_hz"]
        )
        c["fit"]["qualified"] = False
        np.testing.assert_array_equal(
            correct_track(tracks[0], c, "symmetric")[0], tracks[0]["measured_hz"]
        )
        self.assertEqual(correct_track(tracks[-1], None, "symmetric")[1]["reason"], "no_pair")

    def test_binding_and_donor_gate(self):
        s = fixture()
        s["pairs"] = s["pairs"][:4]
        c = calibrations(s)["a0"]
        self.assertFalse(c["fit"]["qualified"])
        t = track(s["pairs"][0], 0)
        t["rf_hz"] += 1
        with self.assertRaises(ValueError):
            correct_track(t, c, "symmetric")
        with self.assertRaises(ValueError):
            correct_document(dict(session_id="other", tracks=[]), s, "none")


if __name__ == "__main__":
    unittest.main()
