from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
from pathlib import Path

import matplotlib.image as mpimg
import numpy as np

ROOT = Path(__file__).parents[2]
REPORT = ROOT / "reports/2026_08_26_fixed500_calibration_results.md"
ARTIFACT_ROOT = ROOT / "reports/figures/2026_08_26_fixed500_calibration"
METRICS = ARTIFACT_ROOT / "metrics.json"
CAPTURES = {
    "cap-20260825T062228-886fe2dd9cde",
    "cap-20260825T105640-facdadeffb3b",
    "cap-20260825T111222-a2d4ce2afb9a",
}


def _metrics() -> dict[str, object]:
    value = json.loads(METRICS.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_canonical_result_receipt_is_hash_bound_to_the_frozen_rerun() -> None:
    metrics = _metrics()

    assert metrics["repository_head_at_execution"] == ("0ac073382416ca250bca88abdfdd79be2f0de235")
    assert metrics["protocol_commit"] == "8e6e98e4a3824723b04ef3c9bcb92df3080a7336"
    assert metrics["protocol_sha256"] == (
        "sha256:e1cee914fa6ec3f7a28819e7035968e023989a19f4ccf0a32577275cf1ed559f"
    )
    assert metrics["scenario_count"] == 36
    assert len(metrics["primary_scenario_ids"]) == 12
    assert float(metrics["runtime_seconds"]) < 20 * 60
    authority = metrics["execution_authority"]
    assert authority["mode"] == "hash_bound_serialization_correction"
    assert authority["corrected_implementation_commit"] == (
        "69ce329f8243b08c5ea525aa15db3f01cd8c0d89"
    )
    assert {item["session_id"] for item in metrics["inputs"]} == CAPTURES
    presentation = metrics["presentation_postprocess"]
    assert presentation["repository_head"] == "44950ccc1c9505f42d250ce191fd15422e80af47"
    assert presentation["scientific_metrics_changed"] is False
    maintenance = metrics["source_layout_maintenance"]
    assert maintenance["source_layout_commit"] == ("27e37f0d4df0004e31809267305f3e578908af31")
    assert maintenance["scientific_metrics_changed"] is False
    assert maintenance["canonical_execution_artifacts_changed"] is False
    assert hashlib.sha256(
        (ROOT / maintenance["amendment_path"]).read_bytes()
    ).hexdigest() == maintenance["amendment_sha256"].removeprefix("sha256:")

    for relative, expected in metrics["artifact_sha256"].items():
        payload = (ROOT / relative).read_bytes()
        actual = f"sha256:{hashlib.sha256(payload).hexdigest()}"
        assert actual == expected


def test_primary_results_retain_failures_and_frozen_promotion_decisions() -> None:
    metrics = _metrics()
    rows = {item["estimator"]: item for item in metrics["primary_aggregate"]}

    assert set(rows) == {
        "fixed_125ms_linear",
        "fixed_500ms_linear",
        "fixed_500ms_calibrated",
        "lean_curvature_500ms",
    }
    assert all(item["scenario_count"] == 12 for item in rows.values())
    assert all(item["evaluable_scenario_count"] == 12 for item in rows.values())
    assert np.isclose(rows["fixed_125ms_linear"]["rmse_hz_s"], 92.7065009641)
    assert np.isclose(rows["fixed_500ms_linear"]["rmse_hz_s"], 291.592149528)
    assert np.isclose(rows["lean_curvature_500ms"]["rmse_hz_s"], 37.175686071)
    assert np.isclose(rows["fixed_500ms_linear"]["endpoint_coverage"], 1 / 12)
    assert rows["fixed_500ms_linear"]["scenario_simultaneous_coverage"] == 0.0
    assert rows["fixed_500ms_calibrated"]["endpoint_coverage"] == 1.0
    assert rows["fixed_500ms_calibrated"]["scenario_simultaneous_coverage"] == 1.0
    assert np.isclose(
        rows["fixed_500ms_calibrated"]["median_interval_half_width_hz_s"],
        501.144134975,
    )

    calibration = metrics["interval_calibration"]
    assert calibration == {
        "confidence": 0.95,
        "usable_scenario_count": 12,
        "order": 12,
        "multiplier": 25.7252654407,
        "small_sample_order_is_maximum": True,
    }
    promotion = metrics["promotion"]
    assert promotion["fixed500_interval_status"] == "fail"
    assert promotion["fixed500_checks"]["unchanged_fixed500_point_rmse"] is False
    assert sum(not passed for passed in promotion["fixed500_checks"].values()) == 1
    assert promotion["curvature_status"] == "pass"
    assert np.isclose(promotion["curvature_rmse_ratio"], 0.127492067709)


def test_frame_and_endpoint_ledgers_keep_exact_authority_and_all_rows() -> None:
    with gzip.open(
        ARTIFACT_ROOT / "frame-evidence.csv.gz", mode="rt", newline="", encoding="utf-8"
    ) as source:
        frames = list(csv.DictReader(source))
    with (ARTIFACT_ROOT / "endpoint-estimates.csv").open(newline="", encoding="utf-8") as source:
        endpoints = list(csv.DictReader(source))

    assert len(frames) == 90_000
    assert len(endpoints) == 720
    assert {row["background_session_id"] for row in frames} == CAPTURES
    assert {row["background_session_id"] for row in endpoints} == CAPTURES
    assert {row["split"] for row in frames} == {"calibration", "evaluation"}
    assert {row["alignment"] for row in frames} == {
        "oracle_true_resampled_lattice",
        "nominal_fixed_lattice",
    }
    assert any(row["status"] != "complete" for row in endpoints)
    assert all("odd_heldout_cfo_error_hz" in row for row in endpoints)


def test_report_links_and_plain_matplotlib_pngs_resolve() -> None:
    text = REPORT.read_text(encoding="utf-8")
    assert "primary RMSE of 291.59 Hz/s" in text
    assert "quadratic **passed**" in text
    assert "86.3%" in text and "2.1%" in text
    assert "only 12 usable no-step" in text
    assert "fixed-500 line only" in text
    assert "legacy residual-chi-square conditional covariance" in text
    assert "Nonzero 400-Hz step" in text and "919.17" in text
    assert "No result here authorizes opening the sealed holdout" in text
    assert "historical polynomial-injection kernel was restored byte-for-byte" in text
    assert "Component and adjacent provenance/DSP suite: **95 passed**" in text

    links = re.findall(r"\]\(([^)]+)\)", text)
    assert links
    for target in links:
        if target.startswith(("http://", "https://", "#")):
            continue
        assert (REPORT.parent / target).resolve().is_file(), target

    figures = sorted(ARTIFACT_ROOT.glob("*.png"))
    assert len(figures) == 4
    for figure in figures:
        image = mpimg.imread(figure)
        assert image.ndim == 3
        assert image.shape[0] >= 800
        assert image.shape[1] >= 2_000
