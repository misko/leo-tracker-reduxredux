from itertools import product
import gzip
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import numpy as np

from reports.ALGO08.v3.profiled_grid_fidelity import audit, predictive_error, scalar_witness


class ProfiledGridFidelityTest(TestCase):
    def test_perfect_conditioning_and_stationarity_can_miss_the_score_gate(self):
        low, saddle, high = scalar_witness()
        self.assertLess(low["slope"], 1.)
        self.assertGreater(saddle["slope"], 1.)
        self.assertLess(high["slope"], 1.)
        for result in (low, high):
            self.assertLess(result["log_residual"], 1e-12)
            self.assertEqual(result["reciprocal_condition"], 1.)
        self.assertGreater(abs(low["full_score"]-high["full_score"]), 90.)

    def test_relative_rate_bound_encloses_gaussian_drift_for_both_signs(self):
        u = np.array([[1., 2.], [3., -1.], [0.5, 1.]])
        y = np.array([2., -4., 5.])
        v = np.array([[2., 1.], [4., -1.], [3., 0.5]])
        prediction = np.array([6., 3., -2.])
        bias = np.array([1., 1., 0.])
        base = np.diag([2., 3., 4.]) + np.outer(bias, bias)

        def exact(weights, prior):
            normal = u.T @ (weights[:, None]*u) + np.diag(prior)
            mean = np.linalg.solve(normal, u.T @ (weights*y))
            covariance = base + v @ np.linalg.solve(normal, v.T)
            error = prediction-v@mean
            quadratic = error @ np.linalg.solve(covariance, error)
            curved = (y-u@mean)**2 @ weights + mean**2 @ prior
            return curved, quadratic, quadratic+np.linalg.slogdet(covariance)[1]

        weights, prior = np.array([1.0, 0.5, 2.]), np.array([1.5, 2.5])
        curved, quad, old = exact(weights, prior)
        for radius in (1e-5, .03, .2):
            bound = predictive_error(radius, curved, quad, rank=2)
            for direction in product((-radius, radius), repeat=5):
                scales = np.exp(direction)
                _, _, changed = exact(weights*scales[:3], prior*scales[3:])
                self.assertLessEqual(abs(changed-old), bound)

    def test_predictive_bound_cannot_infer_a_rate_radius_from_a_large_score(self):
        self.assertEqual(predictive_error(0., 12., 400., 3), 0.)
        self.assertGreater(predictive_error(1e-5, 25., 1000., 3), .005)
        with self.assertRaises(ValueError):
            predictive_error(-1e-5, 0., 0., 1)

    def test_original_failed_grid_is_read_back_from_the_digest_bound_receipt(self):
        path = Path(__file__).parents[2]/"reports/ALGO08/v3/measurements/profiled-grid-export-south.json.gz"
        result = audit(path)["offers"]
        self.assertFalse(result["containing"]["accepted"])
        self.assertTrue(result["omitted"]["accepted"])
        outlier = result["containing"]["stats"]["c0"]
        self.assertEqual(outlier["worst_index"], 39)
        self.assertAlmostEqual(outlier["worst_change"], .016604073468442948, places=13)
        rows = [item for offer in result.values() for item in offer["stats"].values()]
        self.assertEqual(sum(item["count"] for item in rows), 590)
        self.assertEqual(sum(item["over_limit"] for item in rows), 1)
        with TemporaryDirectory() as area:
            modified = Path(area)/"receipt.json.gz"
            modified.write_bytes(gzip.compress(b"{}"))
            with self.assertRaisesRegex(ValueError, "receipt changed"):
                audit(modified)
