from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic import ValidationError

from leo.analysis.multi_dwell_catalogue_persistence import (
    build_multi_dwell_catalogue_posterior,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.multi_dwell_catalogue import MultiDwellCataloguePosteriorV1
from tests.analysis.test_multi_dwell_catalogue_smoothing import (
    _CATALOG_NUMBERS,
    _config,
    _curve,
    _fixture,
)


def test_persists_complete_history_posterior_without_receiver_nuisance() -> None:
    dwells, bank = _fixture((101, 101, 202, 202))

    product = build_multi_dwell_catalogue_posterior(
        dwells=dwells,
        prediction_bank=bank,
        config=_config(),
    )

    assert product.retained_history_family_complete
    assert not product.any_beam_pruning
    assert product.modes[0].active_catalog_numbers == (101, 202)
    assert tuple(item.catalog_number for item in product.modes[0].assignments) == (
        101,
        101,
        202,
        202,
    )
    assert product.modes[0].handoff_count == 1
    assert product.receiver_local_nuisance_excluded
    assert not product.nuisance_transferable_to_satellite_state
    assert not product.identity_claimed
    serialized = product.model_dump_json()
    assert "dwell_offset_mean_hz" not in serialized
    assert "filtered_drift_mean_hz_per_s" not in serialized
    assert "receiver_local_state" not in serialized


def test_persisted_smoothed_marginal_uses_later_geometry_but_keeps_ambiguity() -> None:
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

    product = build_multi_dwell_catalogue_posterior(
        dwells=dwells,
        prediction_bank=bank,
        config=_config(),
    )

    first = product.smoothed_identity_posteriors[0]
    probabilities = {
        item.catalog_number: item.posterior_probability for item in first.catalogue_probabilities
    }
    assert probabilities[101] > probabilities[202]
    assert not first.exact_tie
    assert product.future_response_used_for_retrospective_identity_smoothing
    assert not product.forward_scores_recomputed_during_persistence


def test_pruned_posterior_remains_explicitly_conditional() -> None:
    dwells, bank = _fixture((101, 101, 101))

    product = build_multi_dwell_catalogue_posterior(
        dwells=dwells,
        prediction_bank=bank,
        config=_config(retained_mode_limit=1),
    )

    assert product.any_beam_pruning
    assert not product.retained_history_family_complete
    assert product.posterior_conditioned_on_retained_beam


def test_response_prediction_and_config_changes_have_distinct_lineage() -> None:
    dwells, bank = _fixture((101, 101))
    baseline = build_multi_dwell_catalogue_posterior(
        dwells=dwells,
        prediction_bank=bank,
        config=_config(),
    )
    changed_dwell = replace(
        dwells[-1],
        measured_cfo_hz=tuple(item + 0.25 for item in dwells[-1].measured_cfo_hz),
    )
    changed_response = build_multi_dwell_catalogue_posterior(
        dwells=(*dwells[:-1], changed_dwell),
        prediction_bank=bank,
        config=_config(),
    )
    changed_config = build_multi_dwell_catalogue_posterior(
        dwells=dwells,
        prediction_bank=bank,
        config=_config(handoff_log_weight=-3.0),
    )

    assert baseline.source_evidence_digest != changed_response.source_evidence_digest
    assert baseline.filter_config_digest != changed_config.filter_config_digest


def test_resealed_marginal_tamper_is_rejected() -> None:
    dwells, bank = _fixture((101, 101))
    product = build_multi_dwell_catalogue_posterior(
        dwells=dwells,
        prediction_bank=bank,
        config=_config(),
    )
    payload = product.model_dump(mode="json", exclude={"content_digest"})
    payload["smoothed_identity_posteriors"][0]["unassigned_probability"] = 0.9

    with pytest.raises(ValidationError, match="sum to one|disagrees"):
        MultiDwellCataloguePosteriorV1.model_validate(
            {**payload, "content_digest": canonical_digest(payload)}
        )
