import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

MODULE_PATH = Path(__file__).with_name("run_experiment.py")
SPEC = importlib.util.spec_from_file_location("ds5_search", MODULE_PATH)
search = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(search)


class CandidateTests(unittest.TestCase):
    def candidate(self, **updates):
        value = {
            "fractional_complete": 1,
            "margin": 0.026,
            "window_index": 2,
            "epoch": 10,
            "fractional_offset_samples": 0.25,
            "tracking_cfo_hz": 1000.0,
            "exact_score": 0.1,
            "control_score": 0.02,
        }
        value.update(updates)
        return value

    def test_gate_is_strict_and_requires_fractional_completion(self):
        self.assertTrue(search.gated(self.candidate()))
        self.assertFalse(search.gated(self.candidate(margin=0.025)))
        self.assertFalse(search.gated(self.candidate(fractional_complete=0)))

    def test_digest_field_accepts_dataset_prefix_and_rejects_malformed_values(self):
        value = "a" * 64
        self.assertEqual(search.expected_digest("sha256:" + value), value)
        self.assertEqual(search.expected_digest(value), value)
        with self.assertRaisesRegex(ValueError, "invalid SHA-256"):
            search.expected_digest("sha256:no")

    def test_identity_match_includes_fractional_epoch_wrap_and_cfo(self):
        rate = 2_500_000
        period = rate / 750
        policy = {
            "maximum_cfo_difference_hz": 8000,
            "maximum_circular_epoch_difference_us": 2,
            "require_same_window": True,
        }
        left = self.candidate(epoch=0, fractional_offset_samples=0.25)
        right = self.candidate(
            epoch=int(period) - 1,
            fractional_offset_samples=(period % 1) + 0.25,
            tracking_cfo_hz=8999.0,
        )
        self.assertTrue(search.candidates_match(left, right, rate, policy))
        self.assertFalse(
            search.candidates_match(
                left, self.candidate(tracking_cfo_hz=9001.0), rate, policy
            )
        )
        self.assertFalse(
            search.candidates_match(left, self.candidate(window_index=3), rate, policy)
        )

    def test_inventory_reports_candidate_and_case_retention_separately(self):
        policy = {
            "maximum_cfo_difference_hz": 8000,
            "maximum_circular_epoch_difference_us": 2,
            "require_same_window": True,
        }
        reference = [self.candidate(), self.candidate(epoch=100, tracking_cfo_hz=20_000)]
        actual = [self.candidate(epoch=10, tracking_cfo_hz=1001)]
        result = search.compare_candidate_inventories(actual, reference, 2_500_000, policy)
        self.assertTrue(result["case_retained"])
        self.assertEqual(result["matched_reference_candidates"], 1)
        self.assertEqual(result["lost_reference_candidates"], 1)

    def test_constructed_pilot_requires_injected_window_timing_and_cfo(self):
        truth = {
            "starlink_model_present": True,
            "receivers": [
                {
                    "window": 2,
                    "epoch_samples": 10,
                    "fractional_delay_samples": 0.25,
                    "cfo_hz": 1000,
                }
            ],
        }
        result = search.compare_constructed_pilot(
            [self.candidate()], truth, 0, 2_500_000
        )
        self.assertTrue(result["matched"])
        result = search.compare_constructed_pilot(
            [self.candidate(window_index=3)], truth, 0, 2_500_000
        )
        self.assertFalse(result["matched"])


class DatasetDisciplineTests(unittest.TestCase):
    def test_case_loading_filters_metadata_before_any_iq_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(
                json.dumps(
                    [
                        {"case_id": "d", "split": "dev", "rate_hz": 2_500_000},
                        {"case_id": "h", "split": "holdout", "rate_hz": 5_000_000},
                    ]
                )
            )
            cases, inventory = search.load_cases(path, "dev")
            self.assertEqual([case["case_id"] for case in cases], ["d"])
            self.assertEqual(inventory["selected_by_rate"], {"2500000": 1})

    def test_load_iq_checks_hash_shape_dtype_and_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = np.zeros((300_000, 2, 2), dtype="<i2")
            path = root / "case.npy"
            np.save(path, values, allow_pickle=False)
            case = {
                "case_id": "case",
                "rate_hz": 2_500_000,
                "raw_npy": {"path": path.name, "sha256": search.digest(path)},
            }
            loaded = search.load_iq(case, root)
            self.assertEqual(loaded.shape, values.shape)
            case["raw_npy"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                search.load_iq(case, root)

    def test_validation_refuses_unfrozen_development_config(self):
        path = Path(__file__).with_name("development_search.json")
        with self.assertRaisesRegex(ValueError, "frozen configuration"):
            search.load_config(path, "validation")

    def test_control_accepts_development_config_as_separate_search_stratum(self):
        path = Path(__file__).with_name("development_search.json")
        config = search.load_config(path, "control")
        self.assertEqual(config["stage"], "development_search")


if __name__ == "__main__":
    unittest.main()
