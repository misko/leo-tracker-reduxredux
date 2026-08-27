"""Known-position batch calibration of joint satellite frequency states.

For each exact catalogue-association mode this analyzer fits one bias/drift
state per active satellite together with continuity-component CFO offsets and
hardware-epoch drift.  Receiver-local states use externally calibrated proper
priors and are marginalized from the returned satellite covariance.  The
resulting cross-satellite covariance is therefore retained without exporting
receiver, LNB, path, or component estimates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from leo.analysis.satellite_correction_joint_replay import (
    JointSatelliteFrequencyCalibrationEstimate,
)
from leo.analysis.satellite_correction_replay import (
    SatelliteCorrectionInputError,
    SatelliteCorrectionNumericalError,
    SatelliteFrequencyCalibrationEstimate,
)
from leo.contracts.catalogue_association import (
    CatalogueAssociationModeV1,
    CatalogueAssociationResultV1,
    CataloguePredictionBankV1,
    CataloguePredictionSupportV1,
    PhysicalCfoEpisodeV1,
    PhysicalEpisodeGraphV1,
    SupportIntegratedCfoObservationV1,
)
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.satellite_pnt import SatelliteFrequencyScope


@dataclass(frozen=True, slots=True)
class ReceiverComponentOffsetPrior:
    continuity_component_id: Sha256Digest
    mean_hz: float
    standard_uncertainty_hz: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.mean_hz):
            raise SatelliteCorrectionInputError("component-prior mean must be finite")
        if not math.isfinite(self.standard_uncertainty_hz) or self.standard_uncertainty_hz <= 0.0:
            raise SatelliteCorrectionInputError(
                "component-prior uncertainty must be finite and positive"
            )


@dataclass(frozen=True, slots=True)
class ReceiverHardwareDriftPrior:
    hardware_epoch_id: str
    reference_utc_ns: int
    mean_hz_s: float
    standard_uncertainty_hz_s: float

    def __post_init__(self) -> None:
        if not self.hardware_epoch_id:
            raise SatelliteCorrectionInputError("hardware-prior identity cannot be empty")
        if (
            isinstance(self.reference_utc_ns, bool)
            or not isinstance(self.reference_utc_ns, int)
            or self.reference_utc_ns <= 0
        ):
            raise SatelliteCorrectionInputError(
                "hardware-prior reference time must be a positive integer"
            )
        if not math.isfinite(self.mean_hz_s):
            raise SatelliteCorrectionInputError("hardware-prior mean must be finite")
        if (
            not math.isfinite(self.standard_uncertainty_hz_s)
            or self.standard_uncertainty_hz_s <= 0.0
        ):
            raise SatelliteCorrectionInputError(
                "hardware-prior uncertainty must be finite and positive"
            )


@dataclass(frozen=True, slots=True)
class JointFrequencyCalibrationConfig:
    satellite_bias_prior_sigma_hz: float = 10_000.0
    satellite_drift_prior_sigma_hz_s: float = 100.0
    minimum_observations_per_satellite: int = 4
    minimum_span_s_per_satellite: float = 1.0
    hardware_drift_random_walk_sigma_hz_s_per_sqrt_s: float | None = None
    maximum_condition_number: float = 1e14
    maximum_mode_observation_evaluations: int = 1_000_000

    def __post_init__(self) -> None:
        positive = (
            self.satellite_bias_prior_sigma_hz,
            self.satellite_drift_prior_sigma_hz_s,
            self.minimum_span_s_per_satellite,
            self.maximum_condition_number,
        )
        if any(not math.isfinite(item) or item <= 0.0 for item in positive):
            raise SatelliteCorrectionInputError(
                "joint frequency calibration scales must be finite and positive"
            )
        if self.hardware_drift_random_walk_sigma_hz_s_per_sqrt_s is not None and (
            not math.isfinite(self.hardware_drift_random_walk_sigma_hz_s_per_sqrt_s)
            or self.hardware_drift_random_walk_sigma_hz_s_per_sqrt_s <= 0.0
        ):
            raise SatelliteCorrectionInputError(
                "hardware-drift random-walk scale must be finite and positive"
            )
        if (
            isinstance(self.minimum_observations_per_satellite, bool)
            or self.minimum_observations_per_satellite < 2
        ):
            raise SatelliteCorrectionInputError(
                "joint frequency calibration needs at least two observations per satellite"
            )
        if (
            isinstance(self.maximum_mode_observation_evaluations, bool)
            or self.maximum_mode_observation_evaluations < 1
        ):
            raise SatelliteCorrectionInputError("joint frequency work cap must be positive")


@dataclass(frozen=True, slots=True)
class JointFrequencyModeDiagnostic:
    association_mode_digest: Sha256Digest
    active_catalog_numbers: tuple[int, ...]
    observation_count: int
    normal_condition_number: float
    minimum_catalogue_observation_count: int
    minimum_catalogue_span_s: float
    calibration_evidence_eligible: bool


@dataclass(frozen=True, slots=True)
class JointFrequencyBatchCalibrationResult:
    association_result_digest: Sha256Digest
    graph_digest: Sha256Digest
    prediction_bank_digest: Sha256Digest
    receiver_frequency_reference_authority_digest: Sha256Digest
    receiver_frequency_gauge_resolved: bool
    frequency_estimates: tuple[JointSatelliteFrequencyCalibrationEstimate, ...]
    mode_diagnostics: tuple[JointFrequencyModeDiagnostic, ...]
    full_joint_state_digest: Sha256Digest
    receiver_local_state_digest: Sha256Digest
    receiver_local_state_exportable: bool
    receiver_drift_model: str
    cross_dwell_random_walk_modeled: bool
    receiver_local_priors_externally_supplied: bool
    known_position_used: bool
    identity_claimed: bool


@dataclass(frozen=True, slots=True)
class _ModeSolve:
    mean: np.ndarray
    covariance: np.ndarray
    condition_number: float
    satellite_dimension: int
    observation_count: int
    minimum_catalogue_observation_count: int
    minimum_catalogue_span_s: float
    full_state_digest: Sha256Digest
    receiver_state_digest: Sha256Digest


def calibrate_joint_satellite_frequency(
    *,
    graph: PhysicalEpisodeGraphV1,
    prediction_bank: CataloguePredictionBankV1,
    association: CatalogueAssociationResultV1,
    component_priors: tuple[ReceiverComponentOffsetPrior, ...],
    hardware_priors: tuple[ReceiverHardwareDriftPrior, ...],
    receiver_frequency_reference_authority_digest: Sha256Digest,
    receiver_frequency_gauge_resolved: bool,
    config: JointFrequencyCalibrationConfig | None = None,
) -> JointFrequencyBatchCalibrationResult:
    """Calibrate every non-null reported association mode on known-position data."""

    graph = PhysicalEpisodeGraphV1.model_validate(graph.model_dump(mode="json"))
    prediction_bank = CataloguePredictionBankV1.model_validate(
        prediction_bank.model_dump(mode="json")
    )
    association = CatalogueAssociationResultV1.model_validate(association.model_dump(mode="json"))
    supplied_config = config or JointFrequencyCalibrationConfig()
    config = JointFrequencyCalibrationConfig(
        satellite_bias_prior_sigma_hz=supplied_config.satellite_bias_prior_sigma_hz,
        satellite_drift_prior_sigma_hz_s=supplied_config.satellite_drift_prior_sigma_hz_s,
        minimum_observations_per_satellite=supplied_config.minimum_observations_per_satellite,
        minimum_span_s_per_satellite=supplied_config.minimum_span_s_per_satellite,
        hardware_drift_random_walk_sigma_hz_s_per_sqrt_s=(
            supplied_config.hardware_drift_random_walk_sigma_hz_s_per_sqrt_s
        ),
        maximum_condition_number=supplied_config.maximum_condition_number,
        maximum_mode_observation_evaluations=(supplied_config.maximum_mode_observation_evaluations),
    )
    component_priors = tuple(
        ReceiverComponentOffsetPrior(
            continuity_component_id=item.continuity_component_id,
            mean_hz=item.mean_hz,
            standard_uncertainty_hz=item.standard_uncertainty_hz,
        )
        for item in component_priors
    )
    hardware_priors = tuple(
        ReceiverHardwareDriftPrior(
            hardware_epoch_id=item.hardware_epoch_id,
            reference_utc_ns=item.reference_utc_ns,
            mean_hz_s=item.mean_hz_s,
            standard_uncertainty_hz_s=item.standard_uncertainty_hz_s,
        )
        for item in hardware_priors
    )
    if not isinstance(receiver_frequency_gauge_resolved, bool):
        raise SatelliteCorrectionInputError("frequency-gauge verdict must be boolean")
    _validate_join(graph=graph, bank=prediction_bank, association=association)
    component_by_id = _exact_component_priors(graph, component_priors)
    hardware_by_id = _exact_hardware_priors(graph, hardware_priors)
    positive_modes = tuple(item for item in association.hypotheses if item.active_catalog_numbers)
    total_work = len(graph.observations) * len(positive_modes)
    if total_work > config.maximum_mode_observation_evaluations:
        raise SatelliteCorrectionInputError(
            "joint frequency calibration exceeds the mode-observation work cap"
        )

    estimates: list[JointSatelliteFrequencyCalibrationEstimate] = []
    diagnostics: list[JointFrequencyModeDiagnostic] = []
    full_state_digests: list[Sha256Digest] = []
    receiver_state_digests: list[Sha256Digest] = []
    for mode in positive_modes:
        mode_digest = canonical_digest(mode.model_dump(mode="json"))
        solve = _solve_mode(
            graph=graph,
            bank=prediction_bank,
            mode=mode,
            component_by_id=component_by_id,
            hardware_by_id=hardware_by_id,
            config=config,
        )
        eligible = (
            receiver_frequency_gauge_resolved
            and solve.minimum_catalogue_observation_count
            >= config.minimum_observations_per_satellite
            and solve.minimum_catalogue_span_s >= config.minimum_span_s_per_satellite
            and not mode.tau_boundary_hit
        )
        reference_utc_ns = _mode_reference_utc_ns(graph=graph, mode=mode)
        satellite_covariance = solve.covariance[
            : solve.satellite_dimension, : solve.satellite_dimension
        ]
        states = tuple(
            SatelliteFrequencyCalibrationEstimate(
                catalog_number=number,
                activity_epoch_id=f"joint-frequency-{number}-{mode_digest[-12:]}",
                scope=SatelliteFrequencyScope.SATELLITE,
                beam_channel_id=None,
                reference_utc_ns=reference_utc_ns,
                bias_hz=float(solve.mean[2 * index]),
                drift_hz_s=float(solve.mean[2 * index + 1]),
                bias_variance_hz2=float(satellite_covariance[2 * index, 2 * index]),
                drift_variance_hz2_s2=float(satellite_covariance[2 * index + 1, 2 * index + 1]),
                bias_drift_covariance_hz2_s=float(satellite_covariance[2 * index, 2 * index + 1]),
                calibration_evidence_eligible=eligible,
            )
            for index, number in enumerate(mode.active_catalog_numbers)
        )
        estimates.append(
            JointSatelliteFrequencyCalibrationEstimate(
                association_mode_digest=mode_digest,
                states=states,
                frequency_covariance=tuple(
                    tuple(float(value) for value in row) for row in satellite_covariance
                ),
                receiver_frequency_gauge_resolved=receiver_frequency_gauge_resolved,
                calibration_evidence_eligible=eligible,
            )
        )
        diagnostics.append(
            JointFrequencyModeDiagnostic(
                association_mode_digest=mode_digest,
                active_catalog_numbers=mode.active_catalog_numbers,
                observation_count=solve.observation_count,
                normal_condition_number=solve.condition_number,
                minimum_catalogue_observation_count=(solve.minimum_catalogue_observation_count),
                minimum_catalogue_span_s=solve.minimum_catalogue_span_s,
                calibration_evidence_eligible=eligible,
            )
        )
        full_state_digests.append(solve.full_state_digest)
        receiver_state_digests.append(solve.receiver_state_digest)

    return JointFrequencyBatchCalibrationResult(
        association_result_digest=association.content_digest,
        graph_digest=graph.content_digest,
        prediction_bank_digest=prediction_bank.content_digest,
        receiver_frequency_reference_authority_digest=(
            receiver_frequency_reference_authority_digest
        ),
        receiver_frequency_gauge_resolved=receiver_frequency_gauge_resolved,
        frequency_estimates=tuple(estimates),
        mode_diagnostics=tuple(diagnostics),
        full_joint_state_digest=canonical_digest(tuple(full_state_digests)),
        receiver_local_state_digest=canonical_digest(tuple(receiver_state_digests)),
        receiver_local_state_exportable=False,
        receiver_drift_model=(
            "dwell-local-hardware-drift-random-walk-v1"
            if config.hardware_drift_random_walk_sigma_hz_s_per_sqrt_s is not None
            else "one-linear-state-per-hardware-epoch-v1"
        ),
        cross_dwell_random_walk_modeled=(
            config.hardware_drift_random_walk_sigma_hz_s_per_sqrt_s is not None
        ),
        receiver_local_priors_externally_supplied=True,
        known_position_used=True,
        identity_claimed=False,
    )


def _solve_mode(
    *,
    graph: PhysicalEpisodeGraphV1,
    bank: CataloguePredictionBankV1,
    mode: CatalogueAssociationModeV1,
    component_by_id: dict[Sha256Digest, ReceiverComponentOffsetPrior],
    hardware_by_id: dict[str, ReceiverHardwareDriftPrior],
    config: JointFrequencyCalibrationConfig,
) -> _ModeSolve:
    assignment_by_episode = {item.episode_id: item.catalog_number for item in mode.assignments}
    episode_by_id = {item.episode_id: item for item in graph.episodes}
    tau_by_catalogue = {item.catalog_number: item.tau_s for item in mode.tau_choices}
    prediction_lookup = {
        (candidate.catalog_number, state.tau_s, prediction.observation_id): prediction
        for candidate in bank.candidates
        for state in candidate.tau_states
        for prediction in state.predictions
    }
    rows = tuple(
        item for item in graph.observations if assignment_by_episode[item.episode_id] is not None
    )
    if not rows:
        raise SatelliteCorrectionInputError("non-null mode has no assigned observations")
    reference_utc_ns = _mode_reference_utc_ns(graph=graph, mode=mode)
    used_components = tuple(
        sorted({episode_by_id[item.episode_id].continuity_component_id for item in rows})
    )
    hardware_state_keys, hardware_references, hardware_prior_covariance = (
        _hardware_drift_state_prior(
            rows=rows,
            episode_by_id=episode_by_id,
            hardware_by_id=hardware_by_id,
            random_walk_sigma=config.hardware_drift_random_walk_sigma_hz_s_per_sqrt_s,
        )
    )
    satellite_count = len(mode.active_catalog_numbers)
    satellite_dimension = 2 * satellite_count
    component_start = satellite_dimension
    hardware_start = component_start + len(used_components)
    dimension = hardware_start + len(hardware_state_keys)
    satellite_index = {item: index for index, item in enumerate(mode.active_catalog_numbers)}
    component_index = {item: index for index, item in enumerate(used_components)}
    hardware_index = {item: index for index, item in enumerate(hardware_state_keys)}
    design = np.zeros((len(rows), dimension), dtype=np.float64)
    residual = np.zeros(len(rows), dtype=np.float64)
    variance = np.zeros(len(rows), dtype=np.float64)
    for row_index, observation in enumerate(rows):
        number = assignment_by_episode[observation.episode_id]
        if number is None:
            raise AssertionError("assigned calibration row unexpectedly became null")
        prediction = prediction_lookup.get(
            (number, tau_by_catalogue[number], observation.observation_id)
        )
        if prediction is None:
            raise SatelliteCorrectionInputError(
                "joint frequency calibration lacks an assigned prediction"
            )
        satellite_column = 2 * satellite_index[number]
        design[row_index, satellite_column] = 1.0
        design[row_index, satellite_column + 1] = (
            observation.support_center_utc_ns - reference_utc_ns
        ) / 1e9
        component_id = episode_by_id[observation.episode_id].continuity_component_id
        design[row_index, component_start + component_index[component_id]] = 1.0
        hardware_key = _hardware_state_key(
            observation.hardware_epoch_id,
            episode_by_id[observation.episode_id].dwell_id,
            random_walk_enabled=(
                config.hardware_drift_random_walk_sigma_hz_s_per_sqrt_s is not None
            ),
        )
        design[row_index, hardware_start + hardware_index[hardware_key]] = (
            observation.support_center_utc_ns - hardware_references[hardware_key]
        ) / 1e9
        residual[row_index] = observation.measured_cfo_hz - prediction.predicted_cfo_hz
        variance[row_index] = (
            observation.standard_uncertainty_hz**2 + prediction.standard_uncertainty_hz**2
        )
    prior_mean = np.zeros(dimension, dtype=np.float64)
    diagonal_prior_variance = np.asarray(
        [
            value
            for _ in mode.active_catalog_numbers
            for value in (
                config.satellite_bias_prior_sigma_hz**2,
                config.satellite_drift_prior_sigma_hz_s**2,
            )
        ]
        + [component_by_id[item].standard_uncertainty_hz ** 2 for item in used_components],
        dtype=np.float64,
    )
    prior_covariance = np.zeros((dimension, dimension), dtype=np.float64)
    prior_covariance[:hardware_start, :hardware_start] = np.diag(diagonal_prior_variance)
    prior_covariance[hardware_start:, hardware_start:] = hardware_prior_covariance
    for index, component_id in enumerate(used_components):
        prior_mean[component_start + index] = component_by_id[component_id].mean_hz
    for index, hardware_key in enumerate(hardware_state_keys):
        prior_mean[hardware_start + index] = hardware_by_id[hardware_key[0]].mean_hz_s
    inverse_variance = 1.0 / variance
    try:
        prior_cholesky = np.linalg.cholesky(prior_covariance)
    except np.linalg.LinAlgError as error:
        raise SatelliteCorrectionNumericalError(
            "joint frequency calibration prior covariance is not positive definite"
        ) from error
    prior_precision = np.linalg.solve(
        prior_cholesky.T,
        np.linalg.solve(prior_cholesky, np.eye(dimension, dtype=np.float64)),
    )
    normal = prior_precision + design.T @ (inverse_variance[:, np.newaxis] * design)
    condition_number = float(np.linalg.cond(normal))
    if not math.isfinite(condition_number) or condition_number > config.maximum_condition_number:
        raise SatelliteCorrectionNumericalError(
            "joint frequency calibration normal matrix is ill-conditioned"
        )
    try:
        cholesky = np.linalg.cholesky(normal)
    except np.linalg.LinAlgError as error:
        raise SatelliteCorrectionNumericalError(
            "joint frequency calibration normal matrix is not positive definite"
        ) from error
    information = prior_precision @ prior_mean + design.T @ (inverse_variance * residual)
    mean = np.linalg.solve(cholesky.T, np.linalg.solve(cholesky, information))
    covariance = np.linalg.solve(
        cholesky.T,
        np.linalg.solve(cholesky, np.eye(dimension, dtype=np.float64)),
    )
    if np.any(~np.isfinite(mean)) or np.any(~np.isfinite(covariance)):
        raise SatelliteCorrectionNumericalError(
            "joint frequency calibration posterior is not finite"
        )
    counts: list[int] = []
    spans: list[float] = []
    for number in mode.active_catalog_numbers:
        times = tuple(
            item.support_center_utc_ns
            for item in rows
            if assignment_by_episode[item.episode_id] == number
        )
        counts.append(len(times))
        spans.append((max(times) - min(times)) / 1e9 if len(times) > 1 else 0.0)
    receiver_mean = mean[satellite_dimension:]
    receiver_covariance = covariance[satellite_dimension:, satellite_dimension:]
    return _ModeSolve(
        mean=mean,
        covariance=covariance,
        condition_number=condition_number,
        satellite_dimension=satellite_dimension,
        observation_count=len(rows),
        minimum_catalogue_observation_count=min(counts),
        minimum_catalogue_span_s=min(spans),
        full_state_digest=canonical_digest(
            {
                "mean": tuple(float(item) for item in mean),
                "covariance": tuple(tuple(float(item) for item in row) for row in covariance),
            }
        ),
        receiver_state_digest=canonical_digest(
            {
                "mean": tuple(float(item) for item in receiver_mean),
                "covariance": tuple(
                    tuple(float(item) for item in row) for row in receiver_covariance
                ),
            }
        ),
    )


def _mode_reference_utc_ns(
    *, graph: PhysicalEpisodeGraphV1, mode: CatalogueAssociationModeV1
) -> int:
    assignment_by_episode = {item.episode_id: item.catalog_number for item in mode.assignments}
    times = tuple(
        item.support_center_utc_ns
        for item in graph.observations
        if assignment_by_episode[item.episode_id] is not None
    )
    if not times:
        raise SatelliteCorrectionInputError("non-null mode has no calibration reference")
    return sum(times) // len(times)


def _hardware_state_key(
    hardware_epoch_id: str,
    dwell_id: Sha256Digest,
    *,
    random_walk_enabled: bool,
) -> tuple[str, Sha256Digest | None]:
    return (hardware_epoch_id, dwell_id if random_walk_enabled else None)


def _hardware_drift_state_prior(
    *,
    rows: tuple[SupportIntegratedCfoObservationV1, ...],
    episode_by_id: dict[Sha256Digest, PhysicalCfoEpisodeV1],
    hardware_by_id: dict[str, ReceiverHardwareDriftPrior],
    random_walk_sigma: float | None,
) -> tuple[
    tuple[tuple[str, Sha256Digest | None], ...],
    dict[tuple[str, Sha256Digest | None], int],
    np.ndarray,
]:
    random_walk_enabled = random_walk_sigma is not None
    rows_by_key: dict[tuple[str, Sha256Digest | None], list[SupportIntegratedCfoObservationV1]] = {}
    for row in rows:
        key = _hardware_state_key(
            row.hardware_epoch_id,
            episode_by_id[row.episode_id].dwell_id,
            random_walk_enabled=random_walk_enabled,
        )
        rows_by_key.setdefault(key, []).append(row)
    references = {
        key: sum(item.support_center_utc_ns for item in group) // len(group)
        if random_walk_enabled
        else hardware_by_id[key[0]].reference_utc_ns
        for key, group in rows_by_key.items()
    }
    keys = tuple(sorted(rows_by_key, key=lambda item: (item[0], references[item], item[1] or "")))
    covariance = np.zeros((len(keys), len(keys)), dtype=np.float64)
    index = {key: offset for offset, key in enumerate(keys)}
    for hardware_id in sorted({item[0] for item in keys}):
        group = tuple(item for item in keys if item[0] == hardware_id)
        initial_variance = hardware_by_id[hardware_id].standard_uncertainty_hz_s ** 2
        first_reference = min(references[item] for item in group)
        for left in group:
            for right in group:
                process_variance = 0.0
                if random_walk_sigma is not None:
                    elapsed_s = (min(references[left], references[right]) - first_reference) / 1e9
                    if elapsed_s < 0.0:
                        raise SatelliteCorrectionNumericalError(
                            "hardware random-walk chronology is invalid"
                        )
                    process_variance = random_walk_sigma**2 * elapsed_s
                covariance[index[left], index[right]] = initial_variance + process_variance
    return keys, references, covariance


def _exact_component_priors(
    graph: PhysicalEpisodeGraphV1,
    priors: tuple[ReceiverComponentOffsetPrior, ...],
) -> dict[Sha256Digest, ReceiverComponentOffsetPrior]:
    by_id = {item.continuity_component_id: item for item in priors}
    if len(by_id) != len(priors):
        raise SatelliteCorrectionInputError("component calibration prior repeats an identity")
    expected = {item.continuity_component_id for item in graph.episodes}
    if set(by_id) != expected:
        raise SatelliteCorrectionInputError(
            "component calibration priors must exactly cover the graph"
        )
    return by_id


def _exact_hardware_priors(
    graph: PhysicalEpisodeGraphV1,
    priors: tuple[ReceiverHardwareDriftPrior, ...],
) -> dict[str, ReceiverHardwareDriftPrior]:
    by_id = {item.hardware_epoch_id: item for item in priors}
    if len(by_id) != len(priors):
        raise SatelliteCorrectionInputError("hardware calibration prior repeats an identity")
    expected = {item.hardware_epoch_id for item in graph.observations}
    if set(by_id) != expected:
        raise SatelliteCorrectionInputError(
            "hardware calibration priors must exactly cover the graph"
        )
    return by_id


def _validate_join(
    *,
    graph: PhysicalEpisodeGraphV1,
    bank: CataloguePredictionBankV1,
    association: CatalogueAssociationResultV1,
) -> None:
    if association.graph_digest != graph.content_digest:
        raise SatelliteCorrectionInputError("frequency calibration association graph is stale")
    if association.prediction_bank_digest != bank.content_digest:
        raise SatelliteCorrectionInputError("frequency calibration prediction bank is stale")
    if bank.support.content_digest != CataloguePredictionSupportV1.from_graph(graph).content_digest:
        raise SatelliteCorrectionInputError("frequency calibration bank support is stale")
    if association.unreported_hypothesis_count != 0:
        raise SatelliteCorrectionInputError(
            "joint frequency calibration requires every association mode"
        )
