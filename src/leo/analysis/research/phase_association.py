"""Held-out phase evidence for cross-receiver association hypotheses.

This factor answers only whether two receiver detections support one coherent
waveform.  Its input is the residual phase in frequency band B after a tracker
was fitted without B and without the held-out groups.  It does not interpret
the residual as geometric phase and therefore cannot distinguish catalogue
candidates that assert the same receiver link.

A replay constructs one :class:`HeldoutPhaseLinkEvidence` per dwell/link from
the saved B residual rows, calls ``score_phase_association_hypotheses(...)``,
and writes ``result.as_serializable()``.  Use one group id per random 20 ms
block, and include only FFT windows whose support lies wholly inside that block.
The concentration and support gates are predeclared across all replayed dwells.
"""

from __future__ import annotations

import math
from collections.abc import Hashable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class RandomGroupSplit:
    seed: int
    training_group_ids: tuple[Hashable, ...]
    heldout_group_ids: tuple[Hashable, ...]


@dataclass(frozen=True, slots=True)
class HeldoutPhaseLinkEvidence:
    """Frequency-held-out residuals and a wrong-pair control for one link."""

    link_id: str
    split: RandomGroupSplit
    residual_phase_rad: np.ndarray
    residual_group_id: np.ndarray
    wrong_pair_phase_rad: np.ndarray
    wrong_pair_group_id: np.ndarray


@dataclass(frozen=True, slots=True)
class PhaseAssociationHypothesis:
    hypothesis_id: str
    asserted_link_ids: frozenset[str]
    base_log_weight: float = 0.0


@dataclass(frozen=True, slots=True)
class PhaseLinkScore:
    link_id: str
    split_seed: int
    training_group_ids: tuple[Hashable, ...]
    heldout_group_ids: tuple[Hashable, ...]
    state: str
    reason: str | None
    conditional_composite_log_factor: float
    heldout_group_count: int
    exact_phase_resultant: float
    wrong_pair_phase_resultant: float


@dataclass(frozen=True, slots=True)
class PhaseAssociationScore:
    hypothesis_ids: tuple[str, ...]
    normalized_conditional_weight: np.ndarray
    phase_log_factor: np.ndarray
    links: tuple[PhaseLinkScore, ...]

    def as_serializable(self) -> dict[str, object]:
        """Return the small JSON-ready result used by saved-IQ research replays."""
        return {
            "hypotheses": [
                {
                    "hypothesis_id": hypothesis_id,
                    "normalized_conditional_weight": float(weight),
                    "phase_log_factor": float(factor),
                }
                for hypothesis_id, weight, factor in zip(
                    self.hypothesis_ids,
                    self.normalized_conditional_weight,
                    self.phase_log_factor,
                    strict=True,
                )
            ],
            "links": [
                {
                    "link_id": item.link_id,
                    "split_seed": item.split_seed,
                    "training_group_ids": list(item.training_group_ids),
                    "heldout_group_ids": list(item.heldout_group_ids),
                    "state": item.state,
                    "reason": item.reason,
                    "conditional_composite_log_factor": (item.conditional_composite_log_factor),
                    "heldout_group_count": item.heldout_group_count,
                    "exact_phase_resultant": item.exact_phase_resultant,
                    "wrong_pair_phase_resultant": item.wrong_pair_phase_resultant,
                }
                for item in self.links
            ],
        }


