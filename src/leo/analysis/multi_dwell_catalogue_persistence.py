"""Build a digest-closed posterior from the bounded synthetic multi-dwell filter."""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

from leo.analysis.multi_dwell_catalogue_backward_smoothing import (
    smooth_multi_dwell_catalogue_identities,
)
from leo.analysis.multi_dwell_catalogue_smoothing import (
    MultiDwellFilterConfig,
    SyntheticCfoDwell,
    SyntheticMultiDwellPredictionBank,
    filter_multi_dwell_catalogue_modes,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.multi_dwell_catalogue import (
    DwellCatalogueProbabilityV1,
    MultiDwellCataloguePosteriorV1,
    MultiDwellHistoryAssignmentV1,
    MultiDwellHistoryModeV1,
    MultiDwellIdentityPosteriorV1,
)
from leo.contracts.standard_pipeline import StandardScientificStatus


def build_multi_dwell_catalogue_posterior(
    *,
    dwells: tuple[SyntheticCfoDwell, ...],
    prediction_bank: SyntheticMultiDwellPredictionBank,
    config: MultiDwellFilterConfig,
) -> MultiDwellCataloguePosteriorV1:
    """Filter once, smooth identities, and persist no receiver-local nuisance state."""

    forward = filter_multi_dwell_catalogue_modes(dwells, prediction_bank, config=config)
    smoothed = smooth_multi_dwell_catalogue_identities(forward)
    positive_modes = tuple(
        item
        for item in forward.final_modes
        if item.posterior_probability_within_retained_beam > 0.0
    )
    if not positive_modes:
        raise ValueError("multi-dwell persistence found no positive retained history")
    positive_mass = math.fsum(
        item.posterior_probability_within_retained_beam for item in positive_modes
    )
    if not math.isfinite(positive_mass) or positive_mass <= 0.0:
        raise ValueError("multi-dwell positive history mass is not representable")

    modes = []
    for rank, source in enumerate(positive_modes, start=1):
        probability = source.posterior_probability_within_retained_beam / positive_mass
        payload: dict[str, object] = {
            "schema_version": 1,
            "rank": rank,
            "assignments": tuple(
                MultiDwellHistoryAssignmentV1(
                    dwell_id=dwell_id,
                    catalog_number=catalog_number,
                ).model_dump(mode="json")
                for dwell_id, catalog_number in zip(
                    forward.dwell_ids,
                    source.assignments,
                    strict=True,
                )
            ),
            "active_catalog_numbers": source.active_catalog_numbers,
            "cumulative_negative_log_joint": source.cumulative_negative_log_joint,
            "log_posterior_probability": math.log(probability),
            "posterior_probability": probability,
            "handoff_count": sum(
                left != right
                for left, right in zip(source.assignments, source.assignments[1:], strict=False)
            ),
            "null_dwell_count": sum(item is None for item in source.assignments),
        }
        modes.append(
            MultiDwellHistoryModeV1.model_validate(
                {**payload, "mode_digest": canonical_digest(payload)}
            )
        )

    identity_posteriors = tuple(
        MultiDwellIdentityPosteriorV1(
            dwell_index=item.dwell_index,
            dwell_id=item.dwell_id,
            unassigned_probability=next(
                entry.posterior_probability
                for entry in item.smoothed_identity_posterior
                if entry.identity is None
            ),
            catalogue_probabilities=tuple(
                DwellCatalogueProbabilityV1(
                    catalog_number=number,
                    posterior_probability=next(
                        entry.posterior_probability
                        for entry in item.smoothed_identity_posterior
                        if entry.identity == number
                    ),
                )
                for number in forward.catalog_numbers
            ),
            exact_tie=item.exact_smoothed_tie,
        )
        for item in smoothed.smoothed_dwells
    )
    values: dict[str, object] = {
        "source_filter_algorithm_version": forward.algorithm_version,
        "source_filter_result_digest": smoothed.source_result_digest,
        "source_evidence_digest": canonical_digest(
            {
                "dwells": tuple(asdict(item) for item in dwells),
                "response_accessed": True,
            }
        ),
        "response_free_prediction_bank_digest": canonical_digest(
            {
                "prediction_bank": asdict(prediction_bank),
                "response_accessed": prediction_bank.response_accessed,
                "tau_policy": prediction_bank.tau_policy,
            }
        ),
        "filter_config_digest": canonical_digest(asdict(config)),
        "smoothing_result_digest": smoothed.content_digest,
        "dwell_ids": forward.dwell_ids,
        "catalog_numbers": forward.catalog_numbers,
        "source_retained_mode_count": len(forward.final_modes),
        "reported_positive_mode_count": len(modes),
        "zero_probability_mode_count": len(forward.final_modes) - len(modes),
        "modes": tuple(modes),
        "smoothed_identity_posteriors": identity_posteriors,
        "any_beam_pruning": forward.any_pruning,
        "retained_history_family_complete": not forward.any_pruning,
        "status": StandardScientificStatus.PARTIAL,
    }
    return _seal_product(values)


def _seal_product(values: dict[str, object]) -> MultiDwellCataloguePosteriorV1:
    draft_values: dict[str, Any] = {
        **values,
        "content_digest": canonical_digest({"draft": "multi-dwell-catalogue-posterior"}),
    }
    draft = MultiDwellCataloguePosteriorV1.model_construct(**draft_values)
    payload = draft.model_dump(mode="json", exclude={"content_digest"}, warnings=False)
    return MultiDwellCataloguePosteriorV1.model_validate(
        {**payload, "content_digest": canonical_digest(payload)}
    )
