from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
REPORT = ROOT / "reports/2026_09_30_native_adaptive_deployment/tracking"


def _native_tracks(text: str) -> tuple[dict, list[dict]]:
    summary: dict = {}
    tracks: list[dict] = []
    for line in text.splitlines():
        fields = line.split("\t")
        if fields[0] == "SUMMARY":
            summary = {
                "input": int(fields[1]),
                "used": int(fields[2]),
                "tracks": int(fields[3]),
            }
        elif fields[0] == "TRACK":
            tracks.append(
                {
                    "segment_id": fields[2],
                    "tracklet_id": fields[3],
                    "lane_key": (int(fields[5]), fields[6], int(fields[4]), float(fields[7])),
                    "start_utc_ns": int(fields[8]),
                    "end_utc_ns": int(fields[9]),
                    "reference_utc_ns": int(fields[10]),
                    "normalized_rate_hz_per_s": float(fields[11]),
                    "normalized_intercept_hz": float(fields[12]),
                    "residual_rms_hz": float(fields[13]),
                    "residual_max_hz": float(fields[14]),
                    "weighted_support": float(fields[15]),
                    "points": [],
                }
            )
        elif fields[0] == "POINT":
            tracks[int(fields[1])]["points"].append(
                {
                    "candidate_id": fields[2],
                    "source_group_id": fields[3],
                    "relative_alias_index": int(fields[4]),
                    "normalized_raw_cfo_hz": float(fields[5]),
                    "normalized_dealiased_cfo_hz": float(fields[6]),
                }
            )
    return summary, tracks


