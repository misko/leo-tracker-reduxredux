"""Checks for the saved-evidence summary; no fits or hardware dependencies."""
import json
import unittest

from summarize import BASE, HERE, calculate, read_csv


class SummaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary, cls.rows = calculate()

    def test_matches_published_aggregate_tables(self):
        visibility = read_csv(BASE / "position-visibility-study/polished/summary.csv")
        sweep = read_csv(BASE / "position-score-sweep/polished/summary.csv")
        for row in self.summary["aggregates"]:
            model = row["model"]
            if model.startswith("historical"):
                continue
            if model in {"C1-Q1", "C1-TIME-Q1"}:
                weighting = "ordinary" if model == "C1-Q1" else "time-balanced"
                expected = next(r for r in visibility if (r["arm"], r["gate"], r["weighting"]) ==
                                (row["arm"], "Q1", weighting))
            else:
                mode = "V16" if model == "V16" else "C1"
                expected = next(r for r in sweep if (r["arm"], r["mode"]) == (row["arm"], mode))
            self.assertAlmostEqual(row["median_m"], float(expected["median_error_m"]), places=6)
            self.assertAlmostEqual(row["mean_m"], float(expected["mean_error_m"]), places=6)
            self.assertEqual(row["converged"], int(expected["converged"]))
            self.assertEqual(row["boundary"], int(expected["boundary"]))

    def test_counts_and_no_false_ab_shortlist_results(self):
        self.assertEqual(len(self.rows), 192)
        self.assertTrue(all(r["scan"].startswith("N") for r in self.rows))
        self.assertEqual(len(self.summary["ab_historical_baseline"]), 4)
        coverage = self.summary["full_data_coverage"][0]
        self.assertEqual((coverage["assigned"], coverage["total"]), (42610, 46775))

    def test_saved_summary_is_current(self):
        self.assertEqual(json.loads((HERE / "summary.json").read_text()), self.summary)

    def test_historical_baseline_is_separate_and_boundary_flagged(self):
        baseline = self.summary["historical_t1_at_v1_baseline"]
        self.assertEqual([round(r["median_m"]) for r in baseline], [1553, 2000])
        self.assertEqual([r["boundary"] for r in baseline], [6, 9])
        self.assertEqual([r["converged"] for r in baseline], [15, 14])
        self.assertTrue(all(r["search_radius_m"] == 2000 for r in baseline))

    def test_report_numeric_tables_match(self):
        report = (HERE / "report.md").read_text()
        lines = report.splitlines()
        for i in range(1, 17):
            scan = f"N{i:02}"
            line = next(line for line in lines if line.startswith(f"| {scan} |"))
            cells = [c.strip() for c in line.strip("|").split("|")][1:]
            expected = []
            for model in ["C1-Q1", "V16", "C1-TIME-Q1"]:
                for arm in ["fitted-c", "zero-c"]:
                    row = next(r for r in self.rows if (r["scan"], r["model"], r["arm"]) ==
                               (scan, model, arm))
                    expected.append(f'{row["distance_m"]:.0f}' +
                                    ('†' if not row['converged'] else '') +
                                    ('‡' if row['boundary'] else ''))
            self.assertEqual(cells, expected)


if __name__ == "__main__":
    unittest.main()
