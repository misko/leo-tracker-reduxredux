"""Design original-history radio block purchases using paired nominal Doppler rows."""

from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np

from arc_design import ARMS, TARGET, profile, whitening
from owner_union_trial import MAX_AGE, histories


SHORTLIST = 8


@dataclass(frozen=True)
class Block:
    key: tuple
    core: frozenset
    paid: frozenset
    owner_rows: tuple
    strata: frozenset


def blocks(probes, anchor, duration, owner_indices):
    """Buy every native lane opportunity in one hardware epoch, plus history."""
    if len(set(owner_indices)) != len(owner_indices):
        raise ValueError("Each installed owner must occupy a distinct native lane")
    rows = {native: index for index, native in enumerate(owner_indices)}
    h = histories(probes, range(len(probes)))
    core = defaultdict(set)
    for i, d in enumerate(probes):
        dt = d["valid_start_counter"] - anchor
        key = (dt // MAX_AGE, d["receiver_id"], d["channel"], d["actual_rf_hz"])
        core[key].add(i)
    result = []
    for key, members in sorted(core.items()):
        matched = sorted(members & rows.keys())
        if not matched:
            continue
        thirds = {min(2, 3 * (probes[i]["valid_start_counter"] - anchor) // duration) for i in matched}
        _, receiver, channel, _ = key
        strata = {f"receiver:{receiver}", f"rf_half:{int(channel > 4)}",
                  *(f"time_third:{third}" for third in thirds)}
        paid = members.union(*(h[i] for i in members))
        result.append(Block(key, frozenset(members), frozenset(paid),
                            tuple(rows[i] for i in matched), frozenset(strata)))
    return result


def ridge_minimizer(gram):
    nuisance = gram[2:, 2:].copy()
    penalized = np.arange(1, len(nuisance))
    nuisance[penalized, penalized] += 1.
    return np.linalg.solve(nuisance, -gram[2:, :2])


def gram_chunks(matrix, choices):
    result = []
    for block in choices:
        tape = matrix[list(block.owner_rows)]
        columns = np.flatnonzero(np.any(tape != 0., axis=0))
        local = tape[:, columns]
        result.append((np.ix_(columns, columns), local.T @ local))
    return result


def increment(current, piece):
    selected, update = piece
    changed = current.copy()
    changed[selected] += update
    return changed


def weakest(matrices):
    return tuple(max(0., float(np.linalg.eigvalsh(matrix)[0])) for matrix in matrices)


def approximate(matrix, nuisance, owners, count):
    residual = matrix[:, :2] + matrix[:, 2:] @ nuisance
    east, north = residual.T
    block = np.zeros((count, 2, 2))
    block[:, 0, 0] = np.bincount(owners, weights=east ** 2, minlength=count)
    block[:, 1, 1] = np.bincount(owners, weights=north ** 2, minlength=count)
    block[:, 0, 1] = block[:, 1, 0] = np.bincount(owners, weights=east * north, minlength=count)
    return block


def upper_bound(choices, matrices, full_grams, owners, capacity):
    overlap = Counter(i for block in choices for i in block.paid)
    prices = [sum(1. / overlap[i] for i in block.paid) for block in choices]
    upper = 1.
    for matrix, gram in zip(matrices, full_grams, strict=True):
        nuisance = ridge_minimizer(gram)
        contributions = approximate(matrix, nuisance, owners, len(choices))
        prior = nuisance[1:].T @ nuisance[1:]
        for angle in np.arange(16) * np.pi / 16:
            direction = np.array([np.cos(angle), np.sin(angle)])
            energy = np.einsum("a,bac,c->b", direction, contributions, direction)
            value, paid = direction @ prior @ direction, 0.
            for ratio, price in sorted(zip(energy / prices, prices, strict=True), reverse=True):
                used = min(capacity - paid, price)
                value += ratio * used
                paid += used
                if paid >= capacity:
                    break
            upper = min(upper, float(value))
    return upper


def select(choices, designs, capacity):
    """Evaluate one bounded, exact final greedy path and a fractional upper bound."""
    full_info = tuple(profile(m.T @ m, 2, unpenalized=1) for m in designs)
    whiteners = whitening(full_info)
    matrices = tuple(np.column_stack((m[:, :2] @ white, m[:, 2:]))
                     for m, white in zip(designs, whiteners, strict=True))
    full = tuple(m.T @ m for m in matrices)
    chunks = [gram_chunks(m, choices) for m in matrices]
    owner_blocks = np.full(len(matrices[0]), -1, int)
    for index, block in enumerate(choices):
        owner_blocks[list(block.owner_rows)] = index
    if np.any(owner_blocks < 0) or sum(len(block.owner_rows) for block in choices) != len(owner_blocks):
        raise ValueError("Radio blocks must partition all installed owner rows")

    required = frozenset().union(*(block.strata for block in choices))
    current = tuple(np.zeros_like(g) for g in full)
    information = tuple(np.zeros((2, 2)) for _ in ARMS)
    present, paid, selected = frozenset(), frozenset(), []
    remaining, trail, best = set(range(len(choices))), [], None

    while remaining:
        affordable = {}
        for i in remaining:
            block = choices[i]
            cost = len(block.paid - paid)
            if len(paid) + cost <= capacity:
                affordable[i] = (len(block.strata - present) / max(1, cost), cost)
        if not affordable:
            break
        arm_scores = []
        for design, gram, known, indiv in zip(matrices, current, full, information, strict=True):
            nuisance = ridge_minimizer(gram if selected else known)
            estimate = approximate(design, nuisance, owner_blocks, len(choices))
            arm_scores.append(np.linalg.eigvalsh(indiv + estimate)[:, 0])
        rough = np.minimum(*arm_scores)
        baseline = min(weakest(information))
        shortlist = sorted(affordable, key=lambda i: (
            -affordable[i][0], -(rough[i] - baseline) / max(1, affordable[i][1]), choices[i].key
        ))[:SHORTLIST]
        ranked = []
        for i in shortlist:
            trial = tuple(increment(gram, arm_chunks[i]) for gram, arm_chunks in zip(current, chunks, strict=True))
            info = tuple(profile(gram, 2, unpenalized=1) for gram in trial)
            scores = weakest(info)
            coverage, cost = affordable[i]
            ranked.append(((-coverage, -(min(scores) - baseline) / max(1, cost), choices[i].key),
                           i, trial, info, scores))
        _, i, current, information, scores = min(ranked, key=lambda option: option[0])
        block = choices[i]
        selected.append(i)
        remaining.remove(i)
        present |= block.strata
        paid |= block.paid
        step = dict(indices=list(selected), lanes=len(paid), strata=sorted(present), fractions=scores,
                    fraction=min(scores))
        trail.append(step)
        if present == required and (best is None or step["fraction"] > best["fraction"]):
            best = step
        if best and best["fraction"] >= TARGET - 1e-10:
            break
    return dict(capacity=capacity, upper_bound=upper_bound(choices, matrices, full, owner_blocks, capacity),
                full_information=full_info, considered_blocks=len(choices), required_strata=sorted(required),
                best=best, trail=trail)
