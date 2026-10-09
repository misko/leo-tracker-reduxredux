"""Synthetic coverage/evaluation guards; no recording or reference authority reads."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("report107_test", HERE / "report.py")
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


class ReportTest(unittest.TestCase):
    def member(self):
        return {"member": {"dataset": "DS16", "inventory_label": "DS16-001", "session_id": "s"}}

    def test_pending_member_never_reads_reference_authority(self):
        def forbidden(member):
            raise AssertionError("Reference authority opened before terminal")

        row = report.describe_member(
            self.member(),
            {"baseline": {"status": "complete"}, "candidate": {"status": "missing"}},
            document_loader=forbidden,
        )
        self.assertFalse(row["paired_terminal"])
        self.assertIsNone(row["arms"]["fitted-c"]["baseline"])

    def test_baseline_failure_candidate_not_run_report_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "baseline.json").write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "protocol_sha256": "frozen",
                        "label": root.name,
                        "phase": "baseline",
                    }
                )
            )
            records, hashes = report.phase_receipts(root, "frozen")
            self.assertEqual(records["candidate"]["status"], "not-run-baseline-failed")
            self.assertTrue(report.paired_terminal(records))
            self.assertFalse((root / "candidate.json").exists())
            self.assertEqual(len(hashes), 1)

    def test_invalid_protocol_is_not_terminal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "baseline.json").write_text(
                json.dumps(
                    {
                        "status": "complete",
                        "protocol_sha256": "wrong",
                        "label": root.name,
                        "phase": "baseline",
                    }
                )
            )
            records, _ = report.phase_receipts(root, "frozen")
            self.assertEqual(records["baseline"]["status"], "receipt-invalid")
            self.assertFalse(report.paired_terminal(records))

    def rows(self):
        return [
            dict(
                label=str(i),
                paired_terminal=True,
                arms={
                    arm: dict(
                        baseline={"error_km": i + 1},
                        candidate={"error_km": i + 0.5},
                        error_delta_km=-0.5,
                    )
                    for arm in report.ARMS
                },
            )
            for i in range(3)
        ]

    def test_full_matched_metrics(self):
        value = report.aggregate(self.rows())
        self.assertEqual(value["arms"]["fitted-c"]["baseline"]["mean_km"], 2)
        self.assertEqual(value["arms"]["zero-c"]["candidate"]["mean_km"], 1.5)

    def test_partial_or_failed_position_withholds_metrics(self):
        rows = self.rows()
        rows[0]["paired_terminal"] = False
        value = report.aggregate(rows)
        self.assertEqual(value["full_membership"], 3)
        self.assertNotIn("baseline", value["arms"]["fitted-c"])
        rows[0]["paired_terminal"] = True
        rows[0]["arms"]["fitted-c"]["candidate"] = None
        self.assertTrue(report.aggregate(rows)["arms"]["fitted-c"]["full_census_metrics_withheld"])

    def test_complete_dataset_withheld_until_census_terminal(self):
        self.assertTrue(
            report.aggregate(self.rows(), census_terminal=False)["arms"]["zero-c"][
                "full_census_metrics_withheld"
            ]
        )

    def test_swapped_label_and_phase_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for label, phase in [("other", "baseline"), (root.name, "candidate")]:
                (root / "baseline.json").write_text(
                    json.dumps(
                        dict(status="complete", protocol_sha256="frozen", label=label, phase=phase)
                    )
                )
                records, _ = report.phase_receipts(root, "frozen")
                self.assertEqual(records["baseline"]["status"], "receipt-invalid")

    def test_budget_record_missing_label_has_explicit_limitation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "baseline.json").write_text(
                json.dumps(
                    dict(
                        status="budget-exhausted",
                        protocol_sha256="frozen",
                        phase="baseline",
                        operational={},
                    )
                )
            )
            records, _ = report.phase_receipts(root, "frozen")
            self.assertEqual(records["baseline"]["status"], "budget-exhausted")
            self.assertIn("report_identity_limitation", records["baseline"])


if __name__ == "__main__":
    unittest.main()
