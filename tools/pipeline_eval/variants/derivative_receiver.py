"""Causal spatial inference from anonymous polynomial Doppler derivatives."""

from dataclasses import dataclass
from itertools import combinations, product
from time import perf_counter

import numpy as np
from scipy.special import logsumexp

from ..reference import grid
from . import blind_track_identity as linker
from . import peak_paths as orbit

METHOD = "derivative_receiver"
BOUNDARY = "Native GLRT peaks through anonymous polynomial derivatives and causal orbit grid"
PHASE = np.arange(-18.0, 19.0, 6.0)
MAX_ORBITS = 16
MAX_ARCS = 36


@dataclass(frozen=True)
class Arc:
    time: np.ndarray
    frequency: np.ndarray
    rf: float
    key: tuple | None
    cut: int
    head: np.ndarray
    tail: np.ndarray
    curvature: tuple
    sigma: float


@dataclass(frozen=True)
class Surface:
    arc: Arc
    norads: np.ndarray
    frequency: np.ndarray
    head: np.ndarray
    held: np.ndarray
    evidence: np.ndarray
    phase: np.ndarray


def polynomial(t):
    """Linear operators for physical d²CFO/dt² at two times within the interval."""
    half = np.ptp(t) / 2
    x = (t - (t[0] + t[-1]) / 2) / half
    design = np.column_stack((np.ones(len(x)), x, x * x, x * x * x))
    q, r = np.linalg.qr(design)
    polynomial_coefficients = np.linalg.solve(r, q.T)
    curvature = np.array([[0, 0, 2, -3], [0, 0, 2, 3]]) @ polynomial_coefficients / half**2
    covariance = curvature @ curvature.T
    values, vectors = np.linalg.eigh(covariance)
    standardized = (vectors / np.sqrt(values)).T @ curvature
    return design @ polynomial_coefficients, curvature, standardized


def features(track, *, measured=False):
    t, y = (np.asarray(track[k], dtype=float) for k in ("times", "values"))
    if (
        len(t) < 19
        or y.shape != t.shape
        or not np.isfinite([t, y]).all()
        or np.any(np.diff(t) <= 0)
    ):
        return None
    # Public tracks can be densely sampled. Use deterministic real points, never a fitted curve.
    if len(t) > 80:
        use = np.linspace(0, len(t) - 1, 80).astype(int)
        t, y = t[use], y[use]
    cut = np.searchsorted(t, t[0] + 0.58 * np.ptp(t))
    if cut < 9 or len(t) - cut < 7 or np.ptp(t[:cut]) < 7 or np.ptp(t[cut:]) < 5:
        return None
    fitted, early_physical, head = polynomial(t[:cut])
    _, late_physical, tail = polynomial(t[cut:])
    off_polynomial = y[:cut] - fitted @ y[:cut]
    noise = max(95.0, 1.4826 * np.median(abs(off_polynomial - np.median(off_polynomial))))
    # Inflate the iid covariance for repeated/coherent pilot observations.
    sigma = float(noise * 2.0)
    curve = early_physical @ y[:cut], late_physical @ y[cut:]
    key = None if measured else (track["receiver"], track["channel"], track["rf_hz"])
    return Arc(t, y, float(track["rf_hz"]), key, cut, head / sigma, tail / sigma, curve, sigma)


def predicted(bank, times, rf, sites):
    terms = []
    for phase in PHASE:
        p, v, _ = grid._interpolated_states(bank, times + phase)
        p, v = (orbit.rotate(x, orbit.EARTH_ROTATION * phase) for x in (p, v))
        ray = p[None, :, :, :] - sites[:, None, None, :]
        distance = np.linalg.norm(ray, axis=-1)
        radial = np.sum(ray * v, axis=-1) / distance
        elevation = (ray @ bank.enu_frame[2]) / distance
        terms.append(np.where(elevation >= -0.03, -rf / grid.LIGHT_SPEED_KM_S * radial, np.nan))
    return np.stack(terms, axis=2)


