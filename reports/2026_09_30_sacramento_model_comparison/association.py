"""Clean-room association baselines for the Sacramento model comparison.

The functions in this module operate only on already-normalized log scores.  They
do not predict Doppler, inspect geographic truth, or assign scientific meaning to
candidate labels.  Candidate exclusivity is an explicit benchmark assumption:
each candidate may explain at most one observation, while every observation has
its own non-exclusive background alternative.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite, log

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


class AssociationInputError(ValueError):
    """The association score matrix or its labels are invalid."""


class AssociationBudgetError(RuntimeError):
    """Exact enumeration would exceed its declared event budget."""


@dataclass(frozen=True, slots=True)
class AssociationProblem:
    """One scan-level association problem.

    ``signal_log_prior`` may be either one value per candidate or a full matrix.
    ``background_log_prior`` may be scalar or one value per observation.
    """

    signal_log_likelihood: FloatArray
    background_log_likelihood: FloatArray
    candidate_labels: tuple[str, ...]
    observation_labels: tuple[str, ...] = ()
    signal_log_prior: FloatArray | None = None
    background_log_prior: FloatArray | None = None

    def __post_init__(self) -> None:
        signal = np.asarray(self.signal_log_likelihood, dtype=np.float64)
        background = np.asarray(self.background_log_likelihood, dtype=np.float64)
        if signal.ndim != 2:
            raise AssociationInputError("signal_log_likelihood must be two-dimensional")
        n_observations, n_candidates = signal.shape
        if background.shape != (n_observations,):
            raise AssociationInputError("background_log_likelihood has the wrong shape")
        if (
            len(self.candidate_labels) != n_candidates
            or len(set(self.candidate_labels)) != n_candidates
        ):
            raise AssociationInputError("candidate labels must be unique and match the matrix")
        observations = self.observation_labels or tuple(
            f"observation-{i}" for i in range(n_observations)
        )
        if len(observations) != n_observations or len(set(observations)) != n_observations:
            raise AssociationInputError("observation labels must be unique and match the matrix")
        if np.isnan(signal).any() or np.isposinf(signal).any():
            raise AssociationInputError("signal scores may be finite or negative infinity")
        if (
            np.isnan(background).any()
            or np.isposinf(background).any()
            or np.isneginf(background).any()
        ):
            raise AssociationInputError("every observation needs a finite background score")
        signal_prior = _broadcast_prior(self.signal_log_prior, signal.shape, "signal_log_prior")
        background_prior = _broadcast_background_prior(
            self.background_log_prior, n_observations
        )
        object.__setattr__(self, "signal_log_likelihood", _readonly(signal))
        object.__setattr__(self, "background_log_likelihood", _readonly(background))
        object.__setattr__(self, "candidate_labels", tuple(self.candidate_labels))
        object.__setattr__(self, "observation_labels", observations)
        object.__setattr__(self, "signal_log_prior", signal_prior)
        object.__setattr__(self, "background_log_prior", background_prior)

    @property
    def log_signal_scores(self) -> FloatArray:
        return self.signal_log_likelihood + self.signal_log_prior

    @property
    def log_background_scores(self) -> FloatArray:
        return self.background_log_likelihood + self.background_log_prior


@dataclass(frozen=True, slots=True)
class JointHypothesis:
    assignments: tuple[str | None, ...]
    log_score: float
    probability: float


@dataclass(frozen=True, slots=True)
class AssociationResult:
    method: str
    hard_assignments: tuple[str | None, ...]
    signal_probabilities: FloatArray
    background_probabilities: FloatArray
    joint_log_evidence: float | None
    joint_hypotheses: tuple[JointHypothesis, ...]
    retained_probability: float
    discarded_probability: float
    candidate_exclusivity_assumed: bool = True
    probabilities_are_calibrated: bool = True
    status: str = "complete"


def hungarian_association(problem: AssociationProblem | object) -> AssociationResult:
    """Return the maximum-score one-to-one assignment with per-row background.

    The Hungarian algorithm is independently implemented here.  Marginals from a
    single maximum assignment are deliberately marked uncalibrated.
    """

    problem = _coerce_problem(problem)
    signal = problem.log_signal_scores
    background = problem.log_background_scores
    n_observations, n_candidates = signal.shape
    columns = n_candidates + n_observations
    scores = np.full((n_observations, columns), -np.inf, dtype=np.float64)
    scores[:, :n_candidates] = signal
    for row in range(n_observations):
        scores[row, n_candidates + row] = background[row]
    finite = scores[np.isfinite(scores)]
    scale = max(1.0, float(np.max(np.abs(finite))))
    invalid_cost = scale * (n_observations + columns + 2) * 1e6
    maximum = float(np.max(finite))
    costs = np.where(np.isfinite(scores), maximum - scores, invalid_cost)
    selected_columns = _hungarian_minimize(costs)
    assignments: list[str | None] = []
    signal_probabilities = np.zeros(signal.shape, dtype=np.float64)
    background_probabilities = np.zeros(n_observations, dtype=np.float64)
    score = 0.0
    for row, column in enumerate(selected_columns):
        if column < n_candidates and isfinite(float(signal[row, column])):
            assignments.append(problem.candidate_labels[column])
            signal_probabilities[row, column] = 1.0
            score += float(signal[row, column])
        else:
            assignments.append(None)
            background_probabilities[row] = 1.0
            score += float(background[row])
    hypothesis = JointHypothesis(tuple(assignments), score, 1.0)
    return AssociationResult(
        method="clean-room-hungarian-v1",
        hard_assignments=tuple(assignments),
        signal_probabilities=_readonly(signal_probabilities),
        background_probabilities=_readonly(background_probabilities),
        joint_log_evidence=None,
        joint_hypotheses=(hypothesis,),
        retained_probability=1.0,
        discarded_probability=0.0,
        probabilities_are_calibrated=False,
    )


def scipy_hungarian_association(problem: AssociationProblem | object) -> AssociationResult:
    """Run SciPy's BSD-licensed assignment solver on the identical cost matrix."""

    problem = _coerce_problem(problem)
    try:
        from scipy.optimize import linear_sum_assignment
    except ImportError as error:
        raise RuntimeError("G1 requires the pinned isolated SciPy environment") from error
    signal = problem.log_signal_scores
    background = problem.log_background_scores
    rows, candidates = signal.shape
    scores = np.full((rows, candidates + rows), -np.inf)
    scores[:, :candidates] = signal
    scores[np.arange(rows), candidates + np.arange(rows)] = background
    finite = scores[np.isfinite(scores)]
    scale = max(1.0, float(np.max(np.abs(finite))))
    cost = np.where(np.isfinite(scores), -scores, scale * (rows + candidates + 2) * 1e6)
    row_indices, columns = linear_sum_assignment(cost)
    selected = np.empty(rows, dtype=np.int64)
    selected[row_indices] = columns
    assignments: list[str | None] = []
    signal_probabilities = np.zeros(signal.shape)
    background_probabilities = np.zeros(rows)
    score = 0.0
    for row, column in enumerate(selected):
        if column < candidates:
            assignments.append(problem.candidate_labels[column])
            signal_probabilities[row, column] = 1.0
            score += float(signal[row, column])
        else:
            assignments.append(None)
            background_probabilities[row] = 1.0
            score += float(background[row])
    return AssociationResult(
        method="scipy-linear-sum-assignment-v1",
        hard_assignments=tuple(assignments),
        signal_probabilities=_readonly(signal_probabilities),
        background_probabilities=_readonly(background_probabilities),
        joint_log_evidence=None,
        joint_hypotheses=(JointHypothesis(tuple(assignments), score, 1.0),),
        retained_probability=1.0,
        discarded_probability=0.0,
        probabilities_are_calibrated=False,
    )


