import math
import unittest

import numpy as np
from scipy.stats import t

import age_scale


def row(dataset, session, track, number, residual, mask, age=1.0, rf=1.0):
    return dict(dataset=dataset, session_id=session, track_id=track, number=number,
                rf_hz=rf, residual=list(residual), mask=list(mask), age_days=age)


class AgeScaleTests(unittest.TestCase):
    def test_normalized_density_and_nested_control(self):
        residual = np.array([[-300.0, 0.0, 120.0]])
        scale = np.array([137.0])
        actual = age_scale.log_density(residual, np.array([17.0]), scale)[0]
        expected = t.logpdf((residual[0] - 17.0) / scale[0], df=4) - math.log(scale[0])
        np.testing.assert_allclose(actual, expected, rtol=0, atol=2e-15)
        np.testing.assert_array_equal(age_scale.scale_from_age([0.1, 4.0], 0.0), [100.0, 100.0])

    def test_profile_is_stationary_and_held_does_not_fit_offset(self):
        rows = []
        for dataset, shift in (("DS7", 0.0), ("DS8", 20.0), ("DS9", -15.0)):
            residual = np.array([-30., -10., 5., 18., 42., 900.]) + shift
            rows.append(row(dataset, dataset + "-scan", dataset + "-track", 1,
                            residual, [1, 1, 1, 1, 0, 0]))
        cases = age_scale.ProfiledCases.from_rows(rows)
        scales = age_scale.scale_from_age(cases.ages, 80.0)
        offsets = cases.profile(scales)
        for i, offset in enumerate(offsets):
            train = np.asarray(rows[i]["residual"])[np.asarray(rows[i]["mask"], bool)]
            r = offset - train
            gradient = np.sum(5 * r / (4 * scales[i] ** 2 + r * r)) + offset / 1e12
            self.assertLess(abs(gradient), 1e-7)
        changed = [dict(item) for item in rows]
        changed[0]["residual"] = list(changed[0]["residual"])
        changed[0]["residual"][-1] += 100000
        changed_cases = age_scale.ProfiledCases.from_rows(changed)
        np.testing.assert_allclose(changed_cases.profile(scales), offsets, rtol=0, atol=1e-12)

    def test_hierarchy_equalizes_datasets_scans_sources_and_tracks(self):
        rows = [
            row("DS7", "a", "a1", 1, [0, 1, 2], [1, 1, 0]),
            row("DS7", "a", "a2", 1, [0, 1, 2], [1, 1, 0]),
            row("DS7", "a", "a3", 2, [0, 1, 2], [1, 1, 0]),
            row("DS7", "b", "b1", 3, [0, 1, 2], [1, 1, 0]),
            row("DS8", "c", "c1", 4, [0, 1, 2], [1, 1, 0]),
            row("DS9", "d", "d1", 5, [0, 1, 2], [1, 1, 0]),
        ]
        weights = age_scale.hierarchical_weights(rows)
        self.assertAlmostEqual(weights.sum(), 1.0)
        for dataset in ("DS7", "DS8", "DS9"):
            self.assertAlmostEqual(sum(w for w, r in zip(weights, rows) if r["dataset"] == dataset), 1/3)
        self.assertAlmostEqual(weights[0], weights[1])
        self.assertAlmostEqual(weights[0] + weights[1], weights[2])
        self.assertAlmostEqual(weights[0] + weights[1] + weights[2], weights[3])


if __name__ == "__main__":
    unittest.main()
