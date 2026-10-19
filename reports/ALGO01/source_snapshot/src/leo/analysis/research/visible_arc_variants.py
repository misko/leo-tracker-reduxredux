"""Bounded multi-peak arc prototypes; pure numerical ports, no storage access.

Greedy graph repair, joint whole-path selection and exclusive probabilistic EM
share observations, candidate generation, nuisance priors and acceptance gates.
They are conditional association experiments, not full position estimators.
"""

from itertools import combinations, product

import numpy as np

from leo.analysis.graph_tracklets import _best_path, _graph
from leo.analysis.polynomial_tracklets import TrackConfig
from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton, paired_phase_frequency
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen

PERIOD = 1 / 4.4e-6


def wrap(values):
    return (np.asarray(values) + PERIOD / 2) % PERIOD - PERIOD / 2


def deduplicate(cfo, margin, probe, tolerance_hz=300.0):
    """Highest-margin representative of each circular-frequency cluster per probe."""
    cfo, margin, probe = np.asarray(cfo), np.asarray(margin), np.asarray(probe)
    representatives, members = [], []
    for group in np.unique(probe):
        pending = list(np.flatnonzero(probe == group))
        pending.sort(key=lambda i: (-margin[i], cfo[i], i))
        while pending:
            first = pending[0]
            cluster = [i for i in pending if abs(wrap(cfo[i] - cfo[first])) <= tolerance_hz]
            representatives.append(first)
            members.append(cluster)
            pending = [i for i in pending if i not in cluster]
    return np.asarray(representatives, int), members


def basis(times, degree, knots, lo, hi):
    x = (np.asarray(times) - lo) / (hi - lo)
    return np.array(
        [x**j for j in range(degree + 1)]
        + [
            np.maximum(x - (k - lo) / (hi - lo), 0) ** j
            for k in knots
            for j in range(2, degree + 1)
        ]
    ).T


def fit_polynomial(times, values, sigma):
    """Same-support BIC search; at most two C1 knots, at most degree four."""
    t, y = np.asarray(times), np.asarray(values)
    if len(t) < 12 or np.ptp(t) < 8:
        return None
    choices = [(d, ()) for d in range(1, 5) if len(t) >= 4 * (d + 1)]
    grid = np.arange(np.ceil((t.min() + 8) / 5) * 5, t.max() - 8, 5.0)
    for d in (2, 3, 4):
        for n in (1, 2):
            for knots in combinations(grid, n):
                counts = np.histogram(t, np.r_[t.min(), knots, t.max() + 1e-6])[0]
                if min(counts) >= max(8, 4 * (d + 1)):
                    choices.append((d, knots))
    best = None
    for degree, knots in choices:
        design = basis(t, degree, knots, t.min(), t.max())
        coefficients = np.linalg.lstsq(design, y, rcond=None)[0]
        residual = y - design @ coefficients
        score = np.sum((residual / sigma) ** 2) + (design.shape[1] + len(knots)) * np.log(len(t))
        screen = batch_noise_screen(residual[None], t)
        if (
            max(abs(residual)) <= 6 * sigma
            and screen["noise_screen_pass"][0]
            and (best is None or score < best["bic"])
        ):
            best = dict(
                degree=degree,
                knots=knots,
                coefficients=coefficients,
                lo=float(t.min()),
                hi=float(t.max()),
                bic=float(score),
                residual_hz=residual,
                rms_hz=float(np.sqrt(np.mean(residual**2))),
                diagnostics={k: v[0] for k, v in screen.items()},
            )
    return best


def curvature_rms(times, polynomial):
    """Actual fitted bending after projection off affine terms, in physical Hz."""
    t = np.asarray(times)
    signal = (
        basis(t, polynomial["degree"], polynomial["knots"], polynomial["lo"], polynomial["hi"])
        @ polynomial["coefficients"]
    )
    affine = np.column_stack([np.ones(len(t)), t - t.mean()])
    bending = signal - affine @ np.linalg.lstsq(affine, signal, rcond=None)[0]
    return float(np.sqrt(np.mean(bending**2)))


def graph_proposals(times, values, count=16):
    """Retain alternative edge chains; do not greedily reserve their observations."""
    t, y = np.asarray(times), np.asarray(values)
    cfg = TrackConfig(max_slope_hz_s=8000)
    graph = _graph(t, y, cfg)
    enabled, available = np.ones(len(graph[0]), bool), np.ones(len(t), bool)
    paths, seen = [], set()
    for _ in range(count):
        path, lifted, edges, score = _best_path(t, y, graph, available, enabled, cfg)
        if not len(path):
            break
        enabled[edges] = False
        signature = tuple(path)
        if signature not in seen:
            seen.add(signature)
            paths.append(dict(indices=path, lifted=lifted, graph_score=float(score)))
    return paths