def exact_joint_association(
    problem: AssociationProblem | object,
    *,
    max_events: int = 1_000_000,
    retained_hypotheses: int | None = None,
) -> AssociationResult:
    """Enumerate and normalize every feasible joint association event.

    This is the probability-preserving M1/G2 oracle for small problems.  It raises
    before partial computation when a conservative event count exceeds the cap.
    """

    problem = _coerce_problem(problem)
    if max_events < 1:
        raise AssociationInputError("max_events must be positive")
    n_observations, n_candidates = problem.log_signal_scores.shape
    upper_bound = (n_candidates + 1) ** n_observations
    if upper_bound > max_events:
        if n_observations <= 2 and retained_hypotheses is not None:
            return _exact_pair_marginals(problem, retained_hypotheses)
        raise AssociationBudgetError(
            f"exact association upper bound {upper_bound} exceeds max_events={max_events}"
        )
    events: list[tuple[tuple[int | None, ...], float]] = []

    def visit(row: int, used: frozenset[int], chosen: tuple[int | None, ...], score: float) -> None:
        if row == n_observations:
            events.append((chosen, score))
            return
        visit(row + 1, used, (*chosen, None), score + float(problem.log_background_scores[row]))
        for candidate in range(n_candidates):
            candidate_score = float(problem.log_signal_scores[row, candidate])
            if candidate not in used and isfinite(candidate_score):
                visit(row + 1, used | {candidate}, (*chosen, candidate), score + candidate_score)

    visit(0, frozenset(), (), 0.0)
    if not events:  # Defensive: finite backgrounds guarantee at least one event.
        raise AssociationInputError("association problem has no feasible events")
    log_evidence = _logsumexp(tuple(score for _, score in events))
    probabilities = np.array([exp(score - log_evidence) for _, score in events])
    signal_marginals = np.zeros((n_observations, n_candidates), dtype=np.float64)
    background_marginals = np.zeros(n_observations, dtype=np.float64)
    for (assignment, _), probability in zip(events, probabilities, strict=True):
        for row, candidate in enumerate(assignment):
            if candidate is None:
                background_marginals[row] += probability
            else:
                signal_marginals[row, candidate] += probability
    ranked = sorted(zip(events, probabilities, strict=True), key=lambda item: -item[1])
    keep = len(ranked) if retained_hypotheses is None else retained_hypotheses
    if keep < 1:
        raise AssociationInputError("retained_hypotheses must be positive")
    hypotheses = tuple(
        JointHypothesis(
            tuple(None if c is None else problem.candidate_labels[c] for c in assignment),
            score,
            float(probability),
        )
        for ((assignment, score), probability) in ranked[:keep]
    )
    retained = float(sum(item.probability for item in hypotheses))
    map_assignment = hypotheses[0].assignments
    return AssociationResult(
        method="exact-joint-association-v1",
        hard_assignments=map_assignment,
        signal_probabilities=_readonly(signal_marginals),
        background_probabilities=_readonly(background_marginals),
        joint_log_evidence=log_evidence,
        joint_hypotheses=hypotheses,
        retained_probability=retained,
        discarded_probability=max(0.0, 1.0 - retained),
    )


