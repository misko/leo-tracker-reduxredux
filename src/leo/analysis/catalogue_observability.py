"""Response-free catalogue-candidate observability geometry.

This module measures how different catalogue Doppler predictions remain after
declared receiver nuisance terms are removed.  Its public entry point accepts
either the immutable wire-contract bank or its digest-identical, read-only
compact execution view.  A measured CFO graph is not part of the interface, so
target response cannot select candidates, prefixes, pairs, nuisance models, or
thresholds.

The primary geometry removes one unconstrained constant CFO offset.  A
diagnostic geometry additionally permits one linear receiver drift with a
Gaussian ridge prior.  Candidate-specific rate, acceleration, jerk, and
fragment-local time shifts are deliberately absent.  The optional measurement
floors are uncalibrated overlays: they produce descriptive neighbourhoods but
do not alter the response-free distance curves or their digest.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Literal, cast

import numpy as np
from numpy.typing import NDArray

from leo.analysis.catalogue_prediction_array_view import (
    CatalogueFieldDelta,
    CataloguePredictionArrayBankView,
    CataloguePredictionArrayViewError,
    catalogue_prediction_array_view_from_bank,
    verify_catalogue_prediction_array_bank_view,
)
from leo.contracts.catalogue_association import CataloguePredictionBankV1
from leo.contracts.digests import Sha256Digest, canonical_digest

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_PRIMARY_MODEL: Literal["offset-only-v1"] = "offset-only-v1"
_DRIFT_MODEL: Literal["offset-plus-ridge-drift-v1"] = "offset-plus-ridge-drift-v1"

type _PredictionBankInput = CataloguePredictionBankV1 | CataloguePredictionArrayBankView


class CatalogueObservabilityInputError(ValueError):
    """A bank, authority binding, or numerical control is invalid."""


class CatalogueObservabilityWorkLimitError(ValueError):
    """The complete response-free analysis exceeds a declared work cap."""


@dataclass(frozen=True, slots=True)
class WrongFieldBankExpectation:
    field_delta_s: Literal[-500, 500]
    prediction_bank_digest: Sha256Digest

    def __post_init__(self) -> None:
        if self.field_delta_s not in (-500, 500):
            raise CatalogueObservabilityInputError("wrong field must equal -500 or +500 s")
        _require_digest(self.prediction_bank_digest, "wrong-field bank digest")


@dataclass(frozen=True, slots=True)
class MeasurementFloorOverlay:
    """A detachable, explicitly uncalibrated descriptive measurement floor."""

    history_ms: float
    floor_hz: float
    source_digest: Sha256Digest
    calibrated: Literal[False] = False

    def __post_init__(self) -> None:
        if (
            isinstance(self.history_ms, bool)
            or not math.isfinite(self.history_ms)
            or self.history_ms <= 0.0
            or isinstance(self.floor_hz, bool)
            or not math.isfinite(self.floor_hz)
            or self.floor_hz <= 0.0
        ):
            raise CatalogueObservabilityInputError("measurement floor values must be positive")
        _require_digest(self.source_digest, "measurement-floor source digest")
        if self.calibrated is not False:
            raise CatalogueObservabilityInputError("C1 measurement floors must remain uncalibrated")


@dataclass(frozen=True, slots=True)
class ObservabilityWorkLimits:
    maximum_candidates_per_field: int = 1_024
    maximum_observations: int = 2_048
    maximum_tau_states: int = 41
    maximum_pair_prefix_evaluations: int = 1_500_000_000
    maximum_tau_prediction_cells: int = 100_000_000
    maximum_close_pair_count: int = 8_192
    maximum_profiled_tau_pair_observation_evaluations: int = 200_000_000_000

    def __post_init__(self) -> None:
        for value, label in (
            (self.maximum_candidates_per_field, "candidate cap"),
            (self.maximum_observations, "observation cap"),
            (self.maximum_tau_states, "tau-state cap"),
            (self.maximum_pair_prefix_evaluations, "pair-prefix cap"),
            (self.maximum_tau_prediction_cells, "tau-cell cap"),
            (self.maximum_close_pair_count, "close-pair cap"),
            (
                self.maximum_profiled_tau_pair_observation_evaluations,
                "profiled-tau pair-observation cap",
            ),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise CatalogueObservabilityInputError(f"{label} must be a positive integer")


@dataclass(frozen=True, slots=True)
class CandidateObservabilityConfig:
    expected_true_field_bank_digest: Sha256Digest
    expected_wrong_field_banks: tuple[WrongFieldBankExpectation, WrongFieldBankExpectation]
    expected_support_digest: Sha256Digest
    expected_tle_snapshot_digest: Sha256Digest
    drift_prior_sigma_hz_per_s: float = 20.0
    drift_reference_measurement_sigma_hz: float = 50.0
    close_pair_neighbours_per_candidate: int = 4
    numerical_negative_tolerance_hz2: float = 1e-6
    floor_overlays: tuple[MeasurementFloorOverlay, ...] = ()
    work_limits: ObservabilityWorkLimits = field(default_factory=ObservabilityWorkLimits)

    def __post_init__(self) -> None:
        _require_digest(self.expected_true_field_bank_digest, "true-field bank digest")
        _require_digest(self.expected_support_digest, "support digest")
        _require_digest(self.expected_tle_snapshot_digest, "TLE snapshot digest")
        if tuple(item.field_delta_s for item in self.expected_wrong_field_banks) != (-500, 500):
            raise CatalogueObservabilityInputError(
                "wrong-field expectations must be canonically ordered -500, +500"
            )
        for value, label in (
            (self.drift_prior_sigma_hz_per_s, "drift prior sigma"),
            (
                self.drift_reference_measurement_sigma_hz,
                "drift reference measurement sigma",
            ),
            (self.numerical_negative_tolerance_hz2, "negative-distance tolerance"),
        ):
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0.0:
                raise CatalogueObservabilityInputError(f"{label} must be finite and positive")
        if (
            not isinstance(self.close_pair_neighbours_per_candidate, int)
            or isinstance(self.close_pair_neighbours_per_candidate, bool)
            or self.close_pair_neighbours_per_candidate <= 0
        ):
            raise CatalogueObservabilityInputError(
                "close-pair neighbour count must be a positive integer"
            )
        histories = tuple(item.history_ms for item in self.floor_overlays)
        if histories != tuple(sorted(set(histories))):
            raise CatalogueObservabilityInputError(
                "measurement-floor histories must be unique and canonically ordered"
            )


@dataclass(frozen=True, slots=True)
class PrefixDistanceSummary:
    prefix_index: int
    duration_s: float
    minimum_nearest_other_rms_hz: float
    median_nearest_other_rms_hz: float
    maximum_nearest_other_rms_hz: float


@dataclass(frozen=True, slots=True)
class PersistentThresholdCrossing:
    history_ms: float
    floor_hz: float
    first_above_prefix_index: int | None
    first_above_duration_s: float | None
    persistent_above_prefix_index: int | None
    persistent_above_duration_s: float | None


@dataclass(frozen=True, slots=True)
class PairDistanceCurve:
    left_catalog_number: int
    right_catalog_number: int
    selected_response_free: Literal[True]
    projected_rms_hz_by_prefix: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class EquivalenceComponent:
    """One threshold-graph component, not a pairwise-equivalent clique."""

    component_index: int
    catalog_numbers: tuple[int, ...]
    diameter_rms_hz: float
    chained: bool
    relationship: Literal["single-linkage-connected-neighborhood-v1"] = (
        "single-linkage-connected-neighborhood-v1"
    )


@dataclass(frozen=True, slots=True)
class CandidateAmbiguitySummary:
    catalog_number: int
    local_candidate_count: int
    soft_effective_candidate_count: float
    component_index: int


@dataclass(frozen=True, slots=True)
class FloorPrefixSummary:
    prefix_index: int
    duration_s: float
    minimum_local_candidate_count: int
    median_local_candidate_count: float
    maximum_local_candidate_count: int
    minimum_soft_effective_candidate_count: float
    median_soft_effective_candidate_count: float
    maximum_soft_effective_candidate_count: float
    component_count: int
    largest_component_size: int
    chained_component_count: int


@dataclass(frozen=True, slots=True)
class FloorOverlayResult:
    history_ms: float
    floor_hz: float
    source_digest: Sha256Digest
    calibrated: Literal[False]
    prefix_summaries: tuple[FloorPrefixSummary, ...]
    final_components: tuple[EquivalenceComponent, ...]
    final_candidate_summaries: tuple[CandidateAmbiguitySummary, ...]
    close_pair_crossings: tuple[PersistentThresholdCrossing, ...]
    identity_gate_applied: Literal[False] = False


@dataclass(frozen=True, slots=True)
class ProfiledTauFloorNeighborhood:
    """Final candidate-identity graph after minimizing over independent tau states."""

    history_ms: float
    floor_hz: float
    source_digest: Sha256Digest
    calibrated: Literal[False]
    candidate_identity_edge_count: int
    minimum_local_candidate_count: int
    median_local_candidate_count: float
    maximum_local_candidate_count: int
    component_count: int
    largest_component_size: int
    singleton_component_count: int
    chained_component_count: int
    final_components: tuple[EquivalenceComponent, ...]
    identity_gate_applied: Literal[False] = False


@dataclass(frozen=True, slots=True)
class ProfiledTauCandidateIdentityAtlas:
    """Response-free final drift geometry over the complete independent tau product."""

    true_field_prediction_bank_digest: Sha256Digest
    support_digest: Sha256Digest
    tle_snapshot_digest: Sha256Digest
    candidate_numbers: tuple[int, ...]
    tau_values_s: tuple[float, ...]
    observation_count: int
    nuisance_model: Literal["offset-plus-ridge-drift-v1"]
    drift_prior_sigma_hz_per_s: float
    reference_measurement_sigma_hz: float
    numerical_negative_tolerance_hz2: float
    tau_pair_distance_matrix_count: int
    pair_observation_evaluations: int
    complete_tau_cross_product_evaluated: bool
    floor_neighborhoods: tuple[ProfiledTauFloorNeighborhood, ...]
    content_digest: Sha256Digest
    algorithm_version: Literal["profiled-tau-candidate-identity-neighborhood-v1"] = field(
        default="profiled-tau-candidate-identity-neighborhood-v1",
        init=False,
    )
    tau_pairing_semantics: Literal["independent-complete-cross-product-minimum-v1"] = field(
        default="independent-complete-cross-product-minimum-v1",
        init=False,
    )
    candidate_node_semantics: Literal[
        "one-node-per-catalogue-identity-all-tau-states-unified-v1"
    ] = field(
        default="one-node-per-catalogue-identity-all-tau-states-unified-v1",
        init=False,
    )
    threshold_graph_semantics: Literal["edge-if-any-profiled-state-pair-within-floor-v1"] = field(
        default="edge-if-any-profiled-state-pair-within-floor-v1",
        init=False,
    )
    measured_response_accessed: Literal[False] = field(default=False, init=False)
    candidate_universe_selected_from_response: Literal[False] = field(
        default=False,
        init=False,
    )
    identity_claimed: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class NuisanceGeometryResult:
    nuisance_model: Literal["offset-only-v1", "offset-plus-ridge-drift-v1"]
    drift_prior_sigma_hz_per_s: float | None
    reference_measurement_sigma_hz: float | None
    prefix_summaries: tuple[PrefixDistanceSummary, ...]
    close_pair_curves: tuple[PairDistanceCurve, ...]
    floor_overlays: tuple[FloorOverlayResult, ...]
    distance_covariance_model: Literal["homoscedastic-identity-rms-v1"] = (
        "homoscedastic-identity-rms-v1"
    )


@dataclass(frozen=True, slots=True)
class TauNuisanceSensitivity:
    nuisance_model: Literal["offset-only-v1", "offset-plus-ridge-drift-v1"]
    final_projected_rms_hz: float


@dataclass(frozen=True, slots=True)
class TauStateSensitivity:
    tau_s: float
    nuisance_sensitivities: tuple[TauNuisanceSensitivity, TauNuisanceSensitivity]
    primary_floor_crossings: tuple[PersistentThresholdCrossing, ...]


@dataclass(frozen=True, slots=True)
class CandidateTauSensitivity:
    catalog_number: int
    states_relative_to_tau_zero: tuple[TauStateSensitivity, ...]


@dataclass(frozen=True, slots=True)
class TauPrefixSummary:
    prefix_index: int
    duration_s: float
    minimum_candidate_max_tau_rms_hz: float
    median_candidate_max_tau_rms_hz: float
    maximum_candidate_max_tau_rms_hz: float


@dataclass(frozen=True, slots=True)
class WrongFieldPrefixSummary:
    prefix_index: int
    duration_s: float
    minimum_nearest_any_rms_hz: float
    median_nearest_any_rms_hz: float
    maximum_nearest_any_rms_hz: float
    minimum_nearest_different_norad_rms_hz: float | None
    median_nearest_different_norad_rms_hz: float | None
    maximum_nearest_different_norad_rms_hz: float | None


@dataclass(frozen=True, slots=True)
class WrongFieldCandidateAlternative:
    true_field_catalog_number: int
    nearest_any_catalog_number: int
    nearest_any_final_rms_hz: float
    nearest_different_norad_catalog_number: int | None
    nearest_different_norad_final_rms_hz: float | None
    nearest_any_primary_floor_crossings: tuple[PersistentThresholdCrossing, ...]
    nearest_different_norad_primary_floor_crossings: tuple[PersistentThresholdCrossing, ...]


@dataclass(frozen=True, slots=True)
class WrongFieldObservabilityResult:
    field_delta_s: Literal[-500, 500]
    prediction_bank_digest: Sha256Digest
    prefix_summaries: tuple[WrongFieldPrefixSummary, ...]
    final_candidate_alternatives: tuple[WrongFieldCandidateAlternative, ...]
    true_field_tau_s: float = 0.0
    comparison_field_tau_s: float = 0.0
    tau_profiled: Literal[False] = False
    observe_only: Literal[True] = True
    p_value_computed: Literal[False] = False
    identity_gate_applied: Literal[False] = False


@dataclass(frozen=True, slots=True)
class ObservabilityWorkReceipt:
    observation_count: int
    true_candidate_count: int
    wrong_candidate_counts: tuple[int, int]
    tau_state_count: int
    nuisance_model_count: int
    pair_prefix_evaluations: int
    tau_prediction_cells: int
    close_pair_count: int
    profiled_tau_pair_distance_matrix_count: int
    profiled_tau_pair_observation_evaluations: int


@dataclass(frozen=True, slots=True)
class CandidateObservabilityResult:
    true_field_prediction_bank_digest: Sha256Digest
    wrong_field_prediction_bank_digests: tuple[Sha256Digest, Sha256Digest]
    support_digest: Sha256Digest
    tle_snapshot_digest: Sha256Digest
    candidate_numbers: tuple[int, ...]
    prefix_end_utc_ns: tuple[int, ...]
    prefix_duration_s: tuple[float, ...]
    nuisance_geometries: tuple[NuisanceGeometryResult, NuisanceGeometryResult]
    tau_sensitivity: tuple[CandidateTauSensitivity, ...]
    tau_prefix_summaries: tuple[TauPrefixSummary, ...]
    profiled_tau_candidate_identity_atlas: ProfiledTauCandidateIdentityAtlas
    wrong_field_observability: tuple[WrongFieldObservabilityResult, WrongFieldObservabilityResult]
    work_receipt: ObservabilityWorkReceipt
    response_free_geometry_digest: Sha256Digest
    config_digest: Sha256Digest
    content_digest: Sha256Digest
    algorithm_version: Literal["catalogue-candidate-observability-v1"] = field(
        default="catalogue-candidate-observability-v1", init=False
    )
    measured_response_accessed: Literal[False] = field(default=False, init=False)
    candidate_universe_selected_from_response: Literal[False] = field(default=False, init=False)
    numerical_thresholds_frozen: Literal[False] = field(default=False, init=False)
    identity_claimed: Literal[False] = field(default=False, init=False)
    wrong_epoch_is_gate: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class _NuisanceSpec:
    name: Literal["offset-only-v1", "offset-plus-ridge-drift-v1"]
    drift_ridge_s2: float | None


@dataclass(frozen=True, slots=True)
class _BankData:
    bank: CataloguePredictionArrayBankView
    candidate_numbers: np.ndarray
    times_s: np.ndarray
    tau_values: tuple[float, ...]
    predictions_by_tau: dict[float, np.ndarray]


@dataclass(slots=True)
class _PairwiseMomentAccumulator:
    """Stable online moments of every left-minus-right prediction pair."""

    mean_left_hz: np.ndarray
    mean_right_hz: np.ndarray
    centered_sum_squares_hz2: np.ndarray
    centered_time_cross_hz_s: np.ndarray | None
    count: int = 0
    mean_time_s: float = 0.0
    centered_time_sum_squares_s2: float = 0.0

    @classmethod
    def create(
        cls,
        shape: tuple[int, int],
        *,
        include_drift: bool,
    ) -> _PairwiseMomentAccumulator:
        return cls(
            mean_left_hz=np.zeros(shape[0], dtype=np.float64),
            mean_right_hz=np.zeros(shape[1], dtype=np.float64),
            centered_sum_squares_hz2=np.zeros(shape, dtype=np.float64),
            centered_time_cross_hz_s=(np.zeros(shape, dtype=np.float64) if include_drift else None),
        )

    def update(
        self,
        left_hz: np.ndarray,
        right_hz: np.ndarray,
        *,
        time_s: float,
    ) -> None:
        """Consume one observation without forming cancellation-prone CFO Grams."""

        self.count += 1
        left_delta = left_hz - self.mean_left_hz
        right_delta = right_hz - self.mean_right_hz
        pair_delta = np.subtract.outer(left_delta, right_delta)
        self.mean_left_hz += left_delta / self.count
        self.mean_right_hz += right_delta / self.count
        post_update_fraction = (self.count - 1.0) / self.count

        if self.centered_time_cross_hz_s is not None:
            time_delta = time_s - self.mean_time_s
            self.mean_time_s += time_delta / self.count
            self.centered_time_sum_squares_s2 += time_delta * (time_s - self.mean_time_s)
            self.centered_time_cross_hz_s += time_delta * post_update_fraction * pair_delta

        np.square(pair_delta, out=pair_delta)
        pair_delta *= post_update_fraction
        self.centered_sum_squares_hz2 += pair_delta

    def projected_rms_hz(
        self,
        spec: _NuisanceSpec,
        tolerance_hz2: float,
    ) -> np.ndarray:
        if self.count <= 0:
            raise CatalogueObservabilityInputError(
                "pairwise nuisance projection has no observations"
            )
        if spec.name == _PRIMARY_MODEL:
            objective = self.centered_sum_squares_hz2
        else:
            cross = self.centered_time_cross_hz_s
            if cross is None:
                raise CatalogueObservabilityInputError(
                    "ridge-drift projection is missing time moments"
                )
            objective = self.centered_sum_squares_hz2 - cross * cross / (
                self.centered_time_sum_squares_s2 + _drift_ridge(spec)
            )
        objective = _clamp_distance(objective, tolerance_hz2)
        return cast(NDArray[np.float64], np.sqrt(objective / self.count))


def analyze_candidate_observability(
    *,
    true_field_bank: _PredictionBankInput,
    wrong_field_banks: tuple[_PredictionBankInput, _PredictionBankInput],
    config: CandidateObservabilityConfig,
) -> CandidateObservabilityResult:
    """Build a complete response-free C1 observability atlas.

    The caller must bind every bank by digest.  Only predictions and their
    response-free support are consumed; measured CFO is structurally absent.
    """

    config = _revalidate_config(config)
    if len(wrong_field_banks) != 2:
        raise CatalogueObservabilityInputError("C1 requires exactly two wrong-field banks")
    true_bank = _revalidate_bank(true_field_bank, "true-time", field_delta_s=0)
    wrong_banks = (
        _revalidate_bank(
            wrong_field_banks[0],
            f"wrong-time {config.expected_wrong_field_banks[0].field_delta_s:+d} s",
            field_delta_s=config.expected_wrong_field_banks[0].field_delta_s,
        ),
        _revalidate_bank(
            wrong_field_banks[1],
            f"wrong-time {config.expected_wrong_field_banks[1].field_delta_s:+d} s",
            field_delta_s=config.expected_wrong_field_banks[1].field_delta_s,
        ),
    )
    _validate_authority(true_bank, wrong_banks, config)
    receipt = _work_receipt(true_bank, wrong_banks, config)

    true_data = _bank_data(true_bank, include_all_tau=True)
    wrong_data = (
        _bank_data(wrong_banks[0], include_all_tau=False),
        _bank_data(wrong_banks[1], include_all_tau=False),
    )
    if any(item.tau_values != true_data.tau_values for item in wrong_data):
        raise CatalogueObservabilityInputError("true and wrong fields have different tau grids")
    primary = _NuisanceSpec(name=_PRIMARY_MODEL, drift_ridge_s2=None)
    drift = _NuisanceSpec(
        name=_DRIFT_MODEL,
        drift_ridge_s2=(
            config.drift_reference_measurement_sigma_hz / config.drift_prior_sigma_hz_per_s
        )
        ** 2,
    )

    true_zero = true_data.predictions_by_tau[0.0]
    final_primary = _within_distance_matrix(
        true_zero,
        true_data.times_s,
        primary,
        config.numerical_negative_tolerance_hz2,
    )
    final_drift = _within_distance_matrix(
        true_zero,
        true_data.times_s,
        drift,
        config.numerical_negative_tolerance_hz2,
    )
    close_pairs = _select_close_pairs(
        (final_primary, final_drift),
        true_data.candidate_numbers,
        config.close_pair_neighbours_per_candidate,
        config.work_limits.maximum_close_pair_count,
    )
    receipt = ObservabilityWorkReceipt(
        observation_count=receipt.observation_count,
        true_candidate_count=receipt.true_candidate_count,
        wrong_candidate_counts=receipt.wrong_candidate_counts,
        tau_state_count=receipt.tau_state_count,
        nuisance_model_count=receipt.nuisance_model_count,
        pair_prefix_evaluations=receipt.pair_prefix_evaluations,
        tau_prediction_cells=receipt.tau_prediction_cells,
        close_pair_count=len(close_pairs),
        profiled_tau_pair_distance_matrix_count=(receipt.profiled_tau_pair_distance_matrix_count),
        profiled_tau_pair_observation_evaluations=(
            receipt.profiled_tau_pair_observation_evaluations
        ),
    )

    primary_geometry = _analyze_within_field(
        true_zero,
        true_data.candidate_numbers,
        true_data.times_s,
        primary,
        close_pairs,
        config,
        include_floor_overlays=True,
    )
    drift_geometry = _analyze_within_field(
        true_zero,
        true_data.candidate_numbers,
        true_data.times_s,
        drift,
        close_pairs,
        config,
        include_floor_overlays=True,
    )
    profiled_tau_atlas = _analyze_profiled_tau_candidate_identity_atlas(
        true_data,
        drift,
        config,
        receipt,
        tau_zero_distance=final_drift,
    )
    tau_sensitivity, tau_prefix = _analyze_tau_sensitivity(
        true_data,
        (primary, drift),
        config,
    )
    wrong_results = (
        _analyze_wrong_field(
            true_data,
            wrong_data[0],
            config.expected_wrong_field_banks[0].field_delta_s,
            config,
        ),
        _analyze_wrong_field(
            true_data,
            wrong_data[1],
            config.expected_wrong_field_banks[1].field_delta_s,
            config,
        ),
    )
    prefix_end = tuple(
        item.support_center_utc_ns
        for item in sorted(
            true_bank.support.observations,
            key=lambda item: item.support_center_utc_ns,
        )
    )
    durations = tuple(float(item) for item in true_data.times_s)
    config_digest = canonical_digest(_config_payload(config, include_floors=True))
    geometry_payload = {
        "algorithm_version": "catalogue-candidate-observability-v1",
        "true_field_prediction_bank_digest": true_bank.content_digest,
        "wrong_field_prediction_bank_digests": [item.content_digest for item in wrong_banks],
        "support_digest": true_bank.support.content_digest,
        "tle_snapshot_digest": true_bank.tle_snapshot.digest,
        "candidate_numbers": true_data.candidate_numbers.tolist(),
        "prefix_end_utc_ns": list(prefix_end),
        "prefix_duration_s": list(durations),
        "geometry_config": _config_payload(config, include_floors=False),
        "nuisance_geometries": [
            _nuisance_geometry_payload(primary_geometry, include_floors=False),
            _nuisance_geometry_payload(drift_geometry, include_floors=False),
        ],
        "tau_sensitivity": _tau_geometry_payload(tau_sensitivity, tau_prefix),
        "profiled_tau_candidate_identity_atlas": (
            _profiled_tau_atlas_geometry_payload(profiled_tau_atlas)
        ),
        "wrong_field_observability": _wrong_geometry_payload(wrong_results),
        "work_receipt": _response_free_geometry_work_receipt_payload(receipt),
        "measured_response_accessed": False,
        "candidate_universe_selected_from_response": False,
    }
    geometry_digest = canonical_digest(geometry_payload)
    body = {
        "true_field_prediction_bank_digest": true_bank.content_digest,
        "wrong_field_prediction_bank_digests": tuple(item.content_digest for item in wrong_banks),
        "support_digest": true_bank.support.content_digest,
        "tle_snapshot_digest": true_bank.tle_snapshot.digest,
        "candidate_numbers": tuple(int(item) for item in true_data.candidate_numbers),
        "prefix_end_utc_ns": prefix_end,
        "prefix_duration_s": durations,
        "nuisance_geometries": (
            asdict(primary_geometry),
            asdict(drift_geometry),
        ),
        "tau_sensitivity": tuple(asdict(item) for item in tau_sensitivity),
        "tau_prefix_summaries": tuple(asdict(item) for item in tau_prefix),
        "profiled_tau_candidate_identity_atlas": asdict(profiled_tau_atlas),
        "wrong_field_observability": tuple(asdict(item) for item in wrong_results),
        "work_receipt": asdict(receipt),
        "response_free_geometry_digest": geometry_digest,
        "config_digest": config_digest,
        "algorithm_version": "catalogue-candidate-observability-v1",
        "measured_response_accessed": False,
        "candidate_universe_selected_from_response": False,
        "numerical_thresholds_frozen": False,
        "identity_claimed": False,
        "wrong_epoch_is_gate": False,
    }
    result = CandidateObservabilityResult(
        true_field_prediction_bank_digest=true_bank.content_digest,
        wrong_field_prediction_bank_digests=(
            wrong_banks[0].content_digest,
            wrong_banks[1].content_digest,
        ),
        support_digest=true_bank.support.content_digest,
        tle_snapshot_digest=true_bank.tle_snapshot.digest,
        candidate_numbers=tuple(int(item) for item in true_data.candidate_numbers),
        prefix_end_utc_ns=prefix_end,
        prefix_duration_s=durations,
        nuisance_geometries=(primary_geometry, drift_geometry),
        tau_sensitivity=tau_sensitivity,
        tau_prefix_summaries=tau_prefix,
        profiled_tau_candidate_identity_atlas=profiled_tau_atlas,
        wrong_field_observability=wrong_results,
        work_receipt=receipt,
        response_free_geometry_digest=geometry_digest,
        config_digest=config_digest,
        content_digest=canonical_digest(body),
    )
    return result


def candidate_observability_result_payload(
    result: CandidateObservabilityResult,
) -> dict[str, object]:
    """Return and recheck the complete digest-closed JSON-compatible result."""

    document = asdict(result)
    claimed = document.pop("content_digest")
    if claimed != canonical_digest(document):
        raise CatalogueObservabilityInputError("observability result digest does not close")
    return {**document, "content_digest": claimed}


def _revalidate_config(config: CandidateObservabilityConfig) -> CandidateObservabilityConfig:
    try:
        return CandidateObservabilityConfig(
            expected_true_field_bank_digest=config.expected_true_field_bank_digest,
            expected_wrong_field_banks=(
                WrongFieldBankExpectation(
                    field_delta_s=config.expected_wrong_field_banks[0].field_delta_s,
                    prediction_bank_digest=(
                        config.expected_wrong_field_banks[0].prediction_bank_digest
                    ),
                ),
                WrongFieldBankExpectation(
                    field_delta_s=config.expected_wrong_field_banks[1].field_delta_s,
                    prediction_bank_digest=(
                        config.expected_wrong_field_banks[1].prediction_bank_digest
                    ),
                ),
            ),
            expected_support_digest=config.expected_support_digest,
            expected_tle_snapshot_digest=config.expected_tle_snapshot_digest,
            drift_prior_sigma_hz_per_s=config.drift_prior_sigma_hz_per_s,
            drift_reference_measurement_sigma_hz=(config.drift_reference_measurement_sigma_hz),
            close_pair_neighbours_per_candidate=(config.close_pair_neighbours_per_candidate),
            numerical_negative_tolerance_hz2=config.numerical_negative_tolerance_hz2,
            floor_overlays=tuple(
                MeasurementFloorOverlay(
                    history_ms=item.history_ms,
                    floor_hz=item.floor_hz,
                    source_digest=item.source_digest,
                    calibrated=item.calibrated,
                )
                for item in config.floor_overlays
            ),
            work_limits=ObservabilityWorkLimits(**asdict(config.work_limits)),
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise CatalogueObservabilityInputError("observability config is invalid") from error


def _revalidate_bank(
    bank: _PredictionBankInput,
    label: str,
    *,
    field_delta_s: CatalogueFieldDelta,
) -> CataloguePredictionArrayBankView:
    try:
        validated = (
            verify_catalogue_prediction_array_bank_view(bank)
            if isinstance(bank, CataloguePredictionArrayBankView)
            else catalogue_prediction_array_view_from_bank(
                bank,
                field_delta_s=field_delta_s,
            )
        )
    except (AttributeError, TypeError, ValueError, CataloguePredictionArrayViewError) as error:
        raise CatalogueObservabilityInputError(f"{label} prediction bank is invalid") from error
    if validated.field_delta_s != field_delta_s:
        raise CatalogueObservabilityInputError(f"{label} field delta differs")
    if len(validated.support.episode_ids) != 1:
        raise CatalogueObservabilityInputError("C1 V1 requires one physical episode per bank")
    return validated


def _validate_authority(
    true_bank: CataloguePredictionArrayBankView,
    wrong_banks: tuple[CataloguePredictionArrayBankView, CataloguePredictionArrayBankView],
    config: CandidateObservabilityConfig,
) -> None:
    if true_bank.content_digest != config.expected_true_field_bank_digest:
        raise CatalogueObservabilityInputError("true-field prediction-bank digest differs")
    for bank, expected in zip(wrong_banks, config.expected_wrong_field_banks, strict=True):
        if bank.content_digest != expected.prediction_bank_digest:
            raise CatalogueObservabilityInputError(
                f"wrong-field {expected.field_delta_s:+d} prediction-bank digest differs"
            )
    if true_bank.support.content_digest != config.expected_support_digest:
        raise CatalogueObservabilityInputError("prediction support digest differs")
    if true_bank.tle_snapshot.digest != config.expected_tle_snapshot_digest:
        raise CatalogueObservabilityInputError("TLE snapshot digest differs")
    if true_bank.field_delta_s != 0:
        raise CatalogueObservabilityInputError("compact true-time bank is not delta zero")
    for bank, expected in zip(wrong_banks, config.expected_wrong_field_banks, strict=True):
        if bank.field_delta_s != expected.field_delta_s:
            raise CatalogueObservabilityInputError("compact wrong-field delta differs")
    reference = (
        true_bank.support.content_digest,
        true_bank.tle_snapshot.model_dump(mode="json"),
        true_bank.observer_site.model_dump(mode="json"),
        true_bank.nominal_rf_hz,
        true_bank.selection_protocol_digest,
        true_bank.tau_search_policy,
    )
    for bank in wrong_banks:
        observed = (
            bank.support.content_digest,
            bank.tle_snapshot.model_dump(mode="json"),
            bank.observer_site.model_dump(mode="json"),
            bank.nominal_rf_hz,
            bank.selection_protocol_digest,
            bank.tau_search_policy,
        )
        if observed != reference:
            raise CatalogueObservabilityInputError(
                "true and wrong fields do not share exact support/site/RF/TLE/tau authority"
            )


def _bank_data(
    bank: CataloguePredictionArrayBankView,
    *,
    include_all_tau: bool,
) -> _BankData:
    support_rows = tuple(
        sorted(bank.support.observations, key=lambda item: item.support_center_utc_ns)
    )
    centers = np.asarray([item.support_center_utc_ns for item in support_rows], dtype=np.int64)
    if np.any(np.diff(centers) <= 0):
        raise CatalogueObservabilityInputError("support centres must be strictly chronological")
    times_s = (centers - centers[0]).astype(np.float64) / 1e9
    observation_ids = tuple(item.observation_id for item in support_rows)
    stored_observation_index = {
        observation_id: index for index, observation_id in enumerate(bank.observation_ids)
    }
    if set(stored_observation_index) != set(observation_ids):
        raise CatalogueObservabilityInputError(
            "compact candidate prediction does not cover exact support"
        )
    positions = [stored_observation_index[item] for item in observation_ids]
    numbers = np.asarray(
        bank.candidate_catalog_numbers,
        dtype=np.int64,
    )
    if len(numbers) < 2:
        raise CatalogueObservabilityInputError("observability requires at least two candidates")
    tau_values = bank.tau_values_s
    if 0.0 not in tau_values:
        raise CatalogueObservabilityInputError("every atlas bank requires exact tau=0")
    selected_tau = tau_values if include_all_tau else (0.0,)
    tau_index = {value: index for index, value in enumerate(tau_values)}
    by_tau: dict[float, np.ndarray] = {}
    for tau_s in selected_tau:
        matrix = np.take(
            bank.predicted_cfo_hz[:, tau_index[tau_s], :],
            positions,
            axis=1,
        ).astype(np.float64, copy=False)
        if not np.all(np.isfinite(matrix)):
            raise CatalogueObservabilityInputError("candidate prediction matrix is non-finite")
        matrix.setflags(write=False)
        by_tau[tau_s] = matrix
    times_s.setflags(write=False)
    numbers.setflags(write=False)
    return _BankData(
        bank=bank,
        candidate_numbers=numbers,
        times_s=times_s,
        tau_values=tau_values,
        predictions_by_tau=by_tau,
    )


def _work_receipt(
    true_bank: CataloguePredictionArrayBankView,
    wrong_banks: tuple[CataloguePredictionArrayBankView, CataloguePredictionArrayBankView],
    config: CandidateObservabilityConfig,
) -> ObservabilityWorkReceipt:
    limits = config.work_limits
    observation_count = len(true_bank.support.observations)
    counts = (len(true_bank.candidate_authority),) + tuple(
        len(item.candidate_authority) for item in wrong_banks
    )
    if observation_count > limits.maximum_observations:
        raise CatalogueObservabilityWorkLimitError("observation count exceeds the C1 cap")
    if any(item > limits.maximum_candidates_per_field for item in counts):
        raise CatalogueObservabilityWorkLimitError("candidate count exceeds the C1 cap")
    tau_grid = true_bank.tau_values_s
    tau_count = len(tau_grid)
    if tau_count > limits.maximum_tau_states:
        raise CatalogueObservabilityWorkLimitError("tau-state count exceeds the C1 cap")
    for bank in (true_bank, *wrong_banks):
        if bank.tau_values_s != tau_grid:
            raise CatalogueObservabilityInputError(
                "true and wrong fields must have one identical complete tau grid"
            )
    true_count = counts[0]
    within = observation_count * true_count * (true_count - 1) // 2 * 2
    cross = observation_count * true_count * (counts[1] + counts[2])
    pair_prefix = within + cross
    if pair_prefix > limits.maximum_pair_prefix_evaluations:
        raise CatalogueObservabilityWorkLimitError("pair-prefix work exceeds the C1 cap")
    tau_cells = observation_count * true_count * max(0, tau_count - 1) * 2
    if tau_cells > limits.maximum_tau_prediction_cells:
        raise CatalogueObservabilityWorkLimitError("tau-sensitivity work exceeds the C1 cap")
    profiled_tau_pair_distance_matrix_count = (
        tau_count * (tau_count + 1) // 2 if config.floor_overlays else 0
    )
    profiled_tau_pair_observation_evaluations = (
        observation_count * true_count * true_count * profiled_tau_pair_distance_matrix_count
    )
    if (
        profiled_tau_pair_observation_evaluations
        > limits.maximum_profiled_tau_pair_observation_evaluations
    ):
        raise CatalogueObservabilityWorkLimitError(
            "profiled-tau pair-observation work exceeds the C1 cap"
        )
    return ObservabilityWorkReceipt(
        observation_count=observation_count,
        true_candidate_count=true_count,
        wrong_candidate_counts=(counts[1], counts[2]),
        tau_state_count=tau_count,
        nuisance_model_count=2,
        pair_prefix_evaluations=pair_prefix,
        tau_prediction_cells=tau_cells,
        close_pair_count=0,
        profiled_tau_pair_distance_matrix_count=(profiled_tau_pair_distance_matrix_count),
        profiled_tau_pair_observation_evaluations=(profiled_tau_pair_observation_evaluations),
    )


def _within_distance_matrix(
    values: np.ndarray,
    times_s: np.ndarray,
    spec: _NuisanceSpec,
    tolerance_hz2: float,
) -> np.ndarray:
    return _cross_distance_matrix(
        values,
        values,
        times_s,
        spec,
        tolerance_hz2,
    )


def _cross_distance_matrix(
    left_values: np.ndarray,
    right_values: np.ndarray,
    times_s: np.ndarray,
    spec: _NuisanceSpec,
    tolerance_hz2: float,
) -> np.ndarray:
    moments = _PairwiseMomentAccumulator.create(
        (left_values.shape[0], right_values.shape[0]),
        include_drift=spec.name == _DRIFT_MODEL,
    )
    for left_column, right_column, time_s in zip(
        left_values.T,
        right_values.T,
        times_s,
        strict=True,
    ):
        moments.update(left_column, right_column, time_s=float(time_s))
    return moments.projected_rms_hz(spec, tolerance_hz2)


def _select_close_pairs(
    final_distances: tuple[np.ndarray, ...],
    candidate_numbers: np.ndarray,
    neighbours: int,
    maximum_pairs: int,
) -> tuple[tuple[int, int], ...]:
    selected: set[tuple[int, int]] = set()
    take = min(neighbours, len(candidate_numbers) - 1)
    for final_distance in final_distances:
        for left in range(len(candidate_numbers)):
            order = np.lexsort((candidate_numbers, final_distance[left]))
            kept = [int(item) for item in order if int(item) != left][:take]
            for right in kept:
                selected.add((min(left, right), max(left, right)))
    pairs = tuple(
        sorted(selected, key=lambda item: (candidate_numbers[item[0]], candidate_numbers[item[1]]))
    )
    if len(pairs) > maximum_pairs:
        raise CatalogueObservabilityWorkLimitError("response-free close-pair set exceeds its cap")
    return pairs


def _analyze_within_field(
    values: np.ndarray,
    candidate_numbers: np.ndarray,
    times_s: np.ndarray,
    spec: _NuisanceSpec,
    close_pairs: tuple[tuple[int, int], ...],
    config: CandidateObservabilityConfig,
    *,
    include_floor_overlays: bool,
) -> NuisanceGeometryResult:
    count, observation_count = values.shape
    moments = _PairwiseMomentAccumulator.create(
        (count, count),
        include_drift=spec.name == _DRIFT_MODEL,
    )
    pair_curves = np.empty((len(close_pairs), observation_count), dtype=np.float64)
    prefix_summaries: list[PrefixDistanceSummary] = []
    overlay_prefix: list[list[FloorPrefixSummary]] = [[] for _ in config.floor_overlays]
    final_overlay_state: list[
        tuple[tuple[EquivalenceComponent, ...], tuple[CandidateAmbiguitySummary, ...]]
    ] = []

    for prefix_zero, time_s in enumerate(times_s):
        column = values[:, prefix_zero]
        moments.update(column, column, time_s=float(time_s))
        n = prefix_zero + 1
        distance = moments.projected_rms_hz(
            spec,
            config.numerical_negative_tolerance_hz2,
        )
        nearest = distance.copy()
        np.fill_diagonal(nearest, np.inf)
        nearest_values = np.min(nearest, axis=1)
        prefix_summaries.append(
            PrefixDistanceSummary(
                prefix_index=n,
                duration_s=float(time_s),
                minimum_nearest_other_rms_hz=float(np.min(nearest_values)),
                median_nearest_other_rms_hz=float(np.median(nearest_values)),
                maximum_nearest_other_rms_hz=float(np.max(nearest_values)),
            )
        )
        for pair_index, (left, right) in enumerate(close_pairs):
            pair_curves[pair_index, prefix_zero] = distance[left, right]
        if include_floor_overlays:
            for overlay_index, overlay in enumerate(config.floor_overlays):
                components = _components(
                    distance,
                    candidate_numbers,
                    overlay.floor_hz,
                    config.numerical_negative_tolerance_hz2,
                )
                local = np.sum(distance <= overlay.floor_hz, axis=1)
                soft = np.sum(np.exp(-0.5 * (distance / overlay.floor_hz) ** 2), axis=1)
                overlay_prefix[overlay_index].append(
                    FloorPrefixSummary(
                        prefix_index=n,
                        duration_s=float(time_s),
                        minimum_local_candidate_count=int(np.min(local)),
                        median_local_candidate_count=float(np.median(local)),
                        maximum_local_candidate_count=int(np.max(local)),
                        minimum_soft_effective_candidate_count=float(np.min(soft)),
                        median_soft_effective_candidate_count=float(np.median(soft)),
                        maximum_soft_effective_candidate_count=float(np.max(soft)),
                        component_count=len(components),
                        largest_component_size=max(
                            len(item.catalog_numbers) for item in components
                        ),
                        chained_component_count=sum(item.chained for item in components),
                    )
                )
                if prefix_zero == observation_count - 1:
                    component_by_number = {
                        number: component.component_index
                        for component in components
                        for number in component.catalog_numbers
                    }
                    summaries = tuple(
                        CandidateAmbiguitySummary(
                            catalog_number=int(number),
                            local_candidate_count=int(local[index]),
                            soft_effective_candidate_count=float(soft[index]),
                            component_index=component_by_number[int(number)],
                        )
                        for index, number in enumerate(candidate_numbers)
                    )
                    final_overlay_state.append((components, summaries))

    curves = tuple(
        PairDistanceCurve(
            left_catalog_number=int(candidate_numbers[left]),
            right_catalog_number=int(candidate_numbers[right]),
            selected_response_free=True,
            projected_rms_hz_by_prefix=tuple(float(item) for item in pair_curves[index]),
        )
        for index, (left, right) in enumerate(close_pairs)
    )
    overlays: list[FloorOverlayResult] = []
    if include_floor_overlays:
        for overlay_index, overlay in enumerate(config.floor_overlays):
            components, candidate_summaries = final_overlay_state[overlay_index]
            crossings = tuple(
                _crossing(curve.projected_rms_hz_by_prefix, times_s, overlay) for curve in curves
            )
            overlays.append(
                FloorOverlayResult(
                    history_ms=overlay.history_ms,
                    floor_hz=overlay.floor_hz,
                    source_digest=overlay.source_digest,
                    calibrated=False,
                    prefix_summaries=tuple(overlay_prefix[overlay_index]),
                    final_components=components,
                    final_candidate_summaries=candidate_summaries,
                    close_pair_crossings=crossings,
                )
            )
    return NuisanceGeometryResult(
        nuisance_model=spec.name,
        drift_prior_sigma_hz_per_s=(
            None if spec.name == _PRIMARY_MODEL else config.drift_prior_sigma_hz_per_s
        ),
        reference_measurement_sigma_hz=(
            None if spec.name == _PRIMARY_MODEL else config.drift_reference_measurement_sigma_hz
        ),
        prefix_summaries=tuple(prefix_summaries),
        close_pair_curves=curves,
        floor_overlays=tuple(overlays),
    )


def _components(
    distance: np.ndarray,
    candidate_numbers: np.ndarray,
    floor_hz: float,
    tolerance: float,
) -> tuple[EquivalenceComponent, ...]:
    adjacency = distance <= floor_hz
    remaining = np.ones(len(candidate_numbers), dtype=bool)
    groups: list[np.ndarray] = []
    while np.any(remaining):
        seed = int(np.flatnonzero(remaining)[0])
        members = np.zeros(len(candidate_numbers), dtype=bool)
        frontier = np.zeros(len(candidate_numbers), dtype=bool)
        frontier[seed] = True
        while np.any(frontier):
            members |= frontier
            neighbours = np.any(adjacency[frontier], axis=0)
            frontier = neighbours & ~members
        remaining[members] = False
        groups.append(np.flatnonzero(members))
    groups.sort(key=lambda indices: int(np.min(candidate_numbers[indices])))
    result = []
    for component_index, indices in enumerate(groups):
        diameter = float(np.max(distance[np.ix_(indices, indices)]))
        result.append(
            EquivalenceComponent(
                component_index=component_index,
                catalog_numbers=tuple(sorted(int(item) for item in candidate_numbers[indices])),
                diameter_rms_hz=diameter,
                chained=diameter > floor_hz + math.sqrt(tolerance),
            )
        )
    return tuple(result)


def _analyze_profiled_tau_candidate_identity_atlas(
    data: _BankData,
    spec: _NuisanceSpec,
    config: CandidateObservabilityConfig,
    receipt: ObservabilityWorkReceipt,
    *,
    tau_zero_distance: np.ndarray,
) -> ProfiledTauCandidateIdentityAtlas:
    if spec.name != _DRIFT_MODEL:
        raise CatalogueObservabilityInputError(
            "profiled-tau candidate identity requires the ridge-drift nuisance"
        )
    expected_matrix_count = receipt.profiled_tau_pair_distance_matrix_count
    expected_work = receipt.profiled_tau_pair_observation_evaluations
    floor_neighborhoods: tuple[ProfiledTauFloorNeighborhood, ...] = ()
    complete = bool(config.floor_overlays)

    if complete:
        candidate_count = len(data.candidate_numbers)
        profiled_minimum = np.full(
            (candidate_count, candidate_count),
            np.inf,
            dtype=np.float64,
        )
        zero_index = data.tau_values.index(0.0)
        evaluated = 0
        for left_tau_index, left_tau_s in enumerate(data.tau_values):
            left_values = data.predictions_by_tau[left_tau_s]
            for right_tau_index in range(left_tau_index, len(data.tau_values)):
                right_tau_s = data.tau_values[right_tau_index]
                if left_tau_index == zero_index and right_tau_index == zero_index:
                    distance = tau_zero_distance
                else:
                    distance = _cross_distance_matrix(
                        left_values,
                        data.predictions_by_tau[right_tau_s],
                        data.times_s,
                        spec,
                        config.numerical_negative_tolerance_hz2,
                    )
                # For tau_a != tau_b, D[i,j] and D[j,i] are the two independent
                # assignments of the unordered tau pair to candidate identities.
                # Applying both orientations on the diagonal is harmless and makes
                # the candidate-identity minimum exactly symmetric by construction.
                np.minimum(profiled_minimum, distance, out=profiled_minimum)
                np.minimum(profiled_minimum, distance.T, out=profiled_minimum)
                evaluated += 1
        if evaluated != expected_matrix_count:
            raise CatalogueObservabilityInputError(
                "profiled-tau distance-matrix work receipt differs"
            )
        if not np.all(np.isfinite(profiled_minimum)) or not np.array_equal(
            profiled_minimum,
            profiled_minimum.T,
        ):
            raise CatalogueObservabilityInputError(
                "profiled-tau candidate minimum geometry is invalid"
            )

        neighborhoods: list[ProfiledTauFloorNeighborhood] = []
        for overlay in config.floor_overlays:
            adjacency = profiled_minimum <= overlay.floor_hz
            local = np.sum(adjacency, axis=1)
            components = _components(
                profiled_minimum,
                data.candidate_numbers,
                overlay.floor_hz,
                config.numerical_negative_tolerance_hz2,
            )
            neighborhoods.append(
                ProfiledTauFloorNeighborhood(
                    history_ms=overlay.history_ms,
                    floor_hz=overlay.floor_hz,
                    source_digest=overlay.source_digest,
                    calibrated=False,
                    candidate_identity_edge_count=int(np.count_nonzero(np.triu(adjacency, k=1))),
                    minimum_local_candidate_count=int(np.min(local)),
                    median_local_candidate_count=float(np.median(local)),
                    maximum_local_candidate_count=int(np.max(local)),
                    component_count=len(components),
                    largest_component_size=max(len(item.catalog_numbers) for item in components),
                    singleton_component_count=sum(
                        len(item.catalog_numbers) == 1 for item in components
                    ),
                    chained_component_count=sum(item.chained for item in components),
                    final_components=components,
                )
            )
        floor_neighborhoods = tuple(neighborhoods)
    elif expected_matrix_count != 0 or expected_work != 0:
        raise CatalogueObservabilityInputError(
            "empty profiled-tau floor inventory has a nonzero work receipt"
        )

    body = {
        "true_field_prediction_bank_digest": data.bank.content_digest,
        "support_digest": data.bank.support.content_digest,
        "tle_snapshot_digest": data.bank.tle_snapshot.digest,
        "candidate_numbers": tuple(int(item) for item in data.candidate_numbers),
        "tau_values_s": data.tau_values,
        "observation_count": len(data.times_s),
        "nuisance_model": _DRIFT_MODEL,
        "drift_prior_sigma_hz_per_s": config.drift_prior_sigma_hz_per_s,
        "reference_measurement_sigma_hz": config.drift_reference_measurement_sigma_hz,
        "numerical_negative_tolerance_hz2": config.numerical_negative_tolerance_hz2,
        "tau_pair_distance_matrix_count": expected_matrix_count,
        "pair_observation_evaluations": expected_work,
        "complete_tau_cross_product_evaluated": complete,
        "floor_neighborhoods": tuple(asdict(item) for item in floor_neighborhoods),
        "algorithm_version": "profiled-tau-candidate-identity-neighborhood-v1",
        "tau_pairing_semantics": "independent-complete-cross-product-minimum-v1",
        "candidate_node_semantics": ("one-node-per-catalogue-identity-all-tau-states-unified-v1"),
        "threshold_graph_semantics": "edge-if-any-profiled-state-pair-within-floor-v1",
        "measured_response_accessed": False,
        "candidate_universe_selected_from_response": False,
        "identity_claimed": False,
    }
    return ProfiledTauCandidateIdentityAtlas(
        true_field_prediction_bank_digest=data.bank.content_digest,
        support_digest=data.bank.support.content_digest,
        tle_snapshot_digest=data.bank.tle_snapshot.digest,
        candidate_numbers=tuple(int(item) for item in data.candidate_numbers),
        tau_values_s=data.tau_values,
        observation_count=len(data.times_s),
        nuisance_model=_DRIFT_MODEL,
        drift_prior_sigma_hz_per_s=config.drift_prior_sigma_hz_per_s,
        reference_measurement_sigma_hz=config.drift_reference_measurement_sigma_hz,
        numerical_negative_tolerance_hz2=config.numerical_negative_tolerance_hz2,
        tau_pair_distance_matrix_count=expected_matrix_count,
        pair_observation_evaluations=expected_work,
        complete_tau_cross_product_evaluated=complete,
        floor_neighborhoods=floor_neighborhoods,
        content_digest=canonical_digest(body),
    )


def _analyze_tau_sensitivity(
    data: _BankData,
    specs: tuple[_NuisanceSpec, _NuisanceSpec],
    config: CandidateObservabilityConfig,
) -> tuple[tuple[CandidateTauSensitivity, ...], tuple[TauPrefixSummary, ...]]:
    zero = data.predictions_by_tau[0.0]
    max_tau_by_candidate_prefix = np.zeros_like(zero)
    candidates: list[CandidateTauSensitivity] = []
    for candidate_index, catalog_number in enumerate(data.candidate_numbers):
        states: list[TauStateSensitivity] = []
        for tau_s in data.tau_values:
            if tau_s == 0.0:
                continue
            difference = data.predictions_by_tau[tau_s][candidate_index] - zero[candidate_index]
            primary_curve = _direct_pair_curve(
                difference,
                data.times_s,
                specs[0],
                config.numerical_negative_tolerance_hz2,
            )
            drift_curve = _direct_pair_curve(
                difference,
                data.times_s,
                specs[1],
                config.numerical_negative_tolerance_hz2,
            )
            max_tau_by_candidate_prefix[candidate_index] = np.maximum(
                max_tau_by_candidate_prefix[candidate_index], primary_curve
            )
            states.append(
                TauStateSensitivity(
                    tau_s=tau_s,
                    nuisance_sensitivities=(
                        TauNuisanceSensitivity(
                            nuisance_model=_PRIMARY_MODEL,
                            final_projected_rms_hz=float(primary_curve[-1]),
                        ),
                        TauNuisanceSensitivity(
                            nuisance_model=_DRIFT_MODEL,
                            final_projected_rms_hz=float(drift_curve[-1]),
                        ),
                    ),
                    primary_floor_crossings=tuple(
                        _crossing(primary_curve, data.times_s, item)
                        for item in config.floor_overlays
                    ),
                )
            )
        candidates.append(
            CandidateTauSensitivity(
                catalog_number=int(catalog_number),
                states_relative_to_tau_zero=tuple(states),
            )
        )
    prefix = tuple(
        TauPrefixSummary(
            prefix_index=index + 1,
            duration_s=float(data.times_s[index]),
            minimum_candidate_max_tau_rms_hz=float(np.min(max_tau_by_candidate_prefix[:, index])),
            median_candidate_max_tau_rms_hz=float(np.median(max_tau_by_candidate_prefix[:, index])),
            maximum_candidate_max_tau_rms_hz=float(np.max(max_tau_by_candidate_prefix[:, index])),
        )
        for index in range(len(data.times_s))
    )
    return tuple(candidates), prefix


def _direct_pair_curve(
    difference: np.ndarray,
    times_s: np.ndarray,
    spec: _NuisanceSpec,
    tolerance_hz2: float,
) -> np.ndarray:
    curve = np.empty(len(difference), dtype=np.float64)
    mean_value = 0.0
    centered_sum_squares = 0.0
    mean_time = 0.0
    centered_time_sum_squares = 0.0
    centered_time_value_cross = 0.0
    ridge = None if spec.name == _PRIMARY_MODEL else _drift_ridge(spec)
    for index, (value, time_s) in enumerate(
        zip(difference, times_s, strict=True),
        start=1,
    ):
        value = float(value)
        time_s = float(time_s)
        value_delta = value - mean_value
        mean_value += value_delta / index
        centered_sum_squares += value_delta * (value - mean_value)
        time_delta = time_s - mean_time
        mean_time += time_delta / index
        centered_time_sum_squares += time_delta * (time_s - mean_time)
        centered_time_value_cross += time_delta * (value - mean_value)
        objective = centered_sum_squares
        if ridge is not None:
            objective -= centered_time_value_cross**2 / (centered_time_sum_squares + ridge)
        objective = float(
            _clamp_distance(
                np.asarray((objective,), dtype=np.float64),
                tolerance_hz2,
            )[0]
        )
        curve[index - 1] = math.sqrt(objective / index)
    return curve


def _analyze_wrong_field(
    true_data: _BankData,
    wrong_data: _BankData,
    field_delta_s: Literal[-500, 500],
    config: CandidateObservabilityConfig,
) -> WrongFieldObservabilityResult:
    left = true_data.predictions_by_tau[0.0]
    right = wrong_data.predictions_by_tau[0.0]
    left_count, observation_count = left.shape
    right_count = right.shape[0]
    moments = _PairwiseMomentAccumulator.create(
        (left_count, right_count),
        include_drift=False,
    )
    nearest_any_curve = np.empty((left_count, observation_count), dtype=np.float64)
    nearest_different_curve = np.full((left_count, observation_count), np.inf, dtype=np.float64)
    different_mask = true_data.candidate_numbers[:, None] != wrong_data.candidate_numbers[None, :]
    has_different = np.any(different_mask, axis=1)
    prefix: list[WrongFieldPrefixSummary] = []
    final_any_index = np.zeros(left_count, dtype=np.int64)
    final_different_index = np.full(left_count, -1, dtype=np.int64)
    for prefix_zero in range(observation_count):
        left_column = left[:, prefix_zero]
        right_column = right[:, prefix_zero]
        moments.update(
            left_column,
            right_column,
            time_s=float(true_data.times_s[prefix_zero]),
        )
        count = prefix_zero + 1
        distance = moments.projected_rms_hz(
            _NuisanceSpec(name=_PRIMARY_MODEL, drift_ridge_s2=None),
            config.numerical_negative_tolerance_hz2,
        )
        any_index = np.argmin(distance, axis=1)
        any_values = distance[np.arange(left_count), any_index]
        nearest_any_curve[:, prefix_zero] = any_values
        different_distance = np.where(different_mask, distance, np.inf)
        different_positions = np.argmin(different_distance, axis=1)
        different_values = different_distance[np.arange(left_count), different_positions]
        nearest_different_curve[:, prefix_zero] = different_values
        finite_different = different_values[np.isfinite(different_values)]
        prefix.append(
            WrongFieldPrefixSummary(
                prefix_index=count,
                duration_s=float(true_data.times_s[prefix_zero]),
                minimum_nearest_any_rms_hz=float(np.min(any_values)),
                median_nearest_any_rms_hz=float(np.median(any_values)),
                maximum_nearest_any_rms_hz=float(np.max(any_values)),
                minimum_nearest_different_norad_rms_hz=(
                    None if not len(finite_different) else float(np.min(finite_different))
                ),
                median_nearest_different_norad_rms_hz=(
                    None if not len(finite_different) else float(np.median(finite_different))
                ),
                maximum_nearest_different_norad_rms_hz=(
                    None if not len(finite_different) else float(np.max(finite_different))
                ),
            )
        )
        if prefix_zero == observation_count - 1:
            final_any_index = any_index
            final_different_index = np.where(has_different, different_positions, -1)
    alternatives = []
    for index, catalog_number in enumerate(true_data.candidate_numbers):
        final_different_position = int(final_different_index[index])
        alternatives.append(
            WrongFieldCandidateAlternative(
                true_field_catalog_number=int(catalog_number),
                nearest_any_catalog_number=int(
                    wrong_data.candidate_numbers[final_any_index[index]]
                ),
                nearest_any_final_rms_hz=float(nearest_any_curve[index, -1]),
                nearest_different_norad_catalog_number=(
                    None
                    if final_different_position < 0
                    else int(wrong_data.candidate_numbers[final_different_position])
                ),
                nearest_different_norad_final_rms_hz=(
                    None
                    if final_different_position < 0
                    else float(nearest_different_curve[index, -1])
                ),
                nearest_any_primary_floor_crossings=tuple(
                    _crossing(nearest_any_curve[index], true_data.times_s, item)
                    for item in config.floor_overlays
                ),
                nearest_different_norad_primary_floor_crossings=(
                    ()
                    if final_different_position < 0
                    else tuple(
                        _crossing(nearest_different_curve[index], true_data.times_s, item)
                        for item in config.floor_overlays
                    )
                ),
            )
        )
    return WrongFieldObservabilityResult(
        field_delta_s=field_delta_s,
        prediction_bank_digest=wrong_data.bank.content_digest,
        prefix_summaries=tuple(prefix),
        final_candidate_alternatives=tuple(alternatives),
    )


def _crossing(
    values: tuple[float, ...] | np.ndarray,
    times_s: np.ndarray,
    overlay: MeasurementFloorOverlay,
) -> PersistentThresholdCrossing:
    array = np.asarray(values, dtype=np.float64)
    above = array > overlay.floor_hz
    first_indices = np.flatnonzero(above)
    suffix = np.logical_and.accumulate(above[::-1])[::-1]
    persistent_indices = np.flatnonzero(suffix)
    first = None if not len(first_indices) else int(first_indices[0])
    persistent = None if not len(persistent_indices) else int(persistent_indices[0])
    return PersistentThresholdCrossing(
        history_ms=overlay.history_ms,
        floor_hz=overlay.floor_hz,
        first_above_prefix_index=None if first is None else first + 1,
        first_above_duration_s=None if first is None else float(times_s[first]),
        persistent_above_prefix_index=None if persistent is None else persistent + 1,
        persistent_above_duration_s=(None if persistent is None else float(times_s[persistent])),
    )


def _clamp_distance(value: np.ndarray, tolerance_hz2: float) -> np.ndarray:
    minimum = float(np.min(value))
    scale = max(1.0, float(np.max(np.abs(value))))
    floating_tolerance = 256.0 * np.finfo(np.float64).eps * scale
    if minimum < -(tolerance_hz2 + floating_tolerance):
        raise CatalogueObservabilityInputError("nuisance-projected distance is materially negative")
    return cast(NDArray[np.float64], np.maximum(value, 0.0))


def _drift_ridge(spec: _NuisanceSpec) -> float:
    ridge = spec.drift_ridge_s2
    if spec.name != _DRIFT_MODEL or ridge is None or not math.isfinite(ridge) or ridge <= 0.0:
        raise CatalogueObservabilityInputError("ridge-drift nuisance specification is invalid")
    return ridge


def _config_payload(
    config: CandidateObservabilityConfig, *, include_floors: bool
) -> dict[str, object]:
    payload: dict[str, object] = {
        "expected_true_field_bank_digest": config.expected_true_field_bank_digest,
        "expected_wrong_field_banks": [asdict(item) for item in config.expected_wrong_field_banks],
        "expected_support_digest": config.expected_support_digest,
        "expected_tle_snapshot_digest": config.expected_tle_snapshot_digest,
        "drift_prior_sigma_hz_per_s": config.drift_prior_sigma_hz_per_s,
        "drift_reference_measurement_sigma_hz": (config.drift_reference_measurement_sigma_hz),
        "close_pair_neighbours_per_candidate": (config.close_pair_neighbours_per_candidate),
        "numerical_negative_tolerance_hz2": config.numerical_negative_tolerance_hz2,
        "work_limits": asdict(config.work_limits),
    }
    if include_floors:
        payload["floor_overlays"] = [asdict(item) for item in config.floor_overlays]
    return payload


def _nuisance_geometry_payload(
    result: NuisanceGeometryResult, *, include_floors: bool
) -> dict[str, object]:
    payload = asdict(result)
    if not include_floors:
        payload["floor_overlays"] = []
    return payload


def _profiled_tau_atlas_geometry_payload(
    result: ProfiledTauCandidateIdentityAtlas,
) -> dict[str, object]:
    payload = asdict(result)
    payload.pop("content_digest")
    payload["floor_neighborhoods"] = []
    return payload


def _response_free_geometry_work_receipt_payload(
    receipt: ObservabilityWorkReceipt,
) -> dict[str, object]:
    return asdict(receipt)


def _tau_geometry_payload(
    candidates: tuple[CandidateTauSensitivity, ...],
    prefix: tuple[TauPrefixSummary, ...],
) -> dict[str, object]:
    return {
        "candidates": [
            {
                "catalog_number": item.catalog_number,
                "states_relative_to_tau_zero": [
                    {
                        "tau_s": state.tau_s,
                        "nuisance_sensitivities": [
                            asdict(value) for value in state.nuisance_sensitivities
                        ],
                    }
                    for state in item.states_relative_to_tau_zero
                ],
            }
            for item in candidates
        ],
        "prefix_summaries": [asdict(item) for item in prefix],
    }


def _wrong_geometry_payload(
    results: tuple[WrongFieldObservabilityResult, WrongFieldObservabilityResult],
) -> list[dict[str, object]]:
    return [
        {
            "field_delta_s": result.field_delta_s,
            "prediction_bank_digest": result.prediction_bank_digest,
            "prefix_summaries": [asdict(item) for item in result.prefix_summaries],
            "final_candidate_alternatives": [
                {
                    "true_field_catalog_number": item.true_field_catalog_number,
                    "nearest_any_catalog_number": item.nearest_any_catalog_number,
                    "nearest_any_final_rms_hz": item.nearest_any_final_rms_hz,
                    "nearest_different_norad_catalog_number": (
                        item.nearest_different_norad_catalog_number
                    ),
                    "nearest_different_norad_final_rms_hz": (
                        item.nearest_different_norad_final_rms_hz
                    ),
                }
                for item in result.final_candidate_alternatives
            ],
            "observe_only": True,
            "p_value_computed": False,
            "identity_gate_applied": False,
        }
        for result in results
    ]


def _require_digest(value: str, label: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise CatalogueObservabilityInputError(f"{label} must be a tagged SHA-256 digest")
