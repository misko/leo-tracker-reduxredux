"""Exact small-bank catalogue association with marginalized radio nuisance state.

This module is a pure analyzer.  It performs no storage, TLE, HTTP, CLI, or IQ
access.  The caller supplies a TLE-blind physical episode graph and a complete,
response-free prediction bank.  It enumerates K=0,1,2 hypotheses exactly and
integrates the same proper Gaussian nuisance model for every hypothesis.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

import numpy as np

from leo.contracts.catalogue_association import (
    ActiveCountPosteriorV1,
    CatalogueAssociationConfigV1,
    CatalogueAssociationModeV1,
    CatalogueAssociationResultV1,
    CatalogueCandidatePredictionV1,
    CataloguePredictionBankV1,
    CataloguePredictionSupportObservationV1,
    CataloguePredictionSupportV1,
    CataloguePresencePosteriorV1,
    CatalogueTauChoiceV1,
    ComponentOffsetEstimateV1,
    EpisodeAssignmentPosteriorV1,
    EpisodeAssignmentProbabilityV1,
    EpisodeCatalogueAssignmentV1,
    HardwareDriftEstimateV1,
    PhysicalCfoEpisodeV1,
    PhysicalEpisodeGraphV1,
    SupportIntegratedCfoObservationV1,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.sky import DopplerPolynomialV1
from leo.contracts.standard_pipeline import StandardScientificStatus

type Assignment = tuple[int | None, ...]


class HypothesisSearchLimitError(ValueError):
    """The exact hypothesis family exceeds its predeclared work bound."""


class AssociationNumericalError(ValueError):
    """The conjugate Gaussian nuisance solve is not numerically trustworthy."""


def support_integrated_doppler_hz(
    observation: CataloguePredictionSupportObservationV1,
    polynomial: DopplerPolynomialV1,
) -> float:
    """Integrate one cubic-or-lower Doppler model over the observation support.

    ``factorial_support_moments_s`` are the weighted moments around the
    persisted support centre: ``(1, E[u], E[u**2]/2, E[u**3]/6)``.  Evaluating
    the derivative expansion at that centre avoids the approximately
    ``rate * aperture/2`` bias caused by timestamping a window average at its
    start.
    """

    center_offset_s = (observation.support_center_utc_ns - polynomial.reference_utc_ns) / 1e9
    moment_zero, moment_one, moment_two, moment_three = observation.factorial_support_moments_s
    value_at_center = (
        polynomial.frequency_at_reference_hz
        + polynomial.slope_hz_s * center_offset_s
        + polynomial.acceleration_hz_s2 * center_offset_s**2 / 2.0
        + polynomial.jerk_hz_s3 * center_offset_s**3 / 6.0
    )
    slope_at_center = (
        polynomial.slope_hz_s
        + polynomial.acceleration_hz_s2 * center_offset_s
        + polynomial.jerk_hz_s3 * center_offset_s**2 / 2.0
    )
    acceleration_at_center = polynomial.acceleration_hz_s2 + polynomial.jerk_hz_s3 * center_offset_s
    integrated = (
        value_at_center * moment_zero
        + slope_at_center * moment_one
        + acceleration_at_center * moment_two
        + polynomial.jerk_hz_s3 * moment_three
    )
    if not math.isfinite(integrated):
        raise AssociationNumericalError("support-integrated Doppler is not finite")
    return integrated


@dataclass(frozen=True, slots=True)
class _NuisanceLayout:
    design: np.ndarray
    prior_variances: np.ndarray
    component_ids: tuple[str, ...]
    hardware_ids: tuple[str, ...]
    hardware_reference_utc_ns: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _Evidence:
    negative_log_evidence: float
    posterior_mean: np.ndarray
    posterior_covariance: np.ndarray


@dataclass(frozen=True, slots=True)
class _RawMode:
    active_catalog_numbers: tuple[int, ...]
    assignment: Assignment
    tau_values: tuple[float, ...]
    data_negative_log_evidence: float
    active_count_negative_log_prior: float
    active_set_negative_log_prior: float
    assignment_negative_log_prior: float
    tau_negative_log_prior: float
    total_negative_log_joint: float
    nuisance_mean: np.ndarray
    nuisance_covariance: np.ndarray
    handoff_count: int


def associate_catalogue_hypotheses(
    graph: PhysicalEpisodeGraphV1,
    prediction_bank: CataloguePredictionBankV1,
    *,
    config: CatalogueAssociationConfigV1,
) -> CatalogueAssociationResultV1:
    """Enumerate and normalize the complete bounded K=0,1,2 hypothesis family."""

    expected_support = CataloguePredictionSupportV1.from_graph(graph)
    if prediction_bank.support.content_digest != expected_support.content_digest:
        raise ValueError("prediction bank does not bind the supplied response-free support")
    if prediction_bank.truncated_candidate_count != 0:
        raise ValueError("exact association rejects a truncated candidate bank")
    if prediction_bank.response_accessed:
        raise ValueError("candidate prediction bank must remain response-free")

    episode_ids = tuple(item.episode_id for item in graph.episodes)
    observation_by_id = {item.observation_id: item for item in graph.observations}
    observations_by_episode = {
        episode.episode_id: tuple(observation_by_id[item] for item in episode.observation_ids)
        for episode in graph.episodes
    }
    _validate_prediction_coverage(
        graph=graph,
        prediction_bank=prediction_bank,
        observations_by_episode=observations_by_episode,
    )

    candidate_by_number = {item.catalog_number: item for item in prediction_bank.candidates}
    candidate_numbers = tuple(candidate_by_number)
    maximum_active = min(config.maximum_active_satellites, len(candidate_numbers))
    active_set_count = sum(
        math.comb(len(candidate_numbers), active_count)
        for active_count in range(maximum_active + 1)
    )
    if active_set_count > config.maximum_evaluated_hypotheses:
        raise HypothesisSearchLimitError(
            "exact active-set inventory exceeds the configured limit "
            f"({active_set_count} > {config.maximum_evaluated_hypotheses})"
        )
    assignments_by_active_set: dict[tuple[int, ...], tuple[Assignment, ...]] = {}
    assignment_log_probabilities: dict[tuple[int, ...], tuple[float, ...]] = {}
    exact_mode_count = 0
    enumeration_upper_bound = 0
    for active_set in _iter_active_sets(candidate_numbers, maximum_active):
        tau_product = math.prod(
            len(candidate_by_number[number].tau_states) for number in active_set
        )
        assignment_upper_bound = _bounded_integer_power(
            len(active_set) + 1,
            len(graph.episodes),
            config.maximum_evaluated_hypotheses,
        )
        enumeration_upper_bound += assignment_upper_bound * tau_product
        if enumeration_upper_bound > config.maximum_evaluated_hypotheses:
            raise HypothesisSearchLimitError(
                "conservative exact association enumeration bound exceeds the configured "
                f"limit {config.maximum_evaluated_hypotheses}"
            )
    for active_set in _iter_active_sets(candidate_numbers, maximum_active):
        assignments = _feasible_assignments(
            graph=graph,
            active_set=active_set,
            candidate_by_number=candidate_by_number,
        )
        if not assignments:
            continue
        raw_assignment_weights = tuple(
            _assignment_log_weight(graph=graph, assignment=item, config=config)[0]
            for item in assignments
        )
        normalized_assignment_weights = _normalized_log_weights(raw_assignment_weights)
        assignments_by_active_set[active_set] = assignments
        assignment_log_probabilities[active_set] = normalized_assignment_weights
        tau_product = math.prod(
            len(candidate_by_number[number].tau_states) for number in active_set
        )
        exact_mode_count += len(assignments) * tau_product
        if exact_mode_count > config.maximum_evaluated_hypotheses:
            raise HypothesisSearchLimitError(
                "exact association requires "
                f"{exact_mode_count} hypotheses, exceeding the configured "
                f"limit {config.maximum_evaluated_hypotheses}"
            )
    if exact_mode_count == 0:
        raise ValueError("association has no feasible hypotheses")
    feasible_active_set_counts = {
        active_count: sum(
            len(active_set) == active_count for active_set in assignments_by_active_set
        )
        for active_count in range(maximum_active + 1)
    }
    feasible_active_counts = tuple(
        active_count for active_count, count in feasible_active_set_counts.items() if count > 0
    )
    normalized_count_weights = _normalized_log_weights(
        tuple(config.active_count_log_weights[item] for item in feasible_active_counts)
    )
    active_count_log_probabilities = dict(
        zip(feasible_active_counts, normalized_count_weights, strict=True)
    )

    observation_order = tuple(graph.observations)
    observation_index = {item.observation_id: index for index, item in enumerate(observation_order)}
    measured = np.asarray([item.measured_cfo_hz for item in observation_order], dtype=np.float64)
    base_variance = np.square(
        np.asarray(
            [item.standard_uncertainty_hz for item in observation_order],
            dtype=np.float64,
        )
    )
    layout = _nuisance_layout(graph=graph, config=config)
    prediction_lookup = _prediction_lookup(prediction_bank)

    raw_modes: list[_RawMode] = []
    for active_set, assignments in assignments_by_active_set.items():
        active_count = len(active_set)
        log_active_count = active_count_log_probabilities[active_count]
        log_active_set = -math.log(feasible_active_set_counts[active_count])
        tau_states_by_catalogue = tuple(
            candidate_by_number[number].tau_states for number in active_set
        )
        tau_log_probabilities = tuple(
            _normalized_log_weights(tuple(item.log_prior_weight for item in states))
            for states in tau_states_by_catalogue
        )
        tau_index_products = (
            tuple(itertools.product(*(range(len(states)) for states in tau_states_by_catalogue)))
            if active_set
            else ((),)
        )
        for assignment_position, assignment in enumerate(assignments):
            log_assignment = assignment_log_probabilities[active_set][assignment_position]
            _, handoff_count = _assignment_log_weight(
                graph=graph,
                assignment=assignment,
                config=config,
            )
            for tau_indices in tau_index_products:
                tau_values = tuple(
                    tau_states_by_catalogue[index][tau_index].tau_s
                    for index, tau_index in enumerate(tau_indices)
                )
                log_tau = sum(
                    tau_log_probabilities[index][tau_index]
                    for index, tau_index in enumerate(tau_indices)
                )
                predicted = np.zeros(measured.shape, dtype=np.float64)
                prediction_variance = np.zeros(measured.shape, dtype=np.float64)
                tau_by_catalogue = dict(zip(active_set, tau_values, strict=True))
                for episode_position, catalog_number in enumerate(assignment):
                    if catalog_number is None:
                        continue
                    episode_id = episode_ids[episode_position]
                    tau_s = tau_by_catalogue[catalog_number]
                    for observation in observations_by_episode[episode_id]:
                        row = observation_index[observation.observation_id]
                        mean_hz, sigma_hz = prediction_lookup[
                            catalog_number,
                            tau_s,
                            observation.observation_id,
                        ]
                        predicted[row] = mean_hz
                        prediction_variance[row] = sigma_hz**2
                evidence = _marginal_evidence(
                    residual=measured - predicted,
                    variance=base_variance + prediction_variance,
                    layout=layout,
                    maximum_condition_number=config.maximum_normal_condition_number,
                )
                total_negative_log_joint = (
                    evidence.negative_log_evidence
                    - log_active_count
                    - log_active_set
                    - log_assignment
                    - log_tau
                )
                raw_modes.append(
                    _RawMode(
                        active_catalog_numbers=active_set,
                        assignment=assignment,
                        tau_values=tau_values,
                        data_negative_log_evidence=evidence.negative_log_evidence,
                        active_count_negative_log_prior=-log_active_count,
                        active_set_negative_log_prior=-log_active_set,
                        assignment_negative_log_prior=-log_assignment,
                        tau_negative_log_prior=-log_tau,
                        total_negative_log_joint=total_negative_log_joint,
                        nuisance_mean=evidence.posterior_mean,
                        nuisance_covariance=evidence.posterior_covariance,
                        handoff_count=handoff_count,
                    )
                )
    if len(raw_modes) != exact_mode_count:
        raise AssertionError("internal exact-mode accounting mismatch")

    ordered_raw_modes = tuple(sorted(raw_modes, key=_mode_sort_key))
    log_joints = np.asarray(
        [-item.total_negative_log_joint for item in ordered_raw_modes], dtype=np.float64
    )
    maximum_log_joint = float(np.max(log_joints))
    relative_weights = np.exp(log_joints - maximum_log_joint)
    log_normalizer = maximum_log_joint + math.log(float(np.sum(relative_weights)))
    log_probabilities = log_joints - log_normalizer
    probabilities = np.exp(log_probabilities)
    probabilities[0] += 1.0 - float(np.sum(probabilities))

    reported_count = min(config.reported_hypothesis_limit, exact_mode_count)
    reported_modes = tuple(
        _public_mode(
            raw_mode=ordered_raw_modes[index],
            rank=index + 1,
            log_posterior_probability=float(log_probabilities[index]),
            posterior_probability=float(probabilities[index]),
            graph=graph,
            layout=layout,
        )
        for index in range(reported_count)
    )
    reported_mass = _roundoff_probability(float(np.sum(probabilities[:reported_count])))
    active_count_posterior = _active_count_posterior(
        ordered_raw_modes, probabilities, maximum_active
    )
    catalogue_presence_posterior = _catalogue_presence_posterior(
        ordered_raw_modes, probabilities, candidate_numbers
    )
    episode_assignment_posterior = _episode_assignment_posterior(
        ordered_raw_modes,
        probabilities,
        episode_ids,
        candidate_numbers,
    )
    tau_boundary_abstention = reported_modes[0].tau_boundary_hit

    payload = {
        "schema_version": 1,
        "algorithm_version": "rao-blackwellized-exact-k012-v1",
        "graph_digest": graph.content_digest,
        "prediction_bank_digest": prediction_bank.content_digest,
        "candidate_universe_digest": prediction_bank.candidate_universe_digest,
        "selection_protocol_digest": prediction_bank.selection_protocol_digest,
        "tle_membership_authority_digest": (prediction_bank.tle_membership_authority_digest),
        "tau_search_policy": prediction_bank.tau_search_policy,
        "config_digest": config.digest,
        "observation_error_model": graph.observation_error_model,
        "prediction_error_model": prediction_bank.prediction_error_model,
        "null_model": config.null_model,
        "evaluated_hypothesis_count": exact_mode_count,
        "reported_hypothesis_count": reported_count,
        "unreported_hypothesis_count": exact_mode_count - reported_count,
        "reported_posterior_mass": reported_mass,
        "unreported_posterior_mass": 1.0 - reported_mass,
        "hypotheses": [item.model_dump(mode="json") for item in reported_modes],
        "active_count_posterior": [item.model_dump(mode="json") for item in active_count_posterior],
        "catalogue_presence_posterior": [
            item.model_dump(mode="json") for item in catalogue_presence_posterior
        ],
        "episode_assignment_posterior": [
            item.model_dump(mode="json") for item in episode_assignment_posterior
        ],
        "status": (
            StandardScientificStatus.PARTIAL
            if tau_boundary_abstention
            else StandardScientificStatus.COMPLETE
        ),
        "reason": (
            "exact bounded hypothesis family completed, but the rank-one tau reached the "
            "fixed [-5,+5] second boundary; abstain without widening"
            if tau_boundary_abstention
            else "complete exact bounded hypothesis family; posterior is model-conditional "
            "candidate evidence within the frozen response-free universe, not a satellite "
            "identity claim"
        ),
        "tau_boundary_abstention": tau_boundary_abstention,
        "search_complete": True,
        "candidate_only": True,
        "universe_conditional": True,
        "identity_claimed": False,
        "navigation_fix_claimed": False,
    }
    return CatalogueAssociationResultV1.model_validate(
        {**payload, "content_digest": canonical_digest(payload)}
    )


def _validate_prediction_coverage(
    *,
    graph: PhysicalEpisodeGraphV1,
    prediction_bank: CataloguePredictionBankV1,
    observations_by_episode: dict[str, tuple[SupportIntegratedCfoObservationV1, ...]],
) -> None:
    episode_ids = {item.episode_id for item in graph.episodes}
    for candidate in prediction_bank.candidates:
        eligible = set(candidate.eligible_episode_ids)
        if not eligible <= episode_ids:
            raise ValueError("candidate bank names an unknown eligible episode")
        expected_observations = tuple(
            sorted(
                observation.observation_id
                for episode_id in eligible
                for observation in observations_by_episode[episode_id]
            )
        )
        for state in candidate.tau_states:
            actual = tuple(item.observation_id for item in state.predictions)
            if actual != expected_observations:
                raise ValueError(
                    "candidate tau prediction inventory does not exactly cover eligible episodes"
                )


def _normalized_log_weights(values: tuple[float, ...]) -> tuple[float, ...]:
    if not values:
        raise ValueError("cannot normalize an empty log-weight inventory")
    maximum = max(values)
    normalizer = maximum + math.log(sum(math.exp(item - maximum) for item in values))
    return tuple(item - normalizer for item in values)


def _iter_active_sets(
    candidate_numbers: tuple[int, ...], maximum_active: int
) -> Iterator[tuple[int, ...]]:
    return itertools.chain.from_iterable(
        itertools.combinations(candidate_numbers, active_count)
        for active_count in range(maximum_active + 1)
    )


def _bounded_integer_power(base: int, exponent: int, limit: int) -> int:
    result = 1
    for _ in range(exponent):
        if result > limit // base:
            return limit + 1
        result *= base
    return result


def _feasible_assignments(
    *,
    graph: PhysicalEpisodeGraphV1,
    active_set: tuple[int, ...],
    candidate_by_number: Mapping[int, CatalogueCandidatePredictionV1],
) -> tuple[Assignment, ...]:
    choices: tuple[int | None, ...] = (None, *active_set)
    result: list[Assignment] = []
    eligible_by_candidate = {
        number: set(candidate_by_number[number].eligible_episode_ids) for number in active_set
    }
    replica_positions: dict[str, list[int]] = {}
    exclusion_positions: dict[str, list[int]] = {}
    for index, episode in enumerate(graph.episodes):
        if episode.replica_group_id is not None:
            replica_positions.setdefault(episode.replica_group_id, []).append(index)
        for group_id in episode.exclusion_group_ids:
            exclusion_positions.setdefault(group_id, []).append(index)
    for assignment in itertools.product(choices, repeat=len(graph.episodes)):
        if set(item for item in assignment if item is not None) != set(active_set):
            continue
        if any(
            catalog_number is not None
            and episode.episode_id not in eligible_by_candidate[catalog_number]
            for episode, catalog_number in zip(graph.episodes, assignment, strict=True)
        ):
            continue
        if any(
            len({assignment[index] for index in positions}) != 1
            for positions in replica_positions.values()
        ):
            continue
        exclusion_conflict = False
        for positions in exclusion_positions.values():
            non_null = [assignment[index] for index in positions if assignment[index] is not None]
            if len(non_null) != len(set(non_null)):
                exclusion_conflict = True
                break
        if exclusion_conflict:
            continue
        result.append(assignment)
    return tuple(result)


def _assignment_log_weight(
    *,
    graph: PhysicalEpisodeGraphV1,
    assignment: Assignment,
    config: CatalogueAssociationConfigV1,
) -> tuple[float, int]:
    assigned_count = sum(item is not None for item in assignment)
    unassigned_count = len(assignment) - assigned_count
    assignment_by_episode = {
        episode.episode_id: assignment[index] for index, episode in enumerate(graph.episodes)
    }
    same_count = 0
    handoff_count = 0
    lanes: dict[str, list[PhysicalCfoEpisodeV1]] = {}
    for episode in graph.episodes:
        lanes.setdefault(episode.lane_id, []).append(episode)
    for lane in lanes.values():
        ordered = sorted(lane, key=lambda item: (item.order_index, item.episode_id))
        for left, right in zip(ordered, ordered[1:], strict=False):
            if assignment_by_episode[left.episode_id] == assignment_by_episode[right.episode_id]:
                same_count += 1
            else:
                handoff_count += 1
    return (
        assigned_count * config.assigned_episode_log_weight
        + unassigned_count * config.unassigned_episode_log_weight
        + same_count * config.same_state_log_weight
        + handoff_count * config.handoff_log_weight,
        handoff_count,
    )


def _nuisance_layout(
    *, graph: PhysicalEpisodeGraphV1, config: CatalogueAssociationConfigV1
) -> _NuisanceLayout:
    episode_by_id = {item.episode_id: item for item in graph.episodes}
    component_ids = tuple(sorted({item.continuity_component_id for item in graph.episodes}))
    hardware_ids = tuple(sorted({item.hardware_epoch_id for item in graph.observations}))
    component_index = {item: index for index, item in enumerate(component_ids)}
    hardware_index = {item: index for index, item in enumerate(hardware_ids)}
    hardware_reference_utc_ns = tuple(
        sum(
            item.support_center_utc_ns
            for item in graph.observations
            if item.hardware_epoch_id == hardware_id
        )
        // sum(1 for item in graph.observations if item.hardware_epoch_id == hardware_id)
        for hardware_id in hardware_ids
    )
    reference_by_hardware = dict(zip(hardware_ids, hardware_reference_utc_ns, strict=True))
    design = np.zeros(
        (len(graph.observations), len(component_ids) + len(hardware_ids)),
        dtype=np.float64,
    )
    for row, observation in enumerate(graph.observations):
        episode = episode_by_id[observation.episode_id]
        design[row, component_index[episode.continuity_component_id]] = 1.0
        drift_column = len(component_ids) + hardware_index[observation.hardware_epoch_id]
        design[row, drift_column] = (
            observation.support_center_utc_ns - reference_by_hardware[observation.hardware_epoch_id]
        ) / 1e9
    prior_variances = np.asarray(
        [config.component_offset_prior_sigma_hz**2] * len(component_ids)
        + [config.hardware_drift_prior_sigma_hz_per_s**2] * len(hardware_ids),
        dtype=np.float64,
    )
    return _NuisanceLayout(
        design=design,
        prior_variances=prior_variances,
        component_ids=component_ids,
        hardware_ids=hardware_ids,
        hardware_reference_utc_ns=hardware_reference_utc_ns,
    )


def _prediction_lookup(
    bank: CataloguePredictionBankV1,
) -> dict[tuple[int, float, str], tuple[float, float]]:
    return {
        (candidate.catalog_number, state.tau_s, prediction.observation_id): (
            prediction.predicted_cfo_hz,
            prediction.standard_uncertainty_hz,
        )
        for candidate in bank.candidates
        for state in candidate.tau_states
        for prediction in state.predictions
    }


def _marginal_evidence(
    *,
    residual: np.ndarray,
    variance: np.ndarray,
    layout: _NuisanceLayout,
    maximum_condition_number: float,
) -> _Evidence:
    if (
        residual.ndim != 1
        or variance.shape != residual.shape
        or layout.design.shape[0] != residual.size
        or np.any(~np.isfinite(residual))
        or np.any(~np.isfinite(variance))
        or np.any(variance <= 0)
    ):
        raise AssociationNumericalError("association residual covariance is invalid")
    inverse_variance = 1.0 / variance
    prior_precision = 1.0 / layout.prior_variances
    normal = np.diag(prior_precision) + layout.design.T @ (
        inverse_variance[:, np.newaxis] * layout.design
    )
    condition_number = float(np.linalg.cond(normal))
    if not math.isfinite(condition_number) or condition_number > maximum_condition_number:
        raise AssociationNumericalError(
            "association nuisance normal matrix exceeds the configured condition bound"
        )
    try:
        cholesky = np.linalg.cholesky(normal)
    except np.linalg.LinAlgError as error:
        raise AssociationNumericalError(
            "association nuisance normal matrix is not positive definite"
        ) from error
    information = layout.design.T @ (inverse_variance * residual)
    posterior_mean = np.linalg.solve(cholesky.T, np.linalg.solve(cholesky, information))
    identity = np.eye(normal.shape[0], dtype=np.float64)
    posterior_covariance = np.linalg.solve(
        cholesky.T,
        np.linalg.solve(cholesky, identity),
    )
    posterior_residual = residual - layout.design @ posterior_mean
    quadratic = float(
        posterior_residual @ (inverse_variance * posterior_residual)
        + posterior_mean @ (prior_precision * posterior_mean)
    )
    log_determinant_r = float(np.sum(np.log(variance)))
    log_determinant_p = float(np.sum(np.log(layout.prior_variances)))
    log_determinant_normal = float(2.0 * np.sum(np.log(np.diag(cholesky))))
    negative_log_evidence = 0.5 * (
        quadratic
        + log_determinant_r
        + log_determinant_p
        + log_determinant_normal
        + residual.size * math.log(2.0 * math.pi)
    )
    if not math.isfinite(negative_log_evidence):
        raise AssociationNumericalError("association marginal evidence is not finite")
    return _Evidence(
        negative_log_evidence=negative_log_evidence,
        posterior_mean=posterior_mean,
        posterior_covariance=posterior_covariance,
    )


def _mode_sort_key(mode: _RawMode) -> tuple[object, ...]:
    assignment_key = tuple(-1 if item is None else item for item in mode.assignment)
    assigned_count = sum(item is not None for item in mode.assignment)
    return (
        mode.total_negative_log_joint,
        len(mode.active_catalog_numbers),
        mode.handoff_count,
        assigned_count,
        mode.active_catalog_numbers,
        assignment_key,
        sum(abs(item) for item in mode.tau_values),
        mode.tau_values,
    )


def _public_mode(
    *,
    raw_mode: _RawMode,
    rank: int,
    log_posterior_probability: float,
    posterior_probability: float,
    graph: PhysicalEpisodeGraphV1,
    layout: _NuisanceLayout,
) -> CatalogueAssociationModeV1:
    component_count = len(layout.component_ids)
    return CatalogueAssociationModeV1(
        rank=rank,
        active_catalog_numbers=raw_mode.active_catalog_numbers,
        assignments=tuple(
            EpisodeCatalogueAssignmentV1(
                episode_id=episode.episode_id,
                catalog_number=raw_mode.assignment[index],
            )
            for index, episode in enumerate(graph.episodes)
        ),
        tau_choices=tuple(
            CatalogueTauChoiceV1(catalog_number=number, tau_s=tau_s)
            for number, tau_s in zip(
                raw_mode.active_catalog_numbers,
                raw_mode.tau_values,
                strict=True,
            )
        ),
        data_negative_log_evidence=raw_mode.data_negative_log_evidence,
        active_count_negative_log_prior=raw_mode.active_count_negative_log_prior,
        active_set_negative_log_prior=raw_mode.active_set_negative_log_prior,
        assignment_negative_log_prior=raw_mode.assignment_negative_log_prior,
        tau_negative_log_prior=raw_mode.tau_negative_log_prior,
        total_negative_log_joint=raw_mode.total_negative_log_joint,
        log_posterior_probability=log_posterior_probability,
        posterior_probability=posterior_probability,
        component_offsets=tuple(
            ComponentOffsetEstimateV1(
                continuity_component_id=component_id,
                mean_hz=float(raw_mode.nuisance_mean[index]),
                standard_uncertainty_hz=math.sqrt(
                    max(0.0, float(raw_mode.nuisance_covariance[index, index]))
                ),
            )
            for index, component_id in enumerate(layout.component_ids)
        ),
        hardware_drifts=tuple(
            HardwareDriftEstimateV1(
                hardware_epoch_id=hardware_id,
                reference_utc_ns=layout.hardware_reference_utc_ns[index],
                mean_hz_per_s=float(raw_mode.nuisance_mean[component_count + index]),
                standard_uncertainty_hz_per_s=math.sqrt(
                    max(
                        0.0,
                        float(
                            raw_mode.nuisance_covariance[
                                component_count + index,
                                component_count + index,
                            ]
                        ),
                    )
                ),
            )
            for index, hardware_id in enumerate(layout.hardware_ids)
        ),
        handoff_count=raw_mode.handoff_count,
        tau_boundary_hit=any(
            math.isclose(abs(item), 5.0, rel_tol=0.0, abs_tol=1e-12) for item in raw_mode.tau_values
        ),
    )


def _normalized_distribution(values: list[float]) -> list[float]:
    total = sum(values)
    if total <= 0 or not math.isfinite(total):
        raise AssociationNumericalError("posterior aggregation has invalid mass")
    normalized = [item / total for item in values]
    normalized[-1] += 1.0 - sum(normalized)
    return normalized


def _roundoff_probability(value: float) -> float:
    if not math.isfinite(value) or value < -1e-12 or value > 1.0 + 1e-12:
        raise AssociationNumericalError("posterior probability escaped its numerical bounds")
    return min(1.0, max(0.0, value))


def _active_count_posterior(
    modes: tuple[_RawMode, ...], probabilities: np.ndarray, maximum_active: int
) -> tuple[ActiveCountPosteriorV1, ...]:
    values = [
        float(
            sum(
                probability
                for mode, probability in zip(modes, probabilities, strict=True)
                if len(mode.active_catalog_numbers) == active_count
            )
        )
        for active_count in range(maximum_active + 1)
    ]
    values = _normalized_distribution(values)
    return tuple(
        ActiveCountPosteriorV1(
            active_count=active_count,
            posterior_probability=values[active_count],
        )
        for active_count in range(maximum_active + 1)
    )


def _catalogue_presence_posterior(
    modes: tuple[_RawMode, ...],
    probabilities: np.ndarray,
    candidate_numbers: tuple[int, ...],
) -> tuple[CataloguePresencePosteriorV1, ...]:
    return tuple(
        CataloguePresencePosteriorV1(
            catalog_number=catalog_number,
            posterior_probability=_roundoff_probability(
                float(
                    sum(
                        probability
                        for mode, probability in zip(modes, probabilities, strict=True)
                        if catalog_number in mode.active_catalog_numbers
                    )
                )
            ),
        )
        for catalog_number in candidate_numbers
    )


def _episode_assignment_posterior(
    modes: tuple[_RawMode, ...],
    probabilities: np.ndarray,
    episode_ids: tuple[str, ...],
    candidate_numbers: tuple[int, ...],
) -> tuple[EpisodeAssignmentPosteriorV1, ...]:
    result = []
    for episode_index, episode_id in enumerate(episode_ids):
        values = [
            float(
                sum(
                    probability
                    for mode, probability in zip(modes, probabilities, strict=True)
                    if mode.assignment[episode_index] is None
                )
            )
        ] + [
            float(
                sum(
                    probability
                    for mode, probability in zip(modes, probabilities, strict=True)
                    if mode.assignment[episode_index] == catalog_number
                )
            )
            for catalog_number in candidate_numbers
        ]
        values = _normalized_distribution(values)
        result.append(
            EpisodeAssignmentPosteriorV1(
                episode_id=episode_id,
                unassigned_probability=values[0],
                catalogue_probabilities=tuple(
                    EpisodeAssignmentProbabilityV1(
                        catalog_number=catalog_number,
                        posterior_probability=values[index + 1],
                    )
                    for index, catalog_number in enumerate(candidate_numbers)
                ),
            )
        )
    return tuple(result)


__all__ = [
    "AssociationNumericalError",
    "HypothesisSearchLimitError",
    "associate_catalogue_hypotheses",
    "support_integrated_doppler_hz",
]
