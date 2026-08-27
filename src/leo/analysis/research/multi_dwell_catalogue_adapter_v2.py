"""Exact V2 staging adapter for changing multi-dwell catalogue opportunity.

The current causal multi-dwell filter is intentionally narrower than the
contract-level evidence now available: it requires one identity per dwell, a
fixed candidate inventory covering every dwell, and a single precomputed tau
per integer catalogue identity.  Encoding a varying candidate population,
multiple physical episodes, or a persistent catalogue/tau state by padding
predictions or inventing synthetic catalogue numbers would change the model.

This pure adapter therefore stops at a digest-closed staging contract.  It
revalidates each physical graph and complete response-free bank, preserves the
exact graph/bank pairs, constructs persistent catalogue/tau mode identities,
records episode-local mode opportunity, and enumerates bounded NULL, birth,
death, same-state, and handoff transitions between chronological dwells.  A
future filter can consume this staging product without reopening or reranking
the candidate bank.  Lowering to the persisted V1 filter is explicitly rejected
until an additive downstream contract can represent these semantics.

No likelihood is evaluated here.  Measured response is copied only as part of
the validated physical graph; it never affects visibility, tau state, mode, or
transition construction.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Literal, NoReturn

from pydantic import ValidationError

from leo.contracts.catalogue_association import (
    CataloguePredictionBankV1,
    CataloguePredictionSupportV1,
    PhysicalCfoEpisodeV1,
    PhysicalEpisodeGraphV1,
)
from leo.contracts.digests import Sha256Digest, canonical_digest

type StagedTransitionKind = Literal[
    "null-stay",
    "birth-from-null",
    "death-to-null",
    "same-catalogue-tau",
    "catalogue-handoff",
]

_ALGORITHM_VERSION = "multi-dwell-catalogue-adapter-staging-v2"
_NULL_MODE_ID = canonical_digest(
    {
        "schema": "org.leo.research.multi-dwell-persistent-mode/v2",
        "kind": "NULL",
    }
)
_V1_DOWNSTREAM_INCOMPATIBILITIES = (
    "v1-bank-requires-every-candidate-to-predict-every-dwell",
    "v1-history-has-one-integer-or-null-identity-per-dwell-not-per-episode",
    "v1-fixed-precomputed-tau-cannot-retain-catalogue-tau-history-state",
)
_SHA256_PREFIX = "sha256:"
_SHA256_HEX_LENGTH = 64


class MultiDwellCatalogueAdapterV2Error(ValueError):
    """The graph/bank inventory cannot form the exact V2 staging product."""


class MultiDwellCatalogueAdapterV2WorkLimitError(MultiDwellCatalogueAdapterV2Error):
    """A response-free inventory would exceed a predeclared adapter work cap."""


class MultiDwellCatalogueAdapterV2CompatibilityError(MultiDwellCatalogueAdapterV2Error):
    """The precise V2 staging semantics cannot be lowered to the V1 filter."""


@dataclass(frozen=True, slots=True)
class MultiDwellCatalogueAdapterV2Config:
    """Strict input binding and conservative response-free work limits."""

    expected_input_inventory_digest: Sha256Digest
    maximum_dwell_count: int = 256
    maximum_total_episode_count: int = 2_048
    maximum_total_observation_count: int = 32_768
    maximum_candidates_per_dwell: int = 10_000
    maximum_global_candidate_count: int = 10_000
    maximum_tau_states_per_candidate: int = 401
    maximum_candidate_tau_prediction_rows: int = 20_000_000
    maximum_total_mode_opportunities: int = 2_000_000
    maximum_transition_opportunities: int = 10_000_000
    maximum_absolute_tau_s: float = 5.0

    def __post_init__(self) -> None:
        if not _is_digest(self.expected_input_inventory_digest):
            raise MultiDwellCatalogueAdapterV2Error(
                "expected graph/bank inventory must be digest-bound"
            )
        controls = (
            self.maximum_dwell_count,
            self.maximum_total_episode_count,
            self.maximum_total_observation_count,
            self.maximum_candidates_per_dwell,
            self.maximum_global_candidate_count,
            self.maximum_tau_states_per_candidate,
            self.maximum_candidate_tau_prediction_rows,
            self.maximum_total_mode_opportunities,
            self.maximum_transition_opportunities,
        )
        if any(
            isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in controls
        ):
            raise MultiDwellCatalogueAdapterV2Error(
                "V2 adapter work bounds must be positive integers"
            )
        if (
            not math.isfinite(self.maximum_absolute_tau_s)
            or self.maximum_absolute_tau_s <= 0.0
            or self.maximum_absolute_tau_s > 5.0
        ):
            raise MultiDwellCatalogueAdapterV2Error(
                "maximum absolute tau must lie in the contract range (0, 5] seconds"
            )

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(asdict(self))

    @property
    def response_free_policy_digest(self) -> Sha256Digest:
        payload = asdict(self)
        payload.pop("expected_input_inventory_digest")
        return canonical_digest(payload)


@dataclass(frozen=True, slots=True)
class PersistentTauGridPointV2:
    tau_s: float
    declared_log_prior_weight: float
    normalized_log_prior_weight: float


@dataclass(frozen=True, slots=True)
class PersistentCatalogueTauModeV2:
    mode_id: Sha256Digest
    catalog_number: int
    tau_s: float
    normalized_log_tau_prior_weight: float


@dataclass(frozen=True, slots=True)
class CatalogueTauPersistenceConstraintV2:
    """One catalogue keeps exactly one tau mode throughout a retained history."""

    catalog_number: int
    mode_ids: tuple[Sha256Digest, ...]
    visible_dwell_indices: tuple[int, ...]
    persists_across_null_or_invisible_gaps: Literal[True] = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class StagedCatalogueDwellV2:
    """One exact validated graph/bank pair and derived visibility accounting."""

    dwell_index: int
    dwell_id: Sha256Digest
    support_start_utc_ns: int
    support_end_utc_ns: int
    graph: PhysicalEpisodeGraphV1
    prediction_bank: CataloguePredictionBankV1
    visible_catalog_numbers: tuple[int, ...]
    mode_ids: tuple[Sha256Digest, ...]
    entered_visibility_catalog_numbers: tuple[int, ...]
    departed_visibility_catalog_numbers: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class EpisodeModeOpportunityV2:
    dwell_index: int
    dwell_id: Sha256Digest
    episode_id: Sha256Digest
    support_start_utc_ns: int
    support_end_utc_ns: int
    mode_ids: tuple[Sha256Digest, ...]
    null_mode_explicit: Literal[True] = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class DwellModeOpportunityV2:
    dwell_index: int
    dwell_id: Sha256Digest
    mode_ids: tuple[Sha256Digest, ...]
    entered_visibility_catalog_numbers: tuple[int, ...]
    departed_visibility_catalog_numbers: tuple[int, ...]
    null_mode_explicit: Literal[True] = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class StagedModeTransitionV2:
    from_dwell_index: int
    to_dwell_index: int
    from_mode_id: Sha256Digest
    to_mode_id: Sha256Digest
    kind: StagedTransitionKind
    response_free: Literal[True] = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class MultiDwellCatalogueAdapterV2Staging:
    input_inventory_digest: Sha256Digest
    response_free_inventory_digest: Sha256Digest
    config: MultiDwellCatalogueAdapterV2Config
    config_digest: Sha256Digest
    graph_content_digests: tuple[Sha256Digest, ...]
    prediction_bank_content_digests: tuple[Sha256Digest, ...]
    persistent_tau_grid: tuple[PersistentTauGridPointV2, ...]
    persistent_modes: tuple[PersistentCatalogueTauModeV2, ...]
    tau_persistence_constraints: tuple[CatalogueTauPersistenceConstraintV2, ...]
    dwells: tuple[StagedCatalogueDwellV2, ...]
    episode_mode_opportunities: tuple[EpisodeModeOpportunityV2, ...]
    dwell_mode_opportunities: tuple[DwellModeOpportunityV2, ...]
    transitions: tuple[StagedModeTransitionV2, ...]
    changing_visibility_present: bool
    multiple_episodes_per_dwell_present: bool
    content_digest: Sha256Digest = field(init=False)
    algorithm_version: Literal["multi-dwell-catalogue-adapter-staging-v2"] = field(
        default="multi-dwell-catalogue-adapter-staging-v2", init=False
    )
    target_filter_algorithm_version: Literal["causal-rb-multi-dwell-filter-v1"] = field(
        default="causal-rb-multi-dwell-filter-v1", init=False
    )
    target_smoother_algorithm_version: Literal[
        "retained-history-fixed-interval-identity-smoother-v1"
    ] = field(default="retained-history-fixed-interval-identity-smoother-v1", init=False)
    staging_only: Literal[True] = field(default=True, init=False)
    v1_filter_lowering_supported: Literal[False] = field(default=False, init=False)
    v1_downstream_incompatibilities: tuple[str, str, str] = field(
        default=_V1_DOWNSTREAM_INCOMPATIBILITIES,
        init=False,
    )
    complete_response_free_banks: Literal[True] = field(default=True, init=False)
    measured_response_used_for_mode_construction: Literal[False] = field(default=False, init=False)
    multiple_physical_episodes_preserved: Literal[True] = field(default=True, init=False)
    persistent_tau_required_across_history: Literal[True] = field(default=True, init=False)
    null_mode_explicit: Literal[True] = field(default=True, init=False)
    handoff_modes_explicit: Literal[True] = field(default=True, init=False)
    likelihood_evaluated: Literal[False] = field(default=False, init=False)
    smoothing_performed: Literal[False] = field(default=False, init=False)
    real_evidence_claimed: Literal[False] = field(default=False, init=False)
    identity_claimed: Literal[False] = field(default=False, init=False)

    def __post_init__(self) -> None:
        if self.config_digest != self.config.content_digest:
            raise MultiDwellCatalogueAdapterV2Error(
                "V2 staging config digest differs from the retained config"
            )
        graphs = tuple(item.graph for item in self.dwells)
        banks = tuple(item.prediction_bank for item in self.dwells)
        if (
            self.input_inventory_digest
            != multi_dwell_catalogue_v2_input_inventory_digest(graphs, banks)
            or self.input_inventory_digest != self.config.expected_input_inventory_digest
        ):
            raise MultiDwellCatalogueAdapterV2Error(
                "V2 staging input digest differs from its exact graph/bank pairs"
            )
        if self.graph_content_digests != tuple(item.content_digest for item in graphs) or (
            self.prediction_bank_content_digests != tuple(item.content_digest for item in banks)
        ):
            raise MultiDwellCatalogueAdapterV2Error(
                "V2 staging source digest inventory is inconsistent"
            )
        expected_response_free_digest = canonical_digest(
            _response_free_payload(
                config=self.config,
                dwells=self.dwells,
                tau_grid=self.persistent_tau_grid,
                modes=self.persistent_modes,
                constraints=self.tau_persistence_constraints,
                episode_opportunities=self.episode_mode_opportunities,
                dwell_opportunities=self.dwell_mode_opportunities,
                transitions=self.transitions,
            )
        )
        if self.response_free_inventory_digest != expected_response_free_digest:
            raise MultiDwellCatalogueAdapterV2Error(
                "V2 staging response-free inventory digest is inconsistent"
            )
        object.__setattr__(self, "content_digest", canonical_digest(_staging_payload(self)))


def multi_dwell_catalogue_v2_input_inventory_digest(
    graphs: tuple[PhysicalEpisodeGraphV1, ...],
    prediction_banks: tuple[CataloguePredictionBankV1, ...],
) -> Sha256Digest:
    """Bind the ordered graph/bank pair inventory without inspecting response values."""

    try:
        pairs = tuple(
            {
                "graph_content_digest": graph.content_digest,
                "prediction_bank_content_digest": bank.content_digest,
            }
            for graph, bank in zip(graphs, prediction_banks, strict=True)
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise MultiDwellCatalogueAdapterV2Error(
            "graph/bank inventory cannot be digest-bound"
        ) from error
    return canonical_digest(
        {
            "schema": "org.leo.research.multi-dwell-catalogue-adapter-input/v2",
            "pairs": pairs,
        }
    )


def stage_multi_dwell_catalogue_inputs_v2(
    *,
    graphs: tuple[PhysicalEpisodeGraphV1, ...],
    prediction_banks: tuple[CataloguePredictionBankV1, ...],
    config: MultiDwellCatalogueAdapterV2Config,
) -> MultiDwellCatalogueAdapterV2Staging:
    """Build exact response-separated V2 staging without scoring candidates."""

    config = _revalidate_config(config)
    _preflight_work(graphs, prediction_banks, config=config)
    graphs, prediction_banks = _revalidate_inputs(graphs, prediction_banks)
    input_digest = multi_dwell_catalogue_v2_input_inventory_digest(graphs, prediction_banks)
    if input_digest != config.expected_input_inventory_digest:
        raise MultiDwellCatalogueAdapterV2Error(
            "graph/bank inventory digest differs from the predeclared input"
        )
    _validate_graph_bank_pairs(graphs, prediction_banks, config=config)

    tau_grid = _persistent_tau_grid(prediction_banks)
    normalized_tau_weights = _normalized_log_weights(
        tuple(item.declared_log_prior_weight for item in tau_grid)
    )
    tau_grid = tuple(
        PersistentTauGridPointV2(
            tau_s=item.tau_s,
            declared_log_prior_weight=item.declared_log_prior_weight,
            normalized_log_prior_weight=normalized,
        )
        for item, normalized in zip(tau_grid, normalized_tau_weights, strict=True)
    )
    catalogue_numbers = tuple(
        sorted(
            {candidate.catalog_number for bank in prediction_banks for candidate in bank.candidates}
        )
    )
    mode_by_key = {
        (catalog_number, tau.tau_s): PersistentCatalogueTauModeV2(
            mode_id=_catalogue_tau_mode_id(catalog_number, tau.tau_s),
            catalog_number=catalog_number,
            tau_s=tau.tau_s,
            normalized_log_tau_prior_weight=tau.normalized_log_prior_weight,
        )
        for catalog_number in catalogue_numbers
        for tau in tau_grid
    }
    persistent_modes = tuple(
        mode_by_key[key] for key in sorted(mode_by_key, key=lambda item: (item[0], item[1]))
    )

    staged_dwells: list[StagedCatalogueDwellV2] = []
    episode_opportunities: list[EpisodeModeOpportunityV2] = []
    dwell_opportunities: list[DwellModeOpportunityV2] = []
    previous_visible: set[int] = set()
    for dwell_index, (graph, bank) in enumerate(zip(graphs, prediction_banks, strict=True)):
        dwell_id = graph.episodes[0].dwell_id
        visible = tuple(item.catalog_number for item in bank.candidates)
        visible_set = set(visible)
        entered = tuple(sorted(visible_set - previous_visible))
        departed = tuple(sorted(previous_visible - visible_set))
        dwell_mode_ids = (
            _NULL_MODE_ID,
            *(
                mode_by_key[catalog_number, tau.tau_s].mode_id
                for catalog_number in visible
                for tau in tau_grid
            ),
        )
        support_start = min(item.support_start_utc_ns for item in graph.observations)
        support_end = max(item.support_end_utc_ns for item in graph.observations)
        staged_dwells.append(
            StagedCatalogueDwellV2(
                dwell_index=dwell_index,
                dwell_id=dwell_id,
                support_start_utc_ns=support_start,
                support_end_utc_ns=support_end,
                graph=graph,
                prediction_bank=bank,
                visible_catalog_numbers=visible,
                mode_ids=dwell_mode_ids,
                entered_visibility_catalog_numbers=entered,
                departed_visibility_catalog_numbers=departed,
            )
        )
        dwell_opportunities.append(
            DwellModeOpportunityV2(
                dwell_index=dwell_index,
                dwell_id=dwell_id,
                mode_ids=dwell_mode_ids,
                entered_visibility_catalog_numbers=entered,
                departed_visibility_catalog_numbers=departed,
            )
        )
        candidate_by_number = {item.catalog_number: item for item in bank.candidates}
        rows_by_id = {item.observation_id: item for item in graph.observations}
        for episode in _chronological_episodes(graph):
            eligible_numbers = tuple(
                number
                for number in visible
                if episode.episode_id in candidate_by_number[number].eligible_episode_ids
            )
            episode_mode_ids = (
                _NULL_MODE_ID,
                *(
                    mode_by_key[number, tau.tau_s].mode_id
                    for number in eligible_numbers
                    for tau in tau_grid
                ),
            )
            rows = tuple(rows_by_id[item] for item in episode.observation_ids)
            episode_opportunities.append(
                EpisodeModeOpportunityV2(
                    dwell_index=dwell_index,
                    dwell_id=dwell_id,
                    episode_id=episode.episode_id,
                    support_start_utc_ns=min(item.support_start_utc_ns for item in rows),
                    support_end_utc_ns=max(item.support_end_utc_ns for item in rows),
                    mode_ids=episode_mode_ids,
                )
            )
        previous_visible = visible_set

    transitions = _transition_opportunities(tuple(dwell_opportunities), persistent_modes)
    if len(transitions) > config.maximum_transition_opportunities:
        raise MultiDwellCatalogueAdapterV2WorkLimitError(
            "actual V2 transition inventory exceeds its work cap"
        )
    if math.fsum(len(item.mode_ids) for item in dwell_opportunities) > (
        config.maximum_total_mode_opportunities
    ):
        raise MultiDwellCatalogueAdapterV2WorkLimitError(
            "actual V2 mode-opportunity inventory exceeds its work cap"
        )

    constraints = tuple(
        CatalogueTauPersistenceConstraintV2(
            catalog_number=number,
            mode_ids=tuple(mode_by_key[number, tau.tau_s].mode_id for tau in tau_grid),
            visible_dwell_indices=tuple(
                item.dwell_index for item in staged_dwells if number in item.visible_catalog_numbers
            ),
        )
        for number in catalogue_numbers
    )
    response_free_digest = canonical_digest(
        _response_free_payload(
            config=config,
            dwells=tuple(staged_dwells),
            tau_grid=tau_grid,
            modes=persistent_modes,
            constraints=constraints,
            episode_opportunities=tuple(episode_opportunities),
            dwell_opportunities=tuple(dwell_opportunities),
            transitions=transitions,
        )
    )
    visibility_inventories = tuple(item.visible_catalog_numbers for item in staged_dwells)
    return MultiDwellCatalogueAdapterV2Staging(
        input_inventory_digest=input_digest,
        response_free_inventory_digest=response_free_digest,
        config=config,
        config_digest=config.content_digest,
        graph_content_digests=tuple(item.content_digest for item in graphs),
        prediction_bank_content_digests=tuple(item.content_digest for item in prediction_banks),
        persistent_tau_grid=tau_grid,
        persistent_modes=persistent_modes,
        tau_persistence_constraints=constraints,
        dwells=tuple(staged_dwells),
        episode_mode_opportunities=tuple(episode_opportunities),
        dwell_mode_opportunities=tuple(dwell_opportunities),
        transitions=transitions,
        changing_visibility_present=(
            len(set(visibility_inventories)) > 1 if visibility_inventories else False
        ),
        multiple_episodes_per_dwell_present=any(len(item.episodes) > 1 for item in graphs),
    )


def multi_dwell_catalogue_adapter_v2_payload(
    staging: MultiDwellCatalogueAdapterV2Staging,
) -> dict[str, object]:
    """Return the JSON-compatible staging payload after digest verification."""

    payload = _staging_payload(staging)
    if staging.content_digest != canonical_digest(payload):
        raise MultiDwellCatalogueAdapterV2Error("V2 staging content digest does not close")
    return {**payload, "content_digest": staging.content_digest}


def lower_staged_catalogue_v2_to_v1_filter_inputs(
    staging: MultiDwellCatalogueAdapterV2Staging,
) -> NoReturn:
    """Fail closed rather than corrupt V2 state while V1 contracts remain narrow."""

    multi_dwell_catalogue_adapter_v2_payload(staging)
    joined = "; ".join(_V1_DOWNSTREAM_INCOMPATIBILITIES)
    raise MultiDwellCatalogueAdapterV2CompatibilityError(
        f"V2 staging cannot be lowered truthfully to the V1 filter: {joined}"
    )


def _preflight_work(
    graphs: tuple[PhysicalEpisodeGraphV1, ...],
    prediction_banks: tuple[CataloguePredictionBankV1, ...],
    *,
    config: MultiDwellCatalogueAdapterV2Config,
) -> None:
    """Reject response-free size metadata before measured CFO is validated."""

    try:
        graph_count = len(graphs)
        bank_count = len(prediction_banks)
    except TypeError as error:
        raise MultiDwellCatalogueAdapterV2Error("graph/bank inventories must be sized") from error
    if graph_count == 0 or graph_count != bank_count:
        raise MultiDwellCatalogueAdapterV2Error(
            "graph and prediction-bank inventories need equal nonzero length"
        )
    if graph_count > config.maximum_dwell_count:
        raise MultiDwellCatalogueAdapterV2WorkLimitError("V2 dwell inventory exceeds its cap")
    episode_count = 0
    observation_count = 0
    prediction_rows = 0
    global_catalogues: set[int] = set()
    mode_counts: list[int] = []
    try:
        for graph, bank in zip(graphs, prediction_banks, strict=True):
            episode_count += len(graph.episodes)
            observation_count += len(graph.observations)
            if len(bank.candidates) > config.maximum_candidates_per_dwell:
                raise MultiDwellCatalogueAdapterV2WorkLimitError(
                    "V2 per-dwell candidate inventory exceeds its cap"
                )
            dwell_mode_count = 1
            for candidate in bank.candidates:
                global_catalogues.add(candidate.catalog_number)
                tau_count = len(candidate.tau_states)
                if tau_count > config.maximum_tau_states_per_candidate:
                    raise MultiDwellCatalogueAdapterV2WorkLimitError(
                        "V2 candidate tau inventory exceeds its cap"
                    )
                dwell_mode_count += tau_count
                prediction_rows += sum(len(item.predictions) for item in candidate.tau_states)
            mode_counts.append(dwell_mode_count)
    except MultiDwellCatalogueAdapterV2WorkLimitError:
        raise
    except (AttributeError, TypeError) as error:
        raise MultiDwellCatalogueAdapterV2Error(
            "graph/bank response-free work inventory is malformed"
        ) from error
    if episode_count > config.maximum_total_episode_count:
        raise MultiDwellCatalogueAdapterV2WorkLimitError("V2 episode inventory exceeds its cap")
    if observation_count > config.maximum_total_observation_count:
        raise MultiDwellCatalogueAdapterV2WorkLimitError("V2 observation inventory exceeds its cap")
    if len(global_catalogues) > config.maximum_global_candidate_count:
        raise MultiDwellCatalogueAdapterV2WorkLimitError(
            "V2 global candidate inventory exceeds its cap"
        )
    if prediction_rows > config.maximum_candidate_tau_prediction_rows:
        raise MultiDwellCatalogueAdapterV2WorkLimitError(
            "V2 candidate-tau prediction rows exceed their cap"
        )
    if sum(mode_counts) > config.maximum_total_mode_opportunities:
        raise MultiDwellCatalogueAdapterV2WorkLimitError(
            "V2 conservative mode-opportunity bound exceeds its cap"
        )
    transition_upper_bound = sum(
        left * right for left, right in zip(mode_counts, mode_counts[1:], strict=False)
    )
    if transition_upper_bound > config.maximum_transition_opportunities:
        raise MultiDwellCatalogueAdapterV2WorkLimitError(
            "V2 conservative transition bound exceeds its cap"
        )


def _revalidate_config(
    config: MultiDwellCatalogueAdapterV2Config,
) -> MultiDwellCatalogueAdapterV2Config:
    try:
        return MultiDwellCatalogueAdapterV2Config(**asdict(config))
    except (AttributeError, TypeError, ValueError) as error:
        raise MultiDwellCatalogueAdapterV2Error("V2 adapter config is invalid") from error


def _revalidate_inputs(
    graphs: tuple[PhysicalEpisodeGraphV1, ...],
    banks: tuple[CataloguePredictionBankV1, ...],
) -> tuple[tuple[PhysicalEpisodeGraphV1, ...], tuple[CataloguePredictionBankV1, ...]]:
    try:
        validated_graphs = tuple(
            PhysicalEpisodeGraphV1.model_validate(item.model_dump(mode="json")) for item in graphs
        )
        validated_banks = tuple(
            CataloguePredictionBankV1.model_validate(item.model_dump(mode="json")) for item in banks
        )
    except (AttributeError, TypeError, ValueError, ValidationError) as error:
        raise MultiDwellCatalogueAdapterV2Error(
            "graph or response-free bank fails validated digest closure"
        ) from error
    return validated_graphs, validated_banks


def _validate_graph_bank_pairs(
    graphs: tuple[PhysicalEpisodeGraphV1, ...],
    banks: tuple[CataloguePredictionBankV1, ...],
    *,
    config: MultiDwellCatalogueAdapterV2Config,
) -> None:
    dwell_ids: list[str] = []
    dwell_bounds: list[tuple[int, int]] = []
    first_bank = banks[0]
    tau_reference: tuple[tuple[float, float], ...] | None = None
    for graph, bank in zip(graphs, banks, strict=True):
        expected_support = CataloguePredictionSupportV1.from_graph(graph)
        if bank.support != expected_support:
            raise MultiDwellCatalogueAdapterV2Error(
                "prediction bank does not bind the exact response-free physical support"
            )
        if bank.response_accessed or not bank.support.response_fields_excluded:
            raise MultiDwellCatalogueAdapterV2Error(
                "catalogue prediction bank must remain response-free"
            )
        if bank.truncated_candidate_count != 0:
            raise MultiDwellCatalogueAdapterV2Error(
                "every per-dwell candidate population must be complete, not truncated"
            )
        if (
            bank.observer_site != first_bank.observer_site
            or bank.nominal_rf_hz != first_bank.nominal_rf_hz
            or bank.propagation_model != first_bank.propagation_model
            or bank.selection_protocol_digest != first_bank.selection_protocol_digest
            or bank.selection_policy_digest != first_bank.selection_policy_digest
            or bank.tau_search_policy != first_bank.tau_search_policy
        ):
            raise MultiDwellCatalogueAdapterV2Error(
                "per-dwell banks must share site, RF, model, selection, and tau authority"
            )
        graph_dwell_ids = {item.dwell_id for item in graph.episodes}
        if len(graph_dwell_ids) != 1:
            raise MultiDwellCatalogueAdapterV2Error(
                "one per-dwell graph cannot mix physical dwell identities"
            )
        dwell_ids.append(next(iter(graph_dwell_ids)))
        dwell_bounds.append(
            (
                min(item.support_start_utc_ns for item in graph.observations),
                max(item.support_end_utc_ns for item in graph.observations),
            )
        )
        for candidate in bank.candidates:
            tau_inventory = tuple(
                (item.tau_s, item.log_prior_weight) for item in candidate.tau_states
            )
            if tau_reference is None:
                tau_reference = tau_inventory
            elif tau_inventory != tau_reference:
                raise MultiDwellCatalogueAdapterV2Error(
                    "every catalogue appearance must use one exact persistent tau grid and prior"
                )
            if any(abs(tau_s) > config.maximum_absolute_tau_s for tau_s, _ in tau_inventory):
                raise MultiDwellCatalogueAdapterV2Error(
                    "catalogue tau grid exceeds the configured persistent support"
                )
    if len(set(dwell_ids)) != len(dwell_ids):
        raise MultiDwellCatalogueAdapterV2Error("V2 graph inventory repeats a dwell identity")
    if any(right[0] < left[1] for left, right in zip(dwell_bounds, dwell_bounds[1:], strict=False)):
        raise MultiDwellCatalogueAdapterV2Error(
            "V2 dwell graphs must be chronological and nonoverlapping"
        )
    if tau_reference is None and any(bank.candidates for bank in banks):
        raise AssertionError("candidate inventory exists without a tau grid")


def _persistent_tau_grid(
    banks: tuple[CataloguePredictionBankV1, ...],
) -> tuple[PersistentTauGridPointV2, ...]:
    for bank in banks:
        for candidate in bank.candidates:
            return tuple(
                PersistentTauGridPointV2(
                    tau_s=item.tau_s,
                    declared_log_prior_weight=item.log_prior_weight,
                    normalized_log_prior_weight=0.0,
                )
                for item in candidate.tau_states
            )
    return ()


def _normalized_log_weights(values: tuple[float, ...]) -> tuple[float, ...]:
    if not values:
        return ()
    if any(not math.isfinite(item) for item in values):
        raise MultiDwellCatalogueAdapterV2Error("tau prior weights must be finite")
    maximum = max(values)
    mass = math.fsum(math.exp(item - maximum) for item in values)
    if not math.isfinite(mass) or mass <= 0.0:
        raise MultiDwellCatalogueAdapterV2Error("tau prior mass is not representable")
    normalizer = maximum + math.log(mass)
    return tuple(item - normalizer for item in values)


def _transition_opportunities(
    dwells: tuple[DwellModeOpportunityV2, ...],
    modes: tuple[PersistentCatalogueTauModeV2, ...],
) -> tuple[StagedModeTransitionV2, ...]:
    mode_by_id = {item.mode_id: item for item in modes}
    transitions: list[StagedModeTransitionV2] = []
    for left, right in zip(dwells, dwells[1:], strict=False):
        for from_mode_id in left.mode_ids:
            for to_mode_id in right.mode_ids:
                kind = _transition_kind(
                    from_mode_id,
                    to_mode_id,
                    mode_by_id=mode_by_id,
                )
                if kind is None:
                    continue
                transitions.append(
                    StagedModeTransitionV2(
                        from_dwell_index=left.dwell_index,
                        to_dwell_index=right.dwell_index,
                        from_mode_id=from_mode_id,
                        to_mode_id=to_mode_id,
                        kind=kind,
                    )
                )
    return tuple(transitions)


def _transition_kind(
    from_mode_id: str,
    to_mode_id: str,
    *,
    mode_by_id: dict[str, PersistentCatalogueTauModeV2],
) -> StagedTransitionKind | None:
    if from_mode_id == _NULL_MODE_ID:
        return "null-stay" if to_mode_id == _NULL_MODE_ID else "birth-from-null"
    if to_mode_id == _NULL_MODE_ID:
        return "death-to-null"
    previous = mode_by_id[from_mode_id]
    following = mode_by_id[to_mode_id]
    if previous.catalog_number != following.catalog_number:
        return "catalogue-handoff"
    if previous.tau_s == following.tau_s:
        return "same-catalogue-tau"
    # Tau is one persistent catalogue-history state.  A per-dwell tau switch is
    # deliberately absent rather than charged as a satellite handoff.
    return None


def _chronological_episodes(
    graph: PhysicalEpisodeGraphV1,
) -> tuple[PhysicalCfoEpisodeV1, ...]:
    rows = {item.observation_id: item for item in graph.observations}
    return tuple(
        sorted(
            graph.episodes,
            key=lambda episode: (
                min(rows[item].support_start_utc_ns for item in episode.observation_ids),
                max(rows[item].support_end_utc_ns for item in episode.observation_ids),
                episode.lane_id,
                episode.order_index,
                episode.episode_id,
            ),
        )
    )


def _catalogue_tau_mode_id(catalog_number: int, tau_s: float) -> Sha256Digest:
    return canonical_digest(
        {
            "schema": "org.leo.research.multi-dwell-persistent-mode/v2",
            "kind": "catalogue-tau",
            "catalog_number": catalog_number,
            "tau_s": tau_s,
        }
    )


def _response_free_payload(
    *,
    config: MultiDwellCatalogueAdapterV2Config,
    dwells: tuple[StagedCatalogueDwellV2, ...],
    tau_grid: tuple[PersistentTauGridPointV2, ...],
    modes: tuple[PersistentCatalogueTauModeV2, ...],
    constraints: tuple[CatalogueTauPersistenceConstraintV2, ...],
    episode_opportunities: tuple[EpisodeModeOpportunityV2, ...],
    dwell_opportunities: tuple[DwellModeOpportunityV2, ...],
    transitions: tuple[StagedModeTransitionV2, ...],
) -> dict[str, object]:
    return {
        "schema": "org.leo.research.multi-dwell-catalogue-adapter-response-free/v2",
        "algorithm_version": _ALGORITHM_VERSION,
        "response_free_policy_digest": config.response_free_policy_digest,
        "dwells": tuple(
            {
                "dwell_index": item.dwell_index,
                "dwell_id": item.dwell_id,
                "support_start_utc_ns": item.support_start_utc_ns,
                "support_end_utc_ns": item.support_end_utc_ns,
                "physical_episodes": tuple(
                    episode.model_dump(mode="json") for episode in item.graph.episodes
                ),
                "prediction_bank": item.prediction_bank.model_dump(mode="json"),
                "visible_catalog_numbers": item.visible_catalog_numbers,
                "mode_ids": item.mode_ids,
                "entered_visibility_catalog_numbers": (item.entered_visibility_catalog_numbers),
                "departed_visibility_catalog_numbers": (item.departed_visibility_catalog_numbers),
            }
            for item in dwells
        ),
        "persistent_tau_grid": tuple(asdict(item) for item in tau_grid),
        "persistent_modes": tuple(asdict(item) for item in modes),
        "tau_persistence_constraints": tuple(asdict(item) for item in constraints),
        "episode_mode_opportunities": tuple(asdict(item) for item in episode_opportunities),
        "dwell_mode_opportunities": tuple(asdict(item) for item in dwell_opportunities),
        "transitions": tuple(asdict(item) for item in transitions),
        "measured_response_used_for_mode_construction": False,
    }


def _staging_payload(staging: MultiDwellCatalogueAdapterV2Staging) -> dict[str, object]:
    return {
        "input_inventory_digest": staging.input_inventory_digest,
        "response_free_inventory_digest": staging.response_free_inventory_digest,
        "config": asdict(staging.config),
        "config_digest": staging.config_digest,
        "graph_content_digests": staging.graph_content_digests,
        "prediction_bank_content_digests": staging.prediction_bank_content_digests,
        "persistent_tau_grid": tuple(asdict(item) for item in staging.persistent_tau_grid),
        "persistent_modes": tuple(asdict(item) for item in staging.persistent_modes),
        "tau_persistence_constraints": tuple(
            asdict(item) for item in staging.tau_persistence_constraints
        ),
        "dwells": tuple(
            {
                "dwell_index": item.dwell_index,
                "dwell_id": item.dwell_id,
                "support_start_utc_ns": item.support_start_utc_ns,
                "support_end_utc_ns": item.support_end_utc_ns,
                "graph": item.graph.model_dump(mode="json"),
                "prediction_bank": item.prediction_bank.model_dump(mode="json"),
                "visible_catalog_numbers": item.visible_catalog_numbers,
                "mode_ids": item.mode_ids,
                "entered_visibility_catalog_numbers": (item.entered_visibility_catalog_numbers),
                "departed_visibility_catalog_numbers": (item.departed_visibility_catalog_numbers),
            }
            for item in staging.dwells
        ),
        "episode_mode_opportunities": tuple(
            asdict(item) for item in staging.episode_mode_opportunities
        ),
        "dwell_mode_opportunities": tuple(
            asdict(item) for item in staging.dwell_mode_opportunities
        ),
        "transitions": tuple(asdict(item) for item in staging.transitions),
        "changing_visibility_present": staging.changing_visibility_present,
        "multiple_episodes_per_dwell_present": (staging.multiple_episodes_per_dwell_present),
        "algorithm_version": staging.algorithm_version,
        "target_filter_algorithm_version": staging.target_filter_algorithm_version,
        "target_smoother_algorithm_version": staging.target_smoother_algorithm_version,
        "staging_only": staging.staging_only,
        "v1_filter_lowering_supported": staging.v1_filter_lowering_supported,
        "v1_downstream_incompatibilities": staging.v1_downstream_incompatibilities,
        "complete_response_free_banks": staging.complete_response_free_banks,
        "measured_response_used_for_mode_construction": (
            staging.measured_response_used_for_mode_construction
        ),
        "multiple_physical_episodes_preserved": (staging.multiple_physical_episodes_preserved),
        "persistent_tau_required_across_history": (staging.persistent_tau_required_across_history),
        "null_mode_explicit": staging.null_mode_explicit,
        "handoff_modes_explicit": staging.handoff_modes_explicit,
        "likelihood_evaluated": staging.likelihood_evaluated,
        "smoothing_performed": staging.smoothing_performed,
        "real_evidence_claimed": staging.real_evidence_claimed,
        "identity_claimed": staging.identity_claimed,
    }


def _is_digest(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith(_SHA256_PREFIX):
        return False
    hexadecimal = value[len(_SHA256_PREFIX) :]
    return len(hexadecimal) == _SHA256_HEX_LENGTH and all(
        item in "0123456789abcdef" for item in hexadecimal
    )


__all__ = [
    "CatalogueTauPersistenceConstraintV2",
    "DwellModeOpportunityV2",
    "EpisodeModeOpportunityV2",
    "MultiDwellCatalogueAdapterV2CompatibilityError",
    "MultiDwellCatalogueAdapterV2Config",
    "MultiDwellCatalogueAdapterV2Error",
    "MultiDwellCatalogueAdapterV2Staging",
    "MultiDwellCatalogueAdapterV2WorkLimitError",
    "PersistentCatalogueTauModeV2",
    "PersistentTauGridPointV2",
    "StagedCatalogueDwellV2",
    "StagedModeTransitionV2",
    "lower_staged_catalogue_v2_to_v1_filter_inputs",
    "multi_dwell_catalogue_adapter_v2_payload",
    "multi_dwell_catalogue_v2_input_inventory_digest",
    "stage_multi_dwell_catalogue_inputs_v2",
]
