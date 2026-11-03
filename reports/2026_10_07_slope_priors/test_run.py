"""Component-owned checks of matched starts, selection, and independent audits."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

import run
from test_bounded_fit import QuadraticObjective
from bounded_fit import fit_position


class RunnerTest(unittest.TestCase):
    def test_shared_starts_only_change_allowed_c_slopes_and_timing(self):
        initial = np.arange(10, dtype=float)
        initial[[3, 5]] = [-90, 100]
        before = initial.copy()
        digests = {}
        for option, width in run.OPTIONS.items():
            for arm in run.ARMS:
                for label, seed, shared_digest in run.seeds(initial, arm, width):
                    expected = before.copy()
                    if label == "zero-timing":
                        expected[7:] = 0
                    if arm == "zero-c":
                        expected[6] = 0
                    if width is not None:
                        expected[[3, 5]] = np.clip(expected[[3, 5]], -width, width)
                    np.testing.assert_array_equal(seed, expected)
                    digests.setdefault(label, set()).add(shared_digest)
        self.assertTrue(all(len(values)==1 for values in digests.values()))
        np.testing.assert_array_equal(initial, before)

    def test_independent_slope_audit_handles_both_receivers_and_signs(self):
        for index in (3, 5):
            for sign in (-1., 1.):
                target = np.zeros(9)
                target[index] = sign*70
                objective = QuadraticObjective(target)
                fitted = fit_position(objective, np.zeros(9), slope_half_width_hz_s=30.)
                value, gradient, _ = objective.evaluate(fitted.vector)
                receipt = run.audit(fitted.vector, gradient, objective, "fitted-c", np.zeros(2), 30.)
                self.assertTrue(receipt["feasible"])
                self.assertTrue(receipt["converged"])
                self.assertAlmostEqual(receipt["stationarity"], fitted.stationarity, places=7)
                self.assertIn(f"parameter:{index}:{'upper' if sign>0 else 'lower'}", receipt["slope_active_bounds"])
                # A small physical bound violation must be explicitly infeasible.
                bad = fitted.vector.copy()
                bad[index] += sign*.01
                self.assertFalse(run.audit(bad, gradient, objective, "fitted-c", np.zeros(2), 30.)["feasible"])

    def test_selection_uses_score_and_never_reference_error(self):
        common = dict(case="a", method="V16", arm="zero-c", origin="fit:association")
        rows = [dict(common, basin="b", selection_score=3., horizontal_error_m=0.),
                dict(common, basin="c", selection_score=2., horizontal_error_m=90000.)]
        self.assertEqual(run.select(rows, "a", "V16", "zero-c")["basin"], "c")

    def test_total_linear_slopes_use_calibration_coefficients(self):
        vector = np.array([0.,0.,0.,10.,0.,-20.,0.,0.,0.])
        objective = QuadraticObjective()
        objective.score = SimpleNamespace(common_sigma_s=3.)
        objective.observations = SimpleNamespace(receiver=np.array([0,0,1,1]),
                                                times_s=np.array([-1.,1.,-1.,1.]), time_center_s=0.,
                                                rf_hz=np.ones(4)*1e10, rf_center_hz=1e10,
                                                window_ids=("a","b","c","d"))
        objective.baseline = np.array([-50.,50.,-80.,80.])
        terms = SimpleNamespace(nll=20.,responsibilities=np.ones((4,2))*.5,
                                residual_hz=np.ones((4,2)),clutter_probability=np.zeros(4))
        region=dict(calibration_penalty=2.,calibration_vector=[0,0,0,3,0,4,0,0,0],
                    calibration_fields={},center_km=[0,0])
        with patch.object(objective,"evaluate",return_value=(20.,np.zeros(9),terms)):
            row=run.candidate(objective,region,vector,"window30","zero-c","b","V16","initial")
        self.assertEqual(row["calibration_postfit_slopes_hz_s"],[3,4])
        self.assertEqual(row["total_linear_slopes_hz_s"],[13.,-16.])
        self.assertAlmostEqual(row["frozen_baseline_regressed_slopes_hz_s"]["0"],50.)
        self.assertAlmostEqual(row["frozen_baseline_regressed_slopes_hz_s"]["1"],80.)

    def test_fixture_digest_is_checked_before_contract_construction(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs = Path(directory)/"inputs"
            inputs.mkdir()
            path = inputs/"input.npz"
            path.write_bytes(b"tampered")
            case = {"basins":{"b":{"file":"inputs/input.npz","sha256":"sha256:wrong"}}}
            with self.assertRaisesRegex(ValueError, "fixture digest mismatch"):
                run.load_objective(inputs, case, "b", "V16")

    def test_runner_retains_initials_and_has_no_output_seed_sharing(self):
        initial = np.array([1., 2., 3., 80., 5., -90., 7., 1., 2.])
        region = dict(file="unused.npz", sha256="fixture", initial_vector=initial.tolist(),
                      center_km=initial[:2].tolist(), calibration_penalty=4.,
                      calibration_fields={}, calibration_vector=[])
        case = dict(case="a", prior={}, basins={"b":region},
                    methods={"V16":["b"],"T1AT":["b"]}, evaluation_reference=[0.,0.])
        calls=[]
        def fake_fit(objective, start, **settings):
            calls.append((start.copy(), settings))
            vector = start.copy()
            vector[2] = 0 # Optimized outputs differ from all starts.
            return SimpleNamespace(vector=vector, elapsed_s=.01, evaluations=2,
                                   stop_reason="optimizer-success", stationarity=0.,
                                   objective=float(vector@vector))
        def fake_candidate(objective, region, vector, option, arm, basin, method, origin, **extra):
            value=float(vector@vector)
            return dict(option=option,arm=arm,basin=basin,method=method,origin=origin,
                        vector=vector.tolist(),objective=value,selection_score=value+4.,
                        stationarity=0.,converged=True,feasible=True,**extra)
        with tempfile.TemporaryDirectory() as directory:
            manifest=Path(directory)/"manifest.json"
            manifest.write_text(json.dumps({"cases":[case]}))
            with patch.object(run,"load_objective",return_value=SimpleNamespace(size=9)), patch.object(run,"audit",return_value={"feasible":True}), patch.object(run,"candidate",side_effect=fake_candidate), patch.object(run,"fit_position",side_effect=fake_fit), patch.object(run,"RegionalPrior"), patch.object(run,"coordinates",return_value=[0.,0.]):
                output=run.run("window30",Path(directory)/"results",manifest)
            self.assertEqual(len(output["runs"]),8)
            self.assertEqual(len(output["candidates"]),16)
            self.assertEqual(len(output["selections"]),4)
            for start, settings in calls:
                self.assertEqual(start[2],3.)
                self.assertEqual(settings["maximum_seconds"],6.)
                self.assertEqual(settings["maximum_iterations"],300)
                self.assertEqual(settings["local_radius_km"],25.)
            self.assertEqual(output["status"],"complete")
            self.assertTrue((Path(directory)/"results/results.json").exists())
            with self.assertRaises(FileExistsError):
                run.run("window30",Path(directory)/"results",manifest)
            with patch.object(run,"load_objective",return_value=SimpleNamespace(size=9)), patch.object(run,"audit",return_value={"feasible":False}), patch.object(run,"candidate",side_effect=fake_candidate), patch.object(run,"fit_position",side_effect=fake_fit), patch.object(run,"RegionalPrior"), patch.object(run,"coordinates",return_value=[0.,0.]):
                infeasible=run.run("window30",Path(directory)/"infeasible",manifest)
            self.assertEqual(len(infeasible["candidates"]),8)
            self.assertTrue(all(row["origin"].startswith("fit:") for row in infeasible["candidates"]))
            self.assertTrue(all(not row["initial_feasible"] for row in infeasible["seeds"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