def nominate(nominal, derivative, elevation, indices, values, sigma, count=3):
    """Screen every supplied causal satellite with regularized phase/scale tangents."""
    f, d = nominal[:, indices], derivative[:, indices]
    y = np.asarray(values)
    alias = np.rint((f.mean(axis=1) - y.mean()) / PERIOD)
    raw = y[None] + alias[:, None] * PERIOD - f
    design = np.stack((3 * d, np.ones_like(d) * 1000, 0.005 * f), axis=2) / sigma
    normal = np.einsum("sni,snj->sij", design, design) + np.eye(3)[None]
    rhs = np.einsum("sni,sn->si", design, raw / sigma)
    coefficient = np.linalg.solve(normal, rhs[..., None])[..., 0]
    residual = raw / sigma - np.einsum("sni,si->sn", design, coefficient)
    score = np.sum(residual**2, axis=1) + np.sum(coefficient**2, axis=1)
    score[np.min(elevation[:, indices], axis=1) < 0] = np.inf
    ordered = np.argsort(score)[:count]
    return [(int(j), float(score[j]), coefficient[j]) for j in ordered if np.isfinite(score[j])]


def frequency(bank, j, times, parameters, site, rf_hz):
    phase, bias, scale = parameters
    single = dict(
        time_s=bank["time_s"],
        position_km=bank["position_km"][[j]],
        velocity_km_s=bank["velocity_km_s"][[j]],
    )
    f, _ = paired_phase_frequency(
        single, np.asarray(times), np.zeros(len(times), int), np.array([phase]), *site
    )
    return f * (rf_hz / 11.5e9) * (1 + scale) + bias


def fit_satellite(
    bank, j, times, values, site, rf_hz, sigma, initial=None, weights=None, iterations=24
):
    """One shared phase, constant and Doppler scale; no fragment-specific drift."""
    t, y = np.asarray(times), np.asarray(values)
    w = np.ones(len(t)) if weights is None else np.asarray(weights)
    scales = np.array([3.0, 1000.0, 0.005])
    initial = np.zeros(3) if initial is None else np.asarray(initial) / scales

    def residual(z):
        r = wrap(y - frequency(bank, j, t, z * scales, site, rf_hz)) / sigma
        return np.r_[r * np.sqrt(w), z]

    fitted = bounded_gauss_newton(
        residual, initial, [-5.0, -3.0, -1.0], [5.0, 3.0, 1.0], iterations=iterations, step=0.001
    )
    parameters = np.asarray(fitted["parameters"]) * scales
    r = wrap(y - frequency(bank, j, t, parameters, site, rf_hz))
    diagnostics = batch_noise_screen(r[None], t) if len(t) >= 4 else None
    return dict(
        candidate_index=int(j),
        parameters=parameters,
        score=float(residual(fitted["parameters"]) @ residual(fitted["parameters"])),
        residual_hz=r,
        rms_hz=float(np.sqrt(np.sum(w * r * r) / max(w.sum(), 1e-12))),
        diagnostics=None if diagnostics is None else {k: v[0] for k, v in diagnostics.items()},
    )


def choose_points(times, values, probes, quality, prediction, sigma, allowed=None):
    """At most one canonical peak per probe per physical track."""
    residual = wrap(values - prediction)
    permitted = np.ones(len(times), bool) if allowed is None else np.asarray(allowed, bool)
    keep = permitted & (abs(residual) < 3 * sigma)
    indices = []
    for p in np.unique(probes[keep]):
        ix = np.flatnonzero(keep & (probes == p))
        cost = (residual[ix] / sigma) ** 2 - 2 * np.log(np.maximum(quality[ix], 0.05))
        indices.append(int(ix[np.argmin(cost)]))
    return np.asarray(indices, int)


