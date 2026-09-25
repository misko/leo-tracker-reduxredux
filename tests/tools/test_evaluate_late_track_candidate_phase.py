from types import SimpleNamespace

import numpy as np
import pytest

from tools.research.evaluate_late_track_candidate_phase import (
    equal_group_metrics,
    fit_baseline_orientation,
    glrt_timeline_rows,
    joint_receiver_result,
    response_metrics,
    selected_track_points,
    wrap_pi,
)


def test_wrap_pi_has_pi_period() -> None:
    values = np.asarray([-0.4, 0.2, 1.0])
    assert wrap_pi(values + np.pi) == pytest.approx(values)


def test_equal_group_metrics_weights_groups_equally() -> None:
    residual = np.asarray([0.0, 0.0, np.pi / 2])
    groups = np.asarray([1, 1, 2])
    result = equal_group_metrics(residual, groups, (1, 2))
    assert result["composite_score"] == pytest.approx(0.0)
    assert result["circular_r_modulo_pi"] == pytest.approx(0.0)


def test_response_uses_frozen_training_bias() -> None:
    duration = np.full(4, 1 / 750)
    prediction = np.asarray([[0.1, 0.2, 0.3, 0.4]])
    bias = np.asarray([12.5])
    measured = prediction[0] + 2 * np.pi * bias[0] * duration
    result = response_metrics(
        measured,
        prediction,
        duration,
        np.asarray([1, 1, 2, 2]),
        (1, 2),
        bias,
    )
    assert result[0]["composite_score"] == pytest.approx(4.0)
    assert result[0]["circular_r_modulo_pi"] == pytest.approx(1.0)
    assert result[0]["rms_rad"] == pytest.approx(0.0, abs=1e-12)


def test_joint_receiver_result_uses_equal_receiver_weight() -> None:
    def receiver(first_train, first_held, second_train, second_held):
        return {
            "models": [
                {
                    "model_kind": "candidate",
                    "catalog_number": 10,
                    "selected_tau_s": 0.0,
                    "even_training_composite_score": first_train,
                    "odd_held_response": {
                        "composite_score": first_held,
                        "circular_r_modulo_pi": 0.8,
                        "rms_rad": 0.2,
                    },
                },
                {
                    "model_kind": "candidate",
                    "catalog_number": 20,
                    "selected_tau_s": 1.0,
                    "even_training_composite_score": second_train,
                    "odd_held_response": {
                        "composite_score": second_held,
                        "circular_r_modulo_pi": 0.4,
                        "rms_rad": 0.5,
                    },
                },
                {
                    "model_kind": "constant_control",
                    "odd_held_response": {"composite_score": 0.0},
                },
                {
                    "model_kind": "wrong_time_control",
                    "odd_held_response": {"composite_score": -0.1},
                },
            ]
        }

    result = joint_receiver_result(
        [receiver(4.0, 3.0, 0.0, 1.0), receiver(0.0, 1.0, 2.0, 0.0)],
        glrt_leader=10,
    )
    assert result["training_selected_catalog_number"] == 10
    assert result["training_selected_odd_held_score"] == pytest.approx(2.0)
    assert result["training_selected_beats_constant"]


def test_fit_baseline_orientation_uses_training_only() -> None:
    predictions = np.zeros((2, 360, 6))
    predictions[0, 79] = np.array([0.0, 1.0, 2.0, 30.0, 31.0, 32.0])
    predictions[1, 120] = np.array([0.0, 2.0, 4.0, 10.0, 10.0, 10.0])
    measured = np.array([10.0, 11.0, 12.0, 40.0, 41.0, 42.0])

    result = fit_baseline_orientation(
        measured,
        predictions,
        np.array([0, 1, 2]),
        np.array([3, 4, 5]),
        [10, 20],
    )

    assert result["training_selected_catalog_number"] == 10
    selected = result["models"][0]
    assert selected["training_fitted_azimuth_deg"] == 79
    assert selected["training_fitted_receiver_cfo_hz"] == pytest.approx(10.0)
    assert selected["held_rms_hz"] == pytest.approx(0.0)


def test_glrt_timeline_uses_device_counter_scan_clock() -> None:
    candidate = SimpleNamespace(
        candidate_rank=3,
        fractional_margin=0.12,
        fractional_tracking_cfo_hz=1250.0,
        passed_fractional_margin_gate=True,
    )
    probe = SimpleNamespace(
        valid_start_counter=1500,
        probe_start_ms=20,
        candidates=(candidate,),
        visit_index=7,
        receiver_id=1,
        channel=4,
        edge="lower",
    )
    source = SimpleNamespace(
        timing=SimpleNamespace(session_start_device_sample_counter=1000),
        sample_rate_hz=1000,
        probes=(probe,),
        session_id="scan-test",
    )

    rows = glrt_timeline_rows(source)

    assert rows == [
        {
            "session_id": "scan-test",
            "visit_index": 7,
            "receiver_id": 1,
            "channel": 4,
            "edge": "lower",
            "time_s": pytest.approx(0.52),
            "candidate_rank": 3,
            "fractional_margin": 0.12,
            "fractional_tracking_cfo_hz": 1250.0,
            "passed_fractional_margin_gate": True,
        }
    ]


def test_selected_track_points_collapses_phase_intervals() -> None:
    rows = [
        {
            "session_id": "scan-test",
            "visit_index": 4,
            "receiver_id": 0,
            "channel": 2,
            "scan_elapsed_s": time,
            "source_tracking_dealiased_cfo_hz": 12_500.0,
        }
        for time in (10.02, 10.08)
    ]

    assert selected_track_points(rows) == [
        {
            "session_id": "scan-test",
            "visit_index": 4,
            "receiver_id": 0,
            "channel": 2,
            "scan_elapsed_s": pytest.approx(10.05),
            "tracking_cfo_hz": 12_500.0,
        }
    ]
