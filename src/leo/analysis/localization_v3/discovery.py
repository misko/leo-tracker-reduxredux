"""Fresh all-catalogue hypotheses using explicit scan evidence and regional bounds.

Preserves the production seed order, curvature eligibility and shared phase
proposal rules. This policy never receives saved satellite labels or GPS truth.
"""
import itertools

import numpy as np

from leo.analysis.localization_v3.discovery_likelihood import DiscoveryPosition
from leo.analysis.localization_v3.families import nomination_rows, numpy_state
from leo.analysis.localization_v3.scan import group
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD
from leo.analysis.research.shared_orbit_phase_fit import (
    augment_phase_statistics,
    joint_update,
    penalized_score,
    profile_phases,
    proposal_phases,
)

REFERENCE_RF = 11.5e9
DRIFT_BOUND_HZ_S = 5.0


def statistics(groups, bank, corrections, height=0):
    """Exact sufficient statistics; no per-track offset in the fitted model."""
    # npz members decompress on every access. Materialize once for this scan.
    if isinstance(bank, np.lib.npyio.NpzFile):
        bank = {key: bank[key] for key in bank.files}
    fragments, starts, comp_index = [], [], []
    means, cross, centered_rss, visible = [], [], [], []
    ns, mx, xx, gs, qs, curvature, fragment_active = [], [], [], [], [], [], []
    for ci, (_, members) in enumerate(groups):
        starts.append(len(fragments))
        active = False
        for track in members:
            t = track["times"]
            indexes = np.searchsorted(bank["time_s"], t)
            if not np.array_equal(bank["time_s"][indexes], t):
                raise ValueError("bank lacks exact measurement times")
            x = (t - 150) / 150
            xc = x - x.mean()
            q = track["rf_hz"] / REFERENCE_RF
            z = track["values"][None, :] - q * bank[f"doppler_{height}"][:, indexes]
            z -= corrections[str(track["channel"])]
            mean = z.mean(axis=1)
            centered = z - mean[:, None]
            means.append(mean)
            cross.append(centered @ xc)
            centered_rss.append(np.sum(centered**2, axis=1))
            visible.append(np.min(bank["elevation_deg"][:, indexes], axis=1) >= 0.0)
            yd = track["values"] - track["values"].mean()
            affine = yd - xc * (yd @ xc) / max(xc @ xc, 1e-12)
            # Active measured curvature, not merely a degree-2 polynomial label.
            curved = np.ptp(t) >= 20 and np.sqrt(np.mean(affine**2)) >= 250
            active |= curved
            fragment_active.append(curved)
            fragments.append(track)
            comp_index.append(ci)
            ns.append(len(t))
            mx.append(x.mean())
            xx.append(xc @ xc)
            gs.append(group(track))
            qs.append(q)
        curvature.append(active)
    result = dict(
        fragments=fragments,
        starts=np.array(starts),
        ci=np.array(comp_index),
        n=np.array(ns),
        mx=np.array(mx),
        xx=np.array(xx),
        g=np.array(gs),
        q=np.array(qs),
        mean=np.array(means),
        xz=np.array(cross),
        rss=np.array(centered_rss),
        visible=np.array(visible),
        active=np.array(curvature),
        fragment_active=np.array(fragment_active),
    )
    result["count"] = np.add.reduceat(result["n"], result["starts"])
    shape = np.maximum(
        0, result["rss"] - result["xz"] ** 2 / np.maximum(result["xx"][:, None], 1e-12)
    )
    result["shape_rms"] = np.sqrt(
        np.add.reduceat(shape, result["starts"], axis=0) / result["count"][:, None]
    )
    result["component_visible"] = np.logical_and.reduceat(
        result["visible"], result["starts"], axis=0
    )
    return result