def derivative_cost(prediction, observed, operator):
    error = (prediction - observed) @ operator.T
    loss = np.square(error).sum(axis=-1)
    return np.nan_to_num(loss, nan=np.inf, posinf=np.inf)


def surface(bank, numbers, sites, arc, sentinels):
    y, cut = arc.frequency, arc.cut
    scan = predicted(bank, arc.time[:cut], arc.rf, sites[sentinels])
    initial = derivative_cost(scan, y[:cut], arc.head) + (PHASE / 12) ** 2
    best = initial.min(axis=(0, 2))
    k = np.argsort(best, kind="stable")[:MAX_ORBITS]
    k = k[np.isfinite(best[k])]
    if not len(k):
        return None
    sub = orbit.slice_orbit(bank, k)
    f = predicted(sub, arc.time, arc.rf, sites)
    train = derivative_cost(f[..., :cut], y[:cut], arc.head) + (PHASE / 12) ** 2
    hold = derivative_cost(f[..., cut:], y[cut:], arc.tail)
    likelihood = logsumexp(-0.5 * train, axis=2) - logsumexp(-0.5 * (PHASE / 12) ** 2)
    return Surface(arc, numbers[k], f, train, hold, likelihood, train.argmin(axis=2))


def coincident(surfaces):
    """Exact same receiver/RF epochs from distinct linked peaks."""
    found = []
    for (i, a), (j, b) in combinations(enumerate(surfaces), 2):
        if a.arc.key is None or a.arc.key != b.arc.key:
            continue
        t, ia, ib = np.intersect1d(
            a.arc.time[: a.arc.cut], b.arc.time[: b.arc.cut], return_indices=True
        )
        if len(t) < 8 or np.ptp(t) < 7:
            continue
        frequency = a.arc.frequency[ia] - b.arc.frequency[ib]
        if np.ptp(frequency) < 350:
            continue
        x = t - t.mean()
        slope = x / (x @ x)
        # Equal actual RF makes the common oscillator term and calibration coefficient cancel.
        scale = np.hypot(a.arc.sigma, b.arc.sigma) * np.linalg.norm(slope)
        found.append((i, j, ia, ib, frequency @ slope, slope, scale, np.ptp(t)))
    used, picks = set(), []
    for pair in sorted(found, key=lambda p: -p[-1]):
        i, j = pair[:2]
        if i not in used and j not in used:
            picks.append(pair)
            used.update((i, j))
    return picks, len(found)


def select(surfaces, pairs):
    """Marginalize a bounded phase prior and reduce paired orbit assignments locally."""
    best = np.array([a.evidence.argmax(axis=1) for a in surfaces])
    indexes = np.arange(best.shape[1])
    costs = np.array([-a.evidence[indexes, k] for a, k in zip(surfaces, best, strict=True)])
    # A data-dependent pool of four orbit hypotheses per member bounds pair reconciliation.
    for i, j, ia, ib, observed, slope, scale, _ in pairs:
        a, b = surfaces[i], surfaces[j]
        aa, bb = (np.argsort(-s.evidence, axis=1, kind="stable")[:, :4] for s in (a, b))

        def component(s, ids, samples, slope):
            p = s.phase[indexes[:, None], ids]
            f = s.frequency[indexes[:, None], ids, p]
            return s.evidence[indexes[:, None], ids], f[..., samples] @ slope

        ea, fa = component(a, aa, ia, slope)
        eb, fb = component(b, bb, ib, slope)
        score = (
            ea[:, :, None]
            + eb[:, None, :]
            - 0.25 * ((observed - fa[:, :, None] + fb[:, None, :]) / scale) ** 2
        )
        valid = a.norads[aa][:, :, None] != b.norads[bb][:, None, :]
        score = np.where(valid & np.isfinite(score), score, -np.inf)
        x, y = np.unravel_index(score.reshape(len(indexes), -1).argmax(axis=1), score.shape[1:])
        choose = np.isfinite(score[indexes, x, y])
        # One score per two-member factor. The second row retains its diagnostic assignment.
        best[i, choose], best[j, choose] = aa[indexes, x][choose], bb[indexes, y][choose]
        costs[i, choose], costs[j, choose] = (
            -0.5 * score[indexes, x, y][choose],
            -0.5 * score[indexes, x, y][choose],
        )
    return best, np.minimum(costs, 12.0).sum(axis=0)