def _exact_pair_marginals(
    problem: AssociationProblem, retained_hypotheses: int
) -> AssociationResult:
    """Analytic exact JPDA marginals for one or two rows and many candidates."""

    if retained_hypotheses < 1:
        raise AssociationInputError("retained_hypotheses must be positive")
    log_signal = problem.log_signal_scores
    log_background = problem.log_background_scores
    rows, candidates = log_signal.shape
    if rows == 1:
        log_evidence = _logsumexp_array(
            np.concatenate(([log_background[0]], log_signal[0]))
        )
        signal_marginals = np.exp(log_signal - log_evidence)
        background_marginals = np.exp(log_background - log_evidence)
    elif rows == 2:
        totals = np.array(
            [
                _logsumexp_array(np.concatenate(([log_background[row]], log_signal[row])))
                for row in range(2)
            ]
        )
        exclude_zero = _logsumexp_excluding_each(log_signal[0], log_background[0])
        exclude_one = _logsumexp_excluding_each(log_signal[1], log_background[1])
        log_evidence = _logsumexp_array(
            np.concatenate(
                (
                    [log_background[0] + totals[1]],
                    log_signal[0] + exclude_one,
                )
            )
        )
        signal_marginals = np.vstack(
            (
                np.exp(log_signal[0] + exclude_one - log_evidence),
                np.exp(log_signal[1] + exclude_zero - log_evidence),
            )
        )
        background_marginals = np.exp(
            np.array(
                [
                    log_background[0] + totals[1] - log_evidence,
                    log_background[1] + totals[0] - log_evidence,
                ]
            )
        )
    else:  # pragma: no cover - private caller constrains this path.
        raise AssociationInputError("analytic marginalization supports at most two rows")
    map_result = hungarian_association(problem)
    map_hypothesis = map_result.joint_hypotheses[0]
    map_probability = exp(map_hypothesis.log_score - log_evidence)
    hypothesis = JointHypothesis(
        map_hypothesis.assignments, map_hypothesis.log_score, map_probability
    )
    return AssociationResult(
        method="exact-pair-jpda-analytic-v1",
        hard_assignments=hypothesis.assignments,
        signal_probabilities=_readonly(signal_marginals),
        background_probabilities=_readonly(background_marginals),
        joint_log_evidence=log_evidence,
        joint_hypotheses=(hypothesis,),
        retained_probability=map_probability,
        discarded_probability=max(0.0, 1.0 - map_probability),
    )


