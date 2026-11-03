import numpy as np

from tools.investigate_fast_scan_segments import coherent_rows, grouped_folds, search_candidates


def test_groups_stay_together_and_split_is_reproducible():
    times = np.arange(40.0, 60.0, 0.4)
    folds = grouped_folds(times)
    np.testing.assert_array_equal(folds, grouped_folds(times))
    for group in np.unique(np.floor(times / 2)):
        assert len(np.unique(folds[np.floor(times / 2) == group])) == 1
    assert set(folds) == set(range(5))


def test_quadratic_consensus_handles_wrap_and_retains_outlier_inventory():
    times = np.arange(250.0, 280.0)
    dt = times - 265
    values = -90000 - 2100 * dt - 3 * dt**2
    values = (values + 1 / 4.4e-6 / 2) % (1 / 4.4e-6) - 1 / 4.4e-6 / 2
    values[[4, 19]] += 20000
    keep = coherent_rows(times, values)
    assert np.flatnonzero(~keep).tolist() == [4, 19]


def test_test_measurements_cannot_change_candidate_or_parameters():
    grid = np.array([-1.0, 0.0, 1.0])
    times = np.arange(8.0)
    predictions = np.stack([np.column_stack([times * 10 + g, times * 80 + g]) for g in grid])
    visible = np.ones_like(predictions, dtype=bool)
    train = times < 5
    measured = times * 10 + 1
    before = search_candidates(predictions, visible, measured, grid, train, allow_offset=False)
    measured[~train] += 10000
    after = search_candidates(predictions, visible, measured, grid, train, allow_offset=False)
    for key in ("index", "timing_s", "offset_hz", "score", "train_rms_hz"):
        assert before[0][key] == after[0][key]
    assert after[0]["test_rms_hz"] > before[0]["test_rms_hz"]


def test_offset_model_keeps_training_frequency_and_offset_limits():
    grid = np.array([0.0])
    predictions = np.zeros((1, 8, 2))
    predictions[0, :, 1] = np.arange(8.0) * 1000
    measured = np.full(8, 2000.0)
    ranked = search_candidates(
        predictions,
        np.ones_like(predictions, bool),
        measured,
        grid,
        np.ones(8, bool),
        allow_offset=True,
    )
    assert ranked[0]["index"] == 0
    assert ranked[0]["offset_hz"] == 2000
    assert ranked[0]["train_rms_hz"] == 0