def accept_hypothesis(bank, j, seed, data, initial=None):
    """Orbit-gated growth within connected <=10s support; validate whole C1 fit."""
    t, y, p, q = (data[k] for k in ("times", "values", "probes", "quality"))
    sigma = data["sigma"]
    indices = np.asarray(seed, int)
    fitted = None
    for _ in range(3):
        if len(indices) < 12 or np.ptp(t[indices]) < 8:
            return None
        fitted = fit_satellite(
            bank, j, t[indices], y[indices], data["site"], data["rf_hz"], sigma, initial=initial
        )
        initial = fitted["parameters"]
        prediction = frequency(bank, j, t, initial, data["site"], data["rf_hz"])
        new = choose_points(t, y, p, q, prediction, sigma)
        chunks = np.split(new, np.flatnonzero(np.diff(t[new]) > 10) + 1)
        if not len(new):
            return None
        new = max(chunks, key=lambda a: len(np.intersect1d(a, indices)))
        if np.array_equal(new, indices):
            break
        indices = new
    if len(indices) < 12 or np.ptp(t[indices]) < 8:
        return None
    fitted = fit_satellite(
        bank, j, t[indices], y[indices], data["site"], data["rf_hz"], sigma, initial=initial
    )
    if (
        fitted["rms_hz"] > 3 * sigma
        or not fitted["diagnostics"]["noise_screen_pass"]
        or max(abs(fitted["residual_hz"])) > 6 * sigma
    ):
        return None
    predicted = frequency(bank, j, t[indices], fitted["parameters"], data["site"], data["rf_hz"])
    lifted = predicted + wrap(y[indices] - predicted)
    polynomial = fit_polynomial(t[indices], lifted, sigma)
    if polynomial is None:
        return None
    bending = curvature_rms(t[indices], polynomial)
    # New satellite phase/shape adjustments cannot be calibrated on a nearly
    # straight arc. Such points can be extended later from an independent family.
    if bending < 2 * sigma:
        return None
    evidence = 9 * len(indices) - fitted["score"] - 18 - 3 * np.log(len(indices))
    evidence += 2 * np.log(np.maximum(q[indices], 0.05)).sum()
    evidence -= (len(polynomial["coefficients"]) + len(polynomial["knots"])) * np.log(len(indices))
    if evidence <= 0:
        return None
    return dict(
        indices=indices,
        orbit=fitted,
        polynomial=polynomial,
        evidence=float(evidence),
        candidate_index=int(j),
        start_s=float(t[indices].min()),
        end_s=float(t[indices].max()),
        curvature_rms_hz=bending,
    )


def make_hypotheses(bank, data, nominal, derivative, elevation, paths, maximum=24):
    """Whole graph paths and systematic temporal subpaths, no hand-picked times/IDs."""
    hypotheses, attempts, seen = [], [], set()
    for number, path in enumerate(paths):
        ix = path["indices"]
        # Whole path first; subpaths offer alternatives when a path changes emitter.
        supports = [ix]
        if len(ix) >= 24:
            for fraction in (0.35, 0.5, 0.65):
                cut = int(len(ix) * fraction)
                supports.extend([ix[:cut], ix[cut:]])
        for support in supports:
            if len(support) < 12 or np.ptp(data["times"][support]) < 8:
                continue
            lifted = path["lifted"][np.searchsorted(ix, support)]
            radio_polynomial = fit_polynomial(data["times"][support], lifted, data["sigma"])
            nominated = nominate(nominal, derivative, elevation, support, lifted, data["sigma"])
            for j, score, z in nominated:
                signature = (j, tuple(support))
                if signature in seen:
                    continue
                seen.add(signature)
                # Tangents are only initialization; all accepted fits use exact bank geometry.
                initial = np.clip(
                    z * np.array([3.0, 1000.0, 0.005]),
                    [-15.0, -3000.0, -0.005],
                    [15.0, 3000.0, 0.005],
                )
                candidate = accept_hypothesis(bank, j, support, data, initial)
                attempts.append(
                    dict(
                        path=number,
                        candidate_index=j,
                        nomination_score=score,
                        seed_points=len(support),
                        accepted=candidate is not None,
                    )
                )
                if candidate is None:
                    continue
                similar = [
                    h
                    for h in hypotheses
                    if h["candidate_index"] == j
                    and len(np.intersect1d(h["indices"], candidate["indices"]))
                    / min(len(h["indices"]), len(candidate["indices"]))
                    > 0.85
                ]
                if similar:
                    if candidate["evidence"] > similar[0]["evidence"]:
                        hypotheses = [h for h in hypotheses if h is not similar[0]]
                    else:
                        continue
                candidate["seed_radio_polynomial_pass"] = radio_polynomial is not None
                hypotheses.append(candidate)
    hypotheses.sort(key=lambda h: -h["evidence"])
    return hypotheses[:maximum], attempts