def stone_soup_jpda_feasibility(
    problem: AssociationProblem | object,
    *,
    max_events: int = 100_000,
    retained_hypotheses: int | None = None,
) -> AssociationResult:
    """Evaluate the probability semantics required by a Stone Soup JPDA adapter.

    Stone Soup is intentionally not a runtime dependency.  This adapter-equivalent
    oracle establishes whether an externally generated likelihood matrix can be
    normalized under JPDA's one-detection/one-target event constraints.
    """

    result = exact_joint_association(
        problem, max_events=max_events, retained_hypotheses=retained_hypotheses
    )
    return AssociationResult(
        method="stone-soup-jpda-feasibility-v1",
        hard_assignments=result.hard_assignments,
        signal_probabilities=result.signal_probabilities,
        background_probabilities=result.background_probabilities,
        joint_log_evidence=result.joint_log_evidence,
        joint_hypotheses=result.joint_hypotheses,
        retained_probability=result.retained_probability,
        discarded_probability=result.discarded_probability,
    )


def stonesoup_library_jpda_association(
    problem: AssociationProblem | object,
    *,
    max_events: int = 100_000,
) -> AssociationResult:
    """Run the pinned Stone Soup JPDA enumerator with precomputed likelihoods.

    Candidate labels are Stone Soup tracks and observations are detections.
    Dividing each signal score by its observation background score makes an
    unassigned detection's implicit clutter weight exactly the requested private
    background alternative.  The adapter is restricted to preflighted small
    groups because upstream JPDA enumerates association events explicitly.
    """

    problem = _coerce_problem(problem)
    rows, candidates = problem.log_signal_scores.shape
    upper_bound = (rows + 1) ** candidates
    if upper_bound > max_events:
        raise AssociationBudgetError(
            f"Stone Soup JPDA upper bound {upper_bound} exceeds max_events={max_events}"
        )
    try:
        from stonesoup.dataassociator.probability import JPDA
        from stonesoup.types.detection import Detection, MissedDetection
        from stonesoup.types.hypothesis import SingleProbabilityHypothesis
        from stonesoup.types.multihypothesis import MultipleHypothesis
        from stonesoup.types.numeric import Probability
        from stonesoup.types.prediction import StatePrediction
    except ImportError as error:
        raise RuntimeError("G2 requires the pinned isolated Stone Soup environment") from error
    detections = [Detection(np.array([[float(row)]])) for row in range(rows)]
    tracks = list(problem.candidate_labels)
    hypotheses = {}
    for candidate, track in enumerate(tracks):
        prediction = StatePrediction(np.array([[float(candidate)]]))
        singles = [
            SingleProbabilityHypothesis(
                prediction, MissedDetection(), probability=Probability(1.0)
            )
        ]
        for row, detection in enumerate(detections):
            log_ratio = (
                float(problem.log_signal_scores[row, candidate])
                - float(problem.log_background_scores[row])
            )
            singles.append(
                SingleProbabilityHypothesis(
                    prediction,
                    detection,
                    probability=Probability(log_ratio, log_value=True),
                )
            )
        hypotheses[track] = MultipleHypothesis(singles)
    joints = JPDA.enumerate_JPDA_hypotheses(tracks, hypotheses)
    signal_marginals = np.zeros((rows, candidates))
    for joint in joints:
        probability = float(joint.probability)
        for candidate, track in enumerate(tracks):
            measurement = joint.hypotheses[track].measurement
            for row, detection in enumerate(detections):
                if measurement is detection:
                    signal_marginals[row, candidate] += probability
                    break
    background_marginals = 1.0 - signal_marginals.sum(axis=1)
    local = exact_joint_association(problem, max_events=max_events, retained_hypotheses=1)
    return AssociationResult(
        method="stonesoup-jpda-e5a3e09f-v1",
        hard_assignments=local.hard_assignments,
        signal_probabilities=_readonly(signal_marginals),
        background_probabilities=_readonly(background_marginals),
        joint_log_evidence=local.joint_log_evidence,
        joint_hypotheses=local.joint_hypotheses,
        retained_probability=local.retained_probability,
        discarded_probability=local.discarded_probability,
    )


