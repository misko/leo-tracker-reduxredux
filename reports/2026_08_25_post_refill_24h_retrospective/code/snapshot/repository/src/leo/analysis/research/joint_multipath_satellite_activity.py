"""Exact 2--3-satellite activity association across receiver paths.

This research-only layer accepts two or three already-chosen catalogue
hypotheses.  Each hypothesis fixes one orbital-time delay shared across paths
and one constant CFO offset per path.  Every satellite has its own shared
activity mask, while probes, candidates, exclusion groups, clutter, and misses
remain local to each receiver path.

For fixed nuisance states, path evidence is additive.  The implementation
collision-proof namespaces the path inventory, absorbs each path CFO offset
into that satellite's path predictions, and invokes the existing exact joint
fixed-hypothesis decoder.  It then maps the schedules back and independently
re-evaluates them in the original path namespaces.

Exactness is bounded to two or three supplied fixed hypotheses and complete
candidate inventories.  Catalogue search, nuisance-state search or fitting,
more than three simultaneous satellites, and real-corpus adaptation remain
outside this module.

Each satellite/path hypothesis may supply a fixed path-by-cell RF eligibility
mask.  Activity remains global to the satellite, while assignments and misses
are possible only at RF-eligible, hardware-usable probes.  Ineligible peaks
remain clutter, and eligibility is never optimized from those peaks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from leo.analysis.research.multi_satellite_activity import (
    MAXIMUM_EXACT_HYPOTHESES,
    MINIMUM_EXACT_HYPOTHESES,
    decode_joint_fixed_hypotheses,
)
from leo.analysis.research.multipath_satellite_activity import (
    FixedMultipathSatelliteHypothesis,
    MultipathSatelliteActivityProblem,
    ReceiverPathAssignments,
    ReceiverPathFixedHypothesis,
    ReceiverPathObjectiveBreakdown,
    _effective_eligibility_by_cell,
    evaluate_fixed_multipath_satellite_schedule,
)
from leo.analysis.research.satellite_activity import (
    ActivityEpisode,
    CfoCandidate,
    CfoProbe,
    ObjectiveBreakdown,
    PredictedProbeCfo,
    ProbeAssignment,
    SatelliteActivityProblem,
    SingleSatelliteHypothesis,
)

_FLATTENED_COMPONENT_ID = "component:fixed-joint-multipath-gauge"


def _nonempty(value: str, label: str) -> None:
    if not value:
        raise ValueError(f"{label} must not be empty")


@dataclass(frozen=True, slots=True)
class JointMultipathSatelliteSchedule:
    """One fixed satellite's shared mask and path-local assignments."""

    hypothesis_id: str
    activity_by_cell: tuple[bool, ...]
    path_assignments: tuple[ReceiverPathAssignments, ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.hypothesis_id, "joint multipath schedule hypothesis ID")
        activity = tuple(self.activity_by_cell)
        if any(not isinstance(item, bool) for item in activity):
            raise ValueError("joint multipath activity values must be booleans")
        path_assignments = tuple(sorted(self.path_assignments, key=lambda item: item.path_id))
        path_ids = tuple(item.path_id for item in path_assignments)
        if len(set(path_ids)) != len(path_ids):
            raise ValueError("one satellite schedule cannot repeat a receiver path")
        object.__setattr__(self, "activity_by_cell", activity)
        object.__setattr__(self, "path_assignments", path_assignments)


@dataclass(frozen=True, slots=True)
class ReceiverPathSatelliteEvidenceBreakdown:
    """One satellite's non-clutter evidence terms on one path."""

    matched_base_cost: float
    residual_cost: float
    missed_detection_cost: float
    total_cost: float


@dataclass(frozen=True, slots=True)
class JointReceiverPathSatelliteDecision:
    """One satellite's fixed offset, assignments, and misses on one path."""

    path_id: str
    cfo_offset_hz: float
    eligible_by_cell: tuple[bool, ...]
    assignments: tuple[ProbeAssignment, ...]
    missed_probe_ids: tuple[str, ...]
    evidence: ReceiverPathSatelliteEvidenceBreakdown


@dataclass(frozen=True, slots=True)
class JointMultipathSatelliteDecision:
    """One fixed catalogue hypothesis and its shared activity decision."""

    hypothesis_id: str
    object_name: str
    catalog_number: int
    delay_s: float
    selected: bool
    activity_by_cell: tuple[bool, ...]
    episodes: tuple[ActivityEpisode, ...]
    paths: tuple[JointReceiverPathSatelliteDecision, ...]


