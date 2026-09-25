"""Pure research primitives for persistent satellite-activity association.

The first prototype slice deliberately stops before catalogue access and
multi-satellite optimization.  Callers provide per-probe CFO candidates and a
sampled Doppler hypothesis.  This module supplies:

* a solver-neutral, explicitly accounted problem representation;
* an independent objective and feasibility checker;
* an exact single-satellite semi-Markov decoder;
* a robust delay/CFO-offset profile; and
* a deterministic synthetic problem generator.

Only activity is quantized into coarse cells.  CFO evidence remains at its
native probe cadence, including usable probes with no retained candidates so
that an active-but-missed transmission has an explicit cost.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from numbers import Integral

import numpy as np
import numpy.typing as npt


def _nonempty(value: str, label: str) -> None:
    if not value:
        raise ValueError(f"{label} must not be empty")


def _finite(value: float, label: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")


def _nonnegative(value: float, label: str) -> None:
    _finite(value, label)
    if value < 0.0:
        raise ValueError(f"{label} must be nonnegative")


def _positive(value: float, label: str) -> None:
    _finite(value, label)
    if value <= 0.0:
        raise ValueError(f"{label} must be positive")


def _integer_at_least(value: object, minimum: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < minimum:
        raise ValueError(f"{label} must be an integer greater than or equal to {minimum}")


@dataclass(frozen=True, slots=True)
class ActivityGrid:
    """Half-open coarse cells on which latent transmission activity changes."""

    start_s: float
    cell_duration_s: float
    cell_count: int
    minimum_active_cells: int = 5
    allow_left_censored: bool = False
    allow_right_censored: bool = False

    def __post_init__(self) -> None:
        _finite(self.start_s, "activity-grid start")
        _positive(self.cell_duration_s, "activity-cell duration")
        _integer_at_least(self.cell_count, 1, "activity-grid cell count")
        _integer_at_least(self.minimum_active_cells, 1, "minimum active-cell count")
        if not isinstance(self.allow_left_censored, bool) or not isinstance(
            self.allow_right_censored, bool
        ):
            raise ValueError("activity-grid censoring flags must be booleans")

    @property
    def end_s(self) -> float:
        return self.start_s + self.cell_count * self.cell_duration_s


@dataclass(frozen=True, slots=True)
class CfoProbe:
    """One scheduled fine-cadence probe, retained even when it has no peaks."""

    probe_id: str
    time_s: float
    cell_index: int
    missed_detection_cost: float
    usable: bool = True

    def __post_init__(self) -> None:
        _nonempty(self.probe_id, "probe ID")
        _finite(self.time_s, "probe time")
        _integer_at_least(self.cell_index, 0, "probe cell index")
        _nonnegative(self.missed_detection_cost, "probe missed-detection cost")
        if not isinstance(self.usable, bool):
            raise ValueError("probe usability must be a boolean")
        if not self.usable and self.missed_detection_cost != 0.0:
            raise ValueError("an unusable probe cannot carry a missed-detection cost")


@dataclass(frozen=True, slots=True)
class CfoCandidate:
    """One CFO alternative with explicit signal-versus-clutter costs.

    Alternatives for one physical peak share an exclusion group and its single
    clutter cost; consuming one explains every alias in that group.
    """

    observation_id: str
    probe_id: str
    exclusion_group_id: str
    cfo_hz: float
    sigma_hz: float
    clutter_cost: float
    matched_base_cost: float
    component_id: str

    def __post_init__(self) -> None:
        _nonempty(self.observation_id, "observation ID")
        _nonempty(self.probe_id, "observation probe ID")
        _nonempty(self.exclusion_group_id, "observation exclusion-group ID")
        _nonempty(self.component_id, "observation component ID")
        _finite(self.cfo_hz, "observation CFO")
        _positive(self.sigma_hz, "observation CFO uncertainty")
        _nonnegative(self.clutter_cost, "observation clutter cost")
        _nonnegative(self.matched_base_cost, "observation matched base cost")


@dataclass(frozen=True, slots=True)
class AssociationCostModel:
    """Fixed structural costs and the robust residual-loss threshold."""

    satellite_cost: float
    episode_cost: float
    huber_threshold: float = 1.345

    def __post_init__(self) -> None:
        _nonnegative(self.satellite_cost, "satellite selection cost")
        _nonnegative(self.episode_cost, "activity-episode cost")
        _positive(self.huber_threshold, "Huber threshold")


@dataclass(frozen=True, slots=True)
class SatelliteActivityProblem:
    """Infrastructure-free evidence for one path and one activity lattice."""

    grid: ActivityGrid
    probes: tuple[CfoProbe, ...]
    observations: tuple[CfoCandidate, ...]
    costs: AssociationCostModel
    truncated_observation_count: int = 0

    def __post_init__(self) -> None:
        _integer_at_least(
            self.truncated_observation_count,
            0,
            "truncated observation count",
        )

        probes = tuple(sorted(self.probes, key=lambda item: (item.time_s, item.probe_id)))
        observations = tuple(
            sorted(self.observations, key=lambda item: (item.probe_id, item.observation_id))
        )
        object.__setattr__(self, "probes", probes)
        object.__setattr__(self, "observations", observations)

        probe_ids = tuple(item.probe_id for item in probes)
        if len(set(probe_ids)) != len(probe_ids):
            raise ValueError("probe IDs must be unique")
        observation_ids = tuple(item.observation_id for item in observations)
        if len(set(observation_ids)) != len(observation_ids):
            raise ValueError("observation IDs must be unique")
        component_ids = {item.component_id for item in observations}
        if len(component_ids) > 1:
            raise ValueError(
                "one fixed CFO-offset problem cannot span independently gauged components"
            )

        probe_by_id = {item.probe_id: item for item in probes}
        for probe in probes:
            if probe.cell_index >= self.grid.cell_count:
                raise ValueError("probe cell index lies outside the activity grid")
            lower = self.grid.start_s + probe.cell_index * self.grid.cell_duration_s
            upper = lower + self.grid.cell_duration_s
            boundary_tolerance = 8.0 * max(
                math.ulp(lower),
                math.ulp(upper),
                math.ulp(probe.time_s),
            )
            if (
                probe.time_s < lower - boundary_tolerance
                or probe.time_s >= upper - boundary_tolerance
            ):
                raise ValueError("probe time lies outside its declared half-open activity cell")

        exclusion_probe: dict[str, str] = {}
        exclusion_clutter_cost: dict[str, float] = {}
        for observation in observations:
            owning_probe = probe_by_id.get(observation.probe_id)
            if owning_probe is None:
                raise ValueError("observation references an unknown probe")
            if not owning_probe.usable:
                raise ValueError("an unusable probe cannot carry CFO candidates")
            owner = exclusion_probe.setdefault(observation.exclusion_group_id, observation.probe_id)
            if owner != observation.probe_id:
                raise ValueError("one exclusion group cannot span multiple probes")
            group_cost = exclusion_clutter_cost.setdefault(
                observation.exclusion_group_id,
                observation.clutter_cost,
            )
            if group_cost != observation.clutter_cost:
                raise ValueError("aliases in one exclusion group must share one clutter cost")

    @property
    def returned_observation_count(self) -> int:
        return len(self.observations)

    @property
    def source_observation_count(self) -> int:
        return len(self.observations) + self.truncated_observation_count


@dataclass(frozen=True, slots=True)
class PredictedProbeCfo:
    """One geometric Doppler prediction at one scheduled probe."""

    probe_id: str
    cfo_hz: float

    def __post_init__(self) -> None:
        _nonempty(self.probe_id, "prediction probe ID")
        _finite(self.cfo_hz, "predicted CFO")


@dataclass(frozen=True, slots=True)
class SingleSatelliteHypothesis:
    """One fixed satellite, delay-grid point, and shared CFO offset.

    ``eligible_probe_ids`` is a fixed, hypothesis-specific RF-applicability
    mask.  ``None`` preserves the original all-probes-eligible contract; an
    explicit tuple (including an empty tuple) restricts matches and misses to
    that subset without changing hardware/data-quality probe usability or the
    clutter inventory.
    """

    hypothesis_id: str
    object_name: str
    catalog_number: int
    delay_s: float
    cfo_offset_hz: float
    delay_prior_cost: float
    predictions: tuple[PredictedProbeCfo, ...]
    eligible_probe_ids: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        _nonempty(self.hypothesis_id, "hypothesis ID")
        _nonempty(self.object_name, "satellite object name")
        _integer_at_least(self.catalog_number, 1, "satellite catalog number")
        _finite(self.delay_s, "satellite delay")
        _finite(self.cfo_offset_hz, "satellite CFO offset")
        _nonnegative(self.delay_prior_cost, "satellite delay-prior cost")
        predictions = tuple(sorted(self.predictions, key=lambda item: item.probe_id))
        object.__setattr__(self, "predictions", predictions)
        ids = tuple(item.probe_id for item in predictions)
        if len(set(ids)) != len(ids):
            raise ValueError("hypothesis predictions must have unique probe IDs")
        if self.eligible_probe_ids is not None:
            eligible_probe_ids = tuple(sorted(self.eligible_probe_ids))
            if any(not isinstance(item, str) or not item for item in eligible_probe_ids):
                raise ValueError("eligible probe IDs must be nonempty strings")
            if len(set(eligible_probe_ids)) != len(eligible_probe_ids):
                raise ValueError("eligible probe IDs must be unique")
            object.__setattr__(self, "eligible_probe_ids", eligible_probe_ids)


@dataclass(frozen=True, slots=True)
class ProbeAssignment:
    """One selected observation for one active probe."""

    probe_id: str
    observation_id: str

    def __post_init__(self) -> None:
        _nonempty(self.probe_id, "assignment probe ID")
        _nonempty(self.observation_id, "assignment observation ID")


@dataclass(frozen=True, slots=True)
class ActivityEpisode:
    """One maximal half-open run of active cells."""

    start_cell: int
    end_cell_exclusive: int
    duration_s: float
    left_censored: bool
    right_censored: bool


@dataclass(frozen=True, slots=True)
class ObjectiveBreakdown:
    """Absolute negative-log objective recomputed from raw decisions."""

    clutter_cost: float
    matched_base_cost: float
    residual_cost: float
    missed_detection_cost: float
    satellite_cost: float
    episode_cost: float
    delay_prior_cost: float
    null_cost: float
    total_cost: float
    delta_from_null: float


@dataclass(frozen=True, slots=True)
class SingleSatelliteAssociationResult:
    """One feasible schedule and its independently checked objective."""

    hypothesis_id: str
    selected: bool
    activity_by_cell: tuple[bool, ...]
    episodes: tuple[ActivityEpisode, ...]
    assignments: tuple[ProbeAssignment, ...]
    missed_probe_ids: tuple[str, ...]
    unexplained_observation_ids: tuple[str, ...]
    objective: ObjectiveBreakdown
    algorithm: str
    exact: bool


def huber_loss(value: float, threshold: float) -> float:
    """Return the conventional half-square Huber loss."""

    _finite(value, "Huber residual")
    _positive(threshold, "Huber threshold")
    magnitude = abs(value)
    if magnitude <= threshold:
        return 0.5 * magnitude * magnitude
    return threshold * (magnitude - 0.5 * threshold)


def _prediction_by_probe(
    problem: SatelliteActivityProblem,
    hypothesis: SingleSatelliteHypothesis,
) -> dict[str, float]:
    result = {item.probe_id: item.cfo_hz for item in hypothesis.predictions}
    expected = {item.probe_id for item in problem.probes}
    if set(result) != expected:
        raise ValueError("hypothesis predictions must cover every scheduled probe exactly")
    return result


def _eligible_probe_ids(
    problem: SatelliteActivityProblem,
    hypothesis: SingleSatelliteHypothesis,
) -> frozenset[str]:
    scheduled = frozenset(item.probe_id for item in problem.probes)
    if hypothesis.eligible_probe_ids is None:
        return scheduled
    eligible = frozenset(hypothesis.eligible_probe_ids)
    unknown = sorted(eligible - scheduled)
    if unknown:
        raise ValueError(f"hypothesis eligibility references unknown probes: {unknown!r}")
    return eligible


def _activity_episodes(
    grid: ActivityGrid,
    activity_by_cell: tuple[bool, ...],
) -> tuple[ActivityEpisode, ...]:
    if len(activity_by_cell) != grid.cell_count:
        raise ValueError("activity mask length disagrees with the activity grid")
    if any(not isinstance(value, bool) for value in activity_by_cell):
        raise ValueError("activity mask values must be booleans")

    episodes = []
    index = 0
    while index < grid.cell_count:
        if not activity_by_cell[index]:
            index += 1
            continue
        start = index
        while index + 1 < grid.cell_count and activity_by_cell[index + 1]:
            index += 1
        end = index + 1
        left_censored = start == 0 and grid.allow_left_censored
        right_censored = end == grid.cell_count and grid.allow_right_censored
        if end - start < grid.minimum_active_cells and not (left_censored or right_censored):
            raise ValueError("an interior activity episode is shorter than the minimum duration")
        episodes.append(
            ActivityEpisode(
                start_cell=start,
                end_cell_exclusive=end,
                duration_s=(end - start) * grid.cell_duration_s,
                left_censored=left_censored,
                right_censored=right_censored,
            )
        )
        index += 1
    return tuple(episodes)


def _clutter_cost_by_exclusion_group(
    problem: SatelliteActivityProblem,
) -> dict[str, float]:
    result: dict[str, float] = {}
    for observation in problem.observations:
        result.setdefault(observation.exclusion_group_id, observation.clutter_cost)
    return result


def evaluate_single_satellite_schedule(
    problem: SatelliteActivityProblem,
    hypothesis: SingleSatelliteHypothesis,
    activity_by_cell: tuple[bool, ...],
    assignments: tuple[ProbeAssignment, ...] = (),
    *,
    algorithm: str = "independent-objective-checker-v1",
    exact: bool = False,
) -> SingleSatelliteAssociationResult:
    """Validate and independently score one fixed-hypothesis schedule."""

    _nonempty(algorithm, "association algorithm")
    activity = tuple(activity_by_cell)
    episodes = _activity_episodes(problem.grid, activity)
    prediction = _prediction_by_probe(problem, hypothesis)
    eligible_probe_ids = _eligible_probe_ids(problem, hypothesis)
    probe_by_id = {item.probe_id: item for item in problem.probes}
    observation_by_id = {item.observation_id: item for item in problem.observations}

    ordered_assignments = tuple(
        sorted(assignments, key=lambda item: (item.probe_id, item.observation_id))
    )
    assigned_probes = tuple(item.probe_id for item in ordered_assignments)
    assigned_observations = tuple(item.observation_id for item in ordered_assignments)
    if len(set(assigned_probes)) != len(assigned_probes):
        raise ValueError("one satellite cannot consume multiple observations in one probe")
    if len(set(assigned_observations)) != len(assigned_observations):
        raise ValueError("one observation cannot be assigned more than once")

    exclusion_groups = []
    for assignment in ordered_assignments:
        probe = probe_by_id.get(assignment.probe_id)
        observation = observation_by_id.get(assignment.observation_id)
        if probe is None or observation is None:
            raise ValueError("assignment references an unknown probe or observation")
        if observation.probe_id != assignment.probe_id:
            raise ValueError("assignment observation belongs to a different probe")
        if not probe.usable:
            raise ValueError("an unusable probe cannot receive an assignment")
        if probe.probe_id not in eligible_probe_ids:
            raise ValueError("an RF-ineligible probe cannot receive an assignment")
        if not activity[probe.cell_index]:
            raise ValueError("an observation cannot be assigned while the satellite is inactive")
        exclusion_groups.append(observation.exclusion_group_id)
    if len(set(exclusion_groups)) != len(exclusion_groups):
        raise ValueError("one exclusion group cannot be assigned more than once")

    assigned = set(assigned_observations)
    assigned_groups = set(exclusion_groups)
    clutter_by_group = _clutter_cost_by_exclusion_group(problem)
    clutter_terms = [
        clutter_by_group[group_id]
        for group_id in sorted(clutter_by_group)
        if group_id not in assigned_groups
    ]
    matched_terms = []
    residual_terms = []
    for observation in problem.observations:
        if observation.observation_id not in assigned:
            continue
        predicted = prediction[observation.probe_id] + hypothesis.cfo_offset_hz
        residual = (observation.cfo_hz - predicted) / observation.sigma_hz
        matched_terms.append(observation.matched_base_cost)
        residual_terms.append(huber_loss(residual, problem.costs.huber_threshold))

    assignment_by_probe = {item.probe_id: item.observation_id for item in ordered_assignments}
    missed = tuple(
        probe.probe_id
        for probe in problem.probes
        if probe.usable
        and probe.probe_id in eligible_probe_ids
        and activity[probe.cell_index]
        and probe.probe_id not in assignment_by_probe
    )
    missed_terms = [probe_by_id[probe_id].missed_detection_cost for probe_id in missed]
    selected = bool(episodes)
    satellite_cost = problem.costs.satellite_cost if selected else 0.0
    episode_cost = len(episodes) * problem.costs.episode_cost
    delay_prior_cost = hypothesis.delay_prior_cost if selected else 0.0
    values = (
        math.fsum(clutter_terms),
        math.fsum(matched_terms),
        math.fsum(residual_terms),
        math.fsum(missed_terms),
        satellite_cost,
        episode_cost,
        delay_prior_cost,
    )
    null_cost = math.fsum(clutter_by_group.values())
    total_cost = math.fsum(values)
    objective = ObjectiveBreakdown(
        clutter_cost=values[0],
        matched_base_cost=values[1],
        residual_cost=values[2],
        missed_detection_cost=values[3],
        satellite_cost=values[4],
        episode_cost=values[5],
        delay_prior_cost=values[6],
        null_cost=null_cost,
        total_cost=total_cost,
        delta_from_null=total_cost - null_cost,
    )
    return SingleSatelliteAssociationResult(
        hypothesis_id=hypothesis.hypothesis_id,
        selected=selected,
        activity_by_cell=activity,
        episodes=episodes,
        assignments=ordered_assignments,
        missed_probe_ids=missed,
        unexplained_observation_ids=tuple(
            item.observation_id
            for item in problem.observations
            if item.exclusion_group_id not in assigned_groups
        ),
        objective=objective,
        algorithm=algorithm,
        exact=exact,
    )


@dataclass(frozen=True, slots=True)
class _ProbeChoice:
    reduced_cost: float
    observation_id: str | None


def _probe_choices(
    problem: SatelliteActivityProblem,
    hypothesis: SingleSatelliteHypothesis,
) -> tuple[float, dict[str, _ProbeChoice], tuple[float, ...]]:
    prediction = _prediction_by_probe(problem, hypothesis)
    eligible_probe_ids = _eligible_probe_ids(problem, hypothesis)
    observations_by_probe: dict[str, list[CfoCandidate]] = {
        item.probe_id: [] for item in problem.probes
    }
    for observation in problem.observations:
        observations_by_probe[observation.probe_id].append(observation)

    baseline = math.fsum(_clutter_cost_by_exclusion_group(problem).values())
    choices: dict[str, _ProbeChoice] = {}
    cell_reduced = [0.0] * problem.grid.cell_count
    for probe in problem.probes:
        if not probe.usable or probe.probe_id not in eligible_probe_ids:
            continue
        options: list[tuple[float, int, str, str | None]] = [
            (probe.missed_detection_cost, 0, "", None)
        ]
        for observation in observations_by_probe[probe.probe_id]:
            residual = (
                observation.cfo_hz - prediction[probe.probe_id] - hypothesis.cfo_offset_hz
            ) / observation.sigma_hz
            reduced = (
                observation.matched_base_cost
                + huber_loss(residual, problem.costs.huber_threshold)
                - observation.clutter_cost
            )
            options.append((reduced, 1, observation.observation_id, observation.observation_id))
        reduced, _kind, _identity, observation_id = min(options)
        choice = _ProbeChoice(reduced_cost=reduced, observation_id=observation_id)
        choices[probe.probe_id] = choice
        cell_reduced[probe.cell_index] += reduced
    return baseline, choices, tuple(cell_reduced)


@dataclass(frozen=True, slots=True)
class _DpEntry:
    reduced_cost: float
    previous_state: int
    episode_count: int
    active_cell_count: int
    activity_code: int


def _dp_entry_key(
    entry: _DpEntry,
    mature: int,
) -> tuple[float, int, int, int, tuple[int, int]]:
    return (
        entry.reduced_cost,
        entry.episode_count,
        entry.active_cell_count,
        entry.activity_code,
        _state_order(entry.previous_state, mature),
    )


_UNUSED = -2
_OFF_AFTER_USE = -1


def _state_order(state: int, mature: int) -> tuple[int, int]:
    if state == _UNUSED:
        return (0, 0)
    if state == _OFF_AFTER_USE:
        return (1, 0)
    if state == mature:
        return (2, 0)
    return (3, state)


def _transitions(
    state: int,
    *,
    cell_index: int,
    mature: int,
    allow_left_censored: bool,
) -> tuple[tuple[int, bool, bool], ...]:
    """Return ``(next_state, active, starts_episode)`` in canonical order."""

    ordinary_start = mature if mature == 1 else 1
    if state == _UNUSED:
        start = mature if cell_index == 0 and allow_left_censored else ordinary_start
        return ((_UNUSED, False, False), (start, True, True))
    if state == _OFF_AFTER_USE:
        return ((_OFF_AFTER_USE, False, False), (ordinary_start, True, True))
    if state == mature:
        return ((_OFF_AFTER_USE, False, False), (mature, True, False))
    return ((state + 1, True, False),)


def decode_single_satellite(
    problem: SatelliteActivityProblem,
    hypothesis: SingleSatelliteHypothesis,
) -> SingleSatelliteAssociationResult:
    """Exactly decode one fixed satellite/delay/CFO hypothesis in ``O(KL)``."""

    baseline, choices, cell_reduced = _probe_choices(problem, hypothesis)
    eligible_probe_ids = _eligible_probe_ids(problem, hypothesis)
    mature = problem.grid.minimum_active_cells
    previous: dict[int, _DpEntry] = {
        _UNUSED: _DpEntry(
            reduced_cost=0.0,
            previous_state=_UNUSED,
            episode_count=0,
            active_cell_count=0,
            activity_code=0,
        )
    }
    backtrace: list[dict[int, _DpEntry]] = []

    for cell_index in range(problem.grid.cell_count):
        current: dict[int, _DpEntry] = {}
        for state in sorted(previous, key=lambda item: _state_order(item, mature)):
            for next_state, active, starts_episode in _transitions(
                state,
                cell_index=cell_index,
                mature=mature,
                allow_left_censored=problem.grid.allow_left_censored,
            ):
                structural = 0.0
                if starts_episode:
                    structural += problem.costs.episode_cost
                    if state == _UNUSED:
                        structural += problem.costs.satellite_cost + hypothesis.delay_prior_cost
                parent = previous[state]
                candidate_cost = parent.reduced_cost + structural
                if active:
                    candidate_cost += cell_reduced[cell_index]
                candidate = _DpEntry(
                    reduced_cost=candidate_cost,
                    previous_state=state,
                    episode_count=parent.episode_count + int(starts_episode),
                    active_cell_count=parent.active_cell_count + int(active),
                    activity_code=(parent.activity_code << 1) | int(active),
                )
                existing = current.get(next_state)
                if existing is None or _dp_entry_key(candidate, mature) < _dp_entry_key(
                    existing, mature
                ):
                    current[next_state] = candidate
        backtrace.append(current)
        previous = current

    terminal = [_UNUSED, _OFF_AFTER_USE, mature]
    if problem.grid.allow_right_censored:
        terminal.extend(range(1, mature))
    terminal = list(dict.fromkeys(state for state in terminal if state in previous))

    candidates = []
    for final_state in terminal:
        states = [final_state]
        state = final_state
        for cell_index in range(problem.grid.cell_count - 1, 0, -1):
            state = backtrace[cell_index][state].previous_state
            states.append(state)
        states.reverse()
        activity = tuple(state >= 1 for state in states)
        assignments_list = []
        for probe in problem.probes:
            if (
                not activity[probe.cell_index]
                or not probe.usable
                or probe.probe_id not in eligible_probe_ids
            ):
                continue
            observation_id = choices[probe.probe_id].observation_id
            if observation_id is not None:
                assignments_list.append(ProbeAssignment(probe.probe_id, observation_id))
        assignments = tuple(assignments_list)
        evaluation = evaluate_single_satellite_schedule(
            problem,
            hypothesis,
            activity,
            assignments,
            algorithm="exact-single-satellite-semimarkov-v1",
            exact=True,
        )
        expected = baseline + previous[final_state].reduced_cost
        if not math.isclose(
            evaluation.objective.total_cost,
            expected,
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise RuntimeError("semi-Markov reduced cost disagrees with objective checker")
        candidates.append(evaluation)

    def result_key(item: SingleSatelliteAssociationResult) -> tuple[object, ...]:
        return (
            item.objective.total_cost,
            item.selected,
            len(item.episodes),
            sum(item.activity_by_cell),
            item.activity_by_cell,
            tuple(assignment.observation_id for assignment in item.assignments),
        )

    return min(candidates, key=result_key)


@dataclass(frozen=True, slots=True)
class DelayProfileCandidate:
    """One sampled orbital-delay curve before fitting the CFO offset."""

    delay_s: float
    predicted_cfo_hz: tuple[float, ...]

    def __post_init__(self) -> None:
        _finite(self.delay_s, "profile delay")
        if not self.predicted_cfo_hz:
            raise ValueError("delay profile needs at least one predicted CFO")
        if any(not math.isfinite(value) for value in self.predicted_cfo_hz):
            raise ValueError("profiled CFO predictions must be finite")


@dataclass(frozen=True, slots=True)
class DelayCfoProfilePoint:
    """Profiled offset and score at one fixed orbital delay."""

    delay_s: float
    fitted_cfo_offset_hz: float
    data_cost: float
    delay_prior_cost: float
    total_cost: float
    offset_at_bound: bool


@dataclass(frozen=True, slots=True)
class DelayCfoProfile:
    """Auditable data-only and prior-regularized delay/CFO profile."""

    points: tuple[DelayCfoProfilePoint, ...]
    data_only_best_index: int
    posterior_best_index: int
    data_minimum_count: int
    data_cost_span: float
    data_flat: bool
    data_ambiguous: bool
    posterior_differs_from_data_only: bool
    delay_prior_dominated: bool
    posterior_at_delay_boundary: bool

    @property
    def data_only_best(self) -> DelayCfoProfilePoint:
        return self.points[self.data_only_best_index]

    @property
    def posterior_best(self) -> DelayCfoProfilePoint:
        return self.points[self.posterior_best_index]


def _fit_huber_offset(
    raw_offsets_hz: np.ndarray,
    sigma_hz: np.ndarray,
    *,
    threshold: float,
    bounds_hz: tuple[float, float] | None,
    maximum_iterations: int,
) -> tuple[float, bool]:
    def score(offset_hz: float) -> float:
        standardized = (raw_offsets_hz - offset_hz) / sigma_hz
        influence = np.clip(standardized, -threshold, threshold)
        return math.fsum(float(value) for value in influence / sigma_hz)

    lower = float(np.min(raw_offsets_hz)) if bounds_hz is None else bounds_hz[0]
    upper = float(np.max(raw_offsets_hz)) if bounds_hz is None else bounds_hz[1]
    lower_score = score(lower)
    upper_score = score(upper)
    if lower_score <= 0.0:
        return lower, bounds_hz is not None
    if upper_score >= 0.0:
        return upper, bounds_hz is not None

    converged = False
    midpoint = 0.5 * lower + 0.5 * upper
    for _iteration in range(maximum_iterations):
        midpoint = 0.5 * lower + 0.5 * upper
        midpoint_score = score(midpoint)
        if midpoint_score == 0.0:
            converged = True
            break
        if midpoint_score > 0.0:
            lower = midpoint
        else:
            upper = midpoint
        tolerance = 1e-12 * max(1.0, abs(lower), abs(upper))
        if upper - lower <= tolerance or math.nextafter(lower, upper) >= upper:
            midpoint = 0.5 * lower + 0.5 * upper
            converged = True
            break
    if not converged:
        raise RuntimeError("Huber CFO-offset bisection did not converge")

    at_bound = bounds_hz is not None and (
        math.isclose(midpoint, bounds_hz[0], rel_tol=0.0, abs_tol=1e-9)
        or math.isclose(midpoint, bounds_hz[1], rel_tol=0.0, abs_tol=1e-9)
    )
    return midpoint, at_bound


def profile_delay_and_cfo_offset(
    observed_cfo_hz: npt.ArrayLike,
    sigma_hz: npt.ArrayLike,
    candidates: tuple[DelayProfileCandidate, ...],
    *,
    delay_prior_mean_s: float,
    delay_prior_sigma_s: float,
    huber_threshold: float = 1.345,
    cfo_offset_bounds_hz: tuple[float, float] | None = None,
    maximum_iterations: int = 80,
    flat_data_tolerance: float = 1e-9,
) -> DelayCfoProfile:
    """Profile one shared CFO offset at each sampled orbital delay."""

    observed = np.asarray(observed_cfo_hz, dtype=np.float64)
    sigma = np.asarray(sigma_hz, dtype=np.float64)
    if observed.ndim != 1 or sigma.shape != observed.shape or observed.size < 2:
        raise ValueError("delay/CFO profiling needs at least two equal-length samples")
    if not np.all(np.isfinite(observed)) or not np.all(np.isfinite(sigma)):
        raise ValueError("delay/CFO profile inputs must be finite")
    if np.any(sigma <= 0.0):
        raise ValueError("delay/CFO uncertainties must be positive")
    _finite(delay_prior_mean_s, "delay-prior mean")
    _positive(delay_prior_sigma_s, "delay-prior sigma")
    _positive(huber_threshold, "profile Huber threshold")
    _nonnegative(flat_data_tolerance, "flat-profile tolerance")
    _integer_at_least(maximum_iterations, 1, "profile maximum iterations")
    if cfo_offset_bounds_hz is not None:
        lower, upper = cfo_offset_bounds_hz
        if not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper:
            raise ValueError("CFO-offset bounds must be finite and increasing")

    ordered = tuple(sorted(candidates, key=lambda item: item.delay_s))
    if not ordered:
        raise ValueError("delay/CFO profiling needs at least one delay candidate")
    delays = tuple(item.delay_s for item in ordered)
    if len(set(delays)) != len(delays):
        raise ValueError("delay-profile candidates must have unique delays")

    points = []
    for candidate in ordered:
        predicted: npt.NDArray[np.float64] = np.asarray(
            candidate.predicted_cfo_hz, dtype=np.float64
        )
        if predicted.shape != observed.shape:
            raise ValueError("delay prediction length differs from observed CFO length")
        raw_offset = observed - predicted
        offset, at_bound = _fit_huber_offset(
            raw_offset,
            sigma,
            threshold=huber_threshold,
            bounds_hz=cfo_offset_bounds_hz,
            maximum_iterations=maximum_iterations,
        )
        data_cost = math.fsum(
            huber_loss(float(value), huber_threshold) for value in (raw_offset - offset) / sigma
        )
        prior_cost = 0.5 * ((candidate.delay_s - delay_prior_mean_s) / delay_prior_sigma_s) ** 2
        points.append(
            DelayCfoProfilePoint(
                delay_s=candidate.delay_s,
                fitted_cfo_offset_hz=offset,
                data_cost=data_cost,
                delay_prior_cost=prior_cost,
                total_cost=data_cost + prior_cost,
                offset_at_bound=at_bound,
            )
        )

    result = tuple(points)
    data_minimum = min(item.data_cost for item in result)
    data_minima = tuple(
        index
        for index, item in enumerate(result)
        if item.data_cost <= data_minimum + flat_data_tolerance
    )
    data_best = min(
        data_minima,
        key=lambda index: (abs(result[index].delay_s), result[index].delay_s),
    )
    posterior_best = min(
        range(len(result)),
        key=lambda index: (
            result[index].total_cost,
            abs(result[index].delay_s),
            result[index].delay_s,
        ),
    )
    span = max(item.data_cost for item in result) - data_minimum
    data_flat = len(result) > 1 and span <= flat_data_tolerance
    data_ambiguous = len(data_minima) > 1
    posterior_differs = posterior_best != data_best
    return DelayCfoProfile(
        points=result,
        data_only_best_index=data_best,
        posterior_best_index=posterior_best,
        data_minimum_count=len(data_minima),
        data_cost_span=span,
        data_flat=data_flat,
        data_ambiguous=data_ambiguous,
        posterior_differs_from_data_only=posterior_differs,
        delay_prior_dominated=(data_ambiguous or posterior_best not in set(data_minima)),
        posterior_at_delay_boundary=posterior_best in {0, len(result) - 1},
    )


@dataclass(frozen=True, slots=True)
class SyntheticSingleSatelliteConfig:
    """Deterministic synthetic fixture controls for the first prototype slice."""

    seed: int
    cell_count: int
    active_intervals: tuple[tuple[int, int], ...]
    probe_offsets_s: tuple[float, ...] = (0.025, 0.075)
    cell_duration_s: float = 0.1
    minimum_active_cells: int = 5
    allow_left_censored: bool = False
    allow_right_censored: bool = False
    cfo_coefficients_ascending_hz: tuple[float, ...] = (0.0, -3_000.0, 25.0)
    delay_s: float = 0.0
    cfo_offset_hz: float = 100_000.0
    noise_sigma_hz: float = 20.0
    detection_probability: float = 1.0
    mean_clutter_per_probe: float = 0.0
    clutter_cfo_bounds_hz: tuple[float, float] = (-400_000.0, 400_000.0)
    true_peak_clutter_cost: float = 8.0
    true_peak_matched_base_cost: float = 0.0
    clutter_peak_clutter_cost: float = 0.0
    clutter_peak_matched_base_cost: float = 4.0
    missed_detection_cost: float = 4.0
    costs: AssociationCostModel = field(
        default_factory=lambda: AssociationCostModel(
            satellite_cost=6.0,
            episode_cost=2.0,
        )
    )
    delay_prior_cost: float = 0.0

    def __post_init__(self) -> None:
        _integer_at_least(self.seed, 0, "synthetic seed")
        grid = ActivityGrid(
            start_s=0.0,
            cell_duration_s=self.cell_duration_s,
            cell_count=self.cell_count,
            minimum_active_cells=self.minimum_active_cells,
            allow_left_censored=self.allow_left_censored,
            allow_right_censored=self.allow_right_censored,
        )
        if not self.probe_offsets_s:
            raise ValueError("synthetic scenario needs at least one probe per cell")
        if tuple(sorted(set(self.probe_offsets_s))) != self.probe_offsets_s:
            raise ValueError("synthetic probe offsets must be unique and ordered")
        if any(not 0.0 <= value < self.cell_duration_s for value in self.probe_offsets_s):
            raise ValueError("synthetic probe offsets must lie inside one activity cell")
        if not self.cfo_coefficients_ascending_hz or any(
            not math.isfinite(value) for value in self.cfo_coefficients_ascending_hz
        ):
            raise ValueError("synthetic CFO polynomial must be finite and nonempty")
        _finite(self.delay_s, "synthetic delay")
        _finite(self.cfo_offset_hz, "synthetic CFO offset")
        _positive(self.noise_sigma_hz, "synthetic CFO noise sigma")
        if not 0.0 <= self.detection_probability <= 1.0:
            raise ValueError("synthetic detection probability must lie in [0, 1]")
        _nonnegative(self.mean_clutter_per_probe, "synthetic mean clutter count")
        lower, upper = self.clutter_cfo_bounds_hz
        if not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper:
            raise ValueError("synthetic clutter CFO bounds must be finite and increasing")
        for value, label in (
            (self.true_peak_clutter_cost, "true-peak clutter cost"),
            (self.true_peak_matched_base_cost, "true-peak matched cost"),
            (self.clutter_peak_clutter_cost, "clutter-peak clutter cost"),
            (self.clutter_peak_matched_base_cost, "clutter-peak matched cost"),
            (self.missed_detection_cost, "synthetic missed-detection cost"),
            (self.delay_prior_cost, "synthetic delay-prior cost"),
        ):
            _nonnegative(value, label)

        activity = [False] * self.cell_count
        for start, end in self.active_intervals:
            _integer_at_least(start, 0, "synthetic active-interval start")
            _integer_at_least(end, 1, "synthetic active-interval end")
            if start < 0 or end > self.cell_count or start >= end:
                raise ValueError("synthetic active interval lies outside the activity grid")
            if any(activity[start:end]):
                raise ValueError("synthetic active intervals must not overlap")
            activity[start:end] = [True] * (end - start)
        _activity_episodes(grid, tuple(activity))


@dataclass(frozen=True, slots=True)
class SyntheticSingleSatelliteTruth:
    """Planted latent state for one deterministic synthetic problem."""

    activity_by_cell: tuple[bool, ...]
    assignments: tuple[ProbeAssignment, ...]
    delay_s: float
    cfo_offset_hz: float


@dataclass(frozen=True, slots=True)
class SyntheticSingleSatelliteCase:
    """Synthetic problem, its correct fixed hypothesis, and planted truth."""

    problem: SatelliteActivityProblem
    hypothesis: SingleSatelliteHypothesis
    truth: SyntheticSingleSatelliteTruth


def simulate_single_satellite_case(
    config: SyntheticSingleSatelliteConfig,
) -> SyntheticSingleSatelliteCase:
    """Generate one reproducible CFO point cloud with clutter and missed probes."""

    rng = np.random.default_rng(config.seed)
    grid = ActivityGrid(
        start_s=0.0,
        cell_duration_s=config.cell_duration_s,
        cell_count=config.cell_count,
        minimum_active_cells=config.minimum_active_cells,
        allow_left_censored=config.allow_left_censored,
        allow_right_censored=config.allow_right_censored,
    )
    activity = [False] * config.cell_count
    for start, end in config.active_intervals:
        activity[start:end] = [True] * (end - start)

    probes = []
    observations = []
    predictions = []
    truth_assignments = []
    coefficients: npt.NDArray[np.float64] = np.asarray(
        config.cfo_coefficients_ascending_hz, dtype=np.float64
    )
    for cell_index in range(config.cell_count):
        for offset_index, offset_s in enumerate(config.probe_offsets_s):
            probe_id = f"probe-{cell_index:04d}-{offset_index:02d}"
            time_s = cell_index * config.cell_duration_s + offset_s
            probe = CfoProbe(
                probe_id=probe_id,
                time_s=time_s,
                cell_index=cell_index,
                missed_detection_cost=config.missed_detection_cost,
            )
            probes.append(probe)
            geometric = float(
                np.polynomial.polynomial.polyval(time_s + config.delay_s, coefficients)
            )
            predictions.append(PredictedProbeCfo(probe_id=probe_id, cfo_hz=geometric))

            if activity[cell_index] and rng.random() <= config.detection_probability:
                observation_id = f"signal-{probe_id}"
                observations.append(
                    CfoCandidate(
                        observation_id=observation_id,
                        probe_id=probe_id,
                        exclusion_group_id=f"physical-{probe_id}-signal",
                        cfo_hz=(
                            geometric
                            + config.cfo_offset_hz
                            + float(rng.normal(0.0, config.noise_sigma_hz))
                        ),
                        sigma_hz=config.noise_sigma_hz,
                        clutter_cost=config.true_peak_clutter_cost,
                        matched_base_cost=config.true_peak_matched_base_cost,
                        component_id="synthetic-component",
                    )
                )
                truth_assignments.append(ProbeAssignment(probe_id, observation_id))

            clutter_count = int(rng.poisson(config.mean_clutter_per_probe))
            for clutter_index in range(clutter_count):
                observation_id = f"clutter-{probe_id}-{clutter_index:02d}"
                observations.append(
                    CfoCandidate(
                        observation_id=observation_id,
                        probe_id=probe_id,
                        exclusion_group_id=f"physical-{probe_id}-clutter-{clutter_index:02d}",
                        cfo_hz=float(rng.uniform(*config.clutter_cfo_bounds_hz)),
                        sigma_hz=config.noise_sigma_hz,
                        clutter_cost=config.clutter_peak_clutter_cost,
                        matched_base_cost=config.clutter_peak_matched_base_cost,
                        component_id="synthetic-component",
                    )
                )

    problem = SatelliteActivityProblem(
        grid=grid,
        probes=tuple(probes),
        observations=tuple(observations),
        costs=config.costs,
    )
    hypothesis = SingleSatelliteHypothesis(
        hypothesis_id="synthetic-satellite-delay-offset",
        object_name="SYNTHETIC-SATELLITE",
        catalog_number=1,
        delay_s=config.delay_s,
        cfo_offset_hz=config.cfo_offset_hz,
        delay_prior_cost=config.delay_prior_cost,
        predictions=tuple(predictions),
    )
    truth = SyntheticSingleSatelliteTruth(
        activity_by_cell=tuple(activity),
        assignments=tuple(truth_assignments),
        delay_s=config.delay_s,
        cfo_offset_hz=config.cfo_offset_hz,
    )
    return SyntheticSingleSatelliteCase(problem=problem, hypothesis=hypothesis, truth=truth)