def configurations(peak_count, family_count):
    """Exclusive matchings, including missed detections and unassigned peaks."""
    configs = []
    for assignment in product(range(-1, peak_count), repeat=family_count):
        used = [i for i in assignment if i >= 0]
        if len(set(used)) == len(used):
            configs.append(assignment)
    return np.asarray(configs, int)


def exclusive_assignment(log_odds, probes, soft=False):
    """Exact per-probe matching posterior; each family can select zero or one peak."""
    odds = np.asarray(log_odds)
    responsibilities = np.zeros_like(odds)
    owner = np.full(odds.shape[1], -1, int)
    value = 0.0
    cache = {}
    for p in np.unique(probes):
        ix = np.flatnonzero(probes == p)
        key = (len(ix), odds.shape[0])
        if key not in cache:
            cache[key] = configurations(*key)
        assignments = cache[key]
        score = np.zeros(len(assignments))
        for family in range(odds.shape[0]):
            use = assignments[:, family] >= 0
            score[use] += odds[family, ix[assignments[use, family]]]
        best = int(np.argmax(score))
        if soft:
            posterior = np.exp(score - score[best])
            posterior /= posterior.sum()
            value += float(score[best] + np.log(np.exp(score - score[best]).sum()))
            for family in range(odds.shape[0]):
                use = assignments[:, family] >= 0
                np.add.at(responsibilities[family], ix[assignments[use, family]], posterior[use])
        else:
            value += float(score[best])
        for family, local in enumerate(assignments[best]):
            if local >= 0:
                owner[ix[local]] = family
                if not soft:
                    responsibilities[family, ix[local]] = 1
    return owner, responsibilities, value


def model_odds(bank, data, models):
    predictions = np.array(
        [
            frequency(
                bank,
                h["candidate_index"],
                data["times"],
                h["orbit"]["parameters"],
                data["site"],
                data["rf_hz"],
            )
            for h in models
        ]
    )
    residual = wrap(data["values"][None] - predictions)
    return (
        4.5
        - 0.5 * (residual / data["sigma"]) ** 2
        + np.log(np.maximum(data["quality"], 0.05))[None]
    )


def finalize(bank, data, models, posterior_threshold=0.0):
    if not models:
        return dict(
            tracks=[], ambiguous_indices=[], assignment=np.full(len(data["times"]), -1, int)
        )
    owner, responsibilities, _ = exclusive_assignment(
        model_odds(bank, data, models), data["probes"], soft=posterior_threshold > 0
    )
    ambiguous = []
    tracks = []
    assignment = np.full(len(data["times"]), -1, int)
    for k, model in enumerate(models):
        ix = np.flatnonzero(owner == k)
        if posterior_threshold > 0:
            uncertain = responsibilities[k, ix] < posterior_threshold
            ambiguous.extend(ix[uncertain].tolist())
            ix = ix[~uncertain]
        if len(ix) < 12 or np.ptp(data["times"][ix]) < 8:
            continue
        fitted = fit_satellite(
            bank,
            model["candidate_index"],
            data["times"][ix],
            data["values"][ix],
            data["site"],
            data["rf_hz"],
            data["sigma"],
            initial=model["orbit"]["parameters"],
        )
        predicted = frequency(
            bank,
            model["candidate_index"],
            data["times"][ix],
            fitted["parameters"],
            data["site"],
            data["rf_hz"],
        )
        poly = fit_polynomial(data["times"][ix], predicted + fitted["residual_hz"], data["sigma"])
        if (
            poly is None
            or fitted["rms_hz"] > 3 * data["sigma"]
            or not fitted["diagnostics"]["noise_screen_pass"]
            or max(abs(fitted["residual_hz"])) > 6 * data["sigma"]
            or np.max(np.diff(data["times"][ix])) > 10
        ):
            continue
        if curvature_rms(data["times"][ix], poly) < 2 * data["sigma"]:
            continue
        assignment[ix] = len(tracks)
        tracks.append(dict(model, indices=ix, orbit=fitted, polynomial=poly))
    return dict(tracks=tracks, ambiguous_indices=sorted(set(ambiguous)), assignment=assignment)


