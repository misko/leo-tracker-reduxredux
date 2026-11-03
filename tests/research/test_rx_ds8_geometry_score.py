import copy
import inspect

import numpy as np
import pytest

import tools.rx_ds8_geometry_score as scorer
from tools.rx_background_crossvalidation import calibration_rows
from tools.rx_ds8_geometry_score import _json_hash, _prepare, analyze
from tools.rx_empirical_background import fit


def _window(window_id, role, time_ns, values, mu=100.0):
    return {
        "source_window_id": window_id,
        "role": role,
        "prediction_utc_ns": time_ns,
        "sample_rate_hz": 5_000_000,
        "observed": {
            "rx0": [{"canonical_rx0_hz": value} for value in values],
            "rx1": [{"canonical_rx0_hz": value + 70.0} for value in values],
        },
        "predictions": [
            {
                "los_enu_unit": {"east": 0.1, "north": 0.2, "up": 0.97},
                "mu_canonical_rx0_hz": mu,
                "visible": True,
            }
        ],
    }


def _lane(session="ds8-a", split="evaluation", prefix="x"):
    return {
        "recording_split": split,
        "lane": {"session_id": session, "channel": 1, "edge": "lower"},
        "alias_period_hz": 1_000.0,
        "components": [
            {"kind": "track_candidate", "log_prior": 0.0},
            {"kind": "other", "log_prior": None},
        ],
        "windows": [
            _window(f"{prefix}-r0", "reception", 1_000_000_000, [90.0, 120.0]),
            _window(f"{prefix}-r1", "reception", 2_000_000_000, [130.0]),
            _window(f"{prefix}-h0", "held_frequency", 3_000_000_000, [160.0]),
        ],
    }


def _training_document():
    lanes = []
    for index in range(6):
        for channel in range(2):
            prefix = f"cal-{index}-{channel}"
            lane = _lane(f"cal-{index}", "calibration", prefix)
            lane["lane"]["channel"] = channel
            lane["windows"] = lane["windows"][:1]
            lanes.append(lane)
    return {"schema": "rx-geometry-dataset/v1", "lanes": lanes}


def _model(training):
    rows = calibration_rows(training)
    background = fit(rows, "joint")
    ids = sorted(row["window_id"] for row in rows)
    dimensions = {"D": 3, "E": 4, "S": 6, "T": 8}
    fits = {
        arm: {
            "candidates": [
                {
                    "parameters": [-2.0] + [0.0] * (dimension - 1) + [0.0, 0.0],
                    "success": True,
                    "calibration_relative_log_evidence": 1.0,
                    "map_penalty": 0.0,
                    "map_gain": 1.0,
                }
            ],
            "selected": {
                "beta": [-2.0] + [0.0] * (dimension - 1),
                "occupancy": 0.5,
                "tau_s": 1.0,
                "calibration_relative_log_evidence": 1.0,
                "map_penalty": 0.0,
                "map_gain": 1.0,
                "null_selected": False,
            }
        }
        for arm, dimension in dimensions.items()
    }
    return {
        "schema": "rx-causal-full-calibration/v1",
        "status": "complete",
        "sigma_hz": 500.0,
        "calibration_sessions": sorted({row["session_id"] for row in rows}),
        "training_source_window_ids": ids,
        "training_source_window_count": len(ids),
        "training_source_window_ids_sha256": _json_hash(ids),
        "background_model": background,
        "background_model_sha256": _json_hash(background),
        "feature_center": [0.0] * 8,
        "feature_scale": [1.0] * 8,
        "families": {"uniform": {"fits": fits}, "causal": {"fits": copy.deepcopy(fits)}},
    }


def _readiness():
    return {
        "schema": "rx-ds8-confirmation-readiness/v1",
        "selected": [{"session_id": name} for name in ("ds8-a", "ds8-b", "ds8-c", "ds8-d")],
    }


def test_causal_preparation_is_prefix_invariant_to_held_outcome():
    training = _training_document()
    model = _model(training)
    first = {"schema": "rx-geometry-dataset/v1", "lanes": [_lane()]}
    changed = copy.deepcopy(first)
    changed["lanes"][0]["windows"][-1]["observed"]["rx0"] = [
        {"canonical_rx0_hz": 880.0}
    ]
    before = _prepare(first, model["background_model"], np.zeros(8), np.ones(8))[1][0]
    after = _prepare(changed, model["background_model"], np.zeros(8), np.ones(8))[1][0]
    np.testing.assert_allclose(before["reference"][:2], after["reference"][:2])
    np.testing.assert_allclose(before["signal"][:2], after["signal"][:2])


def test_quarter_period_control_changes_signal_but_not_causal_reference():
    training = _training_document()
    background = _model(training)["background_model"]
    document = {"schema": "rx-geometry-dataset/v1", "lanes": [_lane()]}
    base = _prepare(document, background, np.zeros(8), np.ones(8), None)[1][0]
    shifted = _prepare(document, background, np.zeros(8), np.ones(8), "shift")[1][0]
    np.testing.assert_allclose(base["reference"], shifted["reference"], rtol=0, atol=0)
    assert not np.allclose(base["signal"], shifted["signal"], rtol=1e-10, atol=1e-10)


def test_analyze_exports_missing_readiness_coverage_and_common_reference():
    training = _training_document()
    model = _model(training)
    document = {"schema": "rx-geometry-dataset/v1", "lanes": [_lane()]}
    result = analyze(document, model, training, _readiness())
    assert result["eligible_sessions"] == ["ds8-a"]
    assert result["records"]["ds8-b"] == {
        "eligible": False,
        "eligible_lanes": 0,
        "eligible_windows": 0,
        "reason": "no eligible lane in the frozen DS8 dataset",
    }
    assert result["aggregate_equal_record"][
        "held_frequency:causal_T-causal_reference"
    ]["eligible_recordings"] == 1
    record = result["records"]["ds8-a"]
    causal_ref = record["references"]["held_frequency"]["causal_reference_log_score"]
    for family in ("uniform", "causal"):
        for evaluation in record["families"][family]["evaluations"].values():
            assert evaluation["roles"]["held_frequency"]["reference_log_score"] == pytest.approx(
                causal_ref
            )


def test_rejects_training_overlap_and_contains_no_fitting_entrypoint():
    training = _training_document()
    model = _model(training)
    document = {"schema": "rx-geometry-dataset/v1", "lanes": [_lane("cal-0")]}
    readiness = _readiness()
    readiness["selected"][0]["session_id"] = "cal-0"
    with pytest.raises(ValueError, match="overlap"):
        analyze(document, model, training, readiness)
    source = inspect.getsource(scorer)
    assert "fit_arms" not in source
    assert "minimize(" not in source


def test_rejects_wrong_arm_dimension_and_no_converged_candidate():
    training = _training_document()
    document = {"schema": "rx-geometry-dataset/v1", "lanes": [_lane()]}
    malformed = _model(training)
    malformed["families"]["uniform"]["fits"]["D"]["selected"]["beta"].append(0.0)
    with pytest.raises(ValueError, match="D coefficient dimension"):
        analyze(document, malformed, training, _readiness())

    unconverged = _model(training)
    unconverged["families"]["causal"]["fits"]["S"]["candidates"][0]["success"] = False
    with pytest.raises(ValueError, match="no S optimizer candidate converged"):
        analyze(document, unconverged, training, _readiness())
