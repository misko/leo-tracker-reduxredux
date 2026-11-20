"""Gauge-aware calibration and anonymous transfer of measured StarLoc carriers."""

from collections import defaultdict
from dataclasses import dataclass
from itertools import product
from types import SimpleNamespace

import numpy as np

from leo.sky.propagation import parse_element_sets

from ..reference import grid
from . import bearing_transfer as orbit

COMB = 43_945.5
SCALE = 500.0
HOLD = 750.0
MARGIN = 75.0
CAP_LOSS = 25.0
BOUNDARY = "StarLoc anonymous frequency arcs, causal orbit shapes and surveyed other-site levels"
BANKS = ("earlier_author", "earlier_anonymous", "all_other_author")
METHODS = ("shape", *BANKS, *(s + "_permute" for s in BANKS))


def fold(x):
    return (x + COMB / 2) % COMB - COMB / 2


def centre(x, axis=None):
    angles = 2 * np.pi * np.asarray(x) / COMB
    return np.angle(np.mean(np.exp(1j * angles), axis=axis)) * COMB / (2 * np.pi)


def rms(x, axis=None):
    return np.sqrt(np.mean(np.square(x), axis=axis))


def sampled(t, f):
    """Keep actual measurements at the central native row of each one-second bin."""
    _, start, length = np.unique(t.astype(int), return_index=True, return_counts=True)
    index = start + (length - 1) // 2
    t, f = t[index], f[index]
    train = (t // 6).astype(int) % 2 == 0
    return (t, f) if min(train.sum(), (~train).sum()) >= 4 else None


@dataclass(frozen=True)
class Arc:
    number: int
    observed: np.ndarray
    train: np.ndarray
    position: np.ndarray
    velocity: np.ndarray
    ids: np.ndarray

    def profiles(self, xyz, enu):
        delta = self.position - xyz
        los = delta / np.linalg.norm(delta, axis=-1, keepdims=True)
        rf = -orbit.RF / grid.LIGHT_SPEED_KM_S * np.sum(los * self.velocity, axis=-1)
        visible = los @ enu[2] > 0
        difference = self.observed - rf
        level = centre(difference[:, self.train], axis=1)
        residual = fold(difference - level[:, None])
        train, held = (rms(residual[:, m], axis=1) for m in (self.train, ~self.train))
        train = np.where(visible[:, self.train].all(axis=1), train, np.inf)
        held = np.where(visible[:, ~self.train].all(axis=1), held, np.inf)
        return train, held, difference, level


def fields(observation, catalogue, location, labels=None):
    cap = SimpleNamespace(**observation["clock"], catalog=catalogue.encode("ascii"))
    tile, ids, _ = orbit.orbital_bank(cap, location)
    ids = np.asarray(ids)
    origin, up, _ = orbit.site_coords(tile, (0, 0))
    positions = [orbit.site_coords(tile, xy)[:2] for xy in orbit.STARTS]
    if labels is not None:
        parsed = parse_element_sets(catalogue)
        names = dict(zip(parsed.names, parsed.satellite_numbers, strict=True))
    arcs = []
    for row in observation["arcs"]:
        times, y = np.asarray(row["time"]), np.asarray(row["frequency"])
        train = times.astype(int) // 6 % 2 == 0
        p, v, _ = grid._interpolated_states(tile, times)
        d = p[:, train] - origin
        index = ((d @ up[2]) > -0.02 * np.linalg.norm(d, axis=-1)).all(axis=1)
        if labels is not None:
            index &= ids == names[labels[row["arc"]]]
        if not index.any():
            continue
        arc = Arc(row["arc"], y, train, p[index], v[index], ids[index])
        if labels is None:
            merit = np.min([arc.profiles(xyz, frame)[0] for xyz, frame in positions], axis=0)
            short = np.argsort(merit, kind="stable")[:12]
            arc = Arc(
                arc.number, y, train, arc.position[short], arc.velocity[short], arc.ids[short]
            )
        arcs.append(arc)
    return tile, arcs, len(ids)


def candidate(train, held):
    order = np.argsort(train, kind="stable")
    k = int(order[0])
    gap = train[order[1]] - train[k] if len(order) > 1 and np.isfinite(train[k]) else None
    return k, finite(train[k]), finite(held[k]), finite(gap)


def finite(x):
    return float(x) if x is not None and np.isfinite(x) else None


def donor_fit(observation, catalogue, surveyed_location, labels=None):
    tile, arcs, _ = fields(observation, catalogue, surveyed_location, labels)
    xyz, enu, _ = orbit.site_coords(tile, (0, 0))
    rows, accepted = [], {}
    for arc in arcs:
        train, held, values, level = arc.profiles(xyz, enu)
        k, head, tail, gap = candidate(train, held)
        qualified = (
            head is not None
            and tail is not None
            and head <= SCALE
            and tail <= HOLD
            and (labels is not None or gap is not None and gap >= MARGIN)
        )
        record = dict(
            arc=arc.number,
            norad=int(arc.ids[k]),
            training_rms_hz=head,
            held_rms_hz=tail,
            training_gap_hz=gap,
            wrapped_level_hz=float(level[k]),
            raw_level_hz=float(np.median(values[k, arc.train])),
            qualified=qualified,
        )
        rows.append(record)
        order = (head, tail, arc.number)
        previous = accepted.get(record["norad"])
        if qualified and (previous is None or order < previous[0]):
            accepted[record["norad"]] = order, record
    return rows, [r for _, r in sorted(accepted.values())]


def graph(sessions):
    """Solve one independent circular intercept gauge per connected component."""
    links = defaultdict(list)
    for session, observations in sessions.items():
        for r in observations:
            a, b, y = ("capture", session), ("satellite", r["norad"]), r["wrapped_level_hz"]
            links[a].append((b, y))
            links[b].append((a, y))
    values, components = {}, []
    for first in sorted(k for k in links if k[0] == "capture"):
        if first in values:
            continue
        values[first] = 0.0
        waiting, nodes = [first], []
        while waiting:
            node = waiting.pop()
            nodes.append(node)
            for peer, y in links[node]:
                if peer not in values:
                    values[peer] = fold(y - values[node])
                    waiting.append(peer)
        for _ in range(12):
            for node in nodes:
                values[node] = centre([y - values[other] for other, y in links[node]])
        origin = values[first]
        clocks = {k: float(fold(values[c, k] - origin)) for c, k in nodes if c == "capture"}
        levels = {str(k): float(fold(values[c, k] + origin)) for c, k in nodes if c == "satellite"}
        edges = sum(len(links["capture", k]) for k in clocks)
        error = [
            float(fold(y - clocks[s] - levels[str(k)]))
            for s in clocks
            for (_, k), y in links["capture", s]
        ]
        components.append(
            dict(
                captures=clocks,
                levels=levels,
                edges=edges,
                rank=len(nodes) - 1,
                cycle_rank=edges - len(nodes) + 1,
                donor_graph_rms_hz=float(rms(error)),
            )
        )
    return components


def partition(captures, target, *, strict=True):
    """Leave out every capture from the target's physical site."""
    return [
        d
        for d in captures
        if d["site"] != target["site"] and (not strict or d["end_utc_ns"] <= target["start_utc_ns"])
    ]


def permute(levels):
    ids = sorted(levels, key=int)
    return {k: levels[ids[(i + 1) % len(ids)]] for i, k in enumerate(ids)}


def shape(tile, arcs, xy, details=False):
    xyz, enu, point = orbit.site_coords(tile, xy)
    rows = []
    for a in arcs:
        train, held, _, _ = a.profiles(xyz, enu)
        k, h, t, m = candidate(train, held)
        rows.append(dict(arc=a.number, norad=int(a.ids[k]), train=h, held=t, gap=m))

    def aggregate(key):
        parts = [
            (min(CAP_LOSS, (a[key] / SCALE) ** 2) if a[key] is not None else CAP_LOSS) for a in rows
        ]
        return float(np.mean(parts))

    return (
        (aggregate("train"), aggregate("held"), point.tolist(), rows)
        if details
        else aggregate("train")
    )


def search(loss):
    tried = {}

    def visit(x):
        if x not in tried:
            tried[x] = loss(x)
        return tried[x]

    best = min(product(np.linspace(-12.5, 12.5, 11), repeat=2), key=visit)
    for step in (0.5, 0.1):
        options = [
            tuple(np.clip(np.asarray(best) + step * np.asarray(d), -12.5, 12.5))
            for d in product(range(-2, 3), repeat=2)
        ]
        best = min(options, key=visit)
    return best, len(tried)


def transported(arcs, shapes, components):
    observed = {a.number: a for a in arcs}
    rows = {}
    for r in sorted(shapes, key=lambda r: r["train"] if r["train"] is not None else np.inf):
        if (
            r["train"] is not None
            and r["train"] <= SCALE
            and (r["gap"] is not None and r["gap"] >= MARGIN)
        ):
            rows.setdefault(str(r["norad"]), observed[r["arc"]])
    levels = max((c["levels"] for c in components), key=lambda c: len(c.keys() & rows), default={})
    return {k: rows[k] for k in rows if k in levels}, levels


def common_clock(residuals, levels):
    """One clock for all carried arcs, with equal weight per arc."""
    obs = [centre(r[0]) - q for r, q in zip(residuals, levels, strict=True)]
    offset = centre(obs)
    error = [
        (rms(fold(a - offset - level)), rms(fold(b - offset - level)), rms(fold(b - centre(a))))
        for (a, b), level in zip(residuals, levels, strict=True)
    ]
    return float(offset), np.asarray(error)


def replay(tile, xy, records, levels):
    xyz, enu, _ = orbit.site_coords(tile, xy)
    rows = []
    for k, a in records.items():
        idx = int(np.flatnonzero(a.ids == int(k))[0])
        train, held, delta, _ = a.profiles(xyz, enu)
        if not np.isfinite(train[idx]) or not np.isfinite(held[idx]):
            return None
        rows.append((delta[idx, a.train], delta[idx, ~a.train]))
    offset, e = common_clock(rows, [levels[n] for n in records])
    return dict(
        target_offset_hz=offset,
        train_rms_hz=float(rms(e[:, 0])),
        held_rms_hz=float(rms(e[:, 1])),
        same_endpoint_free_held_hz=float(rms(e[:, 2])),
        held_supported=int(np.count_nonzero(e[:, 1] <= HOLD)),
    )


def outcome(reason, metrics, forced=None, publish=False):
    return dict(
        status="ok" if publish else "withheld",
        reason=None if publish else reason,
        boundary=BOUNDARY,
        metrics=metrics | dict(position_attempted=forced is not None, c_identifiable=False),
        arms=dict(
            c0=dict(
                latlon=forced if publish else None,
                forced_latlon=forced,
                rf_rms_hz=metrics.get("held_rms_hz") if forced is not None else None,
            ),
            fitted_c=dict(
                status="unavailable",
                reason="single_RF_intercept_gauge",
                latlon=None,
                forced_latlon=None,
            ),
        ),
    )


def transfer(tile, arcs, anchor, records, levels, permuted, earlier):
    metric = dict(
        nominal_matches=len(records),
        target_level_rank=max(0, len(records) - 1),
        carried_norads=list(map(int, records)),
    )
    if not records:
        return outcome("no_blind_donor_match", metric)
    first, sham = (replay(tile, anchor, records, x) for x in (levels, permuted))
    if first is not None and sham is not None:
        metric.update(first, anchor_permutation_held_rms_hz=sham["held_rms_hz"])
    if len(records) < 2:
        return outcome("one_transferred_level_is_a_receiver_gauge", metric)

    def merit(xy, m, split):
        if m is None:
            return CAP_LOSS
        return (
            min(CAP_LOSS, (m[split + "_rms_hz"] / SCALE) ** 2)
            + shape(tile, arcs, xy, details=True)[split == "held"]
        )

    endpoint, sites = search(lambda xy: merit(xy, replay(tile, xy, records, levels), "train"))
    value = replay(tile, endpoint, records, levels)
    null = replay(tile, endpoint, records, permuted)
    if value is None or null is None:
        return outcome("matched_donor_arcs_below_horizon", metric)
    rivals = [xy for xy in orbit.RIVALS if np.linalg.norm(np.subtract(xy, endpoint)) >= 8]
    lead = min(merit(xy, replay(tile, xy, records, levels), "held") for xy in rivals) - merit(
        endpoint, value, "held"
    )
    metric.update(
        value,
        same_endpoint_permutation_held_rms_hz=null["held_rms_hz"],
        location_trials=sites,
        held_region_lead=lead,
    )
    passed = (
        earlier
        and value["held_supported"] >= 2
        and lead >= 0.05
        and (value["held_rms_hz"] <= 0.85 * null["held_rms_hz"])
    )
    return outcome(
        "unresolved_transferred_geometry",
        metric,
        orbit.site_coords(tile, endpoint)[2].tolist(),
        passed,
    )


def solve(observation, catalogue, location, priors):
    tile, arcs, ids = fields(observation, catalogue, location)
    if len(arcs) < 2:
        return {k: outcome("insufficient_anonymous_doppler_arcs", {}) for k in METHODS}
    anchor, n = search(lambda xy: shape(tile, arcs, xy))
    training, held, point, selected = shape(tile, arcs, anchor, details=True)
    usable = [r["held"] for r in selected if r["held"] is not None]
    result = {
        "shape": outcome(
            "matched_doppler_diagnostic",
            dict(
                training_cost=training,
                held_cost=held,
                evaluated_sites=n,
                causal_orbits=ids,
                arcs=len(arcs),
                selected=selected,
                held_rms_hz=float(rms(usable)) if usable else None,
            ),
            point,
        )
    }
    for mode in BANKS:
        records, levels = transported(arcs, selected, priors[mode])
        mixed = permute(levels)
        result[mode] = transfer(
            tile, arcs, anchor, records, levels, mixed, mode != "all_other_author"
        )
        result[mode + "_permute"] = transfer(tile, arcs, anchor, records, mixed, levels, False)
    return result
