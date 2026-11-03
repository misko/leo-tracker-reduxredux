import hashlib
from pathlib import Path

import numpy as np
import pytest

from evaluate_position_profiles import (
    assert_snapshot_unchanged,
    build_summary,
    paired_time_block_bootstrap,
    validate_profile_record,
)


SESSION = "scan-fw-911c4e5db9243281"


def protocol():
    return {
        "sessions": [SESSION],
        "control": {"sigma_hz": 200},
        "evaluation": {"block_lengths_s": [5, 15, 30]},
    }


def best(log_likelihood, prior=0.0, success=True, status="converged"):
    data_nll = -float(np.sum(log_likelihood))
    return {
        "group_values": [10, 11, 12, 13],
        "group_time_s": [0.0, 1.0, 6.0, 16.0],
        "group_log_likelihood": list(log_likelihood),
        "data_nll": data_nll,
        "prior_objective": prior,
        "objective": data_nll + prior,
        "success": success,
        "status": status,
        "projected_nuisance_gradient_inf_norm": 0.25,
    }


def record(source_path, alternatives=None, complete=True):
    alternatives = alternatives or []
    truth = {
        "label": "truth",
        "kind": "truth",
        "bearing_deg": None,
        "radius_m": None,
        "fixed_position_km": [1.0, 2.0],
        "attempts": [{}],
        "best": best([-2.0, -3.0, -4.0, -5.0], prior=0.5),
    }
    positions = [truth, *alternatives]
    expected = len(positions) if complete else len(positions) + 1
    return {
        "schema": "ds13-position-profile-grid/v1",
        "session": SESSION,
        "sigma_hz": 200,
        "position_count": expected,
        "completed_position_count": len(positions),
        "complete": complete,
        "failed_position_labels": [] if complete else ["east-500m"],
        "positions": positions,
        "source_hashes": {str(source_path): hashlib.sha256(source_path.read_bytes()).hexdigest()},
    }


def alternative(label="north-50m", success=True, likelihood=None, prior=0.7):
    return {
        "label": label,
        "kind": "radial",
        "bearing_deg": 0,
        "radius_m": 50,
        "fixed_position_km": [1.0, 2.05],
        "attempts": [{}, {}],
        "best": best(likelihood or [-2.1, -3.1, -4.1, -5.1], prior, success,
                     "converged" if success else "time_limit"),
    }


def test_paired_bootstrap_is_deterministic_and_adds_prior_once():
    truth = np.array([-2.0, -3.0, -4.0, -5.0])
    other = truth + 0.25
    first = paired_time_block_bootstrap(truth, other, [0, 1, 6, 16], 10.0, 5, 100, 17)
    second = paired_time_block_bootstrap(truth, other, [0, 1, 6, 16], 10.0, 5, 100, 17)
    assert first == second
    assert first["probability_alternative_beats_truth_data_only"] == 1.0
    assert first["probability_alternative_beats_truth_total"] == 0.0
    differences = np.subtract(first["total_delta_nll_quantiles"],
                              first["data_delta_nll_quantiles"])
    assert differences == pytest.approx([10.0, 10.0, 10.0])
    assert first["refit_each_draw"] is False
    assert first["holdout"] is False


def test_validation_detects_source_hash_mismatch(tmp_path):
    source = tmp_path / "source.json"
    source.write_text("old")
    profile = record(source, [alternative()])
    validate_profile_record(profile, protocol(), SESSION)
    source.write_text("new")
    with pytest.raises(RuntimeError, match="provenance mismatch"):
        assert_snapshot_unchanged(profile["source_hashes"])


def test_validation_rejects_objective_decomposition_mismatch(tmp_path):
    source = tmp_path / "source.json"
    source.write_text("source")
    profile = record(source, [alternative()])
    profile["positions"][1]["best"]["objective"] += 1
    with pytest.raises(ValueError, match="objective decomposition"):
        validate_profile_record(profile, protocol(), SESSION)


def test_structural_contract_accepts_separately_labelled_compact_variant(tmp_path):
    source = tmp_path / "source.json"
    source.write_text("source")
    profile = record(source, [alternative()])
    profile["schema"] = "ds13-compact-position-grid/v1"
    profile["model_variant"] = "compact-all-visible-fixedset"
    profile["set_complexity_constant"] = 17.5
    validate_profile_record(profile, protocol(), SESSION)


def test_failed_fit_has_no_bootstrap_probability_and_partial_is_explicit(tmp_path):
    source = tmp_path / "source.json"
    source.write_text("source")
    profile = record(source, [alternative(success=False)], complete=False)
    wrong = {
        "scope": "reference-informed development debugging",
        "scans": [{
            "session": SESSION,
            "variants": [{
                "variant": "common",
                "position_error_km": 2.0,
                "displacement_east_north_km": [1.0, -1.0],
                "success": True,
                "confident_residual_by_channel": [
                    {"mean_hz": -10, "median_hz": -8},
                    {"mean_hz": 20, "median_hz": 16},
                ],
            }],
        }],
    }
    information = {"scope": "retained GLRT peaks, not full response surfaces"}
    amendment = {
        "schema": "ds13-position-profile-resource-amendment/v1",
        "maximum_numerical_workers": 8,
        "scientific_protocol_change": False,
    }
    summary = build_summary([profile], protocol(), amendment, wrong, information, draws=20)
    row = summary["profiles"][0]["positions"][1]
    assert summary["batch_status"] == "partial"
    assert row["bootstrap_eligible"] is False
    assert row["conditional_time_block_bootstrap"] is None
    assert "did not satisfy" in row["bootstrap_exclusion_reason"]


def test_group_order_and_times_must_match_truth(tmp_path):
    source = tmp_path / "source.json"
    source.write_text("source")
    profile = record(source, [alternative()])
    profile["positions"][1]["best"]["group_time_s"][1] += 0.25
    with pytest.raises(ValueError, match="same group receive times"):
        validate_profile_record(profile, protocol(), SESSION)


def test_unresolved_ranking_withholds_bootstrap_even_when_best_converged(tmp_path):
    source = tmp_path / "source.json"
    source.write_text("source")
    candidate = alternative()
    candidate["ranking_resolved"] = False
    profile = record(source, [candidate])
    from evaluate_position_profiles import summarize_profile_record

    row = summarize_profile_record(profile, protocol(), draws=10)["positions"][1]
    assert row["success"] is True
    assert row["ranking_resolved"] is False
    assert row["conditional_time_block_bootstrap"] is None


def test_converged_pair_bootstrap_reports_data_and_timing_separately(tmp_path):
    source = tmp_path / "source.json"
    source.write_text("source")
    profile = record(source, [alternative(likelihood=[-1.9, -2.9, -3.9, -4.9], prior=1.0)])
    validated = validate_profile_record(profile, protocol(), SESSION)
    assert validated is profile
    from evaluate_position_profiles import summarize_profile_record

    summary = summarize_profile_record(profile, protocol(), draws=25)
    row = summary["positions"][1]
    assert row["data_delta_nll_from_truth"] == pytest.approx(-0.4)
    assert row["timing_prior_delta_nll_from_truth"] == pytest.approx(0.5)
    assert row["delta_nll_from_truth"] == pytest.approx(0.1)
    assert len(row["conditional_time_block_bootstrap"]) == 3
    radius = summary["radius_summaries"][0]
    assert radius["optimizer_coordinate_error_km_min"] == pytest.approx(0.05)
    assert radius["optimizer_coordinate_error_km_max"] == pytest.approx(0.05)
