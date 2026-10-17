import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest


@pytest.fixture
def cohort(monkeypatch):
    directory = Path(__file__).resolve().parents[2] / "tools"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location(
        "cohort_study", directory / "evaluate_dsx01_cohort_tracklets.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def frozen_dataset(directory, cohort):
    rows = [
        {
            "source_id": source,
            "observation_id": f"{source}-{rx}-{ch}",
            "receiver": rx,
            "channel": ch,
            "time_s": 0.0,
            "actual_rf_hz": 10e9,
            "measured_cfo_hz": float(ch),
            "original_best_satellite": "must-not-enter-fit",
        }
        for source in ("S01", "S02")
        for rx in (1, 2)
        for ch in range(1, 9)
    ]
    (directory / "context-observations.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n"
    )
    (directory / "sources.json").write_text(
        json.dumps([{"source_id": s, "observation_count": 16} for s in ("S01", "S02")])
    )
    (directory / "dataset.json").write_text(
        json.dumps(
            {
                "recording_count": 2,
                "full_scan_context_observation_count": 32,
                "membership_count": 2,
                "unique_member_observation_count": 2,
            }
        )
    )
    with (directory / "membership.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=["source_id", "region_id", "observation_id"])
        writer.writeheader()
        writer.writerows(
            [
                {"source_id": s, "region_id": s + "-region", "observation_id": s + "-1-1"}
                for s in ("S01", "S02")
            ]
        )
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "files": [
                    {"path": p.name, "bytes": p.stat().st_size, "sha256": cohort.digest(p)}
                    for p in directory.iterdir()
                ]
            }
        )
    )


def test_cohort_loader_keeps_every_scan_and_strips_original_labels(tmp_path, cohort):
    frozen_dataset(tmp_path, cohort)
    rows, sources, members, _ = cohort.load_cohort(tmp_path)
    assert len(rows) == 32 and len(sources) == 2 and len(members) == 2
    assert {r["source_id"] for r in rows} == {"S01", "S02"}
    assert all("original_best_satellite" not in r for r in rows)


def test_cohort_loader_rejects_unbound_input_edits(tmp_path, cohort):
    frozen_dataset(tmp_path, cohort)
    with (tmp_path / "context-observations.jsonl").open("a") as stream:
        stream.write("\n")
    with pytest.raises(AssertionError):
        cohort.load_cohort(tmp_path)


def test_aggregate_uses_observation_and_track_denominators(cohort):
    def record(observations, associated, sizes, durations, challenge_n, challenge_assigned):
        return {
            "method": "graph",
            "phase": "recovered",
            "observations": observations,
            "associated": associated,
            "unassociated": observations - associated,
            "tracks": len(sizes),
            "supported_points": associated,
            "flagged_points": 0,
            "short_points": 0,
            "challenge_observations": challenge_n,
            "challenge_associated": challenge_assigned,
            "track_sizes": sizes,
            "track_durations_s": durations,
        }

    records = [record(100, 80, [40, 40], [20, 20], 5, 3), record(20, 10, [10], [10], 2, 1)]
    result = cohort.aggregate(records)[0]
    assert result["associated_percent"] == 75
    assert result["mean_points_per_track"] == 30
    assert result["median_points_per_track"] == 40
    assert result["mean_duration_s"] == pytest.approx(50 / 3)
    assert result["challenge_associated_percent"] == pytest.approx(400 / 7)


def test_integrity_audit_rejects_accidentally_combined_scans(tmp_path, cohort):
    frozen_dataset(tmp_path, cohort)
    rows, _, _, _ = cohort.load_cohort(tmp_path)
    from leo.analysis.polynomial_tracklets import TrackConfig

    with pytest.raises(AssertionError):
        cohort.audit_result(rows, {"observations": 32}, rows, TrackConfig())