@dataclass(frozen=True, slots=True)
class JointReceiverPathAssociationDecision:
    """Globally exclusive accounting for one receiver path."""

    path_id: str
    unexplained_observation_ids: tuple[str, ...]
    objective: ReceiverPathObjectiveBreakdown


@dataclass(frozen=True, slots=True)
class JointMultipathSatelliteAssociationResult:
    """Joint fixed-state schedules with independently checked accounting."""

    satellites: tuple[JointMultipathSatelliteDecision, ...]
    paths: tuple[JointReceiverPathAssociationDecision, ...]
    objective: ObjectiveBreakdown
    algorithm: str
    exact: bool

    @property
    def selected_catalog_numbers(self) -> tuple[int, ...]:
        return tuple(item.catalog_number for item in self.satellites if item.selected)


def _path_hypotheses(
    problem: MultipathSatelliteActivityProblem,
    hypothesis: FixedMultipathSatelliteHypothesis,
) -> dict[str, ReceiverPathFixedHypothesis]:
    expected_paths = {item.path_id for item in problem.paths}
    supplied_paths = {item.path_id for item in hypothesis.paths}
    if supplied_paths != expected_paths:
        missing = sorted(expected_paths - supplied_paths)
        extra = sorted(supplied_paths - expected_paths)
        raise ValueError(
            f"joint multipath hypothesis path coverage differs: "
            f"missing={missing!r}, extra={extra!r}"
        )
    by_path = {item.path_id: item for item in hypothesis.paths}
    for path in problem.paths:
        path_hypothesis = by_path[path.path_id]
        prediction_ids = {item.probe_id for item in path_hypothesis.predictions}
        probe_ids = {item.probe_id for item in path.probes}
        if prediction_ids != probe_ids:
            raise ValueError(
                f"joint multipath predictions must cover path {path.path_id!r} exactly"
            )
        _effective_eligibility_by_cell(problem, path_hypothesis)
    return by_path


def _canonical_hypotheses(
    problem: MultipathSatelliteActivityProblem,
    hypotheses: tuple[FixedMultipathSatelliteHypothesis, ...],
) -> tuple[FixedMultipathSatelliteHypothesis, ...]:
    hypothesis_count = len(hypotheses)
    if not MINIMUM_EXACT_HYPOTHESES <= hypothesis_count <= MAXIMUM_EXACT_HYPOTHESES:
        raise ValueError("joint multipath decoding requires two or three fixed hypotheses")
    hypothesis_ids = tuple(item.hypothesis_id for item in hypotheses)
    if len(set(hypothesis_ids)) != len(hypothesis_ids):
        raise ValueError("joint multipath hypothesis IDs must be unique")
    catalog_numbers = tuple(item.catalog_number for item in hypotheses)
    if len(set(catalog_numbers)) != len(catalog_numbers):
        raise ValueError("joint multipath fixed hypotheses must have unique catalog numbers")
    ordered = tuple(
        sorted(
            hypotheses,
            key=lambda item: (item.catalog_number, item.object_name, item.hypothesis_id),
        )
    )
    for hypothesis in ordered:
        _path_hypotheses(problem, hypothesis)
    return ordered


def _clutter_by_group(path_observations: tuple[CfoCandidate, ...]) -> dict[str, float]:
    result: dict[str, float] = {}
    for observation in path_observations:
        result.setdefault(observation.exclusion_group_id, observation.clutter_cost)
    return result


