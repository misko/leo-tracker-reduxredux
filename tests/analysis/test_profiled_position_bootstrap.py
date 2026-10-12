from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.continuous_merge_bootstrap import (
    ContinuousBootstrapPolicy,
    bootstrap_with_continuity,
    choose_proposals,
)
from leo.analysis.profiled_position_bootstrap import (
    profile_bootstrap_shapes,
    seed_from_profiled_shapes,
)
from leo.analysis.regional_position_bootstrap import BootstrapMatch, bootstrap_position
from tests.analysis.test_clock_conditioned_bootstrap import fixture, predictor


@pytest.mark.parametrize("alias", [0, 227272.72727272726, -454545.45454545453])
def test_profiled_reconstruction_matches_original_on_aliases_and_overlapping_pool(alias):
    obs, bank, prior, tracks = fixture()
    obs = replace(obs, measured_hz=obs.measured_hz + alias)
    pool = (*tracks, tracks[1])
    old = bootstrap_position(
        obs, bank, prior, [3, -5], pool, maximum_seconds=10, orbit_predictor=predictor
    )
    matches = profile_bootstrap_shapes(
        obs, bank, prior, [3, -5], pool, maximum_seconds=10, orbit_predictor=predictor
    )
    new = seed_from_profiled_shapes(
        obs, bank, prior, [3, -5], matches, maximum_seconds=10, orbit_predictor=predictor
    )
    assert matches == old.matches
    assert new.satellite_indices == old.satellite_indices
    np.testing.assert_array_equal(new.vector, old.vector)


def test_selected_pool_matches_reproduce_old_continuity_seed_with_fewer_predictions():
    obs, bank, prior, tracks = fixture()
    split = (tracks[1][:40], tracks[1][40:], *tracks[:1], *tracks[2:])
    policy = ContinuousBootstrapPolicy(mode="consistent", rms_floor_hz=1000)
    calls = []

    def counted(*args, **kwargs):
        calls.append(1)
        return predictor(*args, **kwargs)

    old = bootstrap_with_continuity(
        obs,
        bank,
        prior,
        [0, 0],
        split,
        merged_tracks=(tracks[1],),
        policy=policy,
        maximum_seconds=10,
        orbit_predictor=counted,
    )
    old_calls = len(calls)
    calls.clear()
    matches = profile_bootstrap_shapes(
        obs, bank, prior, [0, 0], (*split, tracks[1]), maximum_seconds=10, orbit_predictor=counted
    )
    selected, _ = choose_proposals(split, (tracks[1],), matches, obs.times_s, policy)
    by_rows = {m.rows: m for m in matches}
    new = seed_from_profiled_shapes(
        obs,
        bank,
        prior,
        [0, 0],
        [by_rows[t] for t in selected if t in by_rows],
        maximum_seconds=10,
        orbit_predictor=counted,
    )
    assert old_calls == 44 and len(calls) == 22
    assert new.matches == old.matches
    np.testing.assert_array_equal(new.vector, old.vector)


def test_invisible_candidates_and_time_gauge_match_original_oracle():
    obs, bank, prior, tracks = fixture()

    def visible_predictor(*args, **kwargs):
        values, visible, _, _ = predictor(*args, **kwargs)
        visible[:, np.asarray(args[0].numbers) == 101] = False
        return values, visible, None, None

    old = bootstrap_position(
        obs, bank, prior, [0, 0], tracks, maximum_seconds=10, orbit_predictor=visible_predictor
    )
    matches = profile_bootstrap_shapes(
        obs, bank, prior, [0, 0], tracks, maximum_seconds=10, orbit_predictor=visible_predictor
    )
    new = seed_from_profiled_shapes(
        obs, bank, prior, [0, 0], matches, maximum_seconds=10, orbit_predictor=visible_predictor
    )
    assert new.matches == old.matches
    np.testing.assert_array_equal(new.vector, old.vector)
    forced = tuple(
        BootstrapMatch(m.rows, m.satellite_index, 20, m.shape_rms_hz, m.shape_cost) for m in matches
    )
    bounded = seed_from_profiled_shapes(
        obs, bank, prior, [0, 0], forced, maximum_seconds=10, orbit_predictor=visible_predictor
    )
    assert abs(bounded.vector[7]) <= 10


def test_invalid_support_and_expired_work_bounds_fail_explicitly():
    obs, bank, prior, tracks = fixture()
    with pytest.raises(ValueError, match="track indices"):
        profile_bootstrap_shapes(obs, bank, prior, [0, 0], ((0, 0, 0),))
    with pytest.raises(TimeoutError):
        profile_bootstrap_shapes(
            obs, bank, prior, [0, 0], tracks, maximum_seconds=1e-12, orbit_predictor=predictor
        )
    with pytest.raises(ValueError, match="both receivers"):
        seed_from_profiled_shapes(obs, bank, prior, [0, 0], ())
