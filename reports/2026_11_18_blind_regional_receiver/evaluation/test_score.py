import csv
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest
from score import WGS84_A_KM, distance_km, evaluate, sha256, tile_contains


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def make_prediction(query_id, region, point, *, best=None, gate=None, wall=1):
    best = best or (region, point)
    gate = gate or region
    return {
        "id": query_id,
        "status": "fix" if point else "withheld",
        "latlon": point,
        "region_id": region,
        "reason": "toy verdict",
        "best_region": best[0],
        "best_latlon": best[1],
        "diagnostics": {
            "region_result": {
                "status": "accepted" if gate else "withheld",
                "region_id": gate,
                "reason": "toy region verdict",
            },
            "stage_seconds": {"fit": wall / 2},
            "work": {"tiles": 2},
        },
        "wall_s": wall,
    }


@pytest.fixture
def toy(tmp_path):
    public = tmp_path / "public"
    (public / "queries").mkdir(parents=True)
    truth_path, predictions = tmp_path / "truth.json", tmp_path / "predictions.json"
    cases = [
        (
            "p-one",
            "presence-a",
            "site-a",
            "synthetic",
            "present",
            "target-a",
            [0, 179.99],
            "present",
            [("decoy-a", [0, 177]), ("target-a", [0, -179.96])],
            "a",
        ),
        (
            "m-one",
            "presence-a",
            "site-a",
            "synthetic",
            "missing",
            None,
            [0, 179.99],
            "near",
            [("near-a", [0, 179.85]), ("decoy-a", [0, 177])],
            "a",
        ),
        (
            "p-two",
            "presence-b",
            "site-b",
            "field",
            "present",
            "target-b",
            [10, 20],
            "present",
            [("decoy-b", [10, 22]), ("target-b", [10.02, 20])],
            "b",
        ),
        (
            "m-two",
            "presence-b",
            "site-b",
            "field",
            "missing",
            None,
            [10, 20],
            "far",
            [("decoy-b", [10, 22])],
            "b",
        ),
        (
            "p-three",
            "presence-c",
            "site-c",
            "known_site_control",
            "present",
            "target-c",
            [24, 17],
            "present",
            [("target-c", [24, 17])],
            "c",
        ),
    ]
    ids = []
    truth = []
    for query_id, pair, site, source, condition, correct, point, level, regions, digest in cases:
        ids.append(query_id)
        truth.append(
            {
                "id": query_id,
                "pair": pair,
                "site_group": site,
                "source": source,
                "condition": condition,
                "true_region": correct,
                "latlon": point,
                "difficulty": level,
            }
        )
        write_json(
            public / "queries" / f"{query_id}.json",
            {
                "id": query_id,
                "observation": digest * 64,
                "catalog": "f" * 64,
                "regions": [{"id": region, "center": center} for region, center in regions],
            },
        )
    write_json(public / "manifest.json", {"queries": ids})
    write_json(truth_path, {"cases": truth})
    write_json(
        predictions,
        {
            "engine_sha256": "e" * 64,
            "cases": [
                make_prediction("p-one", "target-a", [0, -179.999]),
                make_prediction("m-one", None, None, best=(None, [0, 179.85]), wall=2),
                make_prediction("p-two", "target-b", [10, 22], best=("decoy-b", [10, 22]), wall=3),
                make_prediction("m-two", "decoy-b", [10, 22], wall=4),
                make_prediction("p-three", None, None, gate="target-c", wall=5),
            ],
        },
    )
    return public, truth_path, predictions


def test_wgs84_square_wraps_at_antimeridian_and_excludes_back_hemisphere():
    assert tile_contains((0, 179.99), (0.1, -179.91))
    assert tile_contains((0, 0), (0.11, 0.11))
    assert distance_km((0, 0), (0.11, 0.11)) > 17
    edge = math.degrees(math.asin(12.5 / WGS84_A_KM))
    assert tile_contains((0, 0), (0, edge))
    assert not tile_contains((0, 0), (0, edge + 1e-7))
    assert not tile_contains((0, 0), (0, 180))
    assert distance_km((0, 179.99), (0, -179.99)) == pytest.approx(2.2239, abs=1e-4)


