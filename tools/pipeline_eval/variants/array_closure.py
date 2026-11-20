"""Signed inter-satellite phase contrasts on two orthogonal antenna baselines."""

from dataclasses import dataclass
from itertools import combinations, product
from types import SimpleNamespace

import numpy as np

from leo.sky.propagation import parse_element_sets

from ..reference import grid
from . import bearing_transfer as bearing

METHODS = ("closure", "temporal", "doppler")
SCOPES = ("coincident", "wire_stable")
BOUNDARY = "Measured StarLoc array phase, matched Doppler and causal orbits in one square"
PHASE_SIGMA, RATE_SIGMA, PAD = 0.25, 100, 25.0
YAW = np.arange(0.0, 360.0, 5.0)


def native_rows(raw):
    iq = raw[:, 2:]
    strength = np.min(abs(iq), axis=1)
    keep = np.flatnonzero((strength > 0) & np.isfinite(raw).all(axis=1))
    times = raw[:, 0].real
    ranked = keep[np.lexsort((-strength[keep], times[keep]))]
    _, index = np.unique(times[ranked], return_index=True)
    rows = raw[ranked[index]]
    iq = rows[:, 2:] / abs(rows[:, 2:])
    phasors = np.column_stack((iq[:, 1] * iq[:, 2].conj(), iq[:, 0] * iq[:, 1].conj()))
    return rows[:, 0].real, rows[:, 1].real, phasors


def wire_stability(time, phase, first, last):
    lo = np.searchsorted(time, first, side="right") - 1
    hi = np.searchsorted(time, last, side="left")
    if lo < 0 or hi >= len(time) or hi <= lo:
        return None
    t, p = time[lo : hi + 1], phase[lo : hi + 1]
    excursion = float(np.ptp(p, axis=0).max())
    return excursion if np.diff(t).max() <= 12 and excursion <= 0.12 else None


def bins(time, frequency, phase):
    """Average only native rows inside each half-second measurement bin."""
    groups = np.floor(time * 2).astype(int)
    _, start = np.unique(groups, return_index=True)
    result = []
    for i, end in zip(start, np.r_[start[1:], len(time)] if len(start) else (), strict=True):
        if end - i < 3:
            continue
        mean = phase[i:end].mean(axis=0)
        if np.min(abs(mean)) >= 0.65:
            result.append(
                (
                    np.full(mean.shape[:-1], time[i:end].mean()),
                    np.median(frequency[i:end], axis=0),
                    np.angle(mean),
                    int(end - i),
                    time[i],
                    time[end - 1],
                )
            )
    return result


