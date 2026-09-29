import copy
import unittest

import numpy as np
from align import analyze, feature, fit, predict


def fixture(drift=0.7, lag=0.15):
    pairs = []
    for k, (center, slope) in enumerate(
        zip([30, 70, 110, 150, 190, 230], [-2100, -700, -1600, 500, 1300, -100], strict=True)
    ):
        t = center + np.arange(21.0) - 10
        mask = np.arange(21) % 3 != 0
        mean = 10000 + slope * (t - center) + 0.1 * (t - center) ** 2
        derivative = slope + 0.2 * (t - center)
        delta = 120 + drift * t + lag * derivative
        pairs.append(
            {
                "rx0": f"a{k}",
                "rx1": f"b{k}",
                "selected": True,
                "channel": 1,
                "rf_hz": 10710000000,
                "training": mask.tolist(),
                "held": (~mask).tolist(),
                "times_s": t.tolist(),
                "rx0_hz": (mean + delta / 2).tolist(),
                "rx1_hz": (mean - delta / 2).tolist(),
                "difference_hz": delta.tolist(),
                "offset_hz": float(np.median(delta[mask])),
                "evaluation": {"held_available": True},
            }
        )
    return {"session_id": "toy", "dataset": "synthetic", "pairs": pairs}


class Tests(unittest.TestCase):
    def test_injected_alignment_recovery(self):
        for drift, lag, model in (
            (0, 0, "constant"),
            (0.7, 0, "drift"),
            (0, 0.15, "slope"),
            (0.7, 0.15, "both"),
        ):
            results = analyze(fixture(drift, lag))
            for row in results["rows"]:
                f = row["models"][model]["fit"]
                self.assertTrue(f["qualified"])
                self.assertAlmostEqual(f["drift_hz_s"], drift, places=9)
                self.assertAlmostEqual(f["slope_coefficient_s"], lag, places=9)
                self.assertLess(row["models"][model]["held"]["p90_abs_hz"], 1e-8)

    def test_held_isolation(self):
        doc = fixture()
        old = analyze(doc)
        changed = copy.deepcopy(doc)
        for p in changed["pairs"]:
            for i, held in enumerate(p["held"]):
                if held:
                    p["rx0_hz"][i] += 10000
                    p["difference_hz"][i] += 10000
        new = analyze(changed)
        for a, b in zip(old["rows"], new["rows"], strict=True):
            self.assertEqual(a["feature"], b["feature"])
            for model in a["models"]:
                self.assertEqual(a["models"][model]["fit"], b["models"][model]["fit"])
                if "held" in a["models"][model]:
                    self.assertEqual(
                        a["models"][model]["held"]["prediction_hz"],
                        b["models"][model]["held"]["prediction_hz"],
                    )
                    self.assertNotEqual(
                        a["models"][model]["held"]["log_score"],
                        b["models"][model]["held"]["log_score"],
                    )

    def test_target_differences_excluded_from_calibration(self):
        doc = fixture()
        old = analyze(doc)["rows"][0]
        p = doc["pairs"][0]
        p["rx0_hz"] = (np.array(p["rx0_hz"]) + 500).tolist()
        p["rx1_hz"] = (np.array(p["rx1_hz"]) - 500).tolist()
        p["difference_hz"] = (np.array(p["difference_hz"]) + 1000).tolist()
        p["offset_hz"] += 1000
        new = analyze(doc)["rows"][0]
        for model in old["models"]:
            self.assertEqual(old["models"][model]["fit"], new["models"][model]["fit"])
            if "held" in old["models"][model]:
                np.testing.assert_allclose(
                    old["models"][model]["held"]["prediction_hz"],
                    new["models"][model]["held"]["prediction_hz"],
                    atol=1e-9,
                )

    def test_median_control_and_no_target_donor(self):
        doc = fixture()
        out = analyze(doc)
        for i, row in enumerate(out["rows"]):
            expected = np.median([p["offset_hz"] for j, p in enumerate(doc["pairs"]) if i != j])
            self.assertEqual(row["models"]["median"]["fit"]["intercept_hz"], expected)
            self.assertNotIn((row["rx0"], row["rx1"]), row["donor_ids"])

    def test_donor_count_rank_and_bounds(self):
        pairs = fixture()["pairs"]
        features = [feature(p) for p in pairs]
        self.assertFalse(fit(pairs[:3], features[:3], "constant")["qualified"])
        same = [{**f, "slope_hz_s": 100} for f in features]
        self.assertEqual(fit(pairs, same, "slope")["reason"], "alignment_rank")
        for drift, lag in ((21, 0), (0, 6)):
            p = fixture(drift, lag)["pairs"]
            f = [feature(a) for a in p]
            self.assertEqual(fit(p, f, "both")["reason"], "coefficient_bound")

    def test_deterministic_permutation_control(self):
        doc = fixture(0, 0.15)
        a = analyze(doc)
        b = analyze({**doc, "pairs": list(reversed(doc["pairs"]))})
        self.assertEqual(a, b)
        comparisons = []
        for row in a["rows"]:
            right = row["models"]["slope"]
            wrong = row["models"]["slope_permuted"]
            if "held" in wrong:
                comparisons.append(right["held"]["log_score"] > wrong["held"]["log_score"])
        self.assertTrue(comparisons and all(comparisons))

    def test_polynomial_feature_and_scalar_prediction(self):
        p = fixture()["pairs"][0]
        f = feature(p)
        self.assertAlmostEqual(f["acceleration_hz_s2"], 0.2, places=10)
        self.assertAlmostEqual(f["slope_hz_s"], -2100 + 0.2 * (f["center_s"] - 30), places=10)
        a = {"intercept_hz": 4, "drift_hz_s": 2, "reference_s": 0, "slope_coefficient_s": 0}
        self.assertEqual(float(predict(a, f, 3)), 10)


if __name__ == "__main__":
    unittest.main()
