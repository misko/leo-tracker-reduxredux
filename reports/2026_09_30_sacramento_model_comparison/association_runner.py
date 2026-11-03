"""Position-evaluation integration for the Sacramento association arms.

The numerical runner supplies Doppler likelihood matrices evaluated at fixed
position hypotheses.  This module combines them only inside independently
formed competition groups.  Candidate reuse across groups is allowed, which is
required for separated fragments and observations from different receivers.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import asdict, dataclass
from math import exp, log
from pathlib import Path
from typing import Any, Literal

import numpy as np

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("sacramento_association", HERE / "association.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load association implementation")
association = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = association
SPEC.loader.exec_module(association)

Arm = Literal["G1", "M1", "G2"]
_GROUP_ATTESTATIONS = {
    "response-independent-same-rx-overlap-v1",
    "response-independent-singleton-v1",
}


@dataclass(frozen=True, slots=True)
class CompetitionGroup:
    group_id: str
    observation_labels: tuple[str, ...]
    candidate_labels: tuple[str, ...]
    signal_log_likelihood: np.ndarray
    background_log_likelihood: np.ndarray
    formation_attestation: str

    def __post_init__(self) -> None:
        if not self.group_id:
            raise association.AssociationInputError("group_id must be non-empty")
        if self.formation_attestation not in _GROUP_ATTESTATIONS:
            raise association.AssociationInputError(
                "competition groups require a response-independent formation attestation"
            )
        problem = association.AssociationProblem(
            self.signal_log_likelihood,
            self.background_log_likelihood,
            self.candidate_labels,
            self.observation_labels,
        )
        if (
            self.formation_attestation == "response-independent-singleton-v1"
            and len(problem.observation_labels) != 1
        ):
            raise association.AssociationInputError("singleton groups must contain exactly one row")
        object.__setattr__(self, "signal_log_likelihood", problem.signal_log_likelihood)
        object.__setattr__(self, "background_log_likelihood", problem.background_log_likelihood)
        object.__setattr__(self, "candidate_labels", problem.candidate_labels)
        object.__setattr__(self, "observation_labels", problem.observation_labels)

    def problem(self):
        return association.AssociationProblem(
            self.signal_log_likelihood,
            self.background_log_likelihood,
            self.candidate_labels,
            self.observation_labels,
        )


@dataclass(frozen=True, slots=True)
class PositionAssociationInput:
    position_id: str
    east_km: float
    north_km: float
    log_prior_weight: float
    groups: tuple[CompetitionGroup, ...]


@dataclass(frozen=True, slots=True)
class PositionHypothesis:
    position_id: str
    east_km: float
    north_km: float
    log_joint_score: float
    posterior_probability: float
    group_assignments: tuple[tuple[str | None, ...], ...]


@dataclass(frozen=True, slots=True)
class PositionAssociationResult:
    arm: Arm
    status: str
    point_estimate_east_km: float
    point_estimate_north_km: float
    log_evidence: float
    position_hypotheses: tuple[PositionHypothesis, ...]
    retained_probability: float
    discarded_probability: float
    evaluated_position_count: int
    evaluated_group_count: int
    probability_scope: str
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PositionLocalAssociationScore:
    method: Arm
    log_score: float
    group_assignments: tuple[tuple[str | None, ...], ...]
    group_count: int
    exact_probability_semantics: bool


def score_position_associations(
    groups: tuple[CompetitionGroup, ...],
    method: Arm,
    *,
    max_events_per_group: int = 100_000,
) -> PositionLocalAssociationScore:
    """Combine association evidence at one position without geographic truth.

    When trustworthy competition groups are unavailable, callers may supply one
    response-independent singleton group per retained track.  M1/G2 then exactly
    marginalize every track's candidate/background label without claiming
    scan-wide satellite exclusivity.  G1 takes the hard best label per track.
    """

    if method not in {"G1", "M1", "G2"}:
        raise ValueError(f"unsupported association method {method}")
    total = 0.0
    assignments: list[tuple[str | None, ...]] = []
    for group in groups:
        if method == "G1":
            result = association.scipy_hungarian_association(group.problem())
            total += result.joint_hypotheses[0].log_score
        elif method == "M1":
            result = association.exact_joint_association(
                group.problem(), max_events=max_events_per_group, retained_hypotheses=1
            )
            assert result.joint_log_evidence is not None
            total += result.joint_log_evidence
        else:
            result = association.exact_joint_association(
                group.problem(), max_events=max_events_per_group, retained_hypotheses=1
            )
            assert result.joint_log_evidence is not None
            total += result.joint_log_evidence
        assignments.append(result.hard_assignments)
    return PositionLocalAssociationScore(
        method=method,
        log_score=total,
        group_assignments=tuple(assignments),
        group_count=len(groups),
        exact_probability_semantics=method != "G1",
    )


def evaluate_position_hypotheses(
    positions: tuple[PositionAssociationInput, ...],
    *,
    arm: Arm,
    max_events_per_group: int = 100_000,
    retained_positions: int = 64,
) -> PositionAssociationResult:
    """Score a frozen finite position set with grouped association likelihoods.

    M1 and G2 use exact joint association evidence within every group.  Thus
    retained/discarded mass is exact over the supplied finite position set.  It
    does not certify discretization error or mass outside that set.  G1 uses a
    hard maximum assignment and its normalized position weights are explicitly
    pseudo-posterior weights.
    """

    if arm not in {"G1", "M1", "G2"}:
        raise ValueError(f"unsupported association arm {arm}")
    if not positions or retained_positions < 1:
        raise ValueError("positions and retained_positions must be non-empty")
    position_ids = tuple(item.position_id for item in positions)
    if len(set(position_ids)) != len(position_ids):
        raise ValueError("position IDs must be unique")
    scored: list[tuple[PositionAssociationInput, float, tuple[tuple[str | None, ...], ...]]] = []
    group_count = 0
    for position in positions:
        if not np.isfinite(position.log_prior_weight):
            raise ValueError("position prior weights must be finite")
        local = score_position_associations(
            position.groups, arm, max_events_per_group=max_events_per_group
        )
        group_count += local.group_count
        scored.append(
            (
                position,
                float(position.log_prior_weight) + local.log_score,
                local.group_assignments,
            )
        )
    log_evidence = _logsumexp(tuple(item[1] for item in scored))
    ranked = sorted(scored, key=lambda item: -item[1])
    hypotheses = tuple(
        PositionHypothesis(
            item.position_id,
            item.east_km,
            item.north_km,
            score,
            exp(score - log_evidence),
            assignments,
        )
        for item, score, assignments in ranked[:retained_positions]
    )
    retained = sum(item.posterior_probability for item in hypotheses)
    winner = hypotheses[0]
    if arm == "G1":
        warning = (
            "G1 position weights normalize hard maximum-assignment scores and are not "
            "calibrated probabilities.",
        )
    elif arm == "G2":
        warning = (
            "G2 uses the analytic exact pair calculation on real data and is mathematically "
            "equivalent to M1; qualification requires a separate pinned Stone Soup toy parity "
            "receipt. Probability scope is the supplied finite position set.",
        )
    else:
        warning = (
            "Probability mass is exact only over the supplied finite position set; grid "
            "approximation and outside-support mass require separate audit.",
        )
    return PositionAssociationResult(
        arm=arm,
        status="complete",
        point_estimate_east_km=winner.east_km,
        point_estimate_north_km=winner.north_km,
        log_evidence=log_evidence,
        position_hypotheses=hypotheses,
        retained_probability=retained,
        discarded_probability=max(0.0, 1.0 - retained),
        evaluated_position_count=len(positions),
        evaluated_group_count=group_count,
        probability_scope="finite-position-set-and-exact-within-group",
        warnings=warning,
    )


def _parse_position(document: dict[str, Any]) -> PositionAssociationInput:
    groups = tuple(
        CompetitionGroup(
            group_id=item["group_id"],
            observation_labels=tuple(item["observation_labels"]),
            candidate_labels=tuple(item["candidate_labels"]),
            signal_log_likelihood=np.asarray(item["signal_log_likelihood"], dtype=float),
            background_log_likelihood=np.asarray(item["background_log_likelihood"], dtype=float),
            formation_attestation=item["formation_attestation"],
        )
        for item in document["groups"]
    )
    return PositionAssociationInput(
        position_id=document["position_id"],
        east_km=float(document["east_km"]),
        north_km=float(document["north_km"]),
        log_prior_weight=float(document["log_prior_weight"]),
        groups=groups,
    )


def _jsonable(result: PositionAssociationResult) -> dict[str, Any]:
    return asdict(result)


def _logsumexp(values: tuple[float, ...]) -> float:
    maximum = max(values)
    return maximum + log(sum(exp(value - maximum) for value in values))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--arm", required=True, choices=("G1", "M1", "G2"))
    parser.add_argument("--max-events-per-group", type=int, default=100_000)
    parser.add_argument("--retained-positions", type=int, default=64)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    source = json.loads(args.input.read_text())
    positions = tuple(_parse_position(item) for item in source["positions"])
    result = evaluate_position_hypotheses(
        positions,
        arm=args.arm,
        max_events_per_group=args.max_events_per_group,
        retained_positions=args.retained_positions,
    )
    args.output.write_text(json.dumps(_jsonable(result), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
