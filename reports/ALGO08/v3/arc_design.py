"""One cost-aware complete-family selector using local causal Doppler geometry."""

from copy import copy
from collections import Counter
from dataclasses import dataclass
from itertools import combinations

import numpy as np


SIGMA_HZ = 150.
TARGET = .90
EXACT_BLOCKS = 12
DIVISORS = (12, 6, 3)
ARMS = ("c0", "fitted_c")


@dataclass(frozen=True)
class Block:
    norad: int
    lanes: frozenset
    strata: frozenset
    gram: tuple


def profile(gram, retained, *, unpenalized=0):
    """Profile unit-normal nuisance coefficients, optionally with leading flat terms."""
    cross = gram[:retained, retained:]
    penalty = np.eye(gram.shape[0] - retained)
    penalty[:unpenalized, :unpenalized] = 0.
    eliminated = gram[retained:, retained:] + penalty
    if unpenalized and eliminated[0, 0] == 0:
        return profile(np.delete(np.delete(gram, retained, axis=1), retained, axis=0), retained)
    profiled = gram[:retained, :retained] - cross @ np.linalg.solve(eliminated, cross.T)
    return (profiled + profiled.T) * .5


def named_rows(scan, memberships, *, predictive):
    from leo.analysis.localization_v3.discovery import zero_state

    indices = {int(norad): index for index, norad in enumerate(scan.norads)}
    rows, aliases, entries, receivers = [], [], [], {}
    for i, (norad, role, alias) in enumerate(memberships):
        track = scan.tracks[i]
        label = indices[norad]
        row = dict(component=track["key"], candidate_index=label, points=len(track["times"]))
        if predictive and role == "predictive":
            entries.append(dict(row, track_index=i, norad=norad, alias=alias,
                                observation_ids=track["observation_ids"]))
        else:
            rows.append(dict(row, candidate_norad=norad, active_curvature=True, parts=1, split_at=-1))
            aliases.append(alias if predictive else 0)
            receivers.setdefault(label, set()).add(track["receiver"])
    for entry in entries:
        entry["cross_receiver_curved_support"] = len(receivers[entry["candidate_index"]]) == 2
    return dict(seed=dict(rows=rows, state=zero_state(scan)), aliases=aliases), entries


def geometry_rows(scan, memberships):
    """Whiten nominal row tangents, preserving all cross-arc nuisance columns."""
    from leo.analysis.localization_v3.marginal import JointMarginal
    from leo.analysis.localization_v3.retained_position import phase_widths
    from leo.analysis.research.continuous_curve_fit import paired_phase_states, phase_frequency_from_states

    # The selector sees membership, geometry and hardware coordinates, never measured CFO.
    nominal = copy(scan)
    nominal.tracks = [dict(track, values=np.zeros(len(track["times"]))) for track in scan.tracks]
    nominal.curved = list(range(len(nominal.tracks)))
    node, _ = named_rows(nominal, memberships, predictive=False)
    width, _ = phase_widths(nominal, sorted({r["candidate_index"] for r in node["seed"]["rows"]}))
    centre = np.zeros(2)
    per_arm = []
    for arm in ARMS:
        p = JointMarginal(nominal, node["seed"], arm == "fitted_c", variant="radio_noise",
                          sigma=SIGMA_HZ, aliases=node["aliases"])
        p.phase_sigma = width
        features = p.calculate(centre, geometry_only=True)["features"]
        gradients = [(p.calculate(offset, geometry_only=True)["frequency"]
                      - p.calculate(-offset, geometry_only=True)["frequency"]) / .020
                     for offset in np.eye(2) * .010]
        clock = []
        for offset in (.010, -.010):
            state = paired_phase_states(p.sky, p.flat_times + offset, p.flat_labels, p.reference)
            clock.append(phase_frequency_from_states(*state, *nominal.search_region.latlon(centre))[0])
        clock_tangent = (clock[0] - clock[1]) / .020
        width_shared = p.hardware.shape[1] + p.smooth.shape[1]
        global_design = np.column_stack((p.q[:, None] * np.column_stack((*gradients, clock_tangent)),
                                         features[:, :width_shared]))
        local_design = features[:, width_shared:].copy()
        local_design[:, -len(p.members):] *= .3
        per_arm.append((p.labels, p.flat_labels, global_design.shape[1],
                        np.column_stack((global_design, local_design)) / SIGMA_HZ))
    return per_arm


def geometry(scan, memberships):
    per_arm = []
    for labels, row_labels, shared, design in geometry_rows(scan, memberships):
        matrices = {}
        for local_label, label in enumerate(labels):
            within = design[row_labels == local_label]
            live = np.any(within != 0., axis=0)
            live[:shared] = True
            rows = within[:, live]
            matrices[int(scan.norads[label])] = profile(rows.T @ rows, shared)
        per_arm.append(matrices)
    return {norad: tuple(matrices[norad] for matrices in per_arm) for norad in per_arm[0]}


def union(blocks, field):
    return frozenset().union(*(getattr(b, field) for b in blocks))


