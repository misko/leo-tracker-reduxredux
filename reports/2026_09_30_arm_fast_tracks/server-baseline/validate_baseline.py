#!/usr/bin/env python3
"""Validate the frozen standard-server baseline and both native TSV inputs."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def main() -> int:
    output = Path(__file__).resolve().parent / "output"
    report = json.loads((output / "report.json").read_text())
    server = rows(output / "server-observations.tsv")
    server_map = rows(output / "server-candidate-map.tsv")
    arm = rows(output / "arm-observations.tsv")
    arm_map = rows(output / "arm-candidate-map.tsv")
    members = rows(output / "server-track-members.tsv")
    tracks = json.loads((output / "server-tracks.json").read_text())
    cli_lines = (output / "server-tracks.tsv").read_text().splitlines()

    assert report["status"] == "pass"
    assert len(server) == len(server_map) == report["server_projected_observations"] == 10_066
    assert len(arm) == len(arm_map) == report["arm_projected_observations"] == 9_728
    for observations, mapping, side, epoch_kind in (
        (server, server_map, "server", "fractional"),
        (arm, arm_map, "arm", "integer"),
    ):
        assert len({row["candidate_id"] for row in observations}) == len(observations)
        assert [row["candidate_id"] for row in observations] == [
            row["candidate_id"] for row in mapping
        ]
        assert [row["source_group_id"] for row in observations] == [
            row["source_group_id"] for row in mapping
        ]
        assert all(row["detector_side"] == side for row in mapping)
        assert all(row["epoch_kind"] == epoch_kind for row in mapping)
        assert all(
            0 <= int(row["visit"]) < 2_215
            and int(row["receiver_id"]) in (0, 1)
            and int(row["probe_index"]) == 0
            and 0 <= int(row["candidate_rank"]) < 8
            for row in mapping
        )
        for row in observations:
            assert int(row["support_start_utc_ns"]) <= int(row["support_center_utc_ns"])
            assert int(row["support_center_utc_ns"]) < int(row["support_end_utc_ns"])
            assert all(
                math.isfinite(float(row[field]))
                for field in (
                    "actual_rf_hz",
                    "measured_cfo_hz",
                    "exact_score",
                    "control_score",
                    "margin",
                )
            )
            assert float(row["margin"]) >= 0.025

    server_by_id = {row["candidate_id"]: row for row in server}
    map_by_id = {row["candidate_id"]: row for row in server_map}
    assert all(row["candidate_id"] in server_by_id for row in members)
    assert all(
        row["source_group_id"] == map_by_id[row["candidate_id"]]["source_group_id"]
        and row["visit"] == map_by_id[row["candidate_id"]]["visit"]
        and row["candidate_rank"] == map_by_id[row["candidate_id"]]["candidate_rank"]
        for row in members
    )
    assert len(tracks["tracklets"]) == report["server_tracklets"] == 63
    assert len(tracks["physical_groups"]) == report["server_physical_groups"] == 16
    assert len(tracks["hypotheses"]) == report["server_hypotheses"] == 16
    point_count = sum(len(tracklet["points"]) for tracklet in tracks["tracklets"])
    assert point_count == len(members) == 3_240
    assert len({row["candidate_id"] for row in members}) == report["server_used_observations"]
    assert cli_lines[:2] == [
        "SUMMARY\t10066\t3238\t63",
        "CONFIG\tsha256:d88ef31839ce46dd05653cd285f3bc4edef1ea2c0a7a62ac1a065cdcda3cb2f3",
    ]
    assert sum(line.startswith("TRACK\t") for line in cli_lines) == 63
    assert sum(line.startswith("POINT\t") for line in cli_lines) == 3_240
    assert all(
        len(line.split("\t")) == (17 if line.startswith("TRACK\t") else 7)
        for line in cli_lines[2:]
    )
    print(
        json.dumps(
            {
                "status": "pass",
                "server_observations": len(server),
                "arm_observations": len(arm),
                "server_tracklets": len(tracks["tracklets"]),
                "server_track_points": point_count,
                "server_unique_used_observations": len(
                    {row["candidate_id"] for row in members}
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