def sensitivity(s, row, p, head, tail, axis_indices):
    """Measure exact 25 km CFO change before and after projecting phase and clock."""
    index = np.array(axis_indices)
    f = s.frequency[index, row, p]
    d = f[1::2] - f[::2]
    if not np.isfinite(d).all():
        return None
    phased = (
        s.frequency[index, row, min(p + 1, len(PHASE) - 1)] - s.frequency[index, row, max(p - 1, 0)]
    )
    trend = np.vstack((np.ones(s.arc.time.size), s.arc.time - s.arc.time.mean())).T
    affine = d - (trend @ np.linalg.lstsq(trend, d.T, rcond=None)[0]).T
    cut = s.arc.cut

    def effect(rows):
        return np.column_stack((rows[:, :cut] @ head.T, rows[:, cut:] @ tail.T))

    dx, dp = effect(d), effect(phased.mean(axis=0)[None, :])[0]
    if np.isfinite(dp).all() and dp @ dp > 1e-10:
        dx -= ((dx @ dp) / (dp @ dp))[:, None] * dp
    return np.sqrt(np.mean(d * d, axis=1)), np.sqrt(np.mean(affine * affine, axis=1)), dx


def _rms(values):
    return float(np.sqrt(np.mean(np.square(values)))) if len(values) else None