def seed_calibrations(stats, beta, budget=160):
    beta = beta.copy()
    bound = 150 * DRIFT_BOUND_HZ_S
    beta[4:8] = np.clip(beta[4:8], -bound, bound)
    yield beta.copy()
    anchors = np.flatnonzero(stats["active"])
    anchors = sorted(anchors, key=lambda c: -stats["count"][c])[:20]
    qgroup = np.array(
        [np.mean(stats["q"][stats["g"] == g]) if np.any(stats["g"] == g) else 1.0 for g in range(4)]
    )
    emitted = 0
    for ci in anchors:
        rows = np.flatnonzero((stats["ci"] == ci) & stats["fragment_active"])
        # Curvature alone can rank an impossible Doppler slope ahead of the
        # correct object. Bound seed slopes, allowing 450 Hz over a short span.
        slopes = stats["xz"][rows] / np.maximum(stats["xx"][rows, None], 1e-12)
        spans = np.array([np.ptp(stats["fragments"][r]["times"]) for r in rows])
        limits = bound + 450 * 150 / np.maximum(spans, 1.0)
        possible = np.all(np.abs(slopes) <= limits[:, None], axis=0)
        order = np.argsort(
            np.where(stats["component_visible"][ci] & possible, stats["shape_rms"][ci], np.inf)
        )[:8]
        for satellite in order:
            if not stats["component_visible"][ci, satellite] or not possible[satellite]:
                continue
            # A discovery gauge seed only. Final model is eight shared native-Hz
            # parameters, and final RMS never removes a free track affine term.
            row = rows[np.argmax(stats["n"][rows])]
            g = stats["g"][row]
            slope = stats["xz"][row, satellite] / max(stats["xx"][row], 1e-12)
            intercept = stats["mean"][row, satellite] - slope * stats["mx"][row]
            intercept = (intercept + PERIOD / 2) % PERIOD - PERIOD / 2
            a = (intercept - beta[g]) / stats["q"][row]
            d = (slope - beta[g + 4]) / stats["q"][row]
            seed = beta.copy()
            seed[:4] += a * qgroup
            seed[4:8] = np.clip(seed[4:8] + d * qgroup, -bound, bound)
            for r in rows:
                rg = stats["g"][r]
                rd = stats["xz"][r, satellite] / max(stats["xx"][r], 1e-12)
                seed[rg + 4] = np.clip(rd, -bound, bound)
                seed[rg] = stats["mean"][r, satellite] - seed[rg + 4] * stats["mx"][r]
            seed[:4] = (seed[:4] + PERIOD / 2) % PERIOD - PERIOD / 2
            yield seed
            emitted += 1
            if emitted >= budget:
                return


def improve(
    stats,
    beta,
    phase,
    sigma,
    bounds,
    *,
    gates=(4000.0, 1000.0, 450.0),
    drift_sigma_hz_s=2.0,
    drift_bound_hz_s=5.0,
):
    if not np.isfinite(drift_sigma_hz_s) or drift_sigma_hz_s <= 0:
        raise ValueError("finite positive drift prior sigma required")
    if not np.isfinite(drift_bound_hz_s) or drift_bound_hz_s < 0:
        raise ValueError("finite nonnegative drift bound required")
    beta = beta.copy()
    beta[4:8] = np.clip(beta[4:8], -150 * drift_bound_hz_s, 150 * drift_bound_hz_s)
    score, terms, parts = penalized_score(
        stats, beta, phase, sigma, drift_sigma_hz_s=drift_sigma_hz_s
    )
    best = (score, beta.copy(), phase.copy(), None, parts)
    for gate in gates:
        for _ in range(2):
            terms = profile_phases(stats, beta, phase)
            proposed_beta, proposed_phase, info = joint_update(
                stats,
                terms.best,
                terms.aliases,
                beta,
                phase,
                sigma,
                bounds,
                terms.rms_hz < gate,
                drift_sigma_hz_s=drift_sigma_hz_s,
                drift_bound_hz_s=drift_bound_hz_s,
            )
            step = proposed_beta - beta
            step[:4] = (step[:4] + PERIOD / 2) % PERIOD - PERIOD / 2
            accepted = None
            for fraction in (1.0, 0.5, 0.25, 0.125, 0.0625):
                b = beta + fraction * step
                b[:4] = (b[:4] + PERIOD / 2) % PERIOD - PERIOD / 2
                p = phase + fraction * (proposed_phase - phase)
                value, _, detail = penalized_score(
                    stats, b, p, sigma, drift_sigma_hz_s=drift_sigma_hz_s
                )
                if value < score - 1e-6:
                    accepted = value, b, p, info, detail
                    break
            if accepted is None:
                break
            score, beta, phase, info, parts = accepted
            if score < best[0]:
                best = score, beta.copy(), phase.copy(), info, parts
    return best


