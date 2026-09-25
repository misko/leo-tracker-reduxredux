"""Bounded exact joint activity association for fixed satellite hypotheses.

This research-only module extends :mod:`satellite_activity` from one fixed
satellite to a deliberately small, already-gated set of fixed hypotheses.  It
does not query a catalogue, propagate TLEs, read persisted products, or fit
continuous parameters.  Each supplied hypothesis already fixes one orbital
delay and one CFO offset for the whole problem.

The decoder is exact for two or three hypotheses.  It combines each
satellite's minimum-duration semi-Markov state in a factorial dynamic program
and solves the remaining per-probe observation assignment by exhaustive
matching.  Complexity is exponential in hypothesis count by design; this is a
bounded reference solver and numerical oracle for a later mixed-integer
implementation, not a catalogue-scale search.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

from leo.analysis.research.satellite_activity import (
    ActivityEpisode,
    CfoCandidate,
    CfoProbe,
    ObjectiveBreakdown,
    ProbeAssignment,
    SatelliteActivityProblem,
    SingleSatelliteHypothesis,
    _eligible_probe_ids,
    huber_loss,
)

MINIMUM_EXACT_HYPOTHESES = 2
MAXIMUM_EXACT_HYPOTHESES = 3


def _nonempty(value: str, label: str) -> None:
    if not value:
        raise ValueError(f"{label} must not be empty")


@dataclass(frozen=True, slots=True)
class JointSatelliteSchedule:
    """One fixed hypothesis's proposed activity and native-probe assignments."""

    hypothesis_id: str
    activity_by_cell: tuple[bool, ...]
    assignments: tuple[ProbeAssignment, ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.hypothesis_id, "schedule hypothesis ID")
        activity = tuple(self.activity_by_cell)
        if any(not isinstance(value, bool) for value in activity):
            raise ValueError("activity mask values must be booleans")
        object.__setattr__(self, "activity_by_cell", activity)
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
class JointSatelliteDecision:
    """One fixed hypothesis's checked contribution to a joint result."""

    hypothesis_id: str
    object_name: str
    catalog_number: int
    delay_s: float
    cfo_offset_hz: float
    selected: bool
    activity_by_cell: tuple[bool, ...]
    episodes: tuple[ActivityEpisode, ...]
    assignments: tuple[ProbeAssignment, ...]
    missed_probe_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class JointSatelliteAssociationResult:
    """A globally exclusive joint schedule and independently checked objective."""

    satellites: tuple[JointSatelliteDecision, ...]
    unexplained_observation_ids: tuple[str, ...]
    objective: ObjectiveBreakdown
    algorithm: str
    exact: bool

    @property
    def selected_catalog_numbers(self) -> tuple[int, ...]:
        return tuple(item.catalog_number for item in self.satellites if item.selected)


def _canonical_hypotheses(
    hypotheses: tuple[SingleSatelliteHypothesis, ...],
) -> tuple[SingleSatelliteHypothesis, ...]:
    if not hypotheses:
        raise ValueError("joint satellite association needs at least one hypothesis")
    hypothesis_ids = tuple(item.hypothesis_id for item in hypotheses)
    if len(set(hypothesis_ids)) != len(hypothesis_ids):
        raise ValueError("joint satellite hypothesis IDs must be unique")
    catalog_numbers = tuple(item.catalog_number for item in hypotheses)
    if len(set(catalog_numbers)) != len(catalog_numbers):
        raise ValueError(
            "the bounded fixed-hypothesis solver accepts only one hypothesis per catalog"
        )
    return tuple(
        sorted(
            hypotheses,
            key=lambda item: (item.catalog_number, item.object_name, item.hypothesis_id),
        )
    )


def _predictions_by_hypothesis(
    problem: SatelliteActivityProblem,
    hypotheses: tuple[SingleSatelliteHypothesis, ...],
) -> tuple[dict[str, float], ...]:
    expected = {item.probe_id for item in problem.probes}
    result = []
    for hypothesis in hypotheses:
        prediction = {item.probe_id: item.cfo_hz for item in hypothesis.predictions}
        if set(prediction) != expected:
            raise ValueError("every joint hypothesis must predict every scheduled probe exactly")
        result.append(prediction)
    return tuple(result)


def _activity_episodes(
    problem: SatelliteActivityProblem,
    activity_by_cell: tuple[bool, ...],
) -> tuple[ActivityEpisode, ...]:
    grid = problem.grid
    if len(activity_by_cell) != grid.cell_count:
        raise ValueError("activity mask length disagrees with the activity grid")

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