def greedy_repair(bank, data, hypotheses):
    selected, used = [], set()
    # Greedy evidence ranking is irreversible, unlike the joint subset search.
    for h in hypotheses:
        if h["candidate_index"] in {a["candidate_index"] for a in selected}:
            continue
        fresh = set(map(int, h["indices"])) - used
        if len(fresh) < 12:
            continue
        selected.append(h)
        used.update(map(int, h["indices"]))
        if len(selected) >= 4:
            break
    return finalize(bank, data, selected)


def duplicate_explanations(left, right, overlap_fraction=0.6):
    """Models covering the same canonical peaks are alternative identities.

    This guards against inventing an additional emitter by splitting the small
    residual of a single curve between two nearby orbital hypotheses. Resolved
    simultaneous curves mostly use different canonical peaks and remain allowed.
    """
    overlap = len(np.intersect1d(left["indices"], right["indices"]))
    return overlap > overlap_fraction * min(len(left["indices"]), len(right["indices"]))


def complexity_cost(model):
    """One track, three satellite parameters, and polynomial coefficients/knots."""
    polynomial = model.get("polynomial", {})
    polynomial_free = len(polynomial.get("coefficients", [])) + len(polynomial.get("knots", []))
    return 18 + (3 + polynomial_free) * np.log(len(model["indices"]))


def joint_selection(bank, data, hypotheses, duplicate_overlap=0.6):
    """Bounded exhaustive family subsets; exact peak allocation within each subset."""
    pool = []
    for h in hypotheses:
        if h["candidate_index"] not in {p["candidate_index"] for p in pool}:
            pool.append(h)
        if len(pool) >= 10:
            break
    choices = []
    for count in range(1, min(4, len(pool)) + 1):
        for subset in combinations(range(len(pool)), count):
            models = [pool[i] for i in subset]
            if duplicate_overlap is not None and any(
                duplicate_explanations(a, b, duplicate_overlap) for a, b in combinations(models, 2)
            ):
                continue
            _, _, score = exclusive_assignment(model_odds(bank, data, models), data["probes"])
            penalty = sum(
                complexity_cost(h)
                + np.sum((h["orbit"]["parameters"] / np.array([3.0, 1000.0, 0.005])) ** 2)
                for h in models
            )
            choices.append((2 * score - penalty, subset))
    choices.sort(reverse=True)
    selected = [] if not choices or choices[0][0] <= 0 else [pool[i] for i in choices[0][1]]
    result = finalize(bank, data, selected)
    result["subset_count"] = len(choices)
    result["ranked_subsets"] = [
        dict(score=float(s), candidate_indices=[pool[i]["candidate_index"] for i in ix])
        for s, ix in choices[:8]
    ]
    return result, pool, choices


def em_association(bank, data, pool, choices, rounds=12):
    """Exact exclusive E-step; penalized shared phase/bias/scale M-step, three starts."""
    runs = []
    for _, subset in choices[:3]:
        models = [dict(pool[i], orbit=dict(pool[i]["orbit"])) for i in subset]
        history = []
        for _iteration in range(rounds):
            odds = model_odds(bank, data, models)
            _, weights, log_z = exclusive_assignment(odds, data["probes"], soft=True)
            prior = sum(
                np.sum((h["orbit"]["parameters"] / np.array([3.0, 1000.0, 0.005])) ** 2)
                for h in models
            )
            objective = -2 * log_z + prior + sum(complexity_cost(h) for h in models)
            history.append(float(objective))
            for k, h in enumerate(models):
                if weights[k].sum() < 8:
                    continue
                h["orbit"] = fit_satellite(
                    bank,
                    h["candidate_index"],
                    data["times"],
                    data["values"],
                    data["site"],
                    data["rf_hz"],
                    data["sigma"],
                    initial=h["orbit"]["parameters"],
                    weights=weights[k],
                    iterations=12,
                )
        _, _, log_z = exclusive_assignment(
            model_odds(bank, data, models), data["probes"], soft=True
        )
        prior = sum(
            np.sum((h["orbit"]["parameters"] / np.array([3.0, 1000.0, 0.005])) ** 2) for h in models
        )
        score = -2 * log_z + prior + sum(complexity_cost(h) for h in models)
        result = finalize(bank, data, models, posterior_threshold=0.8)
        result["map_assignment_result"] = finalize(bank, data, models)
        runs.append(dict(score=float(score), history=history, result=result))
    if not runs:
        return finalize(bank, data, [])
    best = min(runs, key=lambda r: r["score"])
    return dict(
        best["result"],
        em_score=best["score"],
        em_runs=[dict(score=r["score"], history=r["history"]) for r in runs],
    )