def evaluate_joint_fixed_multipath_schedule(
    problem: MultipathSatelliteActivityProblem,
    hypotheses: tuple[FixedMultipathSatelliteHypothesis, ...],
    schedules: tuple[JointMultipathSatelliteSchedule, ...] = (),
    *,
    algorithm: str = "independent-joint-fixed-multipath-objective-checker-v2",
    exact: bool = False,
) -> JointMultipathSatelliteAssociationResult:
    """Validate and directly score fixed multi-satellite multipath schedules.

    Exclusion is global among satellites but local to a receiver path.  Thus
    aliases of one physical path peak cannot be split between satellites,
    while distinct groups at one path probe may support simultaneous
    satellites and identical text IDs on another path remain independent.
    """

    _nonempty(algorithm, "joint multipath association algorithm")
    ordered_hypotheses = _canonical_hypotheses(problem, tuple(hypotheses))
    hypothesis_ids = {item.hypothesis_id for item in ordered_hypotheses}
    schedule_ids = tuple(item.hypothesis_id for item in schedules)
    if len(set(schedule_ids)) != len(schedule_ids):
        raise ValueError("joint multipath schedules must have unique hypothesis IDs")
    unknown_hypotheses = sorted(set(schedule_ids) - hypothesis_ids)
    if unknown_hypotheses:
        raise ValueError(
            f"joint multipath schedules reference unknown hypotheses: {unknown_hypotheses!r}"
        )
    schedule_by_hypothesis = {item.hypothesis_id: item for item in schedules}

    checked_by_hypothesis = {}
    satellite_decisions = []
    for hypothesis in ordered_hypotheses:
        schedule = schedule_by_hypothesis.get(
            hypothesis.hypothesis_id,
            JointMultipathSatelliteSchedule(
                hypothesis_id=hypothesis.hypothesis_id,
                activity_by_cell=(False,) * problem.grid.cell_count,
            ),
        )
        checked = evaluate_fixed_multipath_satellite_schedule(
            problem,
            hypothesis,
            schedule.activity_by_cell,
            schedule.path_assignments,
            algorithm="joint-multipath-satellite-subdecision-checker-v2",
            exact=False,
        )
        checked_by_hypothesis[hypothesis.hypothesis_id] = checked
        satellite_decisions.append(
            JointMultipathSatelliteDecision(
                hypothesis_id=hypothesis.hypothesis_id,
                object_name=hypothesis.object_name,
                catalog_number=hypothesis.catalog_number,
                delay_s=hypothesis.delay_s,
                selected=checked.selected,
                activity_by_cell=checked.activity_by_cell,
                episodes=checked.episodes,
                paths=tuple(
                    JointReceiverPathSatelliteDecision(
                        path_id=path.path_id,
                        cfo_offset_hz=path.cfo_offset_hz,
                        eligible_by_cell=path.eligible_by_cell,
                        assignments=path.assignments,
                        missed_probe_ids=path.missed_probe_ids,
                        evidence=ReceiverPathSatelliteEvidenceBreakdown(
                            matched_base_cost=path.objective.matched_base_cost,
                            residual_cost=path.objective.residual_cost,
                            missed_detection_cost=path.objective.missed_detection_cost,
                            total_cost=math.fsum(
                                (
                                    path.objective.matched_base_cost,
                                    path.objective.residual_cost,
                                    path.objective.missed_detection_cost,
                                )
                            ),
                        ),
                    )
                    for path in checked.paths
                ),
            )
        )

    observation_by_path: dict[str, dict[str, CfoCandidate]] = {
        path.path_id: {item.observation_id: item for item in path.observations}
        for path in problem.paths
    }
    assigned_observation_owner: dict[tuple[str, str], str] = {}
    assigned_group_owner: dict[tuple[str, str], str] = {}
    consumed_groups_by_path: dict[str, set[str]] = {path.path_id: set() for path in problem.paths}
    for satellite in satellite_decisions:
        for satellite_path in satellite.paths:
            for assignment in satellite_path.assignments:
                observation = observation_by_path[satellite_path.path_id][assignment.observation_id]
                observation_key = (satellite_path.path_id, observation.observation_id)
                if observation_key in assigned_observation_owner:
                    raise ValueError(
                        "one path observation cannot be assigned to multiple satellites"
                    )
                assigned_observation_owner[observation_key] = satellite.hypothesis_id
                group_key = (satellite_path.path_id, observation.exclusion_group_id)
                if group_key in assigned_group_owner:
                    raise ValueError(
                        "one path-local physical exclusion group cannot feed multiple satellites"
                    )
                assigned_group_owner[group_key] = satellite.hypothesis_id
                consumed_groups_by_path[satellite_path.path_id].add(observation.exclusion_group_id)

    path_decisions = []
    for evidence_path in problem.paths:
        path_satellite_decisions = tuple(
            next(item for item in satellite.paths if item.path_id == evidence_path.path_id)
            for satellite in satellite_decisions
        )
        clutter_by_group = _clutter_by_group(evidence_path.observations)
        consumed_groups = consumed_groups_by_path[evidence_path.path_id]
        clutter_cost = math.fsum(
            cost
            for group_id, cost in sorted(clutter_by_group.items())
            if group_id not in consumed_groups
        )
        matched_cost = math.fsum(
            item.evidence.matched_base_cost for item in path_satellite_decisions
        )
        residual_cost = math.fsum(item.evidence.residual_cost for item in path_satellite_decisions)
        missed_cost = math.fsum(
            item.evidence.missed_detection_cost for item in path_satellite_decisions
        )
        null_cost = math.fsum(clutter_by_group.values())
        total_cost = math.fsum((clutter_cost, matched_cost, residual_cost, missed_cost))
        path_decisions.append(
            JointReceiverPathAssociationDecision(
                path_id=evidence_path.path_id,
                unexplained_observation_ids=tuple(
                    item.observation_id
                    for item in evidence_path.observations
                    if item.exclusion_group_id not in consumed_groups
                ),
                objective=ReceiverPathObjectiveBreakdown(
                    clutter_cost=clutter_cost,
                    matched_base_cost=matched_cost,
                    residual_cost=residual_cost,
                    missed_detection_cost=missed_cost,
                    null_cost=null_cost,
                    total_cost=total_cost,
                    delta_from_null=total_cost - null_cost,
                ),
            )
        )

    selected_satellites = tuple(item for item in satellite_decisions if item.selected)
    values = (
        math.fsum(item.objective.clutter_cost for item in path_decisions),
        math.fsum(item.objective.matched_base_cost for item in path_decisions),
        math.fsum(item.objective.residual_cost for item in path_decisions),
        math.fsum(item.objective.missed_detection_cost for item in path_decisions),
        len(selected_satellites) * problem.costs.satellite_cost,
        sum(len(item.episodes) for item in satellite_decisions) * problem.costs.episode_cost,
        math.fsum(
            hypothesis.delay_prior_cost
            for hypothesis in ordered_hypotheses
            if checked_by_hypothesis[hypothesis.hypothesis_id].selected
        ),
    )
    null_cost = math.fsum(item.objective.null_cost for item in path_decisions)
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
    return JointMultipathSatelliteAssociationResult(
        satellites=tuple(satellite_decisions),
        paths=tuple(path_decisions),
        objective=objective,
        algorithm=algorithm,
        exact=exact,
    )