def coherent_phase(phases, sigma, weight):
    """One weighted phase mode; incompatible component hypotheses stay separate."""
    p, s, w = (np.asarray(a, float) for a in (phases, sigma, weight))
    if p.ndim != 1 or s.shape != p.shape or w.shape != p.shape or not len(p):
        raise ValueError("matching nonempty phase hypotheses required")
    if not np.isfinite(p).all() or np.any(s <= 0) or np.any(w < 0) or not w.sum():
        raise ValueError("finite phases, positive scales and nonzero weights required")
    compatible = abs(p[:, None] - p[None, :]) <= 3 * np.sqrt(s[:, None] ** 2 + s[None, :] ** 2)
    support = compatible @ w
    chosen = int(np.argmax(support))
    mask = compatible[chosen]
    order = np.argsort(p[mask])
    values = p[mask][order]
    weights = w[mask][order]
    phase = float(values[np.searchsorted(np.cumsum(weights), weights.sum() / 2)])
    return phase, float(support[chosen]), int(mask.sum())


def explore(scan, state, anchor, method, topk=4, maximum=64, *, compact_update=False):
    if compact_update:
        raise ValueError("Discovery uses the joint radio-prior fitter, not a compact update")
    base = phase_linear_frequency(scan.geometry, *scan.search_region.latlon(anchor))
    groups = scan.groups
    if method == "receiver_smooth":
        groups = []
        for i in scan.curved:
            t = scan.tracks[i]
            adjusted = dict(
                t,
                values=t["values"]
                - t["rf_hz"] / 11.5e9 * scan.rx_basis[i] @ state["smooth"][t["receiver"] - 1],
            )
            groups.append((t["key"], [adjusted]))
    stats = statistics(
        groups,
        dict(time_s=scan.times, doppler_0=base[0], elevation_deg=base[1]),
        {str(t["channel"]): 0.0 for t in scan.tracks},
    )
    stats = augment_phase_statistics(stats, scan.times, base[0], base[2])
    # Eligibility is frozen from the original raw observations, even when a
    # receiver smooth term was subtracted for proposal generation.
    stats["active"][:] = True
    stats["fragment_active"][:] = True
    phases, scores = proposal_phases(
        stats, state["beta"], scan.sigma, np.full(len(scan.norads), 15.0), return_components=True
    )
    n = stats["n"][:, None]
    information = np.maximum(
        0, stats["hh"] + n * stats["hm"] ** 2 - (n * stats["hm"]) ** 2 / (n + 150**2 / 1000**2)
    )
    phase_sigma = 150 / np.sqrt(information + 150**2 / scan.sigma[None, :] ** 2)
    best = np.argsort(scores, axis=1)[:, :topk]
    weights = np.exp(
        -0.5
        * np.maximum(0, scores - scores.min(axis=1)[:, None])
        * np.minimum(stats["count"], 50)[:, None]
        / 150**2
    )
    hypotheses = {}
    for j in np.unique(best):
        rows = np.flatnonzero(
            np.any(best == j, axis=1) & (scores[:, j] < 1000**2) & (weights[:, j] > 0.001)
        )
        if not len(rows):
            continue
        phase, support, count = coherent_phase(
            phases[rows, j], phase_sigma[rows, j], weights[rows, j]
        )
        hypotheses[int(j)] = dict(phase_s=phase, support=support, coherent_curves=count)
    chosen = sorted(hypotheses, key=lambda j: -hypotheses[j]["support"])[:maximum]
    proposal = numpy_state(state)
    for j in chosen:
        proposal["phases"][j] = hypotheses[j]["phase_s"]
    point = scan.search_region.native_point(scan, anchor)
    # Exploratory component-specific phases are discarded after this step.
    # The update returns one shared phase per selected satellite and no phase
    # fields for unsupported candidate hypotheses.
    _, _, nominations, predicted = scan.association(proposal, base, point, method)
    compact = proposal
    _, rows, nominations, _ = scan.association(compact, base, point, method)
    return dict(state=compact, rows=nomination_rows(scan, rows, nominations)), dict(
        candidate_hypotheses=len(hypotheses),
        explored_candidates=len(chosen),
        hypotheses={str(int(scan.norads[j])): hypotheses[j] for j in chosen},
    )


