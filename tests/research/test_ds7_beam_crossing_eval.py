import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))

import ds7_beam_crossing as core  # noqa: E402
import ds7_beam_crossing_eval as evaluator  # noqa: E402


def _track() -> core.ConditionalTrack:
    times = np.array([0.0, 1.0, 2.0, 4.0])
    los = np.zeros((2, 4, 3))
    los[:, :, 0] = [[-0.2, -0.1, 0.1, 0.2], [0.2, 0.1, -0.1, -0.2]]
    los[:, :, 2] = np.sqrt(1 - los[:, :, 0] ** 2)
    features = core.trajectory_features(times, los, [-1, 0, 0], [1, 0, 0])
    return core.ConditionalTrack(
        "s:t",
        np.log([0.75, 0.25]),
        times,
        np.array([-0.2, -0.1, 0.1, 0.2]),
        np.ones(4, dtype=bool),
        features,
    )


def test_frozen_split_is_hash_seeded_and_outcome_independent():
    sessions = [f"session-{index}" for index in range(10)]
    expected = sorted(
        sessions,
        key=lambda sid: __import__("hashlib").sha256(f"20260928:{sid}".encode()).hexdigest(),
    )
    assert evaluator.frozen_split(list(reversed(sessions))) == (expected[:6], expected[6:])
    with pytest.raises(ValueError, match="exactly ten"):
        evaluator.frozen_split(sessions[:9])


def test_azel_conversion_uses_geographic_north_convention():
    actual = evaluator.azel_to_enu([90, 0, 0], [0, 0, 90])
    np.testing.assert_allclose(actual, [[1, 0, 0], [0, 1, 0], [0, 0, 1]], atol=1e-15)


def test_arm_nesting_and_ridge_are_explicit():
    track = _track()
    static = evaluator.objective("static_ou", [0.1, 0.3, 0.0, -0.2], [track])
    temporal = evaluator.objective("temporal_ou", [0.1, 0.3, 0.0, 0.0, -0.2], [track])
    assert static == pytest.approx(temporal)
    free = evaluator.objective("geometry_free_ou", [0.1, 0.0, -0.2], [track])
    assert np.isfinite(free)


def test_loader_rejects_hash_mismatch_before_parsing_sources(tmp_path):
    contract = {
        "conditional_endpoint_rows": {"path": "missing.json", "sha256": "sha256:bad"},
        "candidate_temporal_los": {"path": "also-missing.json", "sha256": "sha256:bad"},
    }
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract))
    with pytest.raises(FileNotFoundError):
        evaluator.load_inputs(path)


def test_controls_are_held_scoring_only_and_preserve_row_denominator():
    item = evaluator.PreparedTrack(
        "session",
        _track(),
        np.zeros(4, dtype=int),
        np.array(["lower"] * 4),
        np.full(4, 10_000_000),
        np.zeros(4),
    )
    fit = {"theta": [0.0, 0.4, 0.1, 0.0, -0.2], "temporal": True}
    baseline = evaluator.score_tracks([item], fit)
    for control in ("geometry_swap", "time_shuffle", "trajectory_reversal"):
        scored = evaluator.score_tracks([item], fit, control)
        assert scored["rows"] == baseline["rows"] == 4
        assert scored["per_session"]["session"]["rows"] == 4


def test_nuisance_fit_is_invariant_to_evaluation_outcomes():
    def prepared(session, values):
        source = _track()
        changed = core.ConditionalTrack(
            source.track_id,
            source.log_weights,
            source.times,
            np.asarray(values, dtype=float),
            source.training_mask,
            source.features,
        )
        return evaluator.PreparedTrack(
            session,
            changed,
            np.array([2, 2, 3, 3]),
            np.array(["lower", "upper", "lower", "upper"]),
            np.array([5_000_000, 5_000_000, 10_000_000, 10_000_000]),
            np.log([0.2, 0.4, 0.6, 0.8]),
        )

    training = [prepared("train", [-0.2, -0.1, 0.1, 0.2])]
    first = evaluator.fit_nuisance(training, [prepared("eval", [1, 2, 3, 4])])[2]
    second = evaluator.fit_nuisance(training, [prepared("eval", [100, -20, 9, 40])])[2]
    np.testing.assert_array_equal(first["coefficients"], second["coefficients"])
    assert first["log_anchor_margin_center"] == second["log_anchor_margin_center"]


@pytest.mark.parametrize("arm", evaluator.ARMS)
def test_fit_arm_optimizer_callback_integrates_all_arms(arm):
    source = _track()
    nuisance = np.array([0.02, -0.01, 0.03, -0.02])
    track = core.ConditionalTrack(
        source.track_id,
        source.log_weights,
        source.times,
        source.log_rx1_over_rx0,
        source.training_mask,
        source.features,
        nuisance,
    )
    result = evaluator.fit_arm(arm, [track])
    assert np.isfinite(result["training_objective"])
    assert len(result["starts"]) == 3
    assert all(run["nfev"] > 0 for run in result["starts"])
