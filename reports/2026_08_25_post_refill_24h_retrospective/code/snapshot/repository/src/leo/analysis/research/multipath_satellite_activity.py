"""Exact shared-activity association across fixed receiver-path hypotheses.

This pure research layer handles one already-chosen catalogue object at one
already-chosen orbital-time delay.  The activity mask and delay are shared by
every receiver path, while each path carries its own fixed CFO offset,
predictions, probes, candidates, exclusion groups, misses, and clutter.

For fixed nuisance parameters, path likelihoods are additive by activity cell.
The implementation therefore namespaces and flattens the path-local evidence,
absorbs each fixed path CFO offset into that path's predictions, and invokes the
exact single-satellite semi-Markov decoder.  Satellite, episode, and delay-prior
costs remain global and are paid only once.  An independent evaluator scores
the returned schedule directly in the original path-local representation.

Exactness is conditional on the supplied fixed catalogue/delay/path-offset
state and a complete candidate inventory.  Catalogue search, delay search,
per-path CFO-offset fitting, and multi-satellite competition remain outside
this module.

The shared mask describes transmitter activity independently of receiver RF
coverage.  Each hypothesis path may additionally carry a fixed path-by-cell
eligibility mask.  An active satellite is expected only where both that mask
and the path probe's hardware/data-quality ``usable`` flag are true.  An
ineligible probe cannot be assigned and incurs no miss, but its observations
remain in the clutter inventory.  Eligibility is fixed input, never a latent
switch inferred from the same peaks being scored.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Integral

from leo.analysis.research.satellite_activity import (
    ActivityEpisode,
    ActivityGrid,
    AssociationCostModel,
    CfoCandidate,
    CfoProbe,
    ObjectiveBreakdown,
    PredictedProbeCfo,
    ProbeAssignment,
    SatelliteActivityProblem,
    SingleSatelliteHypothesis,
    decode_single_satellite,
    huber_loss,
)

ACTIVITY_CELL_DURATION_S = 0.1
MINIMUM_ACTIVE_DURATION_S = 0.5
MINIMUM_RECEIVER_PATHS = 2
_FLATTENED_COMPONENT_ID = "component:fixed-multipath-gauge"


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


def _positive_catalog_number(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise ValueError("satellite catalog number must be a positive integer")
    return int(value)


@dataclass(frozen=True, slots=True)
class ReceiverPathActivityEvidence:
    """Candidate evidence and hardware usability on one receiver path.

    This evidence object does not declare transmitter RF eligibility.
    ``CfoProbe.usable`` retains its hardware/data-quality meaning and must not
    be repurposed as a band-occupancy selector; fixed satellite-specific RF
    eligibility lives on :class:`ReceiverPathFixedHypothesis`.
    """

    path_id: str
    probes: tuple[CfoProbe, ...]
    observations: tuple[CfoCandidate, ...]
    truncated_observation_count: int = 0

    def __post_init__(self) -> None:
        _nonempty(self.path_id, "receiver-path ID")
        if (
            isinstance(self.truncated_observation_count, bool)
            or not isinstance(self.truncated_observation_count, Integral)
            or self.truncated_observation_count < 0
        ):
            raise ValueError("truncated observation count must be a nonnegative integer")
        object.__setattr__(
            self,
            "probes",
            tuple(sorted(self.probes, key=lambda item: (item.time_s, item.probe_id))),
        )
        object.__setattr__(
            self,
            "observations",
            tuple(sorted(self.observations, key=lambda item: (item.probe_id, item.observation_id))),
        )

    @property
    def returned_observation_count(self) -> int:
        return len(self.observations)

    @property
    def source_observation_count(self) -> int:
        return len(self.observations) + int(self.truncated_observation_count)


@dataclass(frozen=True, slots=True)
class MultipathSatelliteActivityProblem:
    """One common 100-ms UTC grid with independent path-local inventories."""

    grid: ActivityGrid
    paths: tuple[ReceiverPathActivityEvidence, ...]
    costs: AssociationCostModel

    def __post_init__(self) -> None:
        if not math.isclose(
            self.grid.cell_duration_s,
            ACTIVITY_CELL_DURATION_S,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("multipath activity requires an exact 100-ms common UTC grid")
        nearest_boundary_s = round(self.grid.start_s / ACTIVITY_CELL_DURATION_S) * (
            ACTIVITY_CELL_DURATION_S
        )
        boundary_tolerance_s = 8.0 * max(
            math.ulp(self.grid.start_s),
            math.ulp(nearest_boundary_s),
            math.ulp(ACTIVITY_CELL_DURATION_S),
        )
        if not math.isclose(
            self.grid.start_s,
            nearest_boundary_s,
            rel_tol=0.0,
            abs_tol=boundary_tolerance_s,
        ):
            raise ValueError("multipath UTC-grid start must lie on a 100-ms boundary")
        minimum_duration_s = self.grid.minimum_active_cells * self.grid.cell_duration_s
        if minimum_duration_s + 1e-12 < MINIMUM_ACTIVE_DURATION_S:
            raise ValueError("multipath activity requires runs of at least 0.5 seconds")
        if self.grid.allow_left_censored or self.grid.allow_right_censored:
            raise ValueError(
                "multipath activity does not permit boundary censoring below the minimum run"
            )

        paths = tuple(sorted(self.paths, key=lambda item: item.path_id))
        if len(paths) < MINIMUM_RECEIVER_PATHS:
            raise ValueError("multipath activity requires at least two receiver paths")
        path_ids = tuple(item.path_id for item in paths)
        if len(set(path_ids)) != len(path_ids):
            raise ValueError("receiver-path IDs must be unique")

        normalized_paths = []
        for path in paths:
            if not path.probes:
                raise ValueError("every receiver path must retain at least one scheduled probe")
            normalized = SatelliteActivityProblem(
                grid=self.grid,
                probes=path.probes,
                observations=path.observations,
                costs=self.costs,
                truncated_observation_count=int(path.truncated_observation_count),
            )
            normalized_paths.append(
                ReceiverPathActivityEvidence(
                    path_id=path.path_id,
                    probes=normalized.probes,
                    observations=normalized.observations,
                    truncated_observation_count=normalized.truncated_observation_count,
                )
            )
        object.__setattr__(self, "paths", tuple(normalized_paths))

    @property
    def truncated_observation_count(self) -> int:
        return sum(int(item.truncated_observation_count) for item in self.paths)

    @property
    def returned_observation_count(self) -> int:
        return sum(item.returned_observation_count for item in self.paths)

    @property
    def source_observation_count(self) -> int:
        return sum(item.source_observation_count for item in self.paths)


@dataclass(frozen=True, slots=True)
class ReceiverPathFixedHypothesis:
    """One path's Doppler curve, CFO offset, and fixed RF eligibility.

    ``eligible_by_cell=None`` preserves the original all-cells-eligible
    contract.  An explicit Boolean tuple is validated against the common grid
    when the hypothesis is paired with a problem.
    """

    path_id: str
    cfo_offset_hz: float
    predictions: tuple[PredictedProbeCfo, ...]
    eligible_by_cell: tuple[bool, ...] | None = None

    def __post_init__(self) -> None:
        _nonempty(self.path_id, "receiver-path hypothesis ID")
        _finite(self.cfo_offset_hz, "receiver-path CFO offset")
        predictions = tuple(sorted(self.predictions, key=lambda item: item.probe_id))
        prediction_ids = tuple(item.probe_id for item in predictions)
        if len(set(prediction_ids)) != len(prediction_ids):
            raise ValueError("receiver-path predictions must have unique probe IDs")
        object.__setattr__(self, "predictions", predictions)
        if self.eligible_by_cell is not None:
            eligible_by_cell = tuple(self.eligible_by_cell)
            if any(not isinstance(item, bool) for item in eligible_by_cell):
                raise ValueError("receiver-path eligibility values must be booleans")
            object.__setattr__(self, "eligible_by_cell", eligible_by_cell)


@dataclass(frozen=True, slots=True)
class FixedMultipathSatelliteHypothesis:
    """One catalogue object, shared delay, and fixed offset for every path."""

    hypothesis_id: str
    object_name: str
    catalog_number: int
    delay_s: float
    delay_prior_cost: float
    paths: tuple[ReceiverPathFixedHypothesis, ...]

    def __post_init__(self) -> None:
        _nonempty(self.hypothesis_id, "multipath hypothesis ID")
        _nonempty(self.object_name, "satellite object name")
        object.__setattr__(self, "catalog_number", _positive_catalog_number(self.catalog_number))
        _finite(self.delay_s, "satellite delay")
        _nonnegative(self.delay_prior_cost, "satellite delay-prior cost")
        paths = tuple(sorted(self.paths, key=lambda item: item.path_id))
        path_ids = tuple(item.path_id for item in paths)
        if len(set(path_ids)) != len(path_ids):
            raise ValueError("receiver-path hypotheses must have unique path IDs")
        object.__setattr__(self, "paths", paths)


@dataclass(frozen=True, slots=True)
class ReceiverPathAssignments:
    """Assignments on one path for the one shared activity mask."""

    path_id: str
    assignments: tuple[ProbeAssignment, ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.path_id, "receiver-path assignment ID")
        object.__setattr__(
            self,
            "assignments",
            tuple(
                sorted(
                    self.assignments,
                    key=lambda item: (item.probe_id, item.observation_id),
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ReceiverPathObjectiveBreakdown:
    """Path-local evidence terms; structural terms are intentionally absent."""

    clutter_cost: float
    matched_base_cost: float
    residual_cost: float
    missed_detection_cost: float
    null_cost: float
    total_cost: float
    delta_from_null: float


@dataclass(frozen=True, slots=True)
class ReceiverPathActivityDecision:
    """One independently checked path contribution to the shared schedule."""

    path_id: str
    cfo_offset_hz: float
    eligible_by_cell: tuple[bool, ...]
    assignments: tuple[ProbeAssignment, ...]
    missed_probe_ids: tuple[str, ...]
    unexplained_observation_ids: tuple[str, ...]
    objective: ReceiverPathObjectiveBreakdown


@dataclass(frozen=True, slots=True)
class MultipathSatelliteAssociationResult:
    """One shared schedule, path decisions, and globally accounted objective."""

    hypothesis_id: str
    object_name: str
    catalog_number: int
    delay_s: float
    selected: bool
    activity_by_cell: tuple[bool, ...]
    episodes: tuple[ActivityEpisode, ...]
    paths: tuple[ReceiverPathActivityDecision, ...]
    objective: ObjectiveBreakdown
    algorithm: str
    exact: bool


def _validated_path_hypotheses(
    problem: MultipathSatelliteActivityProblem,
    hypothesis: FixedMultipathSatelliteHypothesis,
) -> dict[str, ReceiverPathFixedHypothesis]:
    expected_paths = {item.path_id for item in problem.paths}
    supplied_paths = {item.path_id for item in hypothesis.paths}
    if supplied_paths != expected_paths:
        missing = sorted(expected_paths - supplied_paths)
        extra = sorted(supplied_paths - expected_paths)
        raise ValueError(
            f"multipath hypothesis path coverage differs: missing={missing!r}, extra={extra!r}"
        )
    by_path = {item.path_id: item for item in hypothesis.paths}
    for path in problem.paths:
        path_hypothesis = by_path[path.path_id]
        prediction_ids = {item.probe_id for item in path_hypothesis.predictions}
        probe_ids = {item.probe_id for item in path.probes}
        if prediction_ids != probe_ids:
            raise ValueError(
                f"multipath predictions must cover path {path.path_id!r} probes exactly"
            )
        _effective_eligibility_by_cell(problem, path_hypothesis)
    return by_path


def _effective_eligibility_by_cell(
    problem: MultipathSatelliteActivityProblem,
    hypothesis: ReceiverPathFixedHypothesis,
) -> tuple[bool, ...]:
    if hypothesis.eligible_by_cell is None:
        return (True,) * problem.grid.cell_count
    if len(hypothesis.eligible_by_cell) != problem.grid.cell_count:
        raise ValueError(
            f"receiver-path eligibility for {hypothesis.path_id!r} must cover "
            "the common activity grid exactly"
        )
    return hypothesis.eligible_by_cell


def _activity_episodes(
    grid: ActivityGrid,
    activity_by_cell: tuple[bool, ...],
) -> tuple[ActivityEpisode, ...]:
    if len(activity_by_cell) != grid.cell_count:
        raise ValueError("activity mask length disagrees with the common activity grid")
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
        if end - start < grid.minimum_active_cells:
            raise ValueError("an activity episode is shorter than the minimum duration")
        episodes.append(
            ActivityEpisode(
                start_cell=start,
                end_cell_exclusive=end,
                duration_s=(end - start) * grid.cell_duration_s,
                left_censored=False,
                right_censored=False,
            )
        )
        index += 1
    return tuple(episodes)


def _clutter_by_group(path: ReceiverPathActivityEvidence) -> dict[str, float]:
    result: dict[str, float] = {}
    for observation in path.observations:
        result.setdefault(observation.exclusion_group_id, observation.clutter_cost)
    return result


def evaluate_fixed_multipath_satellite_schedule(
    problem: MultipathSatelliteActivityProblem,
    hypothesis: FixedMultipathSatelliteHypothesis,
    activity_by_cell: tuple[bool, ...],
    path_assignments: tuple[ReceiverPathAssignments, ...] = (),
    *,
    algorithm: str = "independent-fixed-multipath-objective-checker-v2",
    exact: bool = False,
) -> MultipathSatelliteAssociationResult:
    """Validate and directly score one shared activity schedule.

    Observation, probe, component, and exclusion-group IDs are local to their
    receiver path.  The same text ID may therefore appear independently on
    multiple paths without causing an exclusivity collision.
    """

    _nonempty(algorithm, "multipath association algorithm")
    activity = tuple(activity_by_cell)
    episodes = _activity_episodes(problem.grid, activity)
    hypotheses_by_path = _validated_path_hypotheses(problem, hypothesis)

    assignment_path_ids = tuple(item.path_id for item in path_assignments)
    if len(set(assignment_path_ids)) != len(assignment_path_ids):
        raise ValueError("receiver-path assignment entries must have unique path IDs")
    known_path_ids = {item.path_id for item in problem.paths}
    unknown_paths = sorted(set(assignment_path_ids) - known_path_ids)
    if unknown_paths:
        raise ValueError(f"assignments reference unknown receiver paths: {unknown_paths!r}")
    supplied_assignments = {item.path_id: item.assignments for item in path_assignments}

    path_decisions = []
    path_clutter_terms = []
    path_matched_terms = []
    path_residual_terms = []
    path_missed_terms = []
    path_null_terms = []
    for path in problem.paths:
        path_hypothesis = hypotheses_by_path[path.path_id]
        eligible_by_cell = _effective_eligibility_by_cell(problem, path_hypothesis)
        predictions = {item.probe_id: item.cfo_hz for item in path_hypothesis.predictions}
        probe_by_id = {item.probe_id: item for item in path.probes}
        observation_by_id = {item.observation_id: item for item in path.observations}
        assignments = supplied_assignments.get(path.path_id, ())

        assigned_probe_ids = tuple(item.probe_id for item in assignments)
        assigned_observation_ids = tuple(item.observation_id for item in assignments)
        if len(set(assigned_probe_ids)) != len(assigned_probe_ids):
            raise ValueError("one path cannot consume multiple observations in one probe")
        if len(set(assigned_observation_ids)) != len(assigned_observation_ids):
            raise ValueError("one path observation cannot be assigned more than once")

        assigned_groups = []
        matched_terms = []
        residual_terms = []
        for assignment in assignments:
            probe = probe_by_id.get(assignment.probe_id)
            observation = observation_by_id.get(assignment.observation_id)
            if probe is None or observation is None:
                raise ValueError("path assignment references an unknown probe or observation")
            if observation.probe_id != assignment.probe_id:
                raise ValueError("path assignment observation belongs to a different probe")
            if not probe.usable:
                raise ValueError("an unusable path probe cannot receive an assignment")
            if not eligible_by_cell[probe.cell_index]:
                raise ValueError("an RF-ineligible path probe cannot receive an assignment")
            if not activity[probe.cell_index]:
                raise ValueError("a path observation cannot be assigned while activity is off")
            assigned_groups.append(observation.exclusion_group_id)
            predicted = predictions[probe.probe_id] + path_hypothesis.cfo_offset_hz
            residual = (observation.cfo_hz - predicted) / observation.sigma_hz
            matched_terms.append(observation.matched_base_cost)
            residual_terms.append(huber_loss(residual, problem.costs.huber_threshold))
        if len(set(assigned_groups)) != len(assigned_groups):
            raise ValueError("one path-local exclusion group cannot be assigned more than once")

        assigned_probe_set = set(assigned_probe_ids)
        missed = tuple(
            probe.probe_id
            for probe in path.probes
            if probe.usable
            and eligible_by_cell[probe.cell_index]
            and activity[probe.cell_index]
            and probe.probe_id not in assigned_probe_set
        )
        missed_terms = [probe_by_id[probe_id].missed_detection_cost for probe_id in missed]
        clutter_by_group = _clutter_by_group(path)
        consumed_groups = set(assigned_groups)
        clutter_cost = math.fsum(
            cost
            for group_id, cost in sorted(clutter_by_group.items())
            if group_id not in consumed_groups
        )
        matched_cost = math.fsum(matched_terms)
        residual_cost = math.fsum(residual_terms)
        missed_cost = math.fsum(missed_terms)
        null_cost = math.fsum(clutter_by_group.values())
        total_cost = math.fsum((clutter_cost, matched_cost, residual_cost, missed_cost))
        path_objective = ReceiverPathObjectiveBreakdown(
            clutter_cost=clutter_cost,
            matched_base_cost=matched_cost,
            residual_cost=residual_cost,
            missed_detection_cost=missed_cost,
            null_cost=null_cost,
            total_cost=total_cost,
            delta_from_null=total_cost - null_cost,
        )
        path_decisions.append(
            ReceiverPathActivityDecision(
                path_id=path.path_id,
                cfo_offset_hz=path_hypothesis.cfo_offset_hz,
                eligible_by_cell=eligible_by_cell,
                assignments=assignments,
                missed_probe_ids=missed,
                unexplained_observation_ids=tuple(
                    item.observation_id
                    for item in path.observations
                    if item.exclusion_group_id not in consumed_groups
                ),
                objective=path_objective,
            )
        )
        path_clutter_terms.append(clutter_cost)
        path_matched_terms.append(matched_cost)
        path_residual_terms.append(residual_cost)
        path_missed_terms.append(missed_cost)
        path_null_terms.append(null_cost)

    selected = bool(episodes)
    values = (
        math.fsum(path_clutter_terms),
        math.fsum(path_matched_terms),
        math.fsum(path_residual_terms),
        math.fsum(path_missed_terms),
        problem.costs.satellite_cost if selected else 0.0,
        len(episodes) * problem.costs.episode_cost,
        hypothesis.delay_prior_cost if selected else 0.0,
    )
    null_cost = math.fsum(path_null_terms)
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
    return MultipathSatelliteAssociationResult(
        hypothesis_id=hypothesis.hypothesis_id,
        object_name=hypothesis.object_name,
        catalog_number=hypothesis.catalog_number,
        delay_s=hypothesis.delay_s,
        selected=selected,
        activity_by_cell=activity,
        episodes=episodes,
        paths=tuple(path_decisions),
        objective=objective,
        algorithm=algorithm,
        exact=exact,
    )


@dataclass(frozen=True, slots=True)
class _FlattenedMultipathProblem:
    problem: SatelliteActivityProblem
    hypothesis: SingleSatelliteHypothesis
    probe_identity: dict[str, tuple[str, str]]
    observation_identity: dict[str, tuple[str, str]]


def _flatten_fixed_multipath_problem(
    problem: MultipathSatelliteActivityProblem,
    hypothesis: FixedMultipathSatelliteHypothesis,
) -> _FlattenedMultipathProblem:
    hypotheses_by_path = _validated_path_hypotheses(problem, hypothesis)
    probes = []
    observations = []
    predictions = []
    probe_identity: dict[str, tuple[str, str]] = {}
    observation_identity: dict[str, tuple[str, str]] = {}
    eligible_probe_ids = []

    for path_index, path in enumerate(problem.paths):
        path_hypothesis = hypotheses_by_path[path.path_id]
        eligible_by_cell = _effective_eligibility_by_cell(problem, path_hypothesis)
        prediction_by_probe = {item.probe_id: item.cfo_hz for item in path_hypothesis.predictions}
        flattened_probe_by_local = {}
        for probe_index, probe in enumerate(path.probes):
            flattened_probe_id = f"p:{path_index}:{probe_index}"
            flattened_probe_by_local[probe.probe_id] = flattened_probe_id
            probe_identity[flattened_probe_id] = (path.path_id, probe.probe_id)
            if eligible_by_cell[probe.cell_index]:
                eligible_probe_ids.append(flattened_probe_id)
            probes.append(
                CfoProbe(
                    probe_id=flattened_probe_id,
                    time_s=probe.time_s,
                    cell_index=probe.cell_index,
                    missed_detection_cost=probe.missed_detection_cost,
                    usable=probe.usable,
                )
            )
            predictions.append(
                PredictedProbeCfo(
                    probe_id=flattened_probe_id,
                    cfo_hz=(prediction_by_probe[probe.probe_id] + path_hypothesis.cfo_offset_hz),
                )
            )

        group_index = {
            group_id: index
            for index, group_id in enumerate(
                sorted({item.exclusion_group_id for item in path.observations})
            )
        }
        for observation_index, observation in enumerate(path.observations):
            flattened_observation_id = f"o:{path_index}:{observation_index}"
            observation_identity[flattened_observation_id] = (
                path.path_id,
                observation.observation_id,
            )
            observations.append(
                CfoCandidate(
                    observation_id=flattened_observation_id,
                    probe_id=flattened_probe_by_local[observation.probe_id],
                    exclusion_group_id=(
                        f"g:{path_index}:{group_index[observation.exclusion_group_id]}"
                    ),
                    cfo_hz=observation.cfo_hz,
                    sigma_hz=observation.sigma_hz,
                    clutter_cost=observation.clutter_cost,
                    matched_base_cost=observation.matched_base_cost,
                    component_id=_FLATTENED_COMPONENT_ID,
                )
            )

    flattened_problem = SatelliteActivityProblem(
        grid=problem.grid,
        probes=tuple(probes),
        observations=tuple(observations),
        costs=problem.costs,
        truncated_observation_count=problem.truncated_observation_count,
    )
    flattened_hypothesis = SingleSatelliteHypothesis(
        hypothesis_id=hypothesis.hypothesis_id,
        object_name=hypothesis.object_name,
        catalog_number=hypothesis.catalog_number,
        delay_s=hypothesis.delay_s,
        cfo_offset_hz=0.0,
        delay_prior_cost=hypothesis.delay_prior_cost,
        predictions=tuple(predictions),
        eligible_probe_ids=tuple(eligible_probe_ids),
    )
    return _FlattenedMultipathProblem(
        problem=flattened_problem,
        hypothesis=flattened_hypothesis,
        probe_identity=probe_identity,
        observation_identity=observation_identity,
    )


def decode_fixed_multipath_satellite(
    problem: MultipathSatelliteActivityProblem,
    hypothesis: FixedMultipathSatelliteHypothesis,
) -> MultipathSatelliteAssociationResult:
    """Exactly decode one fixed shared-delay/path-offset state.

    The returned exactness claim covers the activity mask and path-local
    assignments only.  It does not cover catalogue identity, delay, or CFO
    offsets, all of which are fixed inputs to this call.
    """

    if problem.truncated_observation_count:
        raise ValueError("exact multipath decoding requires complete path candidate inventories")
    flattened = _flatten_fixed_multipath_problem(problem, hypothesis)
    decoded = decode_single_satellite(flattened.problem, flattened.hypothesis)

    assignments_by_path: dict[str, list[ProbeAssignment]] = {
        item.path_id: [] for item in problem.paths
    }
    for assignment in decoded.assignments:
        path_id, probe_id = flattened.probe_identity[assignment.probe_id]
        observation_path_id, observation_id = flattened.observation_identity[
            assignment.observation_id
        ]
        if observation_path_id != path_id:
            raise RuntimeError("flattened multipath assignment crossed receiver paths")
        assignments_by_path[path_id].append(ProbeAssignment(probe_id, observation_id))

    result = evaluate_fixed_multipath_satellite_schedule(
        problem,
        hypothesis,
        decoded.activity_by_cell,
        tuple(
            ReceiverPathAssignments(path.path_id, tuple(assignments_by_path[path.path_id]))
            for path in problem.paths
        ),
        algorithm="bounded-exact-fixed-nuisance-multipath-semimarkov-v2",
        exact=True,
    )
    if result.activity_by_cell != decoded.activity_by_cell:
        raise RuntimeError("multipath activity mask disagrees with flattened exact decoder")
    for field in (
        "clutter_cost",
        "matched_base_cost",
        "residual_cost",
        "missed_detection_cost",
        "satellite_cost",
        "episode_cost",
        "delay_prior_cost",
        "null_cost",
        "total_cost",
        "delta_from_null",
    ):
        checked_value = getattr(result.objective, field)
        flattened_value = getattr(decoded.objective, field)
        if not math.isclose(checked_value, flattened_value, rel_tol=1e-12, abs_tol=1e-9):
            raise RuntimeError(f"multipath {field} disagrees with the flattened exact decoder")
    return result