def seeded_random_group_split(
    group_ids: tuple[Hashable, ...], *, seed: int, heldout_fraction: float = 0.4
) -> RandomGroupSplit:
    """Assign whole independent groups with a reproducible random permutation."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("split seed must be an integer")
    if not 0.0 < heldout_fraction < 1.0:
        raise ValueError("heldout fraction must lie in (0, 1)")
    unique = tuple(dict.fromkeys(group_ids))
    if len(unique) < 4:
        raise ValueError("random phase validation needs at least four groups")
    permutation = np.random.default_rng(seed).permutation(len(unique))
    heldout_count = min(len(unique) - 2, max(2, round(len(unique) * heldout_fraction)))
    heldout_indexes = frozenset(int(item) for item in permutation[:heldout_count])
    training = tuple(item for index, item in enumerate(unique) if index not in heldout_indexes)
    heldout = tuple(item for index, item in enumerate(unique) if index in heldout_indexes)
    return RandomGroupSplit(seed=seed, training_group_ids=training, heldout_group_ids=heldout)


def score_phase_link(
    evidence: HeldoutPhaseLinkEvidence,
    *,
    concentration: float = 4.0,
    minimum_coherence: float = 0.05,
    control_ratio: float = 3.0,
) -> PhaseLinkScore:
    """Score a coherent-link model against uniform phase, or explicitly abstain.

    Each held-out group contributes once.  Within-group samples are collapsed
    to one circular mean so overlapping/correlated windows do not manufacture
    sample size.  ``concentration`` is fixed before scoring; it must not be fit
    on these held-out residuals.
    """
    if not evidence.link_id:
        raise ValueError("phase evidence needs a link id")
    if isinstance(evidence.split.seed, bool) or not isinstance(evidence.split.seed, int):
        raise ValueError("phase evidence must record an integer random split seed")
    if not math.isfinite(concentration) or concentration <= 0:
        raise ValueError("von Mises concentration must be positive and finite")
    if not 0.0 < minimum_coherence <= 1.0 or control_ratio <= 0:
        raise ValueError("phase support gates are invalid")
    training = set(evidence.split.training_group_ids)
    heldout = set(evidence.split.heldout_group_ids)
    if len(training) < 2 or len(heldout) < 2 or training & heldout:
        raise ValueError("phase split needs disjoint train and held-out group sets")
    exact = _heldout_group_phasors(
        evidence.residual_phase_rad, evidence.residual_group_id, heldout, "exact"
    )
    control = _heldout_group_phasors(
        evidence.wrong_pair_phase_rad, evidence.wrong_pair_group_id, heldout, "control"
    )
    exact_resultant = float(abs(np.mean(exact)))
    control_resultant = float(abs(np.mean(control)))
    if exact_resultant <= max(minimum_coherence, control_ratio * control_resultant):
        return PhaseLinkScore(
            link_id=evidence.link_id,
            split_seed=evidence.split.seed,
            training_group_ids=evidence.split.training_group_ids,
            heldout_group_ids=evidence.split.heldout_group_ids,
            state="abstained",
            reason="exact phase does not clear the wrong-pair support gate",
            conditional_composite_log_factor=0.0,
            heldout_group_count=len(exact),
            exact_phase_resultant=exact_resultant,
            wrong_pair_phase_resultant=control_resultant,
        )
    log_normalizer = math.log(float(np.i0(concentration)))
    log_likelihood_ratio = math.fsum(
        concentration * float(value.real) - log_normalizer for value in exact
    )
    return PhaseLinkScore(
        link_id=evidence.link_id,
        split_seed=evidence.split.seed,
        training_group_ids=evidence.split.training_group_ids,
        heldout_group_ids=evidence.split.heldout_group_ids,
        state="supported",
        reason=None,
        conditional_composite_log_factor=log_likelihood_ratio,
        heldout_group_count=len(exact),
        exact_phase_resultant=exact_resultant,
        wrong_pair_phase_resultant=control_resultant,
    )


def score_phase_association_hypotheses(
    hypotheses: tuple[PhaseAssociationHypothesis, ...],
    evidence: tuple[HeldoutPhaseLinkEvidence, ...],
    *,
    concentration: float = 4.0,
    minimum_coherence: float = 0.05,
    control_ratio: float = 3.0,
) -> PhaseAssociationScore:
    """Reweight hypotheses only through the receiver links they assert."""
    if not hypotheses or len({item.hypothesis_id for item in hypotheses}) != len(hypotheses):
        raise ValueError("phase hypotheses need unique nonempty ids")
    if any(
        not item.hypothesis_id or not math.isfinite(item.base_log_weight) for item in hypotheses
    ):
        raise ValueError("phase hypothesis weights must be finite")
    if len({item.link_id for item in evidence}) != len(evidence):
        raise ValueError("phase link evidence ids must be unique")
    links = tuple(
        score_phase_link(
            item,
            concentration=concentration,
            minimum_coherence=minimum_coherence,
            control_ratio=control_ratio,
        )
        for item in evidence
    )
    available = {item.link_id: item.conditional_composite_log_factor for item in links}
    unknown = set().union(*(item.asserted_link_ids for item in hypotheses)) - set(available)
    if unknown:
        raise ValueError("hypothesis asserts a link without phase evidence")
    phase = np.asarray(
        [
            math.fsum(available[item] for item in hypothesis.asserted_link_ids)
            for hypothesis in hypotheses
        ],
        dtype=float,
    )
    log_weight = phase + np.asarray([item.base_log_weight for item in hypotheses])
    shifted = np.exp(log_weight - float(np.max(log_weight)))
    normalized = shifted / np.sum(shifted)
    return PhaseAssociationScore(
        hypothesis_ids=tuple(item.hypothesis_id for item in hypotheses),
        normalized_conditional_weight=normalized,
        phase_log_factor=phase,
        links=links,
    )


def _heldout_group_phasors(phases, groups, heldout, label):
    phase = np.asarray(phases, dtype=float)
    group = np.asarray(groups)
    if phase.ndim != 1 or group.shape != phase.shape or not np.all(np.isfinite(phase)):
        raise ValueError(f"{label} phase arrays must be matching finite vectors")
    observed = set(group.tolist())
    if observed != heldout:
        raise ValueError(f"{label} residuals must exactly cover held-out groups")
    output = []
    for group_id in sorted(heldout, key=repr):
        # Retain within-group resultant magnitude. Normalizing this mean would
        # promote an arbitrarily weak/noisy group to one unit of evidence.
        output.append(np.mean(np.exp(1j * phase[group == group_id])))
    return np.asarray(output, dtype=complex)
