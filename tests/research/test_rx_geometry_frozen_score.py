import copy
import hashlib
import json

import numpy as np
import pytest

from tools.rx_geometry_frozen_score import (
    build_report,
    clutter_baseline,
    prepare_target,
    validate_frozen_model,
)


def _window(role: str, observed: list[float]) -> dict:
    return {
        "role": role,
        "sample_rate_hz": 5_000_000,
        "observed": {
            "rx0": [{"canonical_rx0_hz": value} for value in observed],
            "rx1": [],
        },
        "predictions": [
            {
                "los_enu_unit": {"east": 0.1, "north": 0.2, "up": 0.97},
                "mu_canonical_rx0_hz": 100.0,
                "visible": True,
            }
        ],
    }


def _dataset(session: str, observed: list[float] | None = None) -> dict:
    return {
        "schema": "rx-geometry-dataset/v1",
        "lanes": [
            {
                "recording_split": "evaluation",
                "lane": {"session_id": session},
                "alias_period_hz": 227_000.0,
                "components": [{"log_prior": 0.0}],
                "windows": [
                    _window("reception", observed or []),
                    _window("held_frequency", observed or []),
                ],
            }
        ],
    }


def _model(training_bytes: bytes) -> dict:
    fits = {
        arm: {"success": True, "parameters": [0.0] * dimension}
        for arm, dimension in {"D": 3, "S": 6, "T": 8}.items()
    }
    return {
        "schema": "rx-geometry-association-pilot/v1",
        "status": "complete",
        "dataset_sha256": hashlib.sha256(training_bytes).hexdigest(),
        "sigma_hz": 500.0,
        "clutter_intensities": [1.0, 1.0],
        "feature_center": [0.0] * 8,
        "feature_scale": [1.0] * 8,
        "fits": fits,
    }


def _payload(document: dict) -> bytes:
    return json.dumps(document, sort_keys=True).encode()


def test_target_features_use_frozen_scaler_and_ignore_outcomes() -> None:
    first = _dataset("new", [])
    second = _dataset("new", [100.0, 200.0, 300.0])
    center = np.arange(8, dtype=float)
    scale = np.arange(1, 9, dtype=float)
    first_lane = prepare_target(first, center, scale)[0]
    second_lane = prepare_target(second, center, scale)[0]
    np.testing.assert_array_equal(first_lane["x"], second_lane["x"])
    assert first_lane["counts"][0, 0] == 0
    assert second_lane["counts"][0, 0] == 3


def test_frozen_model_validation_requires_successful_bounded_fit() -> None:
    training = _payload(_dataset("pilot"))
    model = _model(training)
    validate_frozen_model(model)
    model["fits"]["S"]["success"] = False
    with pytest.raises(ValueError, match="S fit"):
        validate_frozen_model(model)
    model = _model(training)
    model["sigma_hz"] = 20_001.0
    with pytest.raises(ValueError, match="sigma"):
        validate_frozen_model(model)


def test_clutter_baseline_empty_and_single_candidate_are_analytic() -> None:
    document = _dataset("new", [])
    document["lanes"][0]["windows"].append(_window("held_frequency", [50.0]))
    lanes = prepare_target(document, np.zeros(8), np.ones(8))
    rates = np.array([2.0, 3.0])
    baseline = clutter_baseline(lanes, rates)
    record = baseline["recordings"]["new"]
    empty = -rates.sum()
    single = empty + np.log(rates[0] / 227_000.0)
    assert record["held_windows"] == 2
    assert record["full_log_score"] == pytest.approx(empty + single)
    assert record["full_log_score_per_window"] == pytest.approx((empty + single) / 2)


def test_default_rejects_pilot_session_overlap() -> None:
    training_document = _dataset("pilot")
    training_bytes = _payload(training_document)
    model = _model(training_bytes)
    model_bytes = _payload(model)
    with pytest.raises(ValueError, match="overlap"):
        build_report(
            model,
            copy.deepcopy(training_document),
            training_document,
            model_bytes=model_bytes,
            target_bytes=training_bytes,
            training_bytes=training_bytes,
        )


def test_descriptive_overlap_replay_is_explicit_and_does_not_fit(monkeypatch) -> None:
    import tools.rx_geometry_fit as fit_module

    monkeypatch.setattr(
        fit_module,
        "fit",
        lambda *args, **kwargs: pytest.fail("frozen scoring called fit"),
    )
    monkeypatch.setattr(
        fit_module,
        "prepare",
        lambda *args, **kwargs: pytest.fail("frozen scoring called prepare"),
    )
    training_document = _dataset("pilot", [100.0])
    training_bytes = _payload(training_document)
    model = _model(training_bytes)
    model_bytes = _payload(model)
    report = build_report(
        model,
        training_document,
        training_document,
        model_bytes=model_bytes,
        target_bytes=training_bytes,
        training_bytes=training_bytes,
        allow_overlap=True,
    )
    assert report["descriptive_overlap_replay"] is True
    assert set(report["evaluations"]) == {"D", "S", "T", "swap", "reverse"}
    held = report["evaluations"]["D"]["recordings"]["pilot"]["held_windows"]
    assert report["clutter_baseline"]["recordings"]["pilot"]["held_windows"] == held
    assert set(report["arm_minus_clutter_per_record"]) == {"D", "S", "T"}
