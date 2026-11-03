import json
from pathlib import Path
import tempfile
import unittest

from policy_audit import (
    HERE,
    bind_additional_plans,
    select,
    summarize_partition,
    validate_baseline_record,
    validate_challenger_metadata,
)


def start(score=1.0, x=None):
    return {
        "qualified": True,
        "success": True,
        "boundary": False,
        "gradient": 0.0,
        "audit": 0.0,
        "score": score,
        "x": x or [0.0, 0.0, 0.0],
    }


class PolicyAuditTests(unittest.TestCase):
    def test_selection_rule_uses_qualification_only(self):
        challenger = {"qualified": True, "score": -1000.0}
        incumbent = {"qualified": True, "score": 1000.0}
        self.assertEqual(select(challenger, incumbent), (challenger, "challenger"))
        self.assertEqual(select(None, incumbent), (incumbent, "iid_fallback"))
        self.assertEqual(select(challenger, None), (None, "failure"))

    def test_baseline_requires_binding_and_maximum_qualified_start(self):
        first, second = start(1.0), start(2.0, [1.0, 0.0, 0.0])
        record = {
            "index": 3,
            "session": "scan",
            "method": "iid",
            "starts": [first, second],
            "selected": {**second, "estimate_deg": [1.0, 2.0]},
        }
        self.assertTrue(
            validate_baseline_record(record, 3, "scan", {}, require_sources=False)
        )
        with self.assertRaises(AssertionError):
            validate_baseline_record(record, 4, "scan", {}, require_sources=False)
        record["selected"] = {**first, "estimate_deg": [1.0, 2.0]}
        with self.assertRaises(AssertionError):
            validate_baseline_record(record, 3, "scan", {}, require_sources=False)

    def test_failure_keeps_attempt_count_and_labels_matched_denominator(self):
        good = {
            "qualified": True,
            "baseline_qualified": True,
            "selection": "challenger",
            "raw_challenger_qualified": True,
            "error_m": 500.0,
            "baseline_error_m": 1000.0,
            "common_iid_held_gain": 2.0,
            "runtime_s": 1.0,
        }
        failed = {
            **good,
            "qualified": False,
            "baseline_qualified": False,
            "selection": "failure",
            "raw_challenger_qualified": False,
            "error_m": None,
            "baseline_error_m": None,
        }
        summary = summarize_partition([good, failed])
        self.assertEqual(summary["attempts"], 2)
        self.assertEqual(summary["policy_failures"], 1)
        self.assertIsNone(summary["whole_panel_metrics"])
        self.assertEqual(summary["whole_panel_status"], "unavailable")
        self.assertEqual(summary["matched_qualified_denominator"], 1)
        self.assertEqual(summary["matched_qualified_metrics"]["attempts"], 1)

    def test_additional_metadata_digests_are_enforced(self):
        import hashlib

        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "runs").mkdir()
            paths = {
                "plan_sha256": base / "plan.json",
                "identity_sidecar_sha256": base / "catalogue_identities.json",
                "incumbent_iid_sha256": base / "runs/00_iid.json",
                "screen_frozen_model_sha256": HERE / "source_balance/model.py",
                "adapter_sha256": HERE / "source_balance/additional_adapter.py",
                "additional_runner_sha256": HERE / "additional_fit.py",
                "additional_policy_sha256": HERE / "additional-policy.md",
            }
            for path in list(paths.values())[:3]:
                path.write_text("bound")
            metadata = {
                "variant": "source_receiver_equal",
                **{
                    key: hashlib.sha256(path.read_bytes()).hexdigest()
                    for key, path in paths.items()
                },
            }
            result = {"metadata": metadata}
            validate_challenger_metadata(
                result,
                base,
                base / "runs/00_iid.json",
                {},
                additional=True,
            )
            result["metadata"]["adapter_sha256"] = "wrong"
            with self.assertRaises(AssertionError):
                validate_challenger_metadata(
                    result,
                    base,
                    base / "runs/00_iid.json",
                    {},
                    additional=True,
                )

    def test_additional_plan_binding_rejects_manifest_substitution(self):
        # Exercise the essential frozen-to-assembled relation using the real
        # frozen plan and a temporary assembled plan with no artifact reads.
        frozen = json.loads((HERE / "additional-plan.json").read_text())
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            plan = {
                "config": frozen["config"],
                "inputs": [
                    {
                        "session_id": row["session_id"],
                        "manifest_sha256": row["manifest_sha256"],
                        "artifacts": [],
                    }
                    for row in frozen["captures"]
                ],
                "source_sha256": {
                    str(HERE / "additional-plan.json"): __import__(
                        "hashlib"
                    ).sha256((HERE / "additional-plan.json").read_bytes()).hexdigest(),
                    **frozen["source_sha256"],
                },
            }
            (base / "plan.json").write_text(json.dumps(plan))
            self.assertEqual(len(bind_additional_plans(base, {})["inputs"]), 12)
            plan["inputs"][0]["manifest_sha256"] = "sha256:wrong"
            (base / "plan.json").write_text(json.dumps(plan))
            with self.assertRaises(AssertionError):
                bind_additional_plans(base, {})


if __name__ == "__main__":
    unittest.main()
