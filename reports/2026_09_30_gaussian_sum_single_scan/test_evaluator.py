import hashlib
import json

import numpy as np
import pytest

from evaluator import evaluate_attempts, evaluate_receipt, hpd_grid, load_sealed_receipt
from plots import density_grid, make_matched_comparison, ranked_associations, timeline_arrays


REFERENCE = (37.849056280893684, -122.48575489722863)


def _receipt(arm="gaussian_sum", status="complete", components=None):
    return {
        "dataset": "synthetic", "unit_id": "u1", "session_id": "s1", "arm": arm,
        "prior_name": "regional", "status": status, "flags": [],
        "components": components or [{"weight": 1., "mean": [0., 0., 0., 0., 0., 0.],
                                       "covariance": np.eye(6).tolist(), "identity_history": ["A"]}],
        "checkpoints": [], "timings": {}, "evidence_hash": "e", "config_hash": "c", "code_hash": "b",
    }


def test_mode_ellipse_is_distinguished_from_full_mixture_hpd():
    components = [
        {"weight": .55, "mean": [-10., 0.], "covariance": [[1., 0.], [0., 1.]], "identity_history": ["A"]},
        {"weight": .45, "mean": [10., 0.], "covariance": [[1., 0.], [0., 1.]], "identity_history": ["B"]},
    ]
    row = evaluate_receipt(_receipt(components=components), reference_latlon=REFERENCE,
                           prior_center_latlon=REFERENCE, grid_resolution=121)
    assert row["point_latlon"][1] < REFERENCE[1]
    assert not row["reference_in_mode_horizontal95_ellipse"]
    assert row["mixture_90_hpd"]["area_km2"] > row["mode_horizontal95_ellipse_area_km2"]
    assert "mixture_reference_density_per_km2" in row
    assert row["grid_convergence"]["relative_area_change"] < .04


def test_hpd_grid_converges_for_standard_normal():
    components = [(1., np.zeros(2), np.eye(2), ())]
    coarse, fine = hpd_grid(components, resolution=121), hpd_grid(components, resolution=241)
    expected = np.pi * 4.605170185988092  # chi-square(2) 90% area
    assert abs(coarse["area_km2"] - expected) / expected < .025
    assert abs(fine["area_km2"] - expected) / expected < .01
    assert abs(fine["area_km2"] - coarse["area_km2"]) / expected < .01
    assert fine["grid_mass_error"] < 1e-8


def test_all_attempts_preserved_and_prior_control_is_matched():
    prior_components = [
        {"weight": .5, "mean": [-5., 0.], "covariance": np.eye(2).tolist()},
        {"weight": .5, "mean": [5., 0.], "covariance": np.eye(2).tolist()},
    ]
    prior = _receipt(arm="prior_only", components=prior_components)
    posterior = _receipt()
    failed = _receipt(arm="greedy", status="timeout")
    result = evaluate_attempts([prior, posterior, failed], reference_latlon=REFERENCE,
                               prior_centers={"regional": REFERENCE}, grid_resolution=61)
    assert result["attempt_count"] == 3 and result["scored_count"] == 2
    assert result["attempts"][0]["prior_only_mode_error_km"] > 4.9
    assert result["attempts"][0]["prior_only_error_km"] == pytest.approx(0.)
    assert result["attempts"][1]["error_change_vs_prior_km"] == pytest.approx(0.)
    assert result["attempts"][2]["failure_status"] == "timeout"
    assert result["attempts"][2]["prior_only_error_km"] == pytest.approx(0.)
    assert result["attempts"][2]["diagnostic_scored"]
    assert "not accepted" in result["attempts"][2]["diagnostic_warning"]


def test_receipt_checksum_is_verified_before_json_use(tmp_path):
    path = tmp_path / "receipt.json"
    raw = json.dumps(_receipt(), sort_keys=True).encode()
    path.write_bytes(raw)
    expected = hashlib.sha256(raw).hexdigest()
    assert load_sealed_receipt(path, expected)["unit_id"] == "u1"
    path.write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_sealed_receipt(path, expected)


def test_malformed_location_covariance_fails_explicitly():
    receipt = _receipt(components=[{"weight": 1., "mean": [0., 0.],
                                     "covariance": [[1., 2.], [2., 1.]], "identity_history": []}])
    with pytest.raises(np.linalg.LinAlgError):
        evaluate_receipt(receipt, reference_latlon=REFERENCE, prior_center_latlon=REFERENCE)


def test_negative_mixture_weight_fails_explicitly():
    receipt = _receipt(components=[{"weight": -1., "mean": [0., 0.],
                                     "covariance": np.eye(2).tolist(), "identity_history": []}])
    with pytest.raises(ValueError, match="weight"):
        evaluate_receipt(receipt, reference_latlon=REFERENCE, prior_center_latlon=REFERENCE)


def test_protocol_configured_center_baseline_is_reported_independently():
    center = (37.85625, -122.484375)
    row = evaluate_receipt(_receipt(), reference_latlon=REFERENCE,
                           prior_center_latlon=center, grid_resolution=61)
    assert .79 < row["configured_center_reference_error_km"] < .83
    assert row["mixture_mean_reference_error_km"] == pytest.approx(
        row["configured_center_reference_error_km"])


def test_plot_helpers_use_full_mixture_and_missing_top_associations():
    mixture = [(0.5, np.array([-3., 0.]), np.eye(2), ()),
               (0.5, np.array([3., 0.]), np.eye(2), ())]
    east, north, densities = density_grid(mixture, resolution=81)
    density = densities[0]
    assert east[density.max(axis=0).argmax()] < -2 or east[density.max(axis=0).argmax()] > 2
    receipt = {"checkpoints": [
        {"factor": 0, "background_probability": .2, "retained_mass": .9, "top_associations": [["1", .8]]},
        {"factor": 1, "background_probability": .7, "retained_mass": .6, "top_associations": [["2", .3]]},
    ]}
    timeline = timeline_arrays(receipt)
    np.testing.assert_allclose(timeline["association"]["1"], [.8, np.nan], equal_nan=True)
    np.testing.assert_allclose(timeline["association"]["2"], [np.nan, .3], equal_nan=True)
    assert ranked_associations(timeline, limit=1) == ["1"]


def test_association_ranking_ignores_missing_entries_and_alphabetical_order():
    timeline = {"association": {
        "00001": np.array([.01, np.nan]),
        "00002": np.array([np.nan, .02]),
        "99999": np.array([np.nan, .95]),
    }}
    assert ranked_associations(timeline, limit=2) == ["99999", "00002"]


def test_matched_plot_requires_same_factor(tmp_path):
    base = _receipt()
    base["checkpoints"] = []
    with pytest.raises(ValueError, match="both arms"):
        make_matched_comparison(base, base, base, tmp_path, factor=17)
