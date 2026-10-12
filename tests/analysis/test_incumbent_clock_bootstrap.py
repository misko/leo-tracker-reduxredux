import numpy as np
import pytest

from leo.analysis.clock_conditioned_bootstrap import ClockConditioningConfiguration
from leo.analysis.continuous_merge_bootstrap import (
    ContinuousBootstrapPolicy,
    bootstrap_with_continuity,
)
from leo.analysis.incumbent_clock_bootstrap import bootstrap_with_clock_incumbents
from leo.analysis.regional_position_bootstrap import PositionBootstrap
from leo.analysis.regional_position_score import ALIAS_HZ
from tests.analysis.test_clock_conditioned_bootstrap import fixture, predictor


def test_incumbent_recovers_known_drift_and_can_choose_an_early_pass():
    obs, bank, prior, tracks = fixture()
    audit = []
    result = bootstrap_with_clock_incumbents(
        obs,
        bank,
        prior,
        [0, 0],
        tracks,
        merged_tracks=(),
        maximum_seconds=10,
        orbit_predictor=predictor,
        audit=audit.append,
    )
    np.testing.assert_allclose(result.vector[[3, 5]], [12, -8], atol=0.01)
    assert audit[0]["complete_path"]
    selected = audit[0]["candidates"][audit[0]["selected"]]
    assert selected["score"] <= audit[0]["candidates"][0]["score"]
    assert selected["source"]["pass"] < 2


def test_no_conditioning_reuses_exact_passes_and_preserves_old_original_seed():
    obs, bank, prior, tracks = fixture()
    old = bootstrap_with_continuity(
        obs,
        bank,
        prior,
        [0, 0],
        tracks,
        merged_tracks=(),
        maximum_seconds=10,
        orbit_predictor=predictor,
    )
    audit = []
    result = bootstrap_with_clock_incumbents(
        obs,
        bank,
        prior,
        [0, 0],
        tracks,
        merged_tracks=(),
        maximum_seconds=10,
        configuration=ClockConditioningConfiguration(conditioning="none"),
        orbit_predictor=predictor,
        audit=audit.append,
    )
    np.testing.assert_array_equal(result.vector, old.vector)
    assert audit[0]["profiles"] == 1
    assert sum(e["reused"] for e in audit[0]["events"]) == 8
    assert audit[0]["candidates"][audit[0]["selected"]]["source"]["kind"] == "original"


def test_deteriorating_later_seeds_cannot_evict_original_incumbent(monkeypatch):
    import leo.analysis.incumbent_clock_bootstrap as module

    obs, bank, prior, tracks = fixture()
    original_builder = module.seed_from_profiled_shapes
    calls = []

    def drifting_builder(*args, **kwargs):
        result = original_builder(*args, **kwargs)
        calls.append(1)
        if len(calls) > 1:
            vector = result.vector.copy()
            vector[[2, 4]] += ALIAS_HZ / 2
            result = PositionBootstrap(result.satellite_indices, vector, result.matches)
        return result

    monkeypatch.setattr(module, "seed_from_profiled_shapes", drifting_builder)
    audit = []
    result = module.bootstrap_with_clock_incumbents(
        obs,
        bank,
        prior,
        [0, 0],
        tracks,
        merged_tracks=(),
        maximum_seconds=10,
        policy=ContinuousBootstrapPolicy(mode="baseline"),
        orbit_predictor=predictor,
        audit=audit.append,
    )
    assert audit[0]["selected"] == 0
    assert audit[0]["candidates"][0]["source"]["kind"] == "original"
    assert np.isfinite(result.vector).all()


def test_failed_branch_and_expired_search_retain_complete_original_seed(monkeypatch):
    import leo.analysis.incumbent_clock_bootstrap as module

    obs, bank, prior, tracks = fixture()
    original_profile = module.profile_bootstrap_shapes
    calls = []

    def expires(*args, **kwargs):
        calls.append(1)
        if len(calls) > 1:
            raise TimeoutError("injected elapsed budget")
        return original_profile(*args, **kwargs)

    monkeypatch.setattr(module, "profile_bootstrap_shapes", expires)
    audit = []
    result = module.bootstrap_with_clock_incumbents(
        obs,
        bank,
        prior,
        [0, 0],
        tracks,
        merged_tracks=(),
        maximum_seconds=10,
        policy=ContinuousBootstrapPolicy(mode="baseline"),
        orbit_predictor=predictor,
        audit=audit.append,
    )
    assert not audit[0]["complete_path"] and audit[0]["timed_out"]
    assert audit[0]["events"][-1]["status"] == "failed"
    assert audit[0]["selected"] == 0
    assert len(result.matches) == len(tracks)


def test_invalid_selection_and_no_completed_baseline_are_explicit():
    obs, bank, prior, tracks = fixture()
    with pytest.raises(ValueError, match="selection"):
        bootstrap_with_clock_incumbents(
            obs, bank, prior, [0, 0], tracks, merged_tracks=(), selection="unknown"
        )
    with pytest.raises(TimeoutError):
        bootstrap_with_clock_incumbents(
            obs,
            bank,
            prior,
            [0, 0],
            tracks,
            merged_tracks=(),
            maximum_seconds=1e-12,
            orbit_predictor=predictor,
        )
    with pytest.raises(ValueError, match="track indices"):
        bootstrap_with_clock_incumbents(
            obs, bank, prior, [0, 0], ((0, 0, 0),), merged_tracks=(), orbit_predictor=predictor
        )
