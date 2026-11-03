#!/usr/bin/env python3
"""Fail-closed numerical input tests for the public/reference comparator."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import compare_public_reference as comparison


class ComparatorFiniteInputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_candidate_observation_rejects_nonfinite_measurement(self) -> None:
        path = self.root / "candidates.tsv"
        fields = (
            "candidate_id",
            "actual_rf_hz",
            "measured_cfo_hz",
            "exact_score",
            "control_score",
            "margin",
        )
        with path.open("w", newline="") as sink:
            writer = csv.DictWriter(sink, delimiter="\t", fieldnames=fields)
            writer.writeheader()
            writer.writerow(
                {
                    "candidate_id": "candidate",
                    "actual_rf_hz": "11200000000",
                    "measured_cfo_hz": "nan",
                    "exact_score": "1",
                    "control_score": "0",
                    "margin": "1",
                }
            )
        with self.assertRaisesRegex(ValueError, "non-finite candidate measured_cfo_hz"):
            comparison.candidate_rows(path)

    def test_track_rejects_nonfinite_fit(self) -> None:
        path = self.root / "tracks.tsv"
        path.write_text(
            "\t".join(
                (
                    "TRACK",
                    "0",
                    "tracklet",
                    "episode",
                    "0",
                    "1",
                    "lower",
                    "11200000000",
                    "100",
                    "200",
                    "150",
                    "inf",
                    "0",
                    "0",
                    "0",
                    "1",
                    "0",
                )
            )
            + "\n"
        )
        with self.assertRaisesRegex(ValueError, "non-finite track slope"):
            comparison.track_rows(path)

    def test_graph_rejects_nonfinite_moment(self) -> None:
        path = self.root / "graph-candidates.tsv"
        path.write_text(
            "META\tanalysis\ttrajectory\tprofile\n"
            "candidate_id\tstart\tcenter\tend\tm0\tm1\tm2\tm3\n"
            "candidate\t100\t150\t200\t1\t0\t-inf\t0\n"
        )
        with self.assertRaisesRegex(ValueError, "non-finite graph field 6"):
            comparison.graph_rows(path)


if __name__ == "__main__":
    unittest.main()
