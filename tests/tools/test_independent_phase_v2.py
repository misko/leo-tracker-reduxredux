import copy
import json
from dataclasses import dataclass

import numpy as np
import pytest

from tools.research import evaluate_independent_phase_v2 as evaluate
from tools.research.independent_phase_split_gauge import circular_response


def test_v1_model_rejected_before_held_access(tmp_path, monkeypatch):
    model = tmp_path / "model.json"
    model.write_text(json.dumps({"schema": "independent-phase-training-model/v1"}))
    monkeypatch.setattr(
        evaluate, "AdaptiveHopIqStore", lambda *_args, **_kwargs: pytest.fail("IQ accessed")
    )
    with pytest.raises(ValueError, match="only the v2"):
        evaluate.extract(model, evaluate.digest(model))


def test_unsealed_driver_rejected_before_held_access(tmp_path, monkeypatch):
    model = tmp_path / "model.json"
    model.write_text(
        json.dumps({"schema": "independent-phase-training-model/v2", "implementation_sha256": {}})
    )
    monkeypatch.setattr(
        evaluate, "AdaptiveHopIqStore", lambda *_args, **_kwargs: pytest.fail("IQ accessed")
    )
    with pytest.raises(ValueError, match="measurement/scoring code is not sealed"):
        evaluate.extract(model, evaluate.digest(model))


def sample_row():
    return {
        "observation": {
            "visit_index": 3,
            "time_s": 5.0,
            "rf_normalization_scale": 0.9,
            "acquired_cfo_hz": -1000,
            "dealiased_native_cfo_hz": 222000,
            "normalized_cfo_hz": 220000,
            "fractional_tracking_cfo_hz": 223000,
        },
        "selected_seed_index": 1,
        "branches": [
            {
                "seed_cfo_hz": -1000,
                "frames": [
                    {
                        "group_id": 1,
                        "session_time_s": 5.03,
                        "frame": {
                            "training_supported": True,
                            "even": {"coherence_margin": 0.2},
                            "odd": {
                                "absolute_cfo_hz": -1100,
                                "search_boundary": True,
                                "exact_coherence": 0.1,
                            },
                        },
                    }
                ],
            },
            {"seed_cfo_hz": 222000, "frames": []},
        ],
    }


def test_response_ignores_held_glrt_refinement_and_original_branch_selection():
    row = sample_row()
    changed = copy.deepcopy(row)
    for key in ("dealiased_native_cfo_hz", "normalized_cfo_hz", "fractional_tracking_cfo_hz"):
        changed["observation"][key] += 1234567
    changed["selected_seed_index"] = 0
    changed["branches"][1]["seed_cfo_hz"] += 999999
    assert circular_response(row) == circular_response(changed)
    assert circular_response(row)["observed_hz"] == [-990]


def test_odd_quality_and_boundary_never_change_response_eligibility():
    row = sample_row()
    changed = copy.deepcopy(row)
    odd = changed["branches"][0]["frames"][0]["frame"]["odd"]
    odd["exact_coherence"] = 0
    odd["search_boundary"] = False
    odd["absolute_cfo_hz"] += 500000
    first, second = circular_response(row), circular_response(changed)
    assert first["time_s"] == second["time_s"]
    assert first["frame_count"] == second["frame_count"] == 1
    assert first["odd_search_boundary_count"] == 1


def test_wrapped_score_is_invariant_in_response_and_prediction():
    y, mu, period = np.asarray([100, 420, -200]), np.asarray([0, 200, 100]), 113000
    residual, nll = evaluate.circular_score(y, mu, period)
    for observed, predicted in ((y + 3 * period, mu), (y, mu - 4 * period)):
        other_residual, other_nll = evaluate.circular_score(observed, predicted, period)
        np.testing.assert_allclose(other_residual, residual)
        np.testing.assert_allclose(other_nll, nll)


def test_circle_score_equal_dwell_weight_and_missing_support():
    responses = [
        {"visit_index": 1, "observed_hz": [3], "period_hz": 113000},
        {"visit_index": 2, "observed_hz": [4] * 20, "period_hz": 113000},
        {"visit_index": 3, "observed_hz": [], "period_hz": 113000},
    ]
    result = evaluate.score_responses(responses, {"model": [[0], [0] * 20, []]})["model"]
    assert result["covered_held_visits"] == 2
    assert result["total_held_visits"] == 3
    assert result["conditional_equal_visit_rms_hz"] == pytest.approx(np.sqrt(12.5))


def test_acquired_extraction_never_uses_refined_or_dealiased_seed(monkeypatch):
    calls = []

    @dataclass
    class Frame:
        reference_sample: float

    def extract(_samples, _rate, **kwargs):
        calls.append(kwargs["acquisition_absolute_cfo_hz"])
        return Frame(kwargs["frame_start_sample"] + 2.0)

    monkeypatch.setattr(evaluate.pilot, "estimate_edge_pilot_frame_complex_split", extract)
    monkeypatch.setattr(
        evaluate,
        "frame_opportunities",
        lambda *_: [(g, 1 + g * 100) for g in range(6) for _ in range(4)],
    )
    observation = {
        **sample_row()["observation"],
        "probe_start_ms": 0,
        "integer_epoch_sample": 1,
        "valid_start_counter": 1000,
        "edge": "lower",
    }
    binding = {"sample_rate_hz": 2500000, "source_first_counter": 0}
    row = evaluate.extract_acquired_row(binding, observation, np.zeros((300000, 2), complex), 1)
    assert calls == [-1000] * 24
    assert len(row["branches"]) == 1
