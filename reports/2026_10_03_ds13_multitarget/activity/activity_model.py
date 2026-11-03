"""Bounded factorial activity decoder with exclusive peak assignment.

This is a report-local prototype.  A group is an observed positive GLRT group;
absence of a group is deliberately not treated as a non-detection opportunity.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import exp, log

import numpy as np


@dataclass(frozen=True)
class ModelConfig:
    birth_rate_hz: float = 1 / 90.0
    death_rate_hz: float = 1 / 35.0
    initial_active: float = 0.18
    # Edge scores supplied to the decoder are already log likelihood gains over
    # a missed target plus a clutter row, so those baselines are zero.
    miss_score: float = 0.0
    clutter_score: float = 0.0
    beam_width: int = 48
    max_toggles: int = 1
    detection_probability: float = 0.06
    clutter_rate: float = 2.0


def solve_group_exact(scores, miss_score=-1.25, clutter_score=-2.0):
    """Exact maximum-weight matching for a small row x active-target matrix.

    Returns (score, ((row, target), ...)). Each row and target occurs at most
    once. Unused rows are clutter and unused active targets are misses.
    """
    scores = np.asarray(scores, dtype=float)
    if scores.ndim != 2:
        raise ValueError("scores must be a row x target matrix")
    nr, nt = scores.shape
    baseline = nr * clutter_score + nt * miss_score
    gains = scores - clutter_score - miss_score
    # DP over used rows, iterating targets; bounded by 2**rows rather than the
    # much larger label-product enumeration.
    states = {0: (0.0, ())}
    for target in range(nt):
        updated = dict(states)
        for used, (value, pairs) in states.items():
            for row in range(nr):
                edge = gains[row, target]
                if used & (1 << row) or not np.isfinite(edge) or edge <= 0:
                    continue
                new = used | (1 << row)
                candidate = value + float(edge)
                if candidate > updated.get(new, (-np.inf, ()))[0]:
                    updated[new] = (candidate, pairs + ((row, target),))
        states = updated
    value, pairs = max(states.values(), key=lambda item: item[0])
    return baseline + value, pairs


def _transition_bit(old, new, dt, cfg, persistence):
    if not persistence:
        p = cfg.initial_active if new else 1 - cfg.initial_active
        return log(max(p, 1e-12))
    total = cfg.birth_rate_hz + cfg.death_rate_hz
    equilibrium = cfg.birth_rate_hz / total
    decay = exp(-total * max(float(dt), 0.0))
    if old:
        p1 = equilibrium + (1 - equilibrium) * decay
    else:
        p1 = equilibrium * (1 - decay)
    p = p1 if new else 1 - p1
    return log(max(p, 1e-12))


def _transition_mask(old, new, n_targets, dt, cfg, persistence):
    return sum(
        _transition_bit(bool(old & (1 << j)), bool(new & (1 << j)), dt, cfg, persistence)
        for j in range(n_targets)
    )


def _candidate_masks(mask, n_targets, max_toggles):
    yield mask
    bits = range(n_targets)
    for count in range(1, max_toggles + 1):
        for toggles in combinations(bits, count):
            candidate = mask
            for bit in toggles:
                candidate ^= 1 << bit
            yield candidate


def _emission(scores, mask, cfg, visible=None):
    active = [j for j in range(scores.shape[1]) if mask & (1 << j)]
    if visible is None:
        visible = np.ones(scores.shape[1], dtype=bool)
    visible = np.asarray(visible, dtype=bool)
    visible_active = [j for j in active if visible[j]]
    # Condition the likelihood on this being a stored nonempty positive group.
    empty_probability = exp(-cfg.clutter_rate) * (1 - cfg.detection_probability) ** len(visible_active)
    positive_normalizer = -log(max(1 - empty_probability, 1e-12))
    if not active:
        return scores.shape[0] * cfg.clutter_score + positive_normalizer, ()
    matrix = scores[:, active]
    baseline = (matrix.shape[0] * cfg.clutter_score
                + len(visible_active) * cfg.miss_score + positive_normalizer)
    # Scores are gains relative to clutter plus a visible missed detection.
    # Invisible columns are already -inf in the shared adapter.
    gain = matrix
    value_gain, local = solve_group_exact(gain, 0, 0)
    value = baseline + value_gain
    return value, tuple((r, active[j]) for r, j in local)


def decode_groups(groups, config=ModelConfig(), persistence=True, exhaustive=False):
    """Viterbi-decode positive groups.

    ``groups`` contains dicts with ``time_s`` and row x target ``scores``.
    Exhaustive mode is an oracle for small synthetic cases; bounded mode expands
    only nearby activity masks and keeps ``beam_width`` paths.
    """
    if not groups:
        return []
    n_targets = np.asarray(groups[0]["scores"]).shape[1]
    if not persistence:
        result = []
        log_active = log(config.initial_active)
        log_inactive = log(1 - config.initial_active)
        for group in groups:
            scores = np.asarray(group["scores"])
            useful = np.flatnonzero(np.any(np.isfinite(scores) & (scores > 0), axis=0)).tolist()
            candidates = [0]
            for count in range(1, len(useful) + 1):
                candidates.extend(sum(1 << bit for bit in subset)
                                  for subset in combinations(useful, count))
            best = None
            for mask in candidates:
                emit, pairs = _emission(scores, mask, config, group.get("visible"))
                active_count = mask.bit_count()
                total = emit + active_count * log_active + (n_targets-active_count) * log_inactive
                if best is None or total > best[0]:
                    best = (total, mask, pairs)
            result.append({"mask": best[1], "pairs": best[2]})
        return result
    if exhaustive and n_targets > 14:
        raise ValueError("exhaustive oracle is limited to 14 targets")
    masks = range(1 << n_targets)
    first_candidates = masks if exhaustive else range(1 << n_targets)
    beam = {}
    for mask in first_candidates:
        prior = sum(log(config.initial_active if mask & (1 << j) else 1-config.initial_active)
                    for j in range(n_targets))
        emit, pairs = _emission(np.asarray(groups[0]["scores"]), mask, config,
                                groups[0].get("visible"))
        beam[mask] = (prior + emit, [(mask, pairs)])
    if not exhaustive:
        beam = dict(sorted(beam.items(), key=lambda x: x[1][0], reverse=True)[:config.beam_width])
    previous_t = float(groups[0]["time_s"])
    for group in groups[1:]:
        now = float(group["time_s"])
        scores = np.asarray(group["scores"])
        next_beam = {}
        emission_cache = {}
        for old, (path_score, path) in beam.items():
            candidates = masks if exhaustive else _candidate_masks(old, n_targets, config.max_toggles)
            for new in candidates:
                if new not in emission_cache:
                    emission_cache[new] = _emission(scores, new, config, group.get("visible"))
                emit, pairs = emission_cache[new]
                total = path_score + _transition_mask(old, new, n_targets, now-previous_t,
                                                        config, persistence) + emit
                if new not in next_beam or total > next_beam[new][0]:
                    next_beam[new] = (total, path + [(new, pairs)])
        if not exhaustive:
            next_beam = dict(sorted(next_beam.items(), key=lambda x: x[1][0], reverse=True)[:config.beam_width])
        beam = next_beam
        previous_t = now
    score, path = max(beam.values(), key=lambda x: x[0])
    return [{"mask": mask, "pairs": pairs} for mask, pairs in path]


def decode_lanes(groups, config=ModelConfig(), persistence=True, exhaustive=False):
    """Decode receiver/channel lanes independently and return steps aligned to input."""
    lanes = {}
    for index, group in enumerate(groups):
        lanes.setdefault((group["receiver"], group["channel"]), []).append((index, group))
    output = [None] * len(groups)
    for members in lanes.values():
        members.sort(key=lambda item: (item[1]["time_s"], item[1].get("group_id", 0)))
        steps = decode_groups([group for _, group in members], config, persistence, exhaustive)
        for (index, _), step in zip(members, steps):
            output[index] = step
    return output


def assignment_probability(scores, row, target, miss_score, clutter_score):
    """Local bounded confidence; not a calibrated posterior."""
    # Input scores are already edge gains over missed-detection plus clutter.
    gains = np.asarray(scores)
    chosen = gains[row, target]
    competitors = [0.0]
    competitors.extend(gains[row, j] for j in range(gains.shape[1]) if j != target)
    competitors.extend(gains[r, target] for r in range(gains.shape[0]) if r != row)
    margin = chosen - max(competitors)
    return 1.0 / (1.0 + exp(-float(np.clip(margin, -40, 40))))
