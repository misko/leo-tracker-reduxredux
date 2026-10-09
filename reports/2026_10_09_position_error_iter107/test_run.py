"""Synthetic actual-driver tests; never load recordings or run optimizers."""

import copy
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cohort  # noqa: E402

RUN_SPEC = importlib.util.spec_from_file_location("cohort107_run_test", HERE / "run.py")
run = importlib.util.module_from_spec(RUN_SPEC)
RUN_SPEC.loader.exec_module(run)


class DriverTest(unittest.TestCase):
    def test_historical_loader_has_verified82_protocol_adapter(self):
        baseline = sys.modules["baseline"]
        self.assertEqual(baseline.protocol.func.__name__, "verified_protocol")
        self.assertEqual(
            Path(baseline.__file__).resolve(),
            HERE.parent / "2026_10_08_position_error_iter01/baseline.py",
        )
        self.assertEqual(cohort.HISTORICAL["load"].__module__, "cohort_inputs")

    def case(self):
        return dict(
            observations="obs",
            bank="bank",
            prior="prior",
            tracks="tracks",
            binding={"input_digest": "i", "score_signature": "s", "bank_signature": "b"},
        )

    def test_three_current_passes_and_fresh_joint_namespace(self):
        calls = []
        joint = []

        def regional(*args, **kwargs):
            calls.append(kwargs["configuration"].basin_separation_km)
            return {"finals": []}

        def stages(*args):
            joint.append(args[-1]("b7:B7:fitted-c", 90, lambda: None))
            return {}, {}, []

        with (
            patch.object(run, "run_hard60", regional),
            patch.object(run, "run_joint_stages", stages),
        ):
            value = run.run_baseline(self.case(), object(), lambda key, *args: key, 10**20)
        self.assertEqual(calls, [12.5, 25.0, 50.0])
        self.assertEqual(set(value["regions"]), {"baseline", "sep25", "sep50"})
        self.assertEqual(joint, ["baseline107:b7:B7:fitted-c"])

    def test_candidate_preserves_every_ordinary_region(self):
        baseline = {
            "regions": {
                "baseline": {"finals": []},
                "sep25": {"finals": []},
                "sep50": {"finals": []},
            },
            "operational": {},
        }
        before = copy.deepcopy(baseline)
        with (
            patch.object(
                run.pilot,
                "regional_triggers",
                return_value={"candidates": [{"identity": {"any": "grid"}}]},
            ),
            patch.object(run.pilot, "recovered_region", return_value={"finals": []}),
            patch.object(run, "run_joint_stages", return_value=({}, {}, [])),
            patch.object(run, "regional_winners", return_value={}),
        ):
            value = run.run_candidate(self.case(), baseline, lambda *args: None)
        self.assertEqual(baseline, before)
        self.assertEqual(len(value["regions"]), 4)

    def test_local_overlay_precedes_source_and_refuses_foreign_protocol(self):
        class Source:
            def get(self, key):
                return {"result": "external", "reason": None}

        with tempfile.TemporaryDirectory() as temp:
            overlay = run.Overlay(Path(temp), "frozen", Source(), 10**20)
            overlay.put("key", {"result": "local", "reason": None})
            self.assertEqual(overlay.get("key")["result"], "local")
            self.assertEqual(overlay.get("other")["result"], "external")
            other = run.Overlay(Path(temp), "wrong", Source(), 10**20)
            with self.assertRaises(AssertionError):
                other.get("key")

    def test_legacy_coarse_requires_both_policy_and_metadata(self):
        class Store:
            def get(self, key):
                raise AssertionError("Ineligible source must not be accessed")

        source = cohort.Sources.__new__(cohort.Sources)
        source.case = {
            "ordinary_compatibility": {"eligible": False},
            "legacy_coarse_eligibility": {"metadata_eligible": True},
        }
        source.metrics = {"get_calls": 0}
        source.allow_legacy_coarse = False
        source.store = Store()
        self.assertIsNone(source.get("b7-shared:point:1:2"))
        source.allow_legacy_coarse = True
        source.case["legacy_coarse_eligibility"]["metadata_eligible"] = False
        self.assertIsNone(source.get("b7-shared:point:1:2"))

    def test_noncoarse_never_uses_legacy_alias(self):
        source = cohort.Sources.__new__(cohort.Sources)
        source.case = {"ordinary_compatibility": {"eligible": False}}
        source.research = []
        source.allow_legacy_coarse = True
        source.metrics = {"get_calls": 0}
        self.assertIsNone(source.get("current:point:1:2:calibration"))

    def test_research_get_requires_exact_prefix(self):
        class Cache:
            def get(self, key):
                return {"result": "exact", "reason": None}

        source = cohort.Sources.__new__(cohort.Sources)
        source.case = {"ordinary_compatibility": {"eligible": False}}
        source.research = [("current:", Cache())]
        source.metrics = {"get_calls": 0, "research_exact_hits": 0}
        self.assertEqual(source.get("current:point:1:2:calibration")["result"], "exact")
        self.assertIsNone(source.get("foreign:point:1:2:calibration"))

    def test_saved_coarse_convergence_needs_current_kkt(self):
        class Model:
            def evaluate(self, vector):
                return 1, np.zeros(8), None

        class Problem:
            def __init__(self, *args, **kwargs):
                pass

            def feasible(self, vector):
                return True

            def stationarity(self, *args):
                return 0.01

        fit = {"vector": [1, 2, 0, 0, 0, 0, 0, 0], "converged": True}
        value = {"result": {"bootstrap": {"vector": fit["vector"]}, "fits": {}}}
        with (
            patch.object(cohort.pilot, "verify_coarse", return_value=(Model(), fit)),
            patch.object(cohort, "_Problem", Problem),
            self.assertRaises(AssertionError),
        ):
            cohort.verify_point(self.case(), "point:1:2", value)

    def test_saved_coarse_must_belong_to_exact_point(self):
        fit = {"vector": [1, 3, 0, 0, 0, 0, 0, 0], "converged": False}
        value = {"result": {"bootstrap": {"vector": fit["vector"]}}}
        with (
            patch.object(cohort.pilot, "verify_coarse", return_value=(object(), fit)),
            self.assertRaises(AssertionError),
        ):
            cohort.verify_point(self.case(), "point:1:2", value)


if __name__ == "__main__":
    unittest.main()
