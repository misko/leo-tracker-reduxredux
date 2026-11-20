"""Receiver positioning from differential phase on the measured StarLoc array."""

from dataclasses import dataclass
from itertools import product
from types import SimpleNamespace

import numpy as np

from leo.sky.frames import ecef_to_enu_matrix
from leo.sky.propagation import parse_element_sets

from ..reference import grid
from .peak_paths import orbital_bank

RF = 11.325e9
WAVENUMBER = 2 * np.pi * 0.1325 * RF / 299792458
F_SIGMA, P_SIGMA = 100, 0.20
YAW = np.exp(1j * np.deg2rad(np.arange(0, 360, 5)))
STARTS = ((0, 0), (10, 0), (-10, 0), (0, 10), (0, -10))
RIVALS = (*product((-12.5, 0, 12.5), repeat=2), (30, 0), (-30, 0), (0, 30), (0, -30))
BOUNDARY = "Measured three-channel beacon FFT samples and one causal offered region"
METHODS = ("bearing_transfer_joint", "bearing_transfer_doppler")


def secants(raw):
    """Extract non-overlapping short changes of the same complex FFT-bin pair."""
    size = len(raw)
    if not size:
        return []
    t, f = raw[:, :2].real.T
    iq = raw[:, 2:]
    strength = np.min(abs(iq), axis=1)
    take = np.flatnonzero((strength > 0) & np.isfinite(raw).all(axis=1))
    order = take[np.lexsort((-strength[take], t[take]))]
    _, first = np.unique(t[order], return_index=True)
    row = order[first]
    t, f, iq = t[row], f[row], iq[row] / abs(iq[row])
    u = np.column_stack((iq[:, 1] * iq[:, 2].conj(), iq[:, 0] * iq[:, 1].conj()))
    result = []
    for block in np.unique(t.astype(int) // 8):
        hits = []
        for offset in (1.5, 4.5):
            inside = np.flatnonzero(abs(t - (8 * block + offset)) <= 0.4)
            if len(inside) < 4:
                break
            z = u[inside].mean(axis=0)
            if np.min(abs(z)) < 0.65:
                break
            hits.append((float(np.mean(t[inside])), np.median(f[inside]), z, len(inside)))
        if len(hits) < 2:
            continue
        a, b = hits
        phase = np.angle(b[2] * a[2].conj())
        rate = (b[1] - a[1]) / (b[0] - a[0])
        if abs(rate) <= 5000 and np.max(abs(phase)) <= 2.5:
            result.append([a[0], b[0], float(rate), *phase.tolist(), a[3], b[3]])
    return result


@dataclass(frozen=True)
class Arc:
    name: int
    rates: np.ndarray
    phase: np.ndarray
    train: np.ndarray
    t: np.ndarray
    p: np.ndarray
    v: np.ndarray
    norads: np.ndarray
    available: int

    def values(self, xyz, frame):
        d = self.p - xyz
        rays = d / np.linalg.norm(d, axis=-1, keepdims=True)
        los_rate = -RF / grid.LIGHT_SPEED_KM_S * np.sum(rays * self.v, axis=-1)
        speed = np.diff(los_rate, axis=-1)[..., 0] / np.diff(self.t, axis=-1)[..., 0]
        direction = (rays[:, :, 1] - rays[:, :, 0]) @ frame[:2].T
        expected = WAVENUMBER * (direction[..., 0] + 1j * direction[..., 1])
        visible = (rays @ frame[2] >= 0).all(axis=2)
        return speed, expected, visible


def site_coords(tile, xy):
    xyz, _, coords = grid._sites(tile, np.asarray(xy, dtype=float).reshape(1, 2))
    return xyz[0], ecef_to_enu_matrix(*coords[0]), coords[0]


def field(rows, capture, catalogue, center, labels):
    tile, ids, stats = orbital_bank(capture, center)
    if labels is None:
        by_name = {}
    else:
        cat = parse_element_sets(catalogue)
        by_name = dict(zip(cat.names, cat.satellite_numbers, strict=True))
    xyz, basis, _ = site_coords(tile, (0, 0))
    arcs = []
    for row in rows:
        samples = np.asarray(row["pairs"], dtype=float).reshape(-1, 7)
        t = samples[:, :2]
        train = np.asarray(t[:, 0] // 8, dtype=int) % 2 == 0
        if np.count_nonzero(train) < 2 or np.count_nonzero(~train) < 2:
            continue
        p, v, _ = grid._interpolated_states(tile, t.ravel())
        shape = (len(ids), len(samples), 2, 3)
        p, v = p.reshape(shape), v.reshape(shape)
        d = p[:, train] - xyz
        visible = ((d @ basis[2]) >= -0.02 * np.linalg.norm(d, axis=-1)).all(axis=(1, 2))
        if labels is not None:
            visible &= np.asarray(ids) == by_name[labels[row["arc"]]]
        index = np.flatnonzero(visible)
        if not index.size:
            continue
        arc = Arc(
            row["arc"],
            samples[:, 2],
            samples[:, 3] + 1j * samples[:, 4],
            train,
            t,
            p[index],
            v[index],
            np.asarray(ids)[index],
            len(index),
        )
        if labels is None:
            shortlist = screen(arc, [site_coords(tile, xy)[:2] for xy in STARTS])
            arc = Arc(
                arc.name,
                arc.rates,
                arc.phase,
                train,
                t,
                arc.p[shortlist],
                arc.v[shortlist],
                arc.norads[shortlist],
                arc.available,
            )
        arcs.append(arc)
    return tile, arcs, stats | {"regional_orbits": len(ids)}


def screen(arc, poses):
    merit = []
    for xyz, enu in poses:
        f, z, ok = arc.values(xyz, enu)
        t = arc.train
        a = ((f[:, t] - arc.rates[t]) / F_SIGMA) ** 2
        b = ((abs(z[:, t]) - abs(arc.phase[t])) / P_SIGMA) ** 2
        loss = np.stack((np.mean(a, axis=1), np.mean(a + b, axis=1)))
        merit.append(np.where(ok[:, t].all(axis=1), loss, np.inf))
    best = np.argsort(np.min(merit, axis=0), axis=1, kind="stable")[:, :8]
    return np.unique(best)


def training_cost(arc, values):
    f, z, visible = values
    t = arc.train
    y = arc.phase[t]
    z = z[:, t]
    freq = np.mean(((f[:, t] - arc.rates[t]) / F_SIGMA) ** 2, axis=1)
    freq = np.where(visible[:, t].all(axis=1), freq, np.inf)
    mag = np.mean(abs(z) ** 2 + abs(y) ** 2, axis=1) / P_SIGMA**2
    cross = np.mean(y * z.conj(), axis=1) / P_SIGMA**2
    return freq, mag, cross


def discrete_choice(costs, joint):
    if not joint:
        selected = [int(np.argmin(f)) for f, _, _ in costs]
        return selected, align_sum([b[i] for (_, _, b), i in zip(costs, selected, strict=True)])
    scores = [(f + p)[:, None] - 2 * np.real(c[:, None].conj() * YAW) for f, p, c in costs]
    iyaw = int(np.argmin(sum(np.min(v, axis=0) for v in scores)))
    selected = [int(np.argmin(v[:, iyaw])) for v in scores]
    for _ in range(2):
        yaw = align_sum([b[i] for (_, _, b), i in zip(costs, selected, strict=True)])
        selected = [int(np.argmin(f + m - 2 * np.real(b.conj() * yaw))) for f, m, b in costs]
    return selected, align_sum([b[i] for (_, _, b), i in zip(costs, selected, strict=True)])


def align_sum(cross):
    total = sum(cross)
    return total / abs(total) if total else 1.0 + 0.0j


def group_validation(arc, values, i, yaw, joint, cost):
    f, z, visible = values
    hold = ~arc.train
    rf = f[:, hold] - arc.rates[hold]
    phase = z[:, hold] * yaw - arc.phase[hold]
    held_cost = np.mean((rf / F_SIGMA) ** 2, axis=1)
    if joint:
        held_cost += np.mean(abs(phase / P_SIGMA) ** 2, axis=1)
    valid = visible[:, hold].all(axis=1)
    held_cost = np.where(valid, held_cost, np.inf)
    order = [k for k in np.argsort(held_cost, kind="stable") if k != i]
    early_alt = [k for k in np.argsort(cost, kind="stable") if k != i]
    prefix_margin = float(cost[early_alt[0]] - cost[i]) if early_alt else None
    held_margin = float(held_cost[order[0]] - held_cost[i]) if order and valid[i] else None
    base = dict(
        arc=arc.name,
        candidate_count=len(arc.norads),
        near_visible_orbits=arc.available,
        orbit=int(arc.norads[i]),
        train_rows=int(arc.train.sum()),
        held_rows=int(hold.sum()),
        prefix_margin=finite(prefix_margin),
        held_margin=finite(held_margin),
        held_alternative=int(arc.norads[order[0]]) if order else None,
        confirmed=False,
    )
    if not valid[i] or not np.isfinite(cost[i]):
        return base
    obs = arc.phase[hold]
    model = z[i, hold] * yaw
    result = dict(
        held_rate_rms_hz_s=rms(rf[i]),
        held_phase_rms_rad=rms(phase[i]),
        held_phase_time_sham_rad=rms(model - np.roll(obs, 1)),
        held_phase_reflection_rad=rms(model - obs.conj()),
        held_cost=float(held_cost[i]),
        time_s=arc.t[hold].mean(axis=1).tolist(),
        observed_phase_rad=np.column_stack((obs.real, obs.imag)).tolist(),
        modeled_phase_rad=np.column_stack((model.real, model.imag)).tolist(),
    )
    confirmed = (
        prefix_margin is not None
        and prefix_margin >= 0.05
        and held_margin is not None
        and held_margin >= 0.05
        and result["held_rate_rms_hz_s"] <= 150
        and result["held_phase_rms_rad"] <= 0.25
    )
    return base | result | {"confirmed": bool(confirmed)}


def finite(value):
    return value if value is not None and np.isfinite(value) else None


def rms(values):
    return float(np.sqrt(np.mean(np.abs(values) ** 2)))


def evaluate(tile, arcs, xy, joint, *, held=False):
    xyz, enu, _ = site_coords(tile, xy)
    values = [a.values(xyz, enu) for a in arcs]
    pieces = [training_cost(a, v) for a, v in zip(arcs, values, strict=True)]
    indices, yaw = discrete_choice(pieces, joint)
    costs = [f + p - 2 * np.real(c.conj() * yaw) if joint else f for f, p, c in pieces]
    train = float(np.mean([min(30, c[i]) for c, i in zip(costs, indices, strict=True)]))
    if not held:
        return train
    records = [
        group_validation(a, v, i, yaw, joint, cost)
        for a, v, i, cost in zip(arcs, values, indices, costs, strict=True)
    ]
    test = float(np.mean([min(30, r.get("held_cost", 30)) for r in records]))
    return train, test, yaw, indices, records


def conditioning(tile, arcs, xy, yaw, candidates, records, joint):
    """Fixed-assignment held horizontal conditioning after eliminating one yaw."""
    jac, nuisance = [], []
    unit = np.eye(2) * 0.25
    geometry = [site_coords(tile, np.asarray(xy) + o)[:2] for o in np.r_[unit, -unit]]
    xyz, enu, _ = site_coords(tile, xy)
    for arc, i, row in zip(arcs, candidates, records, strict=True):
        if "held_cost" not in row:
            continue
        hold = ~arc.train
        fscale = max(F_SIGMA, row["held_rate_rms_hz_s"])
        pscale = max(P_SIGMA, row["held_phase_rms_rad"])
        phase = arc.values(xyz, enu)[1][i, hold] * yaw
        values = []
        for site, frame in geometry:
            f, p, _ = arc.values(site, frame)
            p = p[i, hold] * yaw / pscale
            rate = f[i, hold] / fscale
            values.append(np.r_[rate, p.real, p.imag] if joint else rate)
        jac.append((np.asarray(values[:2]) - values[2:]).T / 0.5)
        if joint:
            nuisance.extend(np.r_[np.zeros(len(phase)), -phase.imag / pscale, phase.real / pscale])
    if not jac:
        return [], None
    jac = np.vstack(jac)
    norm = np.linalg.norm(nuisance)
    if norm:
        q = np.asarray(nuisance) / norm
        jac -= q[:, None] * (q @ jac)
    singular = np.linalg.svd(jac, compute_uv=False).tolist()
    radius = 1 / singular[-1] if len(singular) == 2 and singular[-1] > 1e-9 else None
    return singular, radius


def fit(tile, arcs, assisted, joint):
    training = {}

    def cost(xy):
        if xy not in training:
            training[xy] = evaluate(tile, arcs, xy, joint)
        return training[xy]

    best = min(product(np.linspace(-12.5, 12.5, 11), repeat=2), key=cost)
    for step in (0.5, 0.1):
        points = [
            tuple(np.clip(np.asarray(best) + step * np.asarray(o), -12.5, 12.5))
            for o in product((-2, -1, 0, 1, 2), repeat=2)
        ]
        best = min(points, key=cost)
    train, test, yaw, indices, rows = evaluate(tile, arcs, best, joint, held=True)
    eligible = [r for r in rows if "held_cost" in r]
    groups = {r["orbit"] for r in eligible if r["confirmed"]}
    rivals = [r for r in RIVALS if np.linalg.norm(np.subtract(r, best)) >= 8]
    other = [r for r in training if np.linalg.norm(np.subtract(r, best)) >= 8]
    rivals += sorted(other, key=cost)[:4]
    lead = min(evaluate(tile, arcs, r, joint, held=True)[1] for r in rivals) - test
    singular, radius = conditioning(tile, arcs, best, yaw, indices, rows, joint)

    def aggregate(field):
        return rms([r[field] for r in eligible]) if eligible else None

    phase, rf = (aggregate(k) for k in ("held_phase_rms_rad", "held_rate_rms_hz_s"))
    sham, reflected = (
        aggregate(k) for k in ("held_phase_time_sham_rad", "held_phase_reflection_rad")
    )
    passed = (
        joint
        and not assisted
        and len(groups) >= 3
        and max(abs(x) for x in best) < 11.5
        and radius is not None
        and radius <= 5
        and lead >= 0.05
        and phase is not None
        and phase <= 0.25
        and rf <= 150
        and phase < min(sham, reflected)
    )
    p = site_coords(tile, best)[2].tolist()
    return outcome(
        assisted,
        joint,
        p=p,
        success=passed,
        metrics=dict(
            train_score=train,
            held_score=test,
            held_spatial_lead=lead,
            held_rate_rms_hz_s=rf,
            held_phase_rms_rad=phase,
            held_phase_time_sham_rad=sham,
            held_phase_reflection_rad=reflected,
            held_singular_per_km=singular,
            held_conditional_radius_km=radius,
            held_independent_norads=sorted(groups),
            train_yaw_deg=float(np.angle(yaw, deg=True)),
            attempted_sites=len(training),
            arcs=rows,
        ),
    )


def outcome(assisted, joint, *, p=None, success=False, metrics=None):
    if assisted:
        reason = "author_id_conditioned_diagnostic"
    elif not joint:
        reason = "matched_doppler_diagnostic"
    else:
        reason = "insufficient_measured_identity_and_geometry"
    return dict(
        status="ok" if success else "withheld",
        reason=None if success else reason,
        boundary=BOUNDARY,
        metrics=(metrics or {})
        | dict(
            position_attempted=p is not None,
            author_id_aided=assisted,
            phase_enabled=joint,
            c_identifiable=False,
        ),
        arms=dict(
            c0=dict(latlon=p if success else None, forced_latlon=p),
            fitted_c=dict(
                latlon=None,
                forced_latlon=None,
                status="unavailable",
                reason="fixed_single_RF_term_cancels_in_each_rate",
            ),
        ),
    )


def solve(observation, catalogue, center, labels):
    cap = SimpleNamespace(**observation["clock"], catalog=catalogue.encode("ascii"))
    tile, arcs, info = field(observation["arcs"], cap, catalogue, center, labels)
    results = [
        fit(tile, arcs, labels is not None, joint)
        if len(arcs) >= 2
        else outcome(labels is not None, joint)
        for joint in (True, False)
    ]
    for r in results:
        r["metrics"].update(
            info,
            modeled_arcs=len(arcs),
            available_arcs=len(observation["arcs"]),
            total_nominees=sum(len(a.norads) for a in arcs),
            train_pairs=sum(int(a.train.sum()) for a in arcs),
            held_pairs=sum(int((~a.train).sum()) for a in arcs),
        )
    return results