def project_radio_state(state):
    """Project proposal drifts to the final RX mean/contrast box before scoring."""
    state = numpy_state(state)
    for receiver in range(2):
        rates = state["beta"][4 + 2 * receiver : 6 + 2 * receiver] / 150
        mean = np.clip(rates.mean(), -30, 30)
        contrast = np.clip((rates[1] - rates[0]) / 2, -1.5, 1.5)
        state["beta"][4 + 2 * receiver : 6 + 2 * receiver] = 150 * np.array(
            [mean - contrast, mean + contrast]
        )
    state["beta"][:4] = (state["beta"][:4] + PERIOD / 2) % PERIOD - PERIOD / 2
    return state


def standard_problem(scan, seed, sigma, *, fitted_c=False, aliases=None):
    seed = dict(seed, state=reference_state(seed["state"]))
    return DiscoveryPosition(
        scan, seed, fitted_c, variant="normal", sigma=sigma, aliases=aliases
    )


def reference_state(state):
    """Clip numerical expansion epochs to the bank; retain the absolute prior."""
    state = numpy_state(state)
    state["phases"] = np.clip(state["phases"], -15, 15)
    return state


def score_at(problem, point):
    r = problem.residual(np.asarray(point))
    return float(r @ r)


def zero_state(scan):
    return dict(
        beta=np.zeros(8),
        phases=np.zeros(len(scan.norads)),
        extra={},
        smooth=np.zeros((2, scan.rx_basis[0].shape[1])),
    )


def fresh_discovery(scan, sigma, *, budget=8):
    base = phase_linear_frequency(scan.geometry, *scan.search_region.center)
    stats = statistics(
        scan.groups,
        dict(time_s=scan.times, doppler_0=base[0], elevation_deg=base[1]),
        {str(t["channel"]): 0.0 for t in scan.tracks},
    )
    stats = augment_phase_statistics(stats, scan.times, base[0], base[2])
    bounds = np.full(len(scan.norads), 15.0)
    initial = np.zeros(8)
    phases, _ = proposal_phases(stats, initial, scan.sigma, bounds, return_components=True)
    phi = phases[stats["ci"]]
    proposals_stats = dict(
        stats,
        mean=stats["mean"] - stats["hm"] * phi,
        xz=stats["xz"] - stats["xh"] * phi,
        rss=np.maximum(0, stats["rss"] - 2 * stats["zh"] * phi + stats["hh"] * phi**2),
    )
    shape = np.maximum(
        0,
        proposals_stats["rss"]
        - proposals_stats["xz"] ** 2 / np.maximum(stats["xx"][:, None], 1e-12),
    )
    proposals_stats["shape_rms"] = np.sqrt(
        np.add.reduceat(shape, stats["starts"], axis=0) / stats["count"][:, None]
    )
    proposals = list(
        itertools.islice(seed_calibrations(proposals_stats, initial, budget), budget)
    )
    candidates = []
    for number, beta in enumerate(proposals):
        state = zero_state(scan)
        if number:
            phase = proposal_phases(stats, beta, scan.sigma, bounds)
            fitted = improve(
                stats, beta, phase, scan.sigma, bounds, drift_sigma_hz_s=10, drift_bound_hz_s=30
            )
            state.update(beta=fitted[1], phases=fitted[2])
        state = project_radio_state(state)
        _, rows, nominees, _ = scan.association(
            state, base, scan.search_region.native_point(scan, (0, 0)), "shared_phase"
        )
        seed = dict(state=state, rows=nomination_rows(scan, rows, nominees))
        for _ in range(2):
            problem = standard_problem(scan, seed, sigma)
            state = problem.state(np.zeros(2))
            seed, _ = explore(
                scan, reference_state(state), (0, 0), "receiver_smooth", compact_update=False
            )
        problem = standard_problem(scan, seed, sigma)
        seed = dict(rows=problem.rows, state=problem.state(np.zeros(2)))
        candidates.append(
            dict(
                hypothesis=number,
                center_score=score_at(problem, [0, 0]),
                seed=seed,
                aliases=problem.alias,
            )
        )
    return candidates


def signature(node):
    rows = node["seed"]["rows"]
    values = [
        (r["component"], int(r["candidate_index"]), int(r["candidate_norad"]), int(a))
        for r, a in zip(rows, node["aliases"], strict=True)
    ]
    if len({r[0] for r in values}) != len(values):
        raise ValueError("duplicate fragment identity")
    return tuple(sorted(values))
