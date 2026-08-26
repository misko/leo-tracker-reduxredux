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

    assert metrics["repository_head_at_execution"] == ("bf0548eeeca3485fe4a85c3a9355a2ac48d9c86c")
    assert metrics["protocol_commit"] == "8e6e98e4a3824723b04ef3c9bcb92df3080a7336"
    assert metrics["protocol_sha256"] == (
        "sha256:e1cee914fa6ec3f7a28819e7035968e023989a19f4ccf0a32577275cf1ed559f"
    )
    assert metrics["scenario_count"] == 36
    assert len(metrics["primary_scenario_ids"]) == 12
    assert float(metrics["runtime_seconds"]) < 20 * 60
    authority = metrics["execution_authority"]
    assert authority["mode"] == "hash_bound_post_outcome_scientific_correction"
    assert authority["corrected_implementation_commit"] == (
        "5439cd34560b5a908a2d4bef2e77260b01cf4db1"
    )
    assert authority["post_outcome_correction"] is True
    assert {item["session_id"] for item in metrics["inputs"]} == CAPTURES
    for key in ("corrective_analysis_amendment", "corrective_execution_authority"):
        relative = authority[f"{key}_path"]
        expected = authority[f"{key}_sha256"]
        assert f"sha256:{hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()}" == expected

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
        "fixed_500ms_max_score_diagnostic",
        "lean_curvature_500ms",
    }
    assert all(item["scenario_count"] == 12 for item in rows.values())
    assert all(item["evaluable_scenario_count"] == 12 for item in rows.values())
    assert np.isclose(rows["fixed_125ms_linear"]["rmse_hz_s"], 92.7065009641)
    assert np.isclose(rows["fixed_500ms_linear"]["rmse_hz_s"], 291.592149528)
    assert np.isclose(rows["lean_curvature_500ms"]["rmse_hz_s"], 35.8038366781)
    assert np.isclose(rows["fixed_500ms_linear"]["endpoint_coverage"], 1 / 12)
    assert rows["fixed_500ms_linear"]["scenario_simultaneous_coverage"] == 0.0
    diagnostic = rows["fixed_500ms_max_score_diagnostic"]
    assert diagnostic["endpoint_coverage"] == 1.0
    assert diagnostic["scenario_simultaneous_coverage"] == 1.0
    assert np.isclose(
        diagnostic["median_interval_half_width_hz_s"],
        501.144134975,
    )

    calibration = metrics["interval_calibration"]
    assert calibration["confidence"] == 0.95
    assert calibration["usable_scenario_count"] == 12
    assert calibration["required_order"] == 13
    assert calibration["finite_sample_95_available"] is False
    assert calibration["formal_multiplier"] is None
    assert calibration["formal_disposition"] == "abstain_insufficient_calibration_groups"
    assert calibration["diagnostic_order"] == 12
    assert np.isclose(calibration["diagnostic_max_score_multiplier"], 25.7252654407)
    assert np.isclose(
        calibration["maximum_attainable_rank_coverage_under_exchangeability"], 12 / 13
    )
    assert calibration["exchangeability_established"] is False
    promotion = metrics["promotion"]
    assert promotion["fixed500_interval_status"] == "fail"
    assert promotion["formal_95_interval_status"] == ("abstain_insufficient_calibration_groups")
    assert promotion["fixed500_checks"]["unchanged_fixed500_point_rmse"] is False
    assert promotion["fixed500_checks"]["finite_sample_95_interval_available"] is False
    assert promotion["fixed500_checks"]["diagnostic_point_rows_are_exact_clones"] is True
    assert sum(not passed for passed in promotion["fixed500_checks"].values()) == 2
    assert promotion["curvature_status"] == "pass"
    assert all(promotion["curvature_identity_checks"].values())
    assert np.isclose(promotion["curvature_rmse_ratio"], 0.122787382088)


def test_step_diagnostics_apply_exclusion_and_make_no_recovery_claim() -> None:
    step = _metrics()["step_diagnostics"]

    assert step["target_strata"] == ["pre_step", "pre_step", "transition_excluded"]
    assert step["post_exclusion_endpoint_available"] is False
    transition = step["scenario_equal_by_stratum"]["transition_excluded"]
    assert np.isclose(transition["fixed_125ms_linear"]["rmse_hz_s"], 320.583353973)
    assert np.isclose(transition["fixed_500ms_linear"]["rmse_hz_s"], 386.978291753)
    assert np.isclose(transition["lean_curvature_500ms"]["rmse_hz_s"], 1592.35175556)
    post = step["scenario_equal_by_stratum"]["post_exclusion"]
    assert all(item["endpoint_row_count"] == 0 for item in post.values())


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
    assert {row["step_stratum"] for row in endpoints} == {
        "no_step",
        "pre_step",
        "transition_excluded",
        "post_exclusion",
    }
    oracle_step = [
        row
        for row in endpoints
        if row["alignment"] == "oracle_true_resampled_lattice" and float(row["cfo_step_hz"]) != 0.0
    ]
    assert {row["step_stratum"] for row in oracle_step} == {
        "pre_step",
        "transition_excluded",
    }


def test_report_links_and_plain_matplotlib_pngs_resolve() -> None:
    text = REPORT.read_text(encoding="utf-8")
    assert "primary RMSE 291.59 Hz/s" in text
    assert "corrected strict-past quadratic" in text
    assert "86.3%" in text and "2.1%" in text
    assert "requested order is 13" in text
    assert "not a conformal or distribution-free guarantee" in text
    assert "post-outcome corrective amendment" in text
    assert "Mixed pre-step/transition diagnostic" in text
    assert "Post-exclusion recovery" in text and "0/0" in text
    assert "No result here authorizes production promotion or opening" in text
    assert "historical polynomial-injection kernel remains byte-identical" in text

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