def information(blocks, template):
    matrices = [np.zeros_like(g) for g in template]
    for block in blocks:
        for total, gram in zip(matrices, block.gram, strict=True):
            total += gram
    return tuple(profile(m, 2, unpenalized=1) for m in matrices)


def whitening(matrices):
    result = []
    for matrix in matrices:
        values, axes = np.linalg.eigh(matrix)
        if values[0] <= 0.:
            raise ValueError("The complete candidate pool must constrain two directions in both arms")
        result.append((axes / np.sqrt(values)) @ axes.T)
    return tuple(result)


def fractions(matrices, whiteners):
    return tuple(max(0., float(np.min(np.linalg.eigvalsh(w @ m @ w))))
                 for m, w in zip(matrices, whiteners, strict=True))


def evaluate(blocks, whiteners, template):
    mats = information(blocks, template)
    per_arm = fractions(mats, whiteners)
    return dict(norads=tuple(b.norad for b in blocks), lanes=len(union(blocks, "lanes")),
                strata=tuple(sorted(union(blocks, "strata"))), fraction=min(per_arm), per_arm=per_arm,
                information=mats)


def greedy(blocks, capacity, required, whiteners, template):
    current, paid, present = (), frozenset(), frozenset()
    pending = list(blocks)
    base = 0.
    while pending:
        options = []
        for block in pending:
            newly_paid = len(block.lanes - paid)
            if len(paid) + newly_paid > capacity:
                continue
            selected = (*current, block)
            row = evaluate(selected, whiteners, template)
            new_strata = len(block.strata & (required - present))
            priority = (new_strata / max(1, newly_paid), (row["fraction"] - base) / max(1, newly_paid),
                        row["fraction"], -newly_paid, -block.norad)
            options.append((priority, block, row))
        if not options:
            break
        _, best, row = max(options, key=lambda option: option[0])
        current += (best,)
        pending.remove(best)
        base = row["fraction"]
        paid |= best.lanes
        present |= best.strata
        yield row


def fractional_upper(blocks, authority, full_whiteners, capacities):
    """Relax union cost and fix the full-set optimal shared nuisance per direction."""
    overlap = Counter(lane for block in blocks for lane in block.lanes)
    prices = [sum(1. / overlap[lane] for lane in block.lanes) for block in blocks]
    bounds = [1.] * len(capacities)
    for arm, white in enumerate(full_whiteners):
        full = sum(block.gram[arm] for block in authority)
        penalty = np.eye(len(full) - 2)
        penalty[0, 0] = 0.
        conditional = np.linalg.solve(full[2:, 2:] + penalty, -full[2:, :2])
        for angle in np.arange(16) * np.pi / 16:
            east_north = white @ [np.cos(angle), np.sin(angle)]
            shared = conditional @ east_north
            direction = np.r_[east_north, shared]
            prior = shared @ penalty @ shared
            choices = sorted(((max(0., direction @ block.gram[arm] @ direction) / price, price)
                              for block, price in zip(blocks, prices, strict=True)), reverse=True)
            for i, capacity in enumerate(capacities):
                paid, upper = 0., prior
                for gain, price in choices:
                    new = min(price, capacity - paid)
                    upper += gain * new
                    paid += new
                    if paid >= capacity:
                        break
                bounds[i] = min(bounds[i], float(upper))
    return bounds


def select(blocks, total_lanes, *, authority=None):
    if authority is None:
        authority = blocks
    template = authority[0].gram
    required = union(authority, "strata")
    full = information(authority, template)
    full_whiteners = whitening(full)
    blocks = sorted(blocks, key=lambda block: block.norad)
    frontier = {}
    capacities = [total_lanes // divisor for divisor in DIVISORS]
    exhaustive = len(blocks) <= EXACT_BLOCKS
    if exhaustive:
        subsets = [evaluate(part, full_whiteners, template)
                   for n in range(1, len(blocks) + 1) for part in combinations(blocks, n)
                   if len(union(part, "lanes")) <= total_lanes // DIVISORS[-1]
                   and union(part, "strata") == required]
    optimistic = fractional_upper(blocks, authority, full_whiteners, capacities)
    for divisor, capacity, upper in zip(DIVISORS, capacities, optimistic, strict=True):
        universe = subsets if exhaustive else greedy(blocks, capacity, required, full_whiteners, template)
        eligible = [row for row in universe if row["lanes"] <= capacity and set(row["strata"]) == required]
        target = [row for row in eligible if row["fraction"] >= TARGET - 1e-10]
        best = max(eligible, key=lambda row: (row["fraction"], -row["lanes"], tuple(-n for n in row["norads"])),
                   default=None)
        cheapest_target = min(target, key=lambda row: (row["lanes"], -row["fraction"], row["norads"]),
                              default=None)
        frontier[str(divisor)] = dict(capacity=capacity, best=best, target=cheapest_target, optimistic_upper=upper,
                                     selected=cheapest_target if cheapest_target is not None else best)
    return dict(exhaustive=exhaustive, required=sorted(required), full=evaluate(authority, full_whiteners, template),
                pool=evaluate(blocks, full_whiteners, template), frontier=frontier)