def infer(capture, tracks, tile, *, differential=True, measured=False):
    began = perf_counter()
    arcs = [a for t in tracks if (a := features(t, measured=measured)) is not None][:MAX_ARCS]
    result = {}
    answer = dict(latlon=None, forced_latlon=None, c_hz_per_ghz=None, c_identifiable=False)
    reason = "insufficient_derivative_arcs"
    if arcs:
        bank, ids, _ = orbit.orbital_bank(capture, tile["center"])
        half = float(tile.get("width_km", 25)) / 2
        xy = np.array(list(product(np.linspace(-half, half, 5), repeat=2)))
        sites, _, latlon = grid._sites(bank, xy)
        candidates = [
            s
            for a in arcs
            if (s := surface(bank, np.asarray(ids), sites, a, [0, 4, 12, 20, 24])) is not None
        ]
        pairs, raw_pairs = coincident(candidates)
        result.update(
            regional_orbits=len(ids),
            grid_sites=len(xy),
            eligible_arcs=len(candidates),
            coincident_pairs=raw_pairs,
            disjoint_pairs=len(pairs),
            proposed_orbits=sum(len(s.norads) for s in candidates),
        )
        if candidates:
            choice, cost = select(candidates, pairs if differential else [])
            winner = int(cost.argmin())
            held = np.array(
                [
                    s.held[np.arange(len(xy)), k, s.phase[np.arange(len(xy)), k]]
                    for s, k in zip(candidates, choice, strict=True)
                ]
            )
            informative, records, projected, raw_rf, affine_rf, fit, extrapolated = (
                set(),
                [],
                [],
                [],
                [],
                [],
                [],
            )
            withheld_idx, conditional_geometry = [], {}
            for i, s in enumerate(candidates):
                j = choice[i, winner]
                p = s.phase[winner, j]
                f = s.frequency[winner, j, p]
                if not np.isfinite(f).all():
                    continue
                norad = int(s.norads[j])
                ordered = np.argsort(-s.evidence[winner], kind="stable")
                alternatives = ordered[ordered != j][:3]
                null = s.held[winner, alternatives, s.phase[winner, alternatives]].min(
                    initial=np.inf
                )
                confidence = null - held[i, winner]
                quality = (
                    held[i, winner] <= 5
                    and np.isfinite(null)
                    and confidence >= 3.0
                    and norad not in informative
                )
                records.append(
                    dict(
                        norad=norad,
                        phase_s=float(PHASE[p]),
                        measured_head_curvature_hz_s2=s.arc.curvature[0].tolist(),
                        measured_tail_curvature_hz_s2=s.arc.curvature[1].tolist(),
                        orbit_weight_conditioned_on_shortlist=float(
                            np.exp(s.evidence[winner, j] - logsumexp(s.evidence[winner]))
                        ),
                        held_polynomial_cost=float(held[i, winner]),
                        nearest_orbit_null_advantage=float(confidence)
                        if np.isfinite(confidence)
                        else None,
                        informative=bool(quality),
                    )
                )
                response = sensitivity(s, j, p, s.arc.head, s.arc.tail, [2, 22, 10, 14])
                if response is not None:
                    raw_rf.extend(response[0])
                    affine_rf.extend(response[1])
                    conditional_geometry.setdefault(norad, response[2])
                if quality:
                    informative.add(norad)
                    withheld_idx.append(i)
                    if response is not None:
                        projected.append(response[2])
                t, cut = s.arc.time, s.arc.cut
                A = np.column_stack((np.ones(len(t)), t - t[:cut].mean()))
                y = s.arc.frequency - f
                bias = np.linalg.lstsq(A[:cut], y[:cut], rcond=None)[0]
                residual = y - A @ bias
                fit.extend(residual[:cut])
                extrapolated.extend(residual[cut:])
            distant = np.linalg.norm(xy - xy[winner], axis=1) >= 8
            advantage = None
            if withheld_idx and distant.any():
                loss = np.minimum(held[withheld_idx], 15).sum(axis=0)
                advantage = float(loss[distant].min() - loss[winner])
            singular = (
                np.linalg.svd(np.hstack(projected), compute_uv=False) if projected else np.zeros(2)
            )
            result.update(
                informative_orbits=len(informative),
                raw_25km_rms_hz=_rms(raw_rf),
                affine_removed_25km_rms_hz=_rms(affine_rf),
                phase_projected_25km_singular=singular.tolist(),
                forced_identity_25km_singular=np.linalg.svd(
                    np.hstack(list(conditional_geometry.values())), compute_uv=False
                ).tolist()
                if conditional_geometry
                else None,
                held_spatial_advantage=advantage,
                orbit_trials=records,
                edge=bool(np.max(abs(xy[winner])) >= half),
            )
            answer.update(
                forced_latlon=latlon[winner].tolist(),
                rf_rms_hz=_rms(fit),
                held_rms_hz=_rms(extrapolated),
                held_points=len(extrapolated),
            )
            reason = (
                "insufficient_held_identity_margin"
                if len(informative) < 3
                else "weak_25km_derivative_geometry"
                if singular[-1] < 3.0
                else "held_spatial_alternative"
                if advantage is None or advantage < 4
                else "tile_edge"
                if result["edge"]
                else None
            )
    if reason is None:
        answer["latlon"] = answer["forced_latlon"]
    result.update(
        anonymous_arcs=len(tracks),
        polynomial_arcs=len(arcs),
        coefficient_gauge="per_arc_affine",
        model_s=perf_counter() - began,
        candidate_differential=bool(differential),
    )
    return dict(
        status="ok" if reason is None else "withheld",
        reason=reason,
        boundary="Measured anonymous beacon factors through causal derivative grid"
        if measured
        else BOUNDARY,
        metrics=result,
        arms=dict(c0=answer | {"c_hz_per_ghz": 0.0}, fitted_c=answer.copy()),
    )


def solve(capture, *, tile, differential=True):
    started = perf_counter()
    _, tracks, metrics = linker.observations(capture, False)
    output = infer(capture, tracks, tile, differential=differential)
    output["metrics"].update(metrics, native_to_position_s=perf_counter() - started)
    return output
