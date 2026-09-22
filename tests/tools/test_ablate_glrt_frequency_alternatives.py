import importlib.util
from pathlib import Path

import numpy as np
import pytest

PATH = Path(__file__).parents[2] / "tools/research/ablate_glrt_frequency_alternatives.py"
SPEC = importlib.util.spec_from_file_location("ablate_glrt_frequency_alternatives", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_deduplicates_cfo_and_epoch_but_keeps_distinct_epoch_solution():
    group = {
        "actual_rf_hz": MODULE.CANONICAL_RF_HZ,
        "selected_candidate_rank": 0,
        "selected_trajectory_cfo_hz": 1000.0,
        "candidates": [
            {
                "candidate_rank": 0,
                "fractional_tracking_cfo_hz": 20.0,
                "integer_epoch_sample": 4,
                "fractional_epoch_offset_samples": 0.1,
                "passed_fractional_margin_gate": True,
            },
            {
                "candidate_rank": 1,
                "fractional_tracking_cfo_hz": 20.001,
                "integer_epoch_sample": 4,
                "fractional_epoch_offset_samples": 0.101,
                "passed_fractional_margin_gate": True,
            },
            {
                "candidate_rank": 2,
                "fractional_tracking_cfo_hz": 20.001,
                "integer_epoch_sample": 5,
                "fractional_epoch_offset_samples": 0.1,
                "passed_fractional_margin_gate": True,
            },
        ],
    }
    unique = MODULE.deduplicate_passing(group)
    assert [row[2] for row in unique] == [0, 2]


def test_selected_nonzero_rank_is_first_profile_seed_even_when_duplicate():
    group = {
        "actual_rf_hz": MODULE.CANONICAL_RF_HZ,
        "selected_candidate_rank": 1,
        "selected_trajectory_cfo_hz": 500.0,
        "candidates": [
            {
                "candidate_rank": rank,
                "fractional_tracking_cfo_hz": value,
                "integer_epoch_sample": 7,
                "fractional_epoch_offset_samples": 0.2,
                "passed_fractional_margin_gate": True,
            }
            for rank, value in ((0, 20.001), (1, 20.0), (2, 800.0))
        ],
    }
    unique = MODULE.deduplicate_passing(group)
    assert unique[0][2] == 1
    assert unique[0][0] == pytest.approx(group["selected_trajectory_cfo_hz"])


def test_selected_offset_is_training_only_and_heldout_is_not_refit():
    observed = np.array([10.0, 12.0, 14.0, 10_000.0])
    predicted = np.zeros(4)
    offset, _, heldout = MODULE.selected_only_offset(
        observed, predicted, np.array([True, True, True, False]), sigma_hz=250
    )
    assert offset == pytest.approx(12.0)
    assert heldout[0] == pytest.approx(-0.5 * ((10_000 - 12) / 250) ** 2 - np.log(250))


def test_multistart_profile_matches_dense_oracle_on_multimodal_scene():
    rows = tuple(
        np.asarray(values, dtype=float)
        for values in ([0, 900], [20, 920], [-10, 890], [30, 930], [40, 940])
    )
    training = np.array([True, True, True, True, False])
    result = MODULE.profile_alternative_offset(rows, np.zeros(5), training, sigma_hz=250)
    grid = np.linspace(-500, 1400, 100_001)
    oracle = np.asarray(
        [sum(MODULE._row_log_mixture(rows[:4], float(offset), 250)) for offset in grid]
    )
    best = grid[int(np.argmax(oracle))]
    assert result["offset_hz"] == pytest.approx(best, abs=0.03)
    assert result["profile_status"].endswith("not-global-certified")


def test_uniform_alternative_likelihood_does_not_use_glrt_scores():
    rows = (np.array([-100.0, 100.0]), np.array([-90.0, 110.0]))
    result = MODULE.profile_alternative_offset(
        rows, np.zeros(2), np.array([True, False]), sigma_hz=250
    )
    assert result["offset_hz"] == pytest.approx(0.0, abs=1e-8)


def test_vectorized_candidate_profile_matches_scalar_profiles():
    rows = (np.array([-100.0, 100.0]), np.array([-90.0, 110.0]), np.array([30.0]))
    prediction = np.array([[0.0, 5.0, 10.0], [30.0, -20.0, 5.0]])
    training = np.array([True, True, False])
    batch = MODULE.profile_candidate_batch(rows, prediction, training)
    for index, candidate in enumerate(prediction):
        scalar = MODULE.profile_alternative_offset(
            rows, candidate, training, tolerance_hz=1e-6, maximum_iterations=120
        )
        assert batch["offset_hz"][index] == pytest.approx(scalar["offset_hz"], abs=1e-6)
        np.testing.assert_allclose(
            batch["heldout_row_log_likelihood"][index],
            scalar["heldout_row_log_likelihood"],
            atol=1e-10,
        )


def test_alternative_profile_training_is_unchanged_by_heldout_values_and_width():
    training = np.array([True, True, False])
    original = (np.array([-100.0, 100.0]), np.array([-90.0, 110.0]), np.array([30.0]))
    poisoned = (
        original[0],
        original[1],
        np.array([-1_000_000.0, 5.0, 700_000.0, 900_000.0]),
    )
    prediction = np.array([[0.0, 5.0, 10.0], [30.0, -20.0, 5.0]])
    batch_a = MODULE.profile_candidate_batch(original, prediction, training)
    batch_b = MODULE.profile_candidate_batch(poisoned, prediction, training)
    np.testing.assert_allclose(batch_a["offset_hz"], batch_b["offset_hz"], atol=1e-9)
    np.testing.assert_allclose(
        batch_a["training_row_log_likelihood"],
        batch_b["training_row_log_likelihood"],
        atol=1e-12,
    )
    scalar_a = MODULE.profile_alternative_offset(original, prediction[0], training)
    scalar_b = MODULE.profile_alternative_offset(poisoned, prediction[0], training)
    assert scalar_a["offset_hz"] == pytest.approx(scalar_b["offset_hz"], abs=1e-9)


def test_checkpoint_qualification_and_nonconvergence_use_json_scalar_boundaries(tmp_path):
    path = tmp_path / "checkpoint.json"
    document = {
        "qualified": bool(np.bool_(False)),
        "selected_candidate_profile_nonconverged_count": int(np.int64(3)),
    }
    MODULE._write_checkpoint(path, document)
    loaded = __import__("json").loads(path.read_text())
    assert loaded["qualified"] is False
    assert loaded["selected_candidate_profile_nonconverged_count"] == 3


def test_common_target_gaussian_uses_frozen_training_offsets_and_selected_rows():
    observed = np.array([100.0, 130.0, 10_000.0])
    prediction = np.array([[10.0, 20.0, 30.0], [-20.0, 0.0, 20.0]])
    offsets = np.array([100.0, 125.0])
    rows = MODULE.gaussian_rows_at_frozen_offsets(observed, prediction, offsets, sigma_hz=250.0)
    expected = -0.5 * ((10_000.0 - 30.0 - 100.0) / 250.0) ** 2 - np.log(250.0)
    assert rows[0, 2] == pytest.approx(expected)
    poisoned = observed.copy()
    poisoned[2] = -20_000.0
    poisoned_rows = MODULE.gaussian_rows_at_frozen_offsets(
        poisoned, prediction, offsets, sigma_hz=250.0
    )
    np.testing.assert_allclose(rows[:, :2], poisoned_rows[:, :2])
