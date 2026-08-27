from __future__ import annotations

from dataclasses import replace

import pytest

from leo.analysis.multi_dwell_catalogue_backward_smoothing import (
    MultiDwellBackwardSmoothingInputError,
    smooth_multi_dwell_catalogue_identities,
)
from leo.analysis.multi_dwell_catalogue_smoothing import (
    filter_multi_dwell_catalogue_modes,
)
from tests.analysis.test_multi_dwell_catalogue_smoothing import (
    _CATALOG_NUMBERS,
    _config,
    _curve,
    _fixture,
)


def _probability(distribution, identity: int | None) -> float:  # type: ignore[no-untyped-def]
    return next(item.posterior_probability for item in distribution if item.identity == identity)


def test_future_geometry_revises_early_identity_without_rewriting_forward_receipt() -> None:
    assignments = (101, 101, 101)
    curves = {
        (catalog_number, dwell_index): (
            _curve(101, dwell_index)
            if dwell_index < 2 or catalog_number == 101
            else _curve(202, dwell_index)
        )
        for catalog_number in _CATALOG_NUMBERS
        for dwell_index in range(len(assignments))
    }
    dwells, bank = _fixture(assignments, curves=curves)
    forward = filter_multi_dwell_catalogue_modes(dwells, bank, config=_config())
    original_rolling = forward.rolling

    smoothed = smooth_multi_dwell_catalogue_identities(forward)

    first = smoothed.smoothed_dwells[0]
    assert _probability(first.forward_identity_posterior, 101) == pytest.approx(
        _probability(first.forward_identity_posterior, 202)
    )
    assert _probability(first.smoothed_identity_posterior, 101) > _probability(
        first.smoothed_identity_posterior, 202
    )
    assert first.total_variation_revision > 0.0
    assert first.smoothed_nearest_identity == 101
    assert forward.rolling == original_rolling
    assert smoothed.future_response_used_for_retrospective_identity_smoothing
    assert smoothed.response_rescored is False
    assert smoothed.nuisance_states_refit_or_smoothed is False
    assert smoothed.forward_receipts_mutated is False
    assert smoothed.fixed_interval_not_online
    assert not smoothed.identity_claimed


def test_smoothed_handoff_retains_distinct_early_and_late_identity() -> None:
    dwells, bank = _fixture((101, 101, 202, 202))
    forward = filter_multi_dwell_catalogue_modes(dwells, bank, config=_config())

    smoothed = smooth_multi_dwell_catalogue_identities(forward)

    assert tuple(item.smoothed_nearest_identity for item in smoothed.smoothed_dwells) == (
        101,
        101,
        202,
        202,
    )
    assert not smoothed.any_input_pruning
    assert smoothed.source_filter_algorithm_version == forward.algorithm_version


def test_pruned_forward_family_remains_conditional_and_abstains() -> None:
    dwells, bank = _fixture((101, 101, 101))
    forward = filter_multi_dwell_catalogue_modes(
        dwells,
        bank,
        config=_config(retained_mode_limit=1),
    )

    smoothed = smooth_multi_dwell_catalogue_identities(forward)

    assert smoothed.any_input_pruning
    assert smoothed.abstention_recommended
    assert "input-beam-pruned" in smoothed.abstention_diagnostics
    assert smoothed.posterior_conditioned_on_retained_beam


def test_exactly_indistinguishable_histories_remain_an_ambiguity_set() -> None:
    assignments = (101, 101)
    curves = {
        (catalog_number, dwell_index): _curve(101, dwell_index)
        for catalog_number in _CATALOG_NUMBERS
        for dwell_index in range(len(assignments))
    }
    dwells, bank = _fixture(assignments, curves=curves)
    forward = filter_multi_dwell_catalogue_modes(dwells, bank, config=_config())

    smoothed = smooth_multi_dwell_catalogue_identities(forward)

    assert smoothed.smoothed_dwells[-1].exact_smoothed_tie
    assert smoothed.smoothed_dwells[-1].smoothed_ambiguity_set == (101, 202)
    assert smoothed.abstention_recommended
    assert "smoothed-exact-tie" in smoothed.abstention_diagnostics


def test_stale_forward_result_is_rejected_before_smoothing() -> None:
    dwells, bank = _fixture((101, 101))
    forward = filter_multi_dwell_catalogue_modes(dwells, bank, config=_config())
    poisoned_mode = replace(
        forward.final_modes[0],
        posterior_probability_within_retained_beam=0.99,
    )
    poisoned = replace(
        forward,
        final_modes=(poisoned_mode, *forward.final_modes[1:]),
    )

    with pytest.raises(MultiDwellBackwardSmoothingInputError, match="final histories"):
        smooth_multi_dwell_catalogue_identities(poisoned)