def test_paired_scoring_uses_all_attempts_and_validates_publication_geometry(toy):
    summary, rows = evaluate(*toy)
    policies = summary["overall"]["by_policy"]
    present = policies["receiver"]["present"]
    assert present["publications"] == {"count": 2, "denominator": 3, "rate": 2 / 3}
    assert present["correct_region_all_attempts"]["count"] == 1
    assert present["published_geometry_violations"] == 1
    assert present["position_within_5km_all_attempts"]["rate"] == 1 / 3
    assert present["joint_within_5km_all_attempts"]["count"] == 1
    assert present["published_error_at_least_10km"]["rate"] == 0.5
    assert present["published_error_km"]["n"] == 2
    assert present["published_error_km"]["worst"] > 200
    assert policies["region_only"]["present"]["correct_region_all_attempts"]["count"] == 3
    assert policies["prior_first"]["present"]["correct_region_all_attempts"]["count"] == 1
    assert rows[2]["decisions"]["receiver"]["containing_regions"] == "decoy-b"

    missing = policies["receiver"]["missing"]
    assert missing["rejections"]["rate"] == 0.5
    assert missing["false_publications"]["rate"] == 0.5
    assert policies["forced_rf"]["missing"]["published_error_km"]["n"] == 2
    assert rows[1]["decisions"]["forced_rf"]["geometry_valid"] is True
    assert policies["always_withhold"]["missing"]["published_error_km"]["median"] is None
    levels = summary["missing_by_difficulty"]
    assert levels["near"]["forced_rf"]["published_error_km"]["median"] < 20
    assert levels["far"]["receiver"]["false_publications"]["count"] == 1

    pairs = summary["pairs"]
    assert pairs["matched_pairs"] == 2
    assert pairs["incomplete_pairs"] == 1
    assert pairs["joint_within_5km_and_reject"] == 1
    assert pairs["present_fix_missing_fix"] == 1
    assert summary["by_site_group"]["groups_without_present_publication"] == 1
    assert summary["by_source"]["known_site_control"]["by_site_group"]["groups"] == 1
    assert summary["resources"]["receiver_wall_s"]["p90"] == pytest.approx(4.6)
    assert summary["resources"]["work"]["tiles"]["median"] == 2


def test_pair_mismatch_stays_out_of_paired_counters(toy):
    public, _, _ = toy
    query_path = public / "queries" / "m-one.json"
    query = json.loads(query_path.read_text())
    query["catalog"] = "0" * 64
    write_json(query_path, query)
    summary, _ = evaluate(*toy)
    assert summary["pairs"]["mismatched_complete_pairs"] == 1
    assert summary["pairs"]["matched_pairs"] == 1
    assert summary["pairs"]["joint_within_5km_and_reject"] == 0
    assert summary["query_count"] == 5


def test_only_first_offer_control_depends_on_display_order(toy):
    public, _, _ = toy
    query_path = public / "queries" / "p-one.json"
    before, before_rows = evaluate(*toy)
    query = json.loads(query_path.read_text())
    query["regions"].reverse()
    write_json(query_path, query)
    after, after_rows = evaluate(*toy)
    old, new = (rows[0]["decisions"] for rows in (before_rows, after_rows))
    assert old["prior_first"]["region_id"] != new["prior_first"]["region_id"]
    assert old["prior_medoid"] == new["prior_medoid"]
    assert old["receiver"] == new["receiver"]
    key = "public_scoring_input_sha256"
    assert before["provenance"][key] != after["provenance"][key]


@pytest.mark.parametrize("mode", ["duplicate", "missing", "extra"])
def test_prediction_ids_must_match_manifest_exactly(toy, mode):
    _, _, predictions = toy
    payload = json.loads(predictions.read_text())
    case = payload["cases"][0].copy()
    if mode == "missing":
        payload["cases"].pop()
    else:
        if mode == "extra":
            case["id"] = "not-offered"
        payload["cases"].append(case)
    write_json(predictions, payload)
    with pytest.raises(ValueError, match="prediction id"):
        evaluate(*toy)


def test_truth_must_be_inside_exactly_the_designated_tile(toy):
    public, _, _ = toy
    query_path = public / "queries" / "p-one.json"
    query = json.loads(query_path.read_text())
    query["regions"][0]["center"] = query["regions"][1]["center"]
    write_json(query_path, query)
    with pytest.raises(ValueError, match="inside exactly its designated offered tile"):
        evaluate(*toy)


def test_cli_writes_digests_and_no_estimate_row(toy, tmp_path):
    public, truth, predictions = toy
    output = tmp_path / "scored"
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("score.py")),
            "--public",
            str(public),
            "--truth",
            str(truth),
            "--predictions",
            str(predictions),
            "--output",
            str(output),
        ],
        check=True,
    )
    summary = json.loads((output / "summary.json").read_text())
    assert summary["provenance"]["engine_sha256"] == "e" * 64
    assert summary["provenance"]["predictions_sha256"] == sha256(predictions.read_bytes())
    assert summary["provenance"]["truth_sha256"] == sha256(truth.read_bytes())
    assert summary["provenance"]["public_manifest_sha256"] == sha256(
        (public / "manifest.json").read_bytes()
    )
    with (output / "per_query.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 5
    assert rows[-1]["receiver_status"] == "withheld"
    assert rows[-1]["forced_rf_status"] == "no_estimate"
    assert rows[-1]["receiver_error_km"] == ""
    assert "truth_point" not in rows[-1]