def stencils(bin_rows):
    groups = {}
    for row in bin_rows:
        groups.setdefault(int(row[0].flat[0] // 8), []).append(row)
    record = {}
    for block, rows in groups.items():
        possible = []
        for a, b in combinations(rows, 2):
            dt = float((b[0] - a[0]).flat[0])
            if 1.5 <= dt <= 5.5 and np.max(abs(b[1] - a[1])) / dt <= 5000:
                possible.append((abs(dt - 3), -min(a[3], b[3]), a, b))
        if possible:
            _, _, a, b = min(possible, key=lambda r: r[:2])
            values = np.stack(
                [
                    np.concatenate((np.stack((t, f), axis=-1), ph), axis=-1)
                    for t, f, ph, _, _, _ in (a, b)
                ],
                axis=-2,
            )
            record[block] = (values, (float(a[4]), float(b[5])), (a[3], b[3]))
    return record


def exact_pairs(a, b):
    t, ia, ib = np.intersect1d(a[0], b[0], assume_unique=True, return_indices=True)
    f = np.column_stack((a[1][ia], b[1][ib]))
    ph = np.stack((a[2][ia], b[2][ib]), axis=1)
    return len(t), stencils(bins(t, f, ph))


def matches(a, b, calibration):
    possible = []
    for i, (x, wx, nx) in a.items():
        for j, (y, wy, ny) in b.items():
            if i % 2 != j % 2:
                continue
            gap = float(np.max(abs(x[:, 0] - y[:, 0])))
            if gap > 60:
                continue
            bound = wire_stability(*calibration, min(wx[0], wy[0]), max(wx[1], wy[1]))
            if bound is not None:
                possible.append((gap, i, j, x, y, bound, nx, ny))
    a_used, b_used, result = set(), set(), []
    for gap, i, j, x, y, bound, nx, ny in sorted(possible, key=lambda z: z[:3]):
        if i in a_used or j in b_used:
            continue
        a_used.add(i)
        b_used.add(j)
        result.append(
            dict(
                fold=i % 2,
                values=np.stack((x, y)).tolist(),
                gap_s=gap,
                ref_excursion_rad=bound,
                counts=(nx, ny),
            )
        )
    return result


def support(curves, excluded, calibration):
    native = {i: native_rows(r) for i, r in enumerate(curves) if i not in excluded}
    corrected = {}
    time, phase = calibration
    for i, (t, f, z) in native.items():
        keep = (t >= time[0]) & (t <= time[-1])
        angles = np.column_stack([np.interp(t[keep], time, p) for p in phase.T])
        corrected[i] = stencils(bins(t[keep], f[keep], z[keep] * np.exp(-1j * angles)))
    pair_data = {key: [] for key in SCOPES}
    inventory = []
    for i, j in combinations(native, 2):
        exact_count, exact = exact_pairs(native[i], native[j])
        shared = [
            dict(
                fold=k % 2,
                values=v.tolist(),
                gap_s=0,
                ref_excursion_rad=None,
                counts=(counts, counts),
            )
            for k, (v, _, counts) in exact.items()
        ]
        stable = matches(corrected[i], corrected[j], calibration)
        count = [
            [sum(r["fold"] == fold for r in rows) for fold in (0, 1)] for rows in (shared, stable)
        ]
        if exact_count or stable:
            inventory.append(
                dict(
                    arcs=(i, j),
                    exact_epochs=exact_count,
                    coincident_train_held=count[0],
                    stable_train_held=count[1],
                )
            )
        for key, rows, n in zip(SCOPES, (shared, stable), count, strict=True):
            if min(n):
                pair_data[key].append((min(n), sum(n), i, j, rows))
    disjoint = {}
    for scope, entries in pair_data.items():
        used, groups = set(), []
        for _, _, i, j, rows in sorted(entries, key=lambda q: (-q[0], -q[1], q[2], q[3])):
            if i not in used and j not in used:
                used.update((i, j))
                groups.append(dict(ids=(i, j), rows=rows))
        disjoint[scope] = groups
    return disjoint, inventory


def wrap(x):
    return (x.real + np.pi) % (2 * np.pi) - np.pi + 1j * ((x.imag + np.pi) % (2 * np.pi) - np.pi)


def phase_difference(z, method):
    if method == "closure":
        return z[..., 1, :] - z[..., 0, :]
    return z[..., 1] - z[..., 0]


def geometry(p, v, time, xyz, enu):
    delta = p - xyz
    ray = delta / np.linalg.norm(delta, axis=-1, keepdims=True)
    field = ray @ enu[:2].T
    phase = bearing.WAVENUMBER * (field[..., 0] + 1j * field[..., 1])
    freq = -bearing.RF / grid.LIGHT_SPEED_KM_S * np.sum(ray * v, axis=-1)
    rate = (freq[..., 1] - freq[..., 0]) / (time[..., 1] - time[..., 0])
    return phase, rate, ray @ enu[2] >= 0


@dataclass(frozen=True)
class Pair:
    arcs: tuple
    time: np.ndarray
    phase: np.ndarray
    rate: np.ndarray
    train: np.ndarray
    p: np.ndarray
    v: np.ndarray
    ids: np.ndarray
    choices: np.ndarray
    visible_count: tuple

    def values(self, xyz, enu):
        return geometry(self.p, self.v, self.time, xyz, enu)


def candidates(p, v, t, train, rate, phase, positions, initial, labels, ids):
    xs = []
    for k in range(2):
        keep = np.flatnonzero(initial[:, k])
        if labels is not None:
            keep = keep[ids[keep] == labels[k]]
        if not len(keep):
            return None
        if labels is None:
            visits = []
            for xyz, enu in positions:
                q, f, visible = geometry(p[keep, :, k], v[keep, :, k], t[:, k], xyz, enu)
                r = np.mean(((f[:, train] - rate[train, k]) / RATE_SIGMA) ** 2, axis=1)
                observed = wrap(phase_difference(phase[train], "temporal"))[:, k]
                modeled = q[:, train, 1] - q[:, train, 0]
                norm = np.mean(((abs(observed) - abs(modeled)) / PHASE_SIGMA) ** 2, axis=1)
                visits.append(np.where(visible[:, train].all(axis=(1, 2)), [r, r + norm], np.inf))
            best = np.argsort(np.min(visits, axis=0), kind="stable", axis=1)[:, :6]
            keep = keep[np.unique(best)]
        xs.append(keep)
    return xs


def compile_pair(document, bank, ids, positions, labels):
    samples = np.asarray([r["values"] for r in document["rows"]])
    time, freq, a, b = samples.transpose(3, 0, 1, 2)
    phase = a + 1j * b
    rate = (freq[..., 1] - freq[..., 0]) / (time[..., 1] - time[..., 0])
    train = np.asarray([r["fold"] == 0 for r in document["rows"]])
    p, v, _ = grid._interpolated_states(bank, time.ravel())
    p, v = (x.reshape((len(ids), *time.shape, 3)) for x in (p, v))
    centre, frame = positions[0]
    d = p[:, train] - centre
    initial = ((d @ frame[2]) > -0.02 * np.linalg.norm(d, axis=-1)).all(axis=(1, 3))
    group_names = tuple(document["ids"])
    authorized = None if labels is None else [labels[k] for k in group_names]
    screen = candidates(p, v, time, train, rate, phase, positions, initial, authorized, ids)
    if screen is None:
        return None
    unique = np.unique(np.concatenate(screen))
    pairs = [(a, b) for a, b in product(*screen) if a != b]
    if not pairs:
        return None
    indices = np.searchsorted(unique, np.asarray(pairs))
    return Pair(
        group_names,
        time,
        phase,
        rate,
        train,
        p[unique],
        v[unique],
        ids[unique],
        indices,
        tuple(map(int, initial.sum(axis=0))),
    )


def choose_rows(matrix, choices):
    a, b = choices.T
    return np.stack((matrix[a, :, 0], matrix[b, :, 1]), axis=2)


def wrap_cost(errors):
    return 4 * (np.sin(errors.real / 2) ** 2 + np.sin(errors.imag / 2) ** 2)


def likelihood(pair, physical, method, yaw, select):
    phase, rate, visible = (choose_rows(a, pair.choices) for a in physical)
    physical_rate = rate[:, select] - pair.rate[select]
    cost = np.mean((physical_rate / RATE_SIGMA) ** 2, axis=(1, 2))
    fit = visible[:, select].all(axis=(1, 2, 3))
    if method == "doppler":
        return np.where(fit[:, None], cost[:, None], np.inf)
    predict = phase_difference(phase[:, select], method)
    measure = phase_difference(pair.phase[select], method)
    direction = np.exp(1j * np.deg2rad(yaw))
    closure = predict[:, None] * direction[None, :, None, None] - measure
    fit_cost = np.mean(wrap_cost(closure), axis=(2, 3)) / PHASE_SIGMA**2
    return np.where(fit[:, None], cost[:, None] + fit_cost, np.inf)


def offsets(cost):
    return np.argmin(cost, axis=0), np.minimum(PAD, np.min(cost, axis=0))


def site(bank, groups, xy, method, describe=False):
    xyz, enu, point = bearing.site_coords(bank, xy)
    values = [v.values(xyz, enu) for v in groups]
    yaw = np.array([0.0]) if method == "doppler" else YAW

    def rank(angles):
        columns = [
            likelihood(group, field, method, angles, group.train)
            for group, field in zip(groups, values, strict=True)
        ]
        choice, cost = (np.stack(x) for x in zip(*(offsets(c) for c in columns), strict=True))
        i = int(np.argmin(np.mean(cost, axis=0)))
        return i, choice[:, i], columns, float(np.mean(cost[:, i]))

    ref, indices, columns, train = rank(yaw)
    if method != "doppler":
        yaw = yaw[ref] + np.arange(-2.0, 3.0)
        ref, indices, columns, train = rank(yaw)
    if not describe:
        return train
    picked = yaw[ref]
    details = [
        score_group(group, physical, method, picked, k, cost[:, ref])
        for group, physical, k, cost in zip(groups, values, indices, columns, strict=True)
    ]
    hold = float(np.mean([min(PAD, r.get("held_cost", PAD)) for r in details]))
    return point.tolist(), train, hold, float(picked), indices, details


def finite(value):
    return float(value) if np.isfinite(value) else None


def rms(x):
    return float(np.sqrt(np.mean(np.abs(x) ** 2)))


def score_group(group, values, method, yaw_deg, k, training):
    phase, freq, visible = values
    held = ~group.train
    index = group.choices[k : k + 1]
    actual = choose_rows(visible, index)[0, held].all()
    held_cost = likelihood(group, values, method, np.array([yaw_deg]), held)[:, 0]
    train_alt = np.delete(training, k)
    hold_alt = np.delete(held_cost, k)
    row = dict(
        arcs=group.arcs,
        orbit_pair=group.ids[index[0]].tolist(),
        candidate_pairs=len(group.choices),
        visible_orbits=group.visible_count,
        train_stencils=int(group.train.sum()),
        held_stencils=int(held.sum()),
        held_cost=finite(held_cost[k]) if actual else None,
        train_gap=finite(np.min(train_alt) - training[k])
        if len(train_alt) and np.isfinite(training[k])
        else None,
        held_gap=finite(np.min(hold_alt) - held_cost[k]) if len(hold_alt) and actual else None,
    )
    if not actual or row["held_cost"] is None or not np.isfinite(training[k]):
        row.pop("held_cost")
        return row
    rf = choose_rows(freq, index)[0, held] - group.rate[held]
    row["held_rate_rms_hz_s"] = rms(rf)
    if method == "doppler":
        return row
    rotation = np.exp(1j * np.deg2rad(yaw_deg))
    predict = phase_difference(choose_rows(phase, index)[0, held], method) * rotation
    observed = phase_difference(group.phase[held], method)
    residual = wrap(predict - observed)
    shuffled = (
        np.roll(observed.ravel(), 1).reshape(observed.shape)
        if method == "closure"
        else np.roll(observed, 1, axis=0)
    )
    row.update(
        held_phase_rms_rad=rms(residual),
        held_phase_time_sham_rad=rms(wrap(predict - shuffled)),
        held_phase_identity_sham_rad=rms(
            wrap(
                phase_difference(choose_rows(phase, index[:, ::-1])[0, held], method) * rotation
                - observed
            )
        ),
        held_phase_bias_removed_rms_rad=rms(remove_bias(residual)),
        held_modeled_phase_rad=np.stack((wrap(predict).real, wrap(predict).imag), axis=-1).tolist(),
        held_observed_phase_rad=np.stack(
            (wrap(observed).real, wrap(observed).imag), axis=-1
        ).tolist(),
    )
    return row


def remove_bias(x):
    if not x.size:
        return x
    measured = np.angle(np.exp(1j * x.real).mean()) + 1j * np.angle(np.exp(1j * x.imag).mean())
    return wrap(x - measured)


def position_jacobian(bank, groups, xy, method, yaw_deg, selected, details):
    rotation = np.exp(1j * np.deg2rad(yaw_deg))
    delta = np.eye(2) * 0.25
    sites = [bearing.site_coords(bank, np.asarray(xy) + k)[:2] for k in np.r_[delta, -delta]]
    base = bearing.site_coords(bank, xy)[:2]
    geodesy, with_biases = [], []
    for g, k, row in zip(groups, selected, details, strict=True):
        if "held_cost" not in row:
            continue
        index, held = g.choices[k : k + 1], ~g.train
        fscale = max(RATE_SIGMA, row["held_rate_rms_hz_s"])
        pscale = max(PHASE_SIGMA, row.get("held_phase_rms_rad", 0))
        f, p = [], []
        for xyz, enu in sites:
            raw_phase, raw_rate, _ = g.values(xyz, enu)
            f.append(choose_rows(raw_rate, index)[0, held].ravel() / fscale)
            phase = phase_difference(choose_rows(raw_phase, index)[0, held], method)
            p.append(phase.ravel() * rotation / pscale)
        fj = (np.asarray(f[:2]) - f[2:]).T / 0.5
        if method == "doppler":
            j = np.column_stack((fj, np.zeros(len(fj))))
            geodesy.append(j)
            with_biases.append(j)
            continue
        pj = (np.asarray(p[:2]) - p[2:]).T / 0.5
        current = choose_rows(g.values(*base)[0], index)[0, held]
        yaw = 1j * phase_difference(current, method).ravel() * rotation / pscale
        design = np.column_stack((pj, yaw))
        freq = np.column_stack((fj, np.zeros(len(fj))))
        geodesy.extend((freq, design.real, design.imag))
        shifted = design - design.mean(axis=0, keepdims=True)
        with_biases.extend((freq, shifted.real, shifted.imag))
    return [radius(x) for x in (geodesy, with_biases)]


def radius(parts):
    if not parts:
        return None
    j = np.vstack(parts)
    q = j[:, -1]
    data = j[:, :2]
    if np.linalg.norm(q) > 0:
        q = q / np.linalg.norm(q)
        data = data - q[:, None] * (q @ data)
    eig = np.linalg.svd(data, compute_uv=False)
    return float(1 / eig[1]) if len(eig) >= 2 and eig[1] > 1e-9 else None


def solve_direction(bank, groups, method, assisted, scope):
    if not groups:
        return result({}, "insufficient_cross_arc_support")
    tested = {}

    def loss(xy):
        if xy not in tested:
            tested[xy] = site(bank, groups, xy, method)
        return tested[xy]

    best = min(product(np.linspace(-12.5, 12.5, 11), repeat=2), key=loss)
    for step in (0.5, 0.1):
        options = [
            tuple(np.clip(np.asarray(best) + step * np.asarray(d), -12.5, 12.5))
            for d in product(range(-2, 3), repeat=2)
        ]
        best = min(options, key=loss)
    point, train, held, yaw, choices, details = site(bank, groups, best, method, True)
    if train >= PAD:
        return result(
            {"candidate_pairs": sum(len(g.choices) for g in groups)},
            "all_training_hypotheses_hit_clutter_cap",
        )
    alternatives = [k for k in bearing.RIVALS if np.linalg.norm(np.subtract(k, best)) >= 8]
    alternatives += sorted(
        [k for k in tested if np.linalg.norm(np.subtract(k, best)) >= 8],
        key=loss,
    )[:4]
    lead = min(site(bank, groups, p, method, True)[2] for p in alternatives) - held
    valid = [r for r in details if "held_cost" in r]
    scales = position_jacobian(bank, groups, best, method, yaw, choices, details)

    def aggregate(name):
        vals = [v[name] for v in valid if name in v]
        return rms(vals) if vals else None

    survivors, used = 0, set()
    for r in valid:
        ids = set(r["orbit_pair"])
        if (
            r["train_gap"] is not None
            and r["train_gap"] >= 0.05
            and r["held_gap"] is not None
            and r["held_gap"] >= 0.05
            and r.get("held_phase_rms_rad", np.inf) <= 0.30
            and r["held_rate_rms_hz_s"] <= 150
            and not used & ids
            and r["held_phase_rms_rad"]
            < min(r["held_phase_time_sham_rad"], r["held_phase_identity_sham_rad"])
        ):
            survivors += 1
            used.update(ids)
    phase_rms = aggregate("held_phase_rms_rad")
    metrics = dict(
        training_cost=train,
        held_cost=held,
        held_region_lead=lead,
        yaw_deg=yaw,
        held_rate_rms_hz_s=aggregate("held_rate_rms_hz_s"),
        held_phase_rms_rad=phase_rms,
        held_phase_time_sham_rad=aggregate("held_phase_time_sham_rad"),
        held_phase_identity_sham_rad=aggregate("held_phase_identity_sham_rad"),
        held_phase_bias_removed_rms_rad=aggregate("held_phase_bias_removed_rms_rad"),
        held_radius_km=scales[0],
        held_pair_bias_free_radius_km=scales[1],
        held_supported_pairs=survivors,
        held_norads=sorted(used),
        pairs=details,
    )
    published = (
        method == "closure"
        and not assisted
        and scope == "coincident"
        and survivors >= 2
        and scales[0] is not None
        and scales[0] <= 5
        and phase_rms <= 0.30
        and lead >= 0.05
        and np.max(abs(np.asarray(best))) < 11.5
    )
    return result(metrics, None if published else "unresolved_cross_arc_geometry", point)


def result(metrics, reason, forced=None):
    return dict(
        status="ok" if reason is None else "withheld",
        reason=reason,
        boundary=BOUNDARY,
        metrics=metrics | dict(c_identifiable=False, position_attempted=forced is not None),
        arms=dict(
            c0=dict(latlon=forced if reason is None else None, forced_latlon=forced),
            fitted_c=dict(
                status="unavailable",
                reason="single_RF_calibration_cancels",
                latlon=None,
                forced_latlon=None,
            ),
        ),
    )


def solve(observation, catalogue, center, labels):
    cap = SimpleNamespace(**observation["clock"], catalog=catalogue.encode("ascii"))
    bank, ids, _ = bearing.orbital_bank(cap, center)
    ids = np.asarray(ids)
    positions = [bearing.site_coords(bank, k)[:2] for k in bearing.STARTS]
    if labels is not None:
        catalogue = parse_element_sets(catalogue)
        names = dict(zip(catalogue.names, catalogue.satellite_numbers, strict=True))
        labels = [names[s] for s in labels]
    outputs = {}
    for scope, rows in observation["groups"].items():
        usable = [
            g for q in rows if (g := compile_pair(q, bank, ids, positions, labels)) is not None
        ]
        for method in METHODS:
            entry = solve_direction(bank, usable, method, labels is not None, scope)
            entry["metrics"].update(
                observed_pairs=len(rows),
                modeled_pairs=len(usable),
                regional_orbits=len(ids),
                observed_stencils=sum(len(q["rows"]) for q in rows),
                modeled_train=sum(int(x.train.sum()) for x in usable),
                modeled_held=sum(int((~x.train).sum()) for x in usable),
                candidate_pairs=sum(len(x.choices) for x in usable),
            )
            outputs[scope + "_" + method] = entry
    return outputs