def _coerce_problem(value: AssociationProblem | object) -> AssociationProblem:
    """Accept the comparison core's structurally identical problem dataclass."""

    if isinstance(value, AssociationProblem):
        return value
    try:
        return AssociationProblem(
            signal_log_likelihood=value.signal_log_likelihood,
            background_log_likelihood=value.background_log_likelihood,
            candidate_labels=tuple(value.candidate_labels),
            observation_labels=tuple(getattr(value, "observation_labels", ())),
            signal_log_prior=getattr(value, "signal_log_prior", None),
            background_log_prior=getattr(value, "background_log_prior", None),
        )
    except (AttributeError, TypeError) as error:
        raise AssociationInputError(
            "object does not implement AssociationProblem fields"
        ) from error


def _hungarian_minimize(cost: FloatArray) -> tuple[int, ...]:
    """Rectangular shortest-augmenting-path Hungarian algorithm for rows <= columns."""

    n_rows, n_columns = cost.shape
    if n_rows > n_columns:
        raise AssociationInputError("Hungarian matrix must have at least as many columns as rows")
    u = np.zeros(n_rows + 1)
    v = np.zeros(n_columns + 1)
    matched_row = np.zeros(n_columns + 1, dtype=np.int64)
    predecessor = np.zeros(n_columns + 1, dtype=np.int64)
    for row in range(1, n_rows + 1):
        matched_row[0] = row
        minimum = np.full(n_columns + 1, np.inf)
        used = np.zeros(n_columns + 1, dtype=bool)
        column = 0
        while True:
            used[column] = True
            active_row = int(matched_row[column])
            delta = np.inf
            next_column = 0
            for candidate_column in range(1, n_columns + 1):
                if not used[candidate_column]:
                    reduced = (
                        cost[active_row - 1, candidate_column - 1]
                        - u[active_row]
                        - v[candidate_column]
                    )
                    if reduced < minimum[candidate_column]:
                        minimum[candidate_column] = reduced
                        predecessor[candidate_column] = column
                    if minimum[candidate_column] < delta:
                        delta = minimum[candidate_column]
                        next_column = candidate_column
            for candidate_column in range(n_columns + 1):
                if used[candidate_column]:
                    u[matched_row[candidate_column]] += delta
                    v[candidate_column] -= delta
                else:
                    minimum[candidate_column] -= delta
            column = next_column
            if matched_row[column] == 0:
                break
        while True:
            previous = int(predecessor[column])
            matched_row[column] = matched_row[previous]
            column = previous
            if column == 0:
                break
    result = [-1] * n_rows
    for column in range(1, n_columns + 1):
        if matched_row[column] != 0:
            result[int(matched_row[column]) - 1] = column - 1
    return tuple(result)


def _broadcast_prior(value: FloatArray | None, shape: tuple[int, int], name: str) -> FloatArray:
    if value is None:
        return _readonly(np.zeros(shape, dtype=np.float64))
    array = np.asarray(value, dtype=np.float64)
    if array.shape == (shape[1],):
        array = np.broadcast_to(array, shape).copy()
    if array.shape != shape or not np.all(np.isfinite(array)):
        raise AssociationInputError(f"{name} must be finite with candidate or matrix shape")
    return _readonly(array)


def _broadcast_background_prior(value: FloatArray | None, size: int) -> FloatArray:
    if value is None:
        return _readonly(np.zeros(size, dtype=np.float64))
    array = np.asarray(value, dtype=np.float64)
    if array.ndim == 0:
        array = np.full(size, float(array), dtype=np.float64)
    if array.shape != (size,) or not np.all(np.isfinite(array)):
        raise AssociationInputError(
            "background_log_prior must be finite and scalar or per observation"
        )
    return _readonly(array)


def _readonly(value: FloatArray) -> FloatArray:
    result = np.array(value, dtype=np.float64, copy=True)
    result.setflags(write=False)
    return result


def _logsumexp(values: tuple[float, ...]) -> float:
    maximum = max(values)
    return maximum + log(sum(exp(value - maximum) for value in values))


def _logsumexp_array(values: FloatArray) -> float:
    return float(np.logaddexp.reduce(values))


def _logsumexp_excluding_each(log_values: FloatArray, log_background: float) -> FloatArray:
    """Log sum of background and every value except the corresponding index."""

    count = log_values.size
    prefix = np.full(count + 1, -np.inf)
    suffix = np.full(count + 1, -np.inf)
    prefix[0] = log_background
    for index in range(count):
        prefix[index + 1] = np.logaddexp(prefix[index], log_values[index])
    for index in range(count - 1, -1, -1):
        suffix[index] = np.logaddexp(suffix[index + 1], log_values[index])
    return np.logaddexp(prefix[:count], suffix[1:])