@dataclass(frozen=True, slots=True)
class _FlattenedJointMultipathProblem:
    problem: SatelliteActivityProblem
    hypotheses: tuple[SingleSatelliteHypothesis, ...]
    probe_identity: dict[str, tuple[str, str]]
    observation_identity: dict[str, tuple[str, str]]


def _flatten_joint_multipath_problem(
    problem: MultipathSatelliteActivityProblem,
    hypotheses: tuple[FixedMultipathSatelliteHypothesis, ...],
) -> _FlattenedJointMultipathProblem:
    ordered_hypotheses = _canonical_hypotheses(problem, hypotheses)
    probes = []
    observations = []
    flattened_probe_by_path_local: dict[tuple[str, str], str] = {}
    probe_identity: dict[str, tuple[str, str]] = {}
    observation_identity: dict[str, tuple[str, str]] = {}

    for path_index, path in enumerate(problem.paths):
        for probe_index, probe in enumerate(path.probes):
            flattened_probe_id = f"p:{path_index}:{probe_index}"
            flattened_probe_by_path_local[path.path_id, probe.probe_id] = flattened_probe_id
            probe_identity[flattened_probe_id] = (path.path_id, probe.probe_id)
            probes.append(
                CfoProbe(
                    probe_id=flattened_probe_id,
                    time_s=probe.time_s,
                    cell_index=probe.cell_index,
                    missed_detection_cost=probe.missed_detection_cost,
                    usable=probe.usable,
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
                    probe_id=flattened_probe_by_path_local[
                        path.path_id,
                        observation.probe_id,
                    ],
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

    flattened_hypotheses = []
    for hypothesis in ordered_hypotheses:
        hypotheses_by_path = _path_hypotheses(problem, hypothesis)
        predictions = []
        eligible_probe_ids = []
        for path in problem.paths:
            path_hypothesis = hypotheses_by_path[path.path_id]
            eligible_by_cell = _effective_eligibility_by_cell(problem, path_hypothesis)
            prediction_by_probe = {
                item.probe_id: item.cfo_hz for item in path_hypothesis.predictions
            }
            for probe in path.probes:
                flattened_probe_id = flattened_probe_by_path_local[
                    path.path_id,
                    probe.probe_id,
                ]
                if eligible_by_cell[probe.cell_index]:
                    eligible_probe_ids.append(flattened_probe_id)
                predictions.append(
                    PredictedProbeCfo(
                        probe_id=flattened_probe_id,
                        cfo_hz=(
                            prediction_by_probe[probe.probe_id] + path_hypothesis.cfo_offset_hz
                        ),
                    )
                )
        flattened_hypotheses.append(
            SingleSatelliteHypothesis(
                hypothesis_id=hypothesis.hypothesis_id,
                object_name=hypothesis.object_name,
                catalog_number=hypothesis.catalog_number,
                delay_s=hypothesis.delay_s,
                cfo_offset_hz=0.0,
                delay_prior_cost=hypothesis.delay_prior_cost,
                predictions=tuple(predictions),
                eligible_probe_ids=tuple(eligible_probe_ids),
            )
        )

    return _FlattenedJointMultipathProblem(
        problem=SatelliteActivityProblem(
            grid=problem.grid,
            probes=tuple(probes),
            observations=tuple(observations),
            costs=problem.costs,
            truncated_observation_count=problem.truncated_observation_count,
        ),
        hypotheses=tuple(flattened_hypotheses),
        probe_identity=probe_identity,
        observation_identity=observation_identity,
    )


def decode_joint_fixed_multipath_satellites(
    problem: MultipathSatelliteActivityProblem,
    hypotheses: tuple[FixedMultipathSatelliteHypothesis, ...],
) -> JointMultipathSatelliteAssociationResult:
    """Exactly decode activity/assignments for two or three fixed states."""

    ordered_hypotheses = _canonical_hypotheses(problem, tuple(hypotheses))
    if problem.truncated_observation_count:
        raise ValueError(
            "exact joint multipath decoding requires complete path candidate inventories"
        )
    flattened = _flatten_joint_multipath_problem(problem, ordered_hypotheses)
    decoded = decode_joint_fixed_hypotheses(flattened.problem, flattened.hypotheses)

    schedules = []
    for decoded_satellite in decoded.satellites:
        assignments_by_path: dict[str, list[ProbeAssignment]] = {
            path.path_id: [] for path in problem.paths
        }
        for assignment in decoded_satellite.assignments:
            path_id, probe_id = flattened.probe_identity[assignment.probe_id]
            observation_path_id, observation_id = flattened.observation_identity[
                assignment.observation_id
            ]
            if observation_path_id != path_id:
                raise RuntimeError("flattened joint assignment crossed receiver paths")
            assignments_by_path[path_id].append(ProbeAssignment(probe_id, observation_id))
        schedules.append(
            JointMultipathSatelliteSchedule(
                hypothesis_id=decoded_satellite.hypothesis_id,
                activity_by_cell=decoded_satellite.activity_by_cell,
                path_assignments=tuple(
                    ReceiverPathAssignments(
                        path.path_id,
                        tuple(assignments_by_path[path.path_id]),
                    )
                    for path in problem.paths
                ),
            )
        )

    result = evaluate_joint_fixed_multipath_schedule(
        problem,
        ordered_hypotheses,
        tuple(schedules),
        algorithm="bounded-exact-fixed-nuisance-joint-multipath-semimarkov-v2",
        exact=True,
    )
    decoded_by_hypothesis = {item.hypothesis_id: item for item in decoded.satellites}
    for checked_satellite in result.satellites:
        flattened_satellite = decoded_by_hypothesis[checked_satellite.hypothesis_id]
        if checked_satellite.activity_by_cell != flattened_satellite.activity_by_cell:
            raise RuntimeError("joint multipath activity disagrees with flattened decoder")
        if checked_satellite.selected != flattened_satellite.selected:
            raise RuntimeError("joint multipath selection disagrees with flattened decoder")
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
            raise RuntimeError(
                f"joint multipath {field} disagrees with the flattened exact decoder"
            )
    if result.selected_catalog_numbers != decoded.selected_catalog_numbers:
        raise RuntimeError("joint multipath catalog selection disagrees with flattened decoder")
    return result