@pytest.mark.real_corpus
@pytest.mark.legacy_oracle
def test_native_weighted_hough_matches_public_ds9_oracle(tmp_path: Path) -> None:
    candidates_path = REPORT / "candidates.tsv"
    oracle_path = REPORT / "oracle-tracks.json"
    if not candidates_path.is_file() or not oracle_path.is_file():
        raise AssertionError(
            "required DS9 fixture is absent; run export_ds9_oracle.py through the maintained "
            "read-only ScannerTrackingInputStore"
        )
    build = tmp_path / "build"
    subprocess.run(
        [str(ROOT / "native/adaptive/tracking/build.sh"), "host", str(build)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    completed = subprocess.run(
        [str(build / "leo-tracking"), str(candidates_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    summary, native = _native_tracks(completed.stdout)
    oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
    with candidates_path.open(encoding="utf-8", newline="") as handle:
        candidates = {row["candidate_id"]: row for row in csv.DictReader(handle, delimiter="\t")}

    assert summary == {"input": 11_747, "used": 3_372, "tracks": 64}
    assert oracle["projected_candidate_count"] == 11_747
    assert oracle["used_candidate_count"] == 3_372
    assert oracle["track_count"] == 64

    by_source_membership = {}
    for track in oracle["tracks"]:
        sources = frozenset(
            candidates[point["candidate_id"]]["source_group_id"] for point in track["points"]
        )
        key = (tuple(track["lane_key"]), sources)
        assert key not in by_source_membership
        by_source_membership[key] = track

    candidate_mismatches = 0
    identity_mismatches = 0
    for track in native:
        sources = frozenset(point["source_group_id"] for point in track["points"])
        expected = by_source_membership[(track["lane_key"], sources)]
        assert track["start_utc_ns"] == expected["start_utc_ns"]
        assert track["end_utc_ns"] == expected["end_utc_ns"]
        assert track["reference_utc_ns"] == expected["reference_utc_ns"]
        assert track["normalized_rate_hz_per_s"] == pytest.approx(
            expected["normalized_rate_hz_per_s"], rel=0.0, abs=4e-9
        )
        assert track["normalized_intercept_hz"] == pytest.approx(
            expected["normalized_intercept_hz"], rel=0.0, abs=1e-6
        )
        assert track["residual_rms_hz"] == pytest.approx(
            expected["residual_rms_hz"], rel=0.0, abs=3e-11
        )
        assert track["residual_max_hz"] == pytest.approx(
            expected["residual_max_hz"], rel=0.0, abs=1e-8
        )
        assert track["weighted_support"] == pytest.approx(
            expected["weighted_support"], rel=0.0, abs=1e-12
        )
        if track["tracklet_id"] != expected["tracklet_id"]:
            identity_mismatches += 1

        expected_points = {
            candidates[point["candidate_id"]]["source_group_id"]: point
            for point in expected["points"]
        }
        assert len(expected_points) == len(track["points"])
        for point in track["points"]:
            oracle_point = expected_points[point["source_group_id"]]
            if point["candidate_id"] != oracle_point["candidate_id"]:
                candidate_mismatches += 1
            assert point["relative_alias_index"] == oracle_point["relative_alias_index"]
            assert point["normalized_raw_cfo_hz"] == pytest.approx(
                oracle_point["normalized_raw_cfo_hz"], rel=0.0, abs=2e-10
            )
            assert point["normalized_dealiased_cfo_hz"] == pytest.approx(
                oracle_point["normalized_dealiased_cfo_hz"], rel=0.0, abs=2e-10
            )

    # Six duplicated server candidates differ only at <= 1.2e-10 Hz.  The
    # portable closed-form least-squares fit and NumPy LAPACK fit resolve those
    # exact residual ties to opposite candidate ranks.  Source membership,
    # support times, aliases, and physical CFO values remain equal above.
    assert candidate_mismatches == 6
    assert identity_mismatches == 6


@pytest.mark.real_corpus
@pytest.mark.legacy_oracle
def test_reconstructed_tracks_drive_public_location_boundary(tmp_path: Path) -> None:
    graph = REPORT / "graph-candidates.tsv"
    orbit_authority = (
        ROOT / "reports/2026_09_30_arm_location_prototype/local/ephemeris-arm-generated.bin"
    )
    old_inputs = ROOT / "reports/2026_09_30_arm_location_prototype/inputs.json"
    for required in (REPORT / "candidates.tsv", graph, orbit_authority, old_inputs):
        if not required.is_file():
            raise AssertionError(f"required E2 authority is absent: {required}")

    pipeline_build = tmp_path / "pipeline"
    location_build = tmp_path / "location"
    subprocess.run(
        [str(ROOT / "native/adaptive/pipeline/build.sh"), "host", str(pipeline_build)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [str(ROOT / "native/adaptive/location/build.sh"), "host", str(location_build)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    loc1 = tmp_path / "native-e2.loc1"
    subprocess.run(
        [
            str(pipeline_build / "leo-adaptive-pipeline"),
            str(REPORT / "candidates.tsv"),
            str(graph),
            str(orbit_authority),
            str(loc1),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    native_tracks = []
    for line in (Path(str(loc1) + ".tracks.tsv")).read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if fields[0] == "TRACK":
            native_tracks.append(
                {
                    "track_id": fields[2],
                    "support_digest": fields[3],
                    "partition_seed": fields[4],
                    "observation_ids": [],
                    "training_mask": [],
                }
            )
        else:
            native_tracks[int(fields[1])]["observation_ids"].append(fields[2])
            native_tracks[int(fields[1])]["training_mask"].append(bool(int(fields[5])))
    assert len(native_tracks) == 64
    published = {
        item["track_id"]: item
        for item in json.loads(old_inputs.read_text(encoding="utf-8"))["tracks"]
    }
    exact = [item for item in native_tracks if item["track_id"] in published]
    assert len(exact) == 58
    for item in exact:
        expected = published[item["track_id"]]
        assert item["support_digest"] == expected["support_digest"]
        assert item["partition_seed"] == expected["partition_seed"]
        assert item["observation_ids"] == expected["observation_ids"]
        assert item["training_mask"] == expected["training_mask"]

    score = subprocess.run(
        [str(location_build / "leo-location"), "score", str(loc1), "2"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    points = json.loads(score.stdout)["points"]
    assert [(item["matched_tracks"], item["score_hz"]) for item in points] == pytest.approx(
        [(64, 223.83559325001423), (64, 411.4285903855997)], rel=0.0, abs=1e-10
    )
