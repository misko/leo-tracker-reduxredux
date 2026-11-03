import hashlib
import tempfile
from pathlib import Path
import unittest

from model_audit import (
    HERE,
    summarize_partition,
    validate_model_metadata,
    validate_receipt,
)


def row(index, *, model=True, baseline=True):
    return {
        "index": index,
        "qualified": model,
        "model_qualified": model,
        "baseline_qualified": baseline,
        "error_m": 500.0 if model else None,
        "baseline_error_m": 1000.0 if baseline else None,
        "common_iid_held_gain": 2.0 if model else None,
        "runtime_s": 1.0,
    }


class ModelAuditTests(unittest.TestCase):
    def test_failure_preserves_full_attempts_and_only_matches_pairs(self):
        summary = summarize_partition([
            row(0),
            row(1, model=False),
            row(2, model=False, baseline=False),
        ])
        self.assertEqual(summary["attempts"], 3)
        self.assertEqual(summary["model_failure_indices"], [1, 2])
        self.assertEqual(summary["baseline_failure_indices"], [2])
        self.assertEqual(summary["whole_panel_status"], "unavailable")
        self.assertIsNone(summary["whole_panel_metrics"])
        self.assertNotIn("median_m", summary)
        self.assertEqual(summary["matched_qualified_denominator"], 1)
        self.assertEqual(summary["matched_qualified_metrics"]["attempts"], 1)

    def test_complete_panel_exposes_aggregate_compatible_metrics(self):
        summary = summarize_partition([row(0), row(1)])
        self.assertEqual(summary["whole_panel_status"], "complete")
        self.assertEqual(summary["attempts"], 2)
        self.assertEqual(summary["median_m"], 500.0)
        self.assertEqual(summary["whole_panel_metrics"]["qualified"], 2)

    def test_receipt_identity_and_terminal_fields_are_strict(self):
        receipt = {
            "family": "family",
            "variant": "variant",
            "index": 4,
            "exit_code": 0,
            "wall_s": 1.0,
        }
        validate_receipt(receipt, "family", "variant", 4)
        receipt["index"] = 5
        with self.assertRaises(AssertionError):
            validate_receipt(receipt, "family", "variant", 4)

    def test_additional_temper_metadata_binds_every_layer(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "runs").mkdir()
            paths = {
                "incumbent_iid_sha256": base / "runs/00_iid.json",
                "incumbent_iid_receipt_sha256": base / "runs/00_iid.receipt.json",
                "plan_sha256": base / "plan.json",
                "identity_sidecar_sha256": base / "catalogue_identities.json",
                "screen_frozen_model_sha256": HERE / "source_balance/model.py",
                "adapter_sha256": HERE / "source_balance/additional_adapter.py",
                "additional_adapter_sha256": HERE / "source_balance/additional_adapter.py",
                "wrapper_sha256": HERE / "source_temper/additional_wrapper.py",
                "screen_frozen_source_temper_sha256": HERE / "source_temper/model.py",
            }
            for path in list(paths.values())[:4]:
                path.write_text(path.name)
            metadata = {
                "variant": "source_alpha050",
                **{
                    key: hashlib.sha256(path.read_bytes()).hexdigest()
                    for key, path in paths.items()
                },
            }
            sources = {str(path): value for path, value in []}
            result = {"metadata": metadata, "sources": sources}
            validate_model_metadata(
                result,
                "source_temper",
                "source_alpha050",
                base,
                0,
                {},
                additional=True,
                qualified=True,
            )
            result["metadata"]["wrapper_sha256"] = "wrong"
            with self.assertRaises(AssertionError):
                validate_model_metadata(
                    result,
                    "source_temper",
                    "source_alpha050",
                    base,
                    0,
                    {},
                    additional=True,
                    qualified=True,
                )

    def test_unknown_digest_must_bind_a_declared_consumed_source(self):
        value = "a" * 64
        result = {
            "metadata": {"future_sha256": value},
            "sources": {"future.py": value},
        }
        validate_model_metadata(
            result, "future", "v", Path("."), 0, {},
            additional=False, qualified=True,
        )
        result["metadata"]["future_sha256"] = "b" * 64
        with self.assertRaises(AssertionError):
            validate_model_metadata(
                result, "future", "v", Path("."), 0, {},
                additional=False, qualified=True,
            )


if __name__ == "__main__":
    unittest.main()