def _clutter_cost_by_group(problem: SatelliteActivityProblem) -> dict[str, float]:
    result: dict[str, float] = {}
    for observation in problem.observations:
        result.setdefault(observation.exclusion_group_id, observation.clutter_cost)
    return result


def evaluate_joint_satellite_schedule(
    problem: SatelliteActivityProblem,
    hypotheses: tuple[SingleSatelliteHypothesis, ...],
    schedules: tuple[JointSatelliteSchedule, ...] = (),
    *,
    algorithm: str = "independent-joint-objective-checker-v1",
    exact: bool = False,
) -> JointSatelliteAssociationResult:
    """Validate and independently score a multi-satellite fixed-hypothesis schedule.

    Clutter is accounted once per physical exclusion group.  Miss cost is paid
    independently for every RF-eligible, usable ``(active satellite, probe)``
    pair without an assignment.  Ineligible observations remain clutter.
    """

    _nonempty(algorithm, "association algorithm")
    ordered_hypotheses = _canonical_hypotheses(hypotheses)
    predictions = _predictions_by_hypothesis(problem, ordered_hypotheses)
    eligible_by_hypothesis = tuple(
        _eligible_probe_ids(problem, hypothesis) for hypothesis in ordered_hypotheses
    )
    hypothesis_index = {item.hypothesis_id: index for index, item in enumerate(ordered_hypotheses)}
    schedule_ids = tuple(item.hypothesis_id for item in schedules)
    if len(set(schedule_ids)) != len(schedule_ids):
        raise ValueError("joint schedules must have unique hypothesis IDs")
    unknown = sorted(set(schedule_ids) - set(hypothesis_index))
    if unknown:
        raise ValueError(f"joint schedule references unknown hypotheses: {unknown!r}")
    supplied = {item.hypothesis_id: item for item in schedules}

    probe_by_id = {item.probe_id: item for item in problem.probes}
    observation_by_id = {item.observation_id: item for item in problem.observations}
    assigned_observation_owner: dict[str, str] = {}
    assigned_group_owner: dict[str, str] = {}
    prepared: list[
        tuple[
            SingleSatelliteHypothesis,
            tuple[bool, ...],
            tuple[ActivityEpisode, ...],
            tuple[ProbeAssignment, ...],
        ]
    ] = []

    for hypothesis in ordered_hypotheses:
        schedule = supplied.get(
            hypothesis.hypothesis_id,
            JointSatelliteSchedule(
                hypothesis_id=hypothesis.hypothesis_id,
                activity_by_cell=(False,) * problem.grid.cell_count,
            ),
        )
        activity = schedule.activity_by_cell
        episodes = _activity_episodes(problem, activity)
        seen_probes: set[str] = set()
        for assignment in schedule.assignments:
            if assignment.probe_id in seen_probes:
                raise ValueError("one satellite cannot consume multiple observations in one probe")
            seen_probes.add(assignment.probe_id)
            probe = probe_by_id.get(assignment.probe_id)
            observation = observation_by_id.get(assignment.observation_id)
            if probe is None or observation is None:
                raise ValueError("assignment references an unknown probe or observation")
            if observation.probe_id != assignment.probe_id:
                raise ValueError("assignment observation belongs to a different probe")
            if not probe.usable:
                raise ValueError("an unusable probe cannot receive an assignment")
            hypothesis_position = hypothesis_index[hypothesis.hypothesis_id]
            if probe.probe_id not in eligible_by_hypothesis[hypothesis_position]:
                raise ValueError("an RF-ineligible probe cannot receive an assignment")
            if not activity[probe.cell_index]:
                raise ValueError(
                    "an observation cannot be assigned while the satellite is inactive"
                )
            prior_observation_owner = assigned_observation_owner.setdefault(
                assignment.observation_id,
                hypothesis.hypothesis_id,
            )
            if prior_observation_owner != hypothesis.hypothesis_id:
                raise ValueError("one observation cannot be assigned to multiple satellites")
            prior_group_owner = assigned_group_owner.setdefault(
                observation.exclusion_group_id,
                hypothesis.hypothesis_id,
            )
            if prior_group_owner != hypothesis.hypothesis_id:
                raise ValueError(
                    "one physical exclusion group cannot be assigned to multiple satellites"
                )
        prepared.append((hypothesis, activity, episodes, schedule.assignments))

    # A second observation from one alias group is invalid even if the same
    # satellite owns both at different syntactic observation IDs.
    assigned_groups = []
    for hypothesis, _activity, _episodes, assignments in prepared:
        for assignment in assignments:
            assigned_groups.append(
                (
                    observation_by_id[assignment.observation_id].exclusion_group_id,
                    hypothesis.hypothesis_id,
                )
            )
    if len({group for group, _owner in assigned_groups}) != len(assigned_groups):
        raise ValueError("one physical exclusion group cannot be assigned more than once")

    matched_terms = []
    residual_terms = []
    missed_terms: list[float] = []
    satellite_count = 0
    episode_count = 0
    delay_prior_terms = []
    decisions = []
    for index, (hypothesis, activity, episodes, assignments) in enumerate(prepared):
        selected = bool(episodes)
        satellite_count += int(selected)
        episode_count += len(episodes)
        if selected:
            delay_prior_terms.append(hypothesis.delay_prior_cost)
        assigned_probe_ids = {item.probe_id for item in assignments}
        for assignment in assignments:
            observation = observation_by_id[assignment.observation_id]
            predicted = predictions[index][assignment.probe_id] + hypothesis.cfo_offset_hz
            residual = (observation.cfo_hz - predicted) / observation.sigma_hz
            matched_terms.append(observation.matched_base_cost)
            residual_terms.append(huber_loss(residual, problem.costs.huber_threshold))
        missed = tuple(
            probe.probe_id
            for probe in problem.probes
            if probe.usable
            and probe.probe_id in eligible_by_hypothesis[index]
            and activity[probe.cell_index]
            and probe.probe_id not in assigned_probe_ids
        )
        missed_terms.extend(probe_by_id[probe_id].missed_detection_cost for probe_id in missed)
        decisions.append(
            JointSatelliteDecision(
                hypothesis_id=hypothesis.hypothesis_id,
                object_name=hypothesis.object_name,
                catalog_number=hypothesis.catalog_number,
                delay_s=hypothesis.delay_s,
                cfo_offset_hz=hypothesis.cfo_offset_hz,
                selected=selected,
                activity_by_cell=activity,
                episodes=episodes,
                assignments=assignments,
                missed_probe_ids=missed,
            )
        )

    clutter_by_group = _clutter_cost_by_group(problem)
    consumed_groups = {group for group, _owner in assigned_groups}
    values = (
        math.fsum(
            cost for group, cost in sorted(clutter_by_group.items()) if group not in consumed_groups
        ),
        math.fsum(matched_terms),
        math.fsum(residual_terms),
        math.fsum(missed_terms),
        satellite_count * problem.costs.satellite_cost,
        episode_count * problem.costs.episode_cost,
        math.fsum(delay_prior_terms),
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
    return JointSatelliteAssociationResult(
        satellites=tuple(decisions),
        unexplained_observation_ids=tuple(
            item.observation_id
            for item in problem.observations
            if item.exclusion_group_id not in consumed_groups
        ),
        objective=objective,
        algorithm=algorithm,
        exact=exact,
    )


@dataclass(frozen=True, slots=True)
class _ProbeMatch:
    reduced_cost: float
    assignments: tuple[tuple[int, ProbeAssignment], ...]


def _probe_match(
    probe: CfoProbe,
    observations: tuple[CfoCandidate, ...],
    active: tuple[bool, ...],
    hypotheses: tuple[SingleSatelliteHypothesis, ...],
    predictions: tuple[dict[str, float], ...],
    eligible_by_hypothesis: tuple[frozenset[str], ...],
    problem: SatelliteActivityProblem,
) -> _ProbeMatch:
    if not probe.usable:
        return _ProbeMatch(0.0, ())
    active_indices = tuple(
        index
        for index, value in enumerate(active)
        if value and probe.probe_id in eligible_by_hypothesis[index]
    )
    if not active_indices:
        return _ProbeMatch(0.0, ())

    options: tuple[CfoCandidate | None, ...] = (None, *observations)
    candidates = []
    for choices in itertools.product(options, repeat=len(active_indices)):
        assigned = tuple(item for item in choices if item is not None)
        groups = tuple(item.exclusion_group_id for item in assigned)
        if len(set(groups)) != len(groups):
            continue
        reduced_terms = []
        assignment_pairs = []
        for hypothesis_index, observation in zip(active_indices, choices, strict=True):
            if observation is None:
                reduced_terms.append(probe.missed_detection_cost)
                continue
            hypothesis = hypotheses[hypothesis_index]
            predicted = predictions[hypothesis_index][probe.probe_id] + hypothesis.cfo_offset_hz
            residual = (observation.cfo_hz - predicted) / observation.sigma_hz
            reduced_terms.append(
                observation.matched_base_cost
                + huber_loss(residual, problem.costs.huber_threshold)
                - observation.clutter_cost
            )
            assignment_pairs.append(
                (
                    hypothesis_index,
                    ProbeAssignment(probe.probe_id, observation.observation_id),
                )
            )
        assignment_tuple = tuple(assignment_pairs)
        signature = tuple(
            (hypotheses[index].hypothesis_id, assignment.observation_id)
            for index, assignment in assignment_tuple
        )
        candidates.append(
            (
                math.fsum(reduced_terms),
                len(assignment_tuple),
                signature,
                assignment_tuple,
            )
        )
    reduced_cost, _count, _signature, selected_assignments = min(candidates)
    return _ProbeMatch(reduced_cost, selected_assignments)


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
    """Return ``(next state, active, starts episode)`` in canonical order."""

    ordinary_start = mature if mature == 1 else 1
    if state == _UNUSED:
        start = mature if cell_index == 0 and allow_left_censored else ordinary_start
        return ((_UNUSED, False, False), (start, True, True))
    if state == _OFF_AFTER_USE:
        return ((_OFF_AFTER_USE, False, False), (ordinary_start, True, True))
    if state == mature:
        return ((_OFF_AFTER_USE, False, False), (mature, True, False))
    return ((state + 1, True, False),)


@dataclass(frozen=True, slots=True)
class _JointDpEntry:
    reduced_cost: float
    selected_count: int
    episode_count: int
    active_cell_count: int
    activity_codes: tuple[int, ...]


def _entry_key(entry: _JointDpEntry) -> tuple[object, ...]:
    # Hypotheses are ordered by catalog number.  After all scientific and
    # structural terms tie, prefer the lexically earlier selected catalog set
    # before comparing the detailed activity masks.  Without this explicit
    # key, Python's ``False < True`` ordering would counter-intuitively prefer
    # leaving the lowest catalog number inactive.
    selected_catalog_key = tuple(not bool(code) for code in entry.activity_codes)
    return (
        entry.reduced_cost,
        entry.selected_count,
        entry.episode_count,
        entry.active_cell_count,
        selected_catalog_key,
        entry.activity_codes,
    )


def _activity_from_code(code: int, cell_count: int) -> tuple[bool, ...]:
    return tuple(bool(code & (1 << shift)) for shift in range(cell_count - 1, -1, -1))


def decode_joint_fixed_hypotheses(
    problem: SatelliteActivityProblem,
    hypotheses: tuple[SingleSatelliteHypothesis, ...],
) -> JointSatelliteAssociationResult:
    """Exactly decode two or three fixed satellite hypotheses.

    The deterministic tie policy is: lower objective, then fewer selected
    satellites, fewer episodes, fewer active satellite-cells, lexicographically
    earlier selected catalog identities, smaller canonical activity masks, and
    finally the local assignment policy of fewer matches followed by lexical
    hypothesis/observation identity.
    """

    ordered_hypotheses = _canonical_hypotheses(hypotheses)
    hypothesis_count = len(ordered_hypotheses)
    if not MINIMUM_EXACT_HYPOTHESES <= hypothesis_count <= MAXIMUM_EXACT_HYPOTHESES:
        raise ValueError("the bounded exact joint decoder requires two or three fixed hypotheses")
    if problem.truncated_observation_count:
        raise ValueError(
            "the bounded exact joint decoder requires an untruncated candidate inventory"
        )
    predictions = _predictions_by_hypothesis(problem, ordered_hypotheses)
    eligible_by_hypothesis = tuple(
        _eligible_probe_ids(problem, hypothesis) for hypothesis in ordered_hypotheses
    )
    observations_by_probe: dict[str, tuple[CfoCandidate, ...]] = {
        probe.probe_id: tuple(
            item for item in problem.observations if item.probe_id == probe.probe_id
        )
        for probe in problem.probes
    }
    probe_matches: dict[tuple[str, int], _ProbeMatch] = {}
    for probe in problem.probes:
        for active_code in range(1 << hypothesis_count):
            active = tuple(bool(active_code & (1 << index)) for index in range(hypothesis_count))
            probe_matches[probe.probe_id, active_code] = _probe_match(
                probe,
                observations_by_probe[probe.probe_id],
                active,
                ordered_hypotheses,
                predictions,
                eligible_by_hypothesis,
                problem,
            )

    cell_reduced: dict[tuple[int, int], float] = {}
    for cell_index in range(problem.grid.cell_count):
        cell_probes = tuple(item for item in problem.probes if item.cell_index == cell_index)
        for active_code in range(1 << hypothesis_count):
            cell_reduced[cell_index, active_code] = math.fsum(
                probe_matches[probe.probe_id, active_code].reduced_cost for probe in cell_probes
            )

    mature = problem.grid.minimum_active_cells
    initial_state = (_UNUSED,) * hypothesis_count
    previous: dict[tuple[int, ...], _JointDpEntry] = {
        initial_state: _JointDpEntry(
            reduced_cost=0.0,
            selected_count=0,
            episode_count=0,
            active_cell_count=0,
            activity_codes=(0,) * hypothesis_count,
        )
    }
    for cell_index in range(problem.grid.cell_count):
        current: dict[tuple[int, ...], _JointDpEntry] = {}
        for state in sorted(
            previous,
            key=lambda value: tuple(_state_order(item, mature) for item in value),
        ):
            transition_sets = tuple(
                _transitions(
                    item,
                    cell_index=cell_index,
                    mature=mature,
                    allow_left_censored=problem.grid.allow_left_censored,
                )
                for item in state
            )
            for transitions in itertools.product(*transition_sets):
                next_state = tuple(item[0] for item in transitions)
                active = tuple(item[1] for item in transitions)
                starts = tuple(item[2] for item in transitions)
                active_code = sum((1 << index) for index, value in enumerate(active) if value)
                first_starts = tuple(
                    index
                    for index, starts_episode in enumerate(starts)
                    if starts_episode and state[index] == _UNUSED
                )
                parent = previous[state]
                structural = sum(starts) * problem.costs.episode_cost
                structural += len(first_starts) * problem.costs.satellite_cost
                structural += math.fsum(
                    ordered_hypotheses[index].delay_prior_cost for index in first_starts
                )
                candidate = _JointDpEntry(
                    reduced_cost=(
                        parent.reduced_cost + structural + cell_reduced[cell_index, active_code]
                    ),
                    selected_count=parent.selected_count + len(first_starts),
                    episode_count=parent.episode_count + sum(starts),
                    active_cell_count=parent.active_cell_count + sum(active),
                    activity_codes=tuple(
                        (code << 1) | int(value)
                        for code, value in zip(parent.activity_codes, active, strict=True)
                    ),
                )
                existing = current.get(next_state)
                if existing is None or _entry_key(candidate) < _entry_key(existing):
                    current[next_state] = candidate
        previous = current

    single_terminal = [_UNUSED, _OFF_AFTER_USE, mature]
    if problem.grid.allow_right_censored:
        single_terminal.extend(range(1, mature))
    terminal_states = tuple(
        state
        for state in itertools.product(dict.fromkeys(single_terminal), repeat=hypothesis_count)
        if state in previous
    )
    if not terminal_states:
        raise RuntimeError("joint semi-Markov decoder has no feasible terminal state")
    final_state = min(
        terminal_states,
        key=lambda state: (
            _entry_key(previous[state]),
            tuple(_state_order(item, mature) for item in state),
        ),
    )
    best = previous[final_state]
    activities = tuple(
        _activity_from_code(code, problem.grid.cell_count) for code in best.activity_codes
    )
    assignments: list[list[ProbeAssignment]] = [[] for _item in ordered_hypotheses]
    for probe in problem.probes:
        active_code = sum(
            (1 << index) for index, activity in enumerate(activities) if activity[probe.cell_index]
        )
        for hypothesis_index, assignment in probe_matches[
            probe.probe_id,
            active_code,
        ].assignments:
            assignments[hypothesis_index].append(assignment)
    schedules = tuple(
        JointSatelliteSchedule(
            hypothesis_id=hypothesis.hypothesis_id,
            activity_by_cell=activities[index],
            assignments=tuple(assignments[index]),
        )
        for index, hypothesis in enumerate(ordered_hypotheses)
    )
    result = evaluate_joint_satellite_schedule(
        problem,
        ordered_hypotheses,
        schedules,
        algorithm="bounded-exact-factorial-semimarkov-v1",
        exact=True,
    )
    expected = result.objective.null_cost + best.reduced_cost
    if not math.isclose(result.objective.total_cost, expected, rel_tol=1e-12, abs_tol=1e-9):
        raise RuntimeError("joint semi-Markov reduced cost disagrees with objective checker")
    if len(result.selected_catalog_numbers) != best.selected_count:
        raise RuntimeError("joint semi-Markov selected count disagrees with objective checker")
    return result
