"""Fail-closed adapter from contract-level dwell evidence to the bounded filter.

This first bridge accepts one TLE-blind physical episode and one authenticated,
response-free catalogue bank per chronological dwell.  It deliberately requires
the same complete candidate universe and an exact fixed ``tau=0`` state in
every dwell.  Missing visibility, simultaneous emitters, tau profiling, and
candidate births therefore remain explicit unsupported cases rather than being
encoded as synthetic predictions.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Literal

from leo.analysis.multi_dwell_catalogue_smoothing import (
    SyntheticCandidateDwellPrediction,
    SyntheticCandidateTrajectory,
    SyntheticCfoDwell,
    SyntheticMultiDwellPredictionBank,
)
from leo.contracts.catalogue_association import (
    CataloguePredictionBankV1,
    CataloguePredictionSupportV1,
    PhysicalEpisodeGraphV1,
    SupportIntegratedCfoObservationV1,
)
from leo.contracts.digests import Sha256Digest, canonical_digest

_ALGORITHM_VERSION = "contract-graph-to-causal-multi-dwell-v1"


class MultiDwellCatalogueAdapterError(ValueError):
    """The contract inputs cannot be represented by the bounded filter."""


@dataclass(frozen=True, slots=True)
class MultiDwellCatalogueAdapterConfig:
    maximum_dwell_count: int = 256
    maximum_candidate_count: int = 2_000
    maximum_rows_per_dwell: int = 4_096
    maximum_candidate_row_evaluations: int = 2_000_000

    def __post_init__(self) -> None:
        values = (
            self.maximum_dwell_count,
            self.maximum_candidate_count,
            self.maximum_rows_per_dwell,
            self.maximum_candidate_row_evaluations,
        )
        if any(isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in values):
            raise MultiDwellCatalogueAdapterError(
                "multi-dwell adapter work bounds must be positive integers"
            )


@dataclass(frozen=True, slots=True)
class MultiDwellCatalogueAdapterResult:
    graph_content_digests: tuple[Sha256Digest, ...]
    prediction_bank_content_digests: tuple[Sha256Digest, ...]
    dwell_ids: tuple[str, ...]
    catalog_numbers: tuple[int, ...]
    dwells: tuple[SyntheticCfoDwell, ...]
    prediction_bank: SyntheticMultiDwellPredictionBank
    algorithm_version: Literal["contract-graph-to-causal-multi-dwell-v1"] = field(
        default="contract-graph-to-causal-multi-dwell-v1", init=False
    )
    candidate_population_policy: Literal["exact-complete-common-universe-across-dwells-v1"] = field(
        default="exact-complete-common-universe-across-dwells-v1", init=False
    )
    tau_policy: Literal["fixed-tau-zero-v1"] = field(default="fixed-tau-zero-v1", init=False)
    one_physical_episode_per_dwell: Literal[True] = field(default=True, init=False)
    simultaneous_emitters_supported: Literal[False] = field(default=False, init=False)
    response_free_prediction_bank: Literal[True] = field(default=True, init=False)
    content_digest: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        payload = {
            "graph_content_digests": self.graph_content_digests,
            "prediction_bank_content_digests": self.prediction_bank_content_digests,
            "dwell_ids": self.dwell_ids,
            "catalog_numbers": self.catalog_numbers,
            "dwells": tuple(asdict(item) for item in self.dwells),
            "prediction_bank": asdict(self.prediction_bank),
            "algorithm_version": self.algorithm_version,
            "candidate_population_policy": self.candidate_population_policy,
            "tau_policy": self.tau_policy,
            "one_physical_episode_per_dwell": self.one_physical_episode_per_dwell,
            "simultaneous_emitters_supported": self.simultaneous_emitters_supported,
            "response_free_prediction_bank": self.response_free_prediction_bank,
        }
        object.__setattr__(self, "content_digest", canonical_digest(payload))


def adapt_catalogue_dwells_to_filter_inputs(
    *,
    graphs: tuple[PhysicalEpisodeGraphV1, ...],
    prediction_banks: tuple[CataloguePredictionBankV1, ...],
    config: MultiDwellCatalogueAdapterConfig | None = None,
) -> MultiDwellCatalogueAdapterResult:
    """Join exact measured graphs to response-free predictions without ranking."""

    config = (
        MultiDwellCatalogueAdapterConfig()
        if config is None
        else MultiDwellCatalogueAdapterConfig(**asdict(config))
    )
    graphs = tuple(
        PhysicalEpisodeGraphV1.model_validate(item.model_dump(mode="json")) for item in graphs
    )
    prediction_banks = tuple(
        CataloguePredictionBankV1.model_validate(item.model_dump(mode="json"))
        for item in prediction_banks
    )
    if not graphs or len(graphs) != len(prediction_banks):
        raise MultiDwellCatalogueAdapterError(
            "multi-dwell graphs and prediction banks need equal nonzero length"
        )
    if len(graphs) > config.maximum_dwell_count:
        raise MultiDwellCatalogueAdapterError("multi-dwell adapter dwell-work cap exceeded")
    if any(len(item.episodes) != 1 for item in graphs):
        raise MultiDwellCatalogueAdapterError(
            "V1 multi-dwell adapter requires exactly one physical episode per dwell"
        )
    if any(item.truncated_candidate_count != 0 for item in prediction_banks):
        raise MultiDwellCatalogueAdapterError(
            "multi-dwell adapter rejects a truncated candidate universe"
        )
    candidate_inventories = tuple(
        tuple(item.catalog_number for item in bank.candidates) for bank in prediction_banks
    )
    if any(item != candidate_inventories[0] for item in candidate_inventories[1:]):
        raise MultiDwellCatalogueAdapterError(
            "every dwell must use the exact same complete candidate universe"
        )
    catalog_numbers = candidate_inventories[0]
    if not catalog_numbers or len(catalog_numbers) > config.maximum_candidate_count:
        raise MultiDwellCatalogueAdapterError("multi-dwell candidate-work cap exceeded")
    row_counts = tuple(len(item.observations) for item in graphs)
    if any(item > config.maximum_rows_per_dwell for item in row_counts):
        raise MultiDwellCatalogueAdapterError("multi-dwell row-work cap exceeded")
    total_work = len(catalog_numbers) * math.fsum(row_counts)
    if not math.isfinite(total_work) or total_work > config.maximum_candidate_row_evaluations:
        raise MultiDwellCatalogueAdapterError("multi-dwell candidate-row work cap exceeded")

    _validate_shared_prediction_authority(prediction_banks)
    dwell_rows = tuple(
        _validate_and_order_dwell(graph, bank)
        for graph, bank in zip(graphs, prediction_banks, strict=True)
    )
    dwell_bounds = tuple(
        (rows[0].support_start_utc_ns, rows[-1].support_end_utc_ns) for rows in dwell_rows
    )
    if any(right[0] < left[1] for left, right in zip(dwell_bounds, dwell_bounds[1:], strict=False)):
        raise MultiDwellCatalogueAdapterError(
            "multi-dwell inputs must be chronological and nonoverlapping"
        )
    dwell_ids = tuple(graph.episodes[0].dwell_id for graph in graphs)
    if len(set(dwell_ids)) != len(dwell_ids):
        raise MultiDwellCatalogueAdapterError("multi-dwell input repeats a dwell identity")

    dwells = tuple(
        _adapt_dwell(graph, rows) for graph, rows in zip(graphs, dwell_rows, strict=True)
    )
    trajectories = tuple(
        SyntheticCandidateTrajectory(
            catalog_number=catalog_number,
            dwell_predictions=tuple(
                _adapt_candidate_dwell(
                    graph=graph,
                    bank=bank,
                    rows=rows,
                    catalog_number=catalog_number,
                )
                for graph, bank, rows in zip(
                    graphs,
                    prediction_banks,
                    dwell_rows,
                    strict=True,
                )
            ),
        )
        for catalog_number in catalog_numbers
    )
    prediction_bank = SyntheticMultiDwellPredictionBank(
        dwell_ids=dwell_ids,
        candidates=trajectories,
        source_candidate_count=len(trajectories),
    )
    return MultiDwellCatalogueAdapterResult(
        graph_content_digests=tuple(item.content_digest for item in graphs),
        prediction_bank_content_digests=tuple(item.content_digest for item in prediction_banks),
        dwell_ids=dwell_ids,
        catalog_numbers=catalog_numbers,
        dwells=dwells,
        prediction_bank=prediction_bank,
    )


def _validate_shared_prediction_authority(
    banks: tuple[CataloguePredictionBankV1, ...],
) -> None:
    first = banks[0]
    for bank in banks:
        if (
            bank.observer_site != first.observer_site
            or bank.nominal_rf_hz != first.nominal_rf_hz
            or bank.propagation_model != first.propagation_model
            or bank.selection_protocol_digest != first.selection_protocol_digest
            or bank.selection_policy_digest != first.selection_policy_digest
        ):
            raise MultiDwellCatalogueAdapterError(
                "multi-dwell prediction banks use inconsistent site/RF/model authority"
            )
        if bank.tau_search_policy != "fixed-tau-zero-v1":
            raise MultiDwellCatalogueAdapterError(
                "V1 multi-dwell adapter permits only a fixed tau=0 bank"
            )
        if any(
            len(item.tau_states) != 1 or item.tau_states[0].tau_s != 0.0 for item in bank.candidates
        ):
            raise MultiDwellCatalogueAdapterError(
                "V1 multi-dwell candidate must contain exactly one tau=0 state"
            )


def _validate_and_order_dwell(
    graph: PhysicalEpisodeGraphV1,
    bank: CataloguePredictionBankV1,
) -> tuple[SupportIntegratedCfoObservationV1, ...]:
    expected_support = CataloguePredictionSupportV1.from_graph(graph)
    if bank.support != expected_support:
        raise MultiDwellCatalogueAdapterError(
            "prediction bank does not bind the exact response-free dwell support"
        )
    episode = graph.episodes[0]
    row_by_id = {item.observation_id: item for item in graph.observations}
    rows = tuple(row_by_id[item] for item in episode.observation_ids)
    if len({item.hardware_epoch_id for item in rows}) != 1:
        raise MultiDwellCatalogueAdapterError("one dwell cannot span hardware epochs")
    return rows


def _adapt_dwell(
    graph: PhysicalEpisodeGraphV1,
    rows: tuple[SupportIntegratedCfoObservationV1, ...],
) -> SyntheticCfoDwell:
    mean_center_ns = math.fsum(item.support_center_utc_ns for item in rows) / len(rows)
    if not math.isfinite(mean_center_ns):
        raise MultiDwellCatalogueAdapterError("dwell reference UTC is not representable")
    center_utc_ns = round(mean_center_ns)
    raw_offsets = tuple((item.support_center_utc_ns - center_utc_ns) / 1e9 for item in rows)
    offset_mean = math.fsum(raw_offsets) / len(raw_offsets)
    support_offsets = tuple(item - offset_mean for item in raw_offsets)
    return SyntheticCfoDwell(
        dwell_id=graph.episodes[0].dwell_id,
        center_utc_ns=center_utc_ns,
        hardware_epoch_id=rows[0].hardware_epoch_id,
        support_offsets_s=support_offsets,
        measured_cfo_hz=tuple(item.measured_cfo_hz for item in rows),
        measurement_standard_uncertainties_hz=tuple(item.standard_uncertainty_hz for item in rows),
    )


def _adapt_candidate_dwell(
    *,
    graph: PhysicalEpisodeGraphV1,
    bank: CataloguePredictionBankV1,
    rows: tuple[SupportIntegratedCfoObservationV1, ...],
    catalog_number: int,
) -> SyntheticCandidateDwellPrediction:
    candidate = next(item for item in bank.candidates if item.catalog_number == catalog_number)
    episode_id = graph.episodes[0].episode_id
    if candidate.eligible_episode_ids != (episode_id,):
        raise MultiDwellCatalogueAdapterError(
            "every common candidate must be eligible for the exact dwell episode"
        )
    prediction_by_id = {item.observation_id: item for item in candidate.tau_states[0].predictions}
    row_ids = tuple(item.observation_id for item in rows)
    if set(prediction_by_id) != set(row_ids):
        raise MultiDwellCatalogueAdapterError(
            "candidate prediction inventory does not exactly cover the dwell"
        )
    return SyntheticCandidateDwellPrediction(
        dwell_id=graph.episodes[0].dwell_id,
        predicted_cfo_hz=tuple(prediction_by_id[item].predicted_cfo_hz for item in row_ids),
        prediction_standard_uncertainties_hz=tuple(
            prediction_by_id[item].standard_uncertainty_hz for item in row_ids
        ),
    )
