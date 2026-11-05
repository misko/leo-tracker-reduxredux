import numpy as np
import pytest

from leo.analysis.localization_v3 import reassociation_predictive as predictive
from leo.analysis.localization_v3.reassociation_uniqueness import conditional_uniqueness


def test_synchronized_partitions_guard_adjacent_blocks_and_remain_unique():
    times = np.tile(np.arange(100.0), 3)
    groups = np.repeat(np.arange(3), 100)
    for partitioner in (predictive.masks, predictive.partitions):
        parts = partitioner(times, groups)
        assert len(parts) == (5 if partitioner is predictive.masks else 10)
        for part in parts:
            blocks = np.floor(times / 5).astype(int)
            np.testing.assert_array_equal(part["test"], np.isin(blocks, part["held_blocks"]))
            assert not np.any(part["train"] & part["test"])
            guarded = np.r_[part["held_blocks"] - 1, part["held_blocks"], part["held_blocks"] + 1]
            assert not part["train"][np.isin(blocks, guarded)].any()
            for group in np.unique(groups):
                assert sum(part["train"] & (groups == group)) >= 5
                assert sum(part["test"] & (groups == group)) >= 2
        repeat = partitioner(times, groups)
        assert [p["held_blocks"].tolist() for p in parts] == [
            p["held_blocks"].tolist() for p in repeat
        ]
    assert len({tuple(p["held_blocks"]) for p in parts}) == len(parts)


@pytest.mark.parametrize("model", ["track_offset", "receiver_offset", "frozen_radio", "inherited"])
def test_held_values_cannot_change_training_aliases_phase_or_nuisance(model):
    times = np.tile(np.arange(40.0), 2)
    groups = np.repeat([0, 1], 40)
    receivers = np.ones(len(times), int)
    train = times < 30
    phase = np.linspace(-2, 2, 11)
    raw = 20 * times[None, :] + 100 * phase[:, None]
    changed = raw.copy()
    changed[:, ~train] += 100000

    def fit(values):
        if model == "inherited":
            return predictive.fit_predict(
                values, times, np.ones(len(times)), groups, train, ~train, phase
            )
        return predictive.predict(
            values, times, np.ones(len(times)), groups, receivers, train, ~train, phase, model, 5.0
        )

    before, after = fit(raw), fit(changed)
    for key in (
        "training_score",
        "phase_map_s",
        "coefficient",
        "aliases",
        "alias_by_group",
        "training_track_cost",
    ):
        if key in before:
            if isinstance(before[key], np.ndarray):
                np.testing.assert_array_equal(before[key], after[key])
            else:
                assert before[key] == after[key]
    assert before["predictive_score"] != after["predictive_score"]


@pytest.mark.parametrize("model", ["track_offset", "receiver_offset", "frozen_radio"])
def test_predictive_density_matches_direct_gaussian_conditioning(model):
    times = np.arange(12.0) + 130
    groups = np.repeat([0, 1, 2], 4)
    rx = np.repeat([1, 1, 2], 4)
    q = np.linspace(0.95, 1.05, 12)
    y = np.arange(12.0) * 17 - 50
    train = np.arange(12) % 2 == 0
    if model == "track_offset":
        columns = [(groups == g) * 300.0 for g in np.unique(groups)]
    elif model == "receiver_offset":
        columns = [(rx == r) * 300.0 for r in np.unique(rx)]
    else:
        columns = []
    design = np.column_stack(columns + [q * (times - 150) * 0.5])
    covariance = 150**2 * np.eye(12) + design @ design.T
    tt = covariance[np.ix_(train, train)]
    ht = covariance[np.ix_(~train, train)]
    hh = covariance[np.ix_(~train, ~train)]
    mean = ht @ np.linalg.solve(tt, y[train])
    conditional = hh - ht @ np.linalg.solve(tt, ht.T)
    residual = y[~train] - mean
    expected = (
        residual @ np.linalg.solve(conditional, residual)
        + np.linalg.slogdet(conditional)[1]
        + sum(~train) * np.log(2 * np.pi)
    )
    result = predictive.predict(
        y[None, :], times, q, groups, rx, train, ~train, np.array([0.0]), model, 5.0
    )
    assert result["predictive_score"] == pytest.approx(expected, abs=1e-10)


def uniqueness_fixture():
    parts = [dict(fold=i, held_blocks=[i]) for i in range(5)]
    rows = [
        dict(
            arm=arm,
            fold=i,
            norad=n,
            model="receiver_offset",
            phase_sd_s=5.0,
            predictive_score=10.0 if n == 1 else 12.0,
        )
        for arm in ("c0", "fitted_c")
        for i in range(5)
        for n in (1, 2, 3)
    ]
    return rows, parts


def test_uniqueness_requires_every_competitor_in_every_distinct_fold_and_both_arms():
    rows, parts = uniqueness_fixture()
    assert conditional_uniqueness(rows, parts, [1, 2, 3], 1)["passed"]
    rows[-1]["predictive_score"] = 9.0
    result = conditional_uniqueness(rows, parts, [1, 2, 3], 1)
    assert not result["passed"] and result["minimum_margin"] == -1.0
    result = conditional_uniqueness(rows[:-1], parts, [1, 2, 3], 1)
    assert result["status"] == "not_evaluated" and result["missing"]


def test_repeated_partitions_cannot_manufacture_minimum_fold_count():
    rows, parts = uniqueness_fixture()
    parts = [parts[0]] * 10
    result = conditional_uniqueness(rows, parts, [1, 2, 3], 1)
    assert result["unique_folds"] == 1 and not result["passed"]


def test_duplicate_or_nonfinite_competitor_scores_are_rejected():
    rows, parts = uniqueness_fixture()
    with pytest.raises(ValueError, match="duplicate"):
        conditional_uniqueness(rows + [rows[0]], parts, [1, 2, 3], 1)
    rows[0]["predictive_score"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        conditional_uniqueness(rows, parts, [1, 2, 3], 1)
