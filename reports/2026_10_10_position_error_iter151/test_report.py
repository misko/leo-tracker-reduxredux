import json
import tempfile
import unittest
from pathlib import Path

from report import build, progression


class CohortReportTests(unittest.TestCase):
    def test_publish_gate_before_plot_or_outputs(self):
        from publish import publish

        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                publish(
                    dict(all_terminal=False, rows=[]),
                    folder,
                    lambda *args: self.fail("must not plot partial cohort"),
                )
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_closure_rejection_before_reporter_exec(self):
        from unittest.mock import patch

        import report

        with patch.object(report, "reporter", side_effect=AssertionError("must not execute")):  # noqa: SIM117
            with self.assertRaises(ValueError):
                build(
                    dict(
                        members=self.members(),
                        source_sha256={
                            "reports/2026_10_10_position_error_iter151/report.py": "wrong"
                        },
                        input_sha256={},
                    ),
                    ".",
                    "d",
                )

    def test_partial_stage_hashes_and_foreign_rejection(self):
        from report import stage_coverage

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "member0/native/stages"
            path.mkdir(parents=True)
            claim = path / "one.claim.json"
            claim.write_text(json.dumps(dict(protocol_sha256="d", key="unfinished")))
            rows, hashes = stage_coverage(folder, "member0", "native", "d")
            self.assertFalse(rows[0]["completed"])
            self.assertEqual(len(hashes), 1)
            claim.with_name("one.json").write_text(
                json.dumps(
                    dict(
                        protocol_sha256="d",
                        value={
                            "result": {
                                "status": "promotion-unqualified",
                                "fit": {"converged": False},
                            }
                        },
                    )
                )
            )
            rows, hashes = stage_coverage(folder, "member0", "native", "d")
            complete = next(r for r in rows if not r["claim"])
            self.assertTrue(
                any(v.get("converged") is False for v in complete["qualification_records"])
            )
            claim.write_text(json.dumps(dict(protocol_sha256="foreign")))
            with self.assertRaises(ValueError):
                stage_coverage(folder, "member0", "native", "d")

    def members(self):
        return [
            dict(label="member" + str(i), dataset=("DS16", "DS17", "DS18")[i // 4])
            for i in range(12)
        ]

    def receipts(self, folder, *, status="failed", foreign=False):
        for m in self.members():
            for phase in ("search", "native", "zero"):
                path = Path(folder) / m["label"] / phase
                path.mkdir(parents=True)
                (path / "result.json").write_text(
                    json.dumps(
                        dict(
                            protocol_sha256="wrong" if foreign else "d",
                            label=m["label"],
                            branch=phase,
                            status=status,
                            fallback_available=False,
                            reason="explicit failure",
                            attempts={},
                        )
                    )
                )

    def test_missing_never_evaluates(self):
        calls = []
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            build(
                dict(members=self.members(), source_sha256={}, input_sha256={}),
                folder,
                "d",
                evaluation_factory=lambda *a: calls.append(1),
            )
        self.assertEqual(calls, [])

    def test_foreign_and_pending_rejected(self):
        for foreign, status in ((True, "failed"), (False, "pending")):
            with tempfile.TemporaryDirectory() as folder:
                self.receipts(folder, foreign=foreign, status=status)
                with self.assertRaises(ValueError):
                    build(
                        dict(members=self.members(), source_sha256={}, input_sha256={}), folder, "d"
                    )

    def test_failed_terminal_keeps_denominator_and_blocks_progression(self):
        with tempfile.TemporaryDirectory() as folder:
            self.receipts(folder)
            summary = build(
                dict(
                    members=self.members(),
                    source_sha256={},
                    input_sha256={},
                    evaluation_source_sha256={},
                ),
                folder,
                "d",
                evaluation_factory=lambda *a: lambda *b: self.fail("no endpoint should evaluate"),
            )
        self.assertEqual(len(summary["rows"]), 12)
        self.assertEqual(summary["aggregates"]["all12"]["fitted-c"]["missing"], 12)
        self.assertFalse(summary["progression"]["passed"])
        self.assertIsNone(summary["rows"][0]["regions"]["zero"][0]["finals"])

    def test_global_gate_rejects_large_member_regression(self):
        rows = [
            dict(
                arms={
                    "fitted-c": dict(delta_km=-0.1, native={"error_km": 2}, zero={"error_km": 1.9})
                }
            )
            for _ in range(12)
        ]
        summary = dict(rows=rows, full_comparison_complete=True)
        self.assertTrue(progression(summary)["passed"])
        rows[0]["arms"]["fitted-c"]["delta_km"] = 1.1
        self.assertFalse(progression(summary)["passed"])


if __name__ == "__main__":
    unittest.main()
