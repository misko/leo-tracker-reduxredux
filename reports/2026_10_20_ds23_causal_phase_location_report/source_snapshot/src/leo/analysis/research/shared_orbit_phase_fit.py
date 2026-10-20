"""Shared receiver hardware and per-satellite phase from sufficient statistics.

Gaussian component constants are eliminated by a Schur complement. Only
individually measured-curved fragments enter calibration. Each selected NORAD
has one phase parameter across all its components; no component slope exists.
Scores are branch-profiled robust research criteria, not identity probabilities.
"""

import numpy as np

from leo.analysis.research.component_frequency_bias import profile_component_bias

PERIOD = 1 / 4.4e-6
NOISE_HZ = 150.0
BIAS_SIGMA_HZ = 1000.0


def augment_phase_statistics(stats, times, frequency, derivative):
    means, xx, cross_time, cross_data = [], [], [], []
    for track, q in zip(stats["fragments"], stats["q"], strict=True):
        indexes = np.searchsorted(times, track["times"])
        if not np.array_equal(times[indexes], track["times"]):
            raise ValueError("phase grid lacks original measurement times")
        h = q * derivative[:, indexes]
        hm = h.mean(axis=1)
        hc = h - hm[:, None]
        z = track["values"][None, :] - q * frequency[:, indexes]
        z -= z.mean(axis=1)[:, None]
        x = (track["times"] - track["times"].mean()) / 150
        means.append(hm)
        xx.append(np.sum(hc * hc, axis=1))
        cross_time.append(hc @ x)
        cross_data.append(np.sum(hc * z, axis=1))
    return dict(
        stats,
        hm=np.asarray(means),
        hh=np.asarray(xx),
        xh=np.asarray(cross_time),
        zh=np.asarray(cross_data),
    )


def apply_phases(stats, phases):
    phases = np.asarray(phases, float)[None, :]
    return dict(
        stats,
        mean=stats["mean"] - stats["hm"] * phases,
        xz=stats["xz"] - stats["xh"] * phases,
        rss=np.maximum(0, stats["rss"] - 2 * stats["zh"] * phases + stats["hh"] * phases**2),
    )


def recenter_phases(stats, anchor):
    """Express a tangent at anchor in absolute phase coordinates for the prior."""
    anchor = np.asarray(anchor, float)[None, :]
    return dict(
        stats,
        mean=stats["mean"] + stats["hm"] * anchor,
        xz=stats["xz"] + stats["xh"] * anchor,
        rss=stats["rss"] + 2 * stats["zh"] * anchor + stats["hh"] * anchor**2,
        zh=stats["zh"] + stats["hh"] * anchor,
    )


def profile_phases(stats, beta, phases):
    return profile_component_bias(apply_phases(stats, phases), beta, bias_sigma_hz=BIAS_SIGMA_HZ)


def box_quadratic(normal, rhs, lower, upper):
    """Convex box-constrained quadratic solve with bound release and scaling."""
    diagonal = np.sqrt(np.maximum(np.diag(normal), 1e-20))
    matrix = normal / diagonal[:, None] / diagonal[None, :]
    target = rhs / diagonal
    lo, hi = lower * diagonal, upper * diagonal
    x = np.clip(np.zeros(len(rhs)), lo, hi)
    scale = max(1.0, np.linalg.norm(target, np.inf))
    converged = False
    for _ in range(10 * len(rhs) + 20):
        gradient = matrix @ x - target
        fixed = lo == hi
        active = (
            fixed | ((x <= lo + 1e-10) & (gradient >= 0)) | ((x >= hi - 1e-10) & (gradient <= 0))
        )
        free = np.flatnonzero(~active)
        if not len(free) or np.linalg.norm(gradient[free], np.inf) <= 1e-10 * scale:
            converged = True
            break
        step = np.zeros_like(x)
        step[free] = np.linalg.lstsq(matrix[np.ix_(free, free)], -gradient[free], rcond=1e-11)[0]
        if np.max(np.abs(step)) < 1e-12:
            break
        alpha = 1.0
        positive, negative = step > 0, step < 0
        if np.any(positive):
            alpha = min(alpha, float(np.min((hi[positive] - x[positive]) / step[positive])))
        if np.any(negative):
            alpha = min(alpha, float(np.min((lo[negative] - x[negative]) / step[negative])))
        x = np.clip(x + max(0.0, alpha) * step, lo, hi)
    return x / diagonal, converged


def joint_update(
    stats,
    best,
    aliases,
    beta,
    phases,
    sigma_s,
    bounds_s,
    selected,
    *,
    drift_sigma_hz_s=2.0,
    drift_bound_hz_s=5.0,
):
    keep = stats["fragment_active"] & selected[stats["ci"]]
    satellites = sorted(set(best[stats["ci"][keep]].tolist()))
    satellites = [j for j in satellites if sigma_s[j] > 0]
    phase_index = {j: len(beta) + i for i, j in enumerate(satellites)}
    size = len(beta) + len(satellites)
    normal, rhs = np.zeros((size, size)), np.zeros(size)
    nuisance = {}
    weight = np.minimum(1.0, 50 / stats["count"])
    supported = np.zeros(4, bool)
    for fi in np.flatnonzero(keep):
        ci = stats["ci"][fi]
        satellite = best[ci]
        g = stats["g"][fi]
        supported[g] = True
        n, mx, w = stats["n"][fi], stats["mx"][fi], weight[ci]
        z = stats["mean"][fi, satellite] + aliases[fi, satellite] * PERIOD
        indexes, mean = [g, g + 4], [1.0, mx]
        if len(beta) == 9:
            indexes.append(8)
            mean.append(stats["q"][fi] * 11.5 - 11.5)
        if satellite in phase_index:
            indexes.append(phase_index[satellite])
            mean.append(stats["hm"][fi, satellite])
        indexes, mean = np.asarray(indexes), np.asarray(mean)
        normal[np.ix_(indexes, indexes)] += w * n * np.outer(mean, mean)
        rhs[indexes] += w * n * mean * z
        normal[g + 4, g + 4] += w * stats["xx"][fi]
        rhs[g + 4] += w * stats["xz"][fi, satellite]
        if satellite in phase_index:
            pi = phase_index[satellite]
            normal[pi, pi] += w * stats["hh"][fi, satellite]
            normal[g + 4, pi] += w * stats["xh"][fi, satellite]
            normal[pi, g + 4] += w * stats["xh"][fi, satellite]
            rhs[pi] += w * stats["zh"][fi, satellite]
        if ci not in nuisance:
            nuisance[ci] = [np.zeros(size), 0.0, 0.0]
        nuisance[ci][0][indexes] += w * n * mean
        nuisance[ci][1] += w * n
        nuisance[ci][2] += w * n * z
    # Eliminate each whole-component constant exactly, including its prior.
    for ci, (cross, count, total) in nuisance.items():
        precision = count + weight[ci] * NOISE_HZ**2 / BIAS_SIGMA_HZ**2
        normal -= np.outer(cross, cross) / precision
        rhs -= cross * total / precision
    data_normal = normal.copy()
    lower, upper = np.full(size, -np.inf), np.full(size, np.inf)
    for g in range(4):
        normal[g + 4, g + 4] += NOISE_HZ**2 / (150 * drift_sigma_hz_s) ** 2
        lower[g + 4], upper[g + 4] = -150 * drift_bound_hz_s, 150 * drift_bound_hz_s
        if not supported[g]:
            # No arbitrary seed drift in absent groups. An observed but currently
            # rejected group retains its discovery intercept, never a drift vote.
            initial_offset = beta[g] if np.any(stats["g"] == g) else 0.0
            lower[g] = upper[g] = initial_offset
            lower[g + 4] = upper[g + 4] = 0.0
    if len(beta) == 9:
        lower[8], upper[8] = -200000, 200000
        if normal[8, 8] == 0:
            lower[8] = upper[8] = 0
    for satellite, index in phase_index.items():
        normal[index, index] += NOISE_HZ**2 / sigma_s[satellite] ** 2
        lower[index], upper[index] = -bounds_s[satellite], bounds_s[satellite]
    solution, converged = box_quadratic(normal, rhs, lower, upper)
    new_beta = solution[: len(beta)]
    new_beta[:4] = (new_beta[:4] + PERIOD / 2) % PERIOD - PERIOD / 2
    new_phase = np.zeros_like(phases)
    for satellite, index in phase_index.items():
        new_phase[satellite] = solution[index]
    info = dict(
        supported_groups=supported.tolist(),
        phase_parameters=len(satellites),
        box_solver_converged=converged,
        data_normal=data_normal,
        normal_with_priors=normal,
        satellite_indexes=satellites,
    )
    return new_beta, new_phase, info


def phase_information(stats, best, *, included=None):
    n = stats["n"][:, None]
    count = stats["count"][:, None]
    sh = np.add.reduceat(n * stats["hm"], stats["starts"], axis=0)
    shh = np.add.reduceat(stats["hh"] + n * stats["hm"] ** 2, stats["starts"], axis=0)
    information = np.maximum(0.0, shh - sh**2 / (count + NOISE_HZ**2 / BIAS_SIGMA_HZ**2))
    w = np.minimum(1.0, 50 / stats["count"])
    if included is not None:
        included = np.asarray(included, bool)
        if included.shape != w.shape:
            raise ValueError("one inclusion flag per calibration component required")
        w = w * included
    return np.bincount(
        best, weights=w * information[np.arange(len(best)), best], minlength=stats["mean"].shape[1]
    )


def penalized_score(stats, beta, phases, sigma_s, *, drift_sigma_hz_s=2.0):
    terms = profile_phases(stats, beta, phases)
    values = terms.score[np.arange(len(terms.best)), terms.best]
    frequency = float(np.sum(np.minimum(stats["count"], 50) * np.minimum(values, 900.0**2)))
    drift = NOISE_HZ**2 * float(np.sum((beta[4:8] / (150 * drift_sigma_hz_s)) ** 2))
    enabled = sigma_s > 0
    prior = NOISE_HZ**2 * float(np.sum((phases[enabled] / sigma_s[enabled]) ** 2))
    # Conditional hardware/labels, one nuisance-volume penalty per satellite.
    information = phase_information(stats, terms.best)
    complexity = NOISE_HZ**2 * float(np.sum(np.log1p(information * sigma_s**2 / NOISE_HZ**2)))
    return (
        frequency + drift + prior + complexity,
        terms,
        dict(
            frequency_score=frequency,
            drift_penalty=drift,
            phase_prior_penalty=prior,
            conditional_phase_complexity=complexity,
        ),
    )


def proposal_phases(stats, beta, sigma_s, bounds_s, *, return_components=False):
    """Component-specific phases are proposals only, never final calibration."""
    b = beta[stats["g"], None] + beta[stats["g"] + 4, None] * stats["mx"][:, None]
    if len(beta) == 9:
        b += beta[8] * (stats["q"][:, None] * 11.5 - 11.5)
    aliases = np.rint((b - stats["mean"]) / PERIOD)
    z = stats["mean"] + aliases * PERIOD - b
    n, count = stats["n"][:, None], stats["count"][:, None]
    sb = np.add.reduceat(n * z, stats["starts"], axis=0)
    sh = np.add.reduceat(n * stats["hm"], stats["starts"], axis=0)
    shh = np.add.reduceat(stats["hh"] + n * stats["hm"] ** 2, stats["starts"], axis=0)
    d = beta[stats["g"] + 4, None]
    cross = np.add.reduceat(
        stats["zh"] - d * stats["xh"] + n * z * stats["hm"], stats["starts"], axis=0
    )
    bdenom = count + NOISE_HZ**2 / BIAS_SIGMA_HZ**2
    precision = np.where(sigma_s > 0, NOISE_HZ**2 / np.maximum(sigma_s, 1e-12) ** 2, np.inf)
    info = np.maximum(0, shh - sh**2 / bdenom)
    phase = np.clip((cross - sh * sb / bdenom) / (info + precision), -bounds_s, bounds_s)
    bias = (sb - sh * phase) / bdenom
    centered = np.maximum(
        0,
        stats["rss"]
        - 2 * d * stats["xz"]
        + d * d * stats["xx"][:, None]
        - 2 * phase[stats["ci"]] * (stats["zh"] - d * stats["xh"])
        + phase[stats["ci"]] ** 2 * stats["hh"],
    )
    residual_mean = z - stats["hm"] * phase[stats["ci"]] - bias[stats["ci"]]
    rss = np.add.reduceat(centered + n * residual_mean**2, stats["starts"], axis=0)
    score = (
        rss
        + NOISE_HZ**2 / BIAS_SIGMA_HZ**2 * bias**2
        + np.where(sigma_s > 0, NOISE_HZ**2 * phase**2 / np.maximum(sigma_s, 1e-12) ** 2, 0)
        + NOISE_HZ**2 * np.log1p(info * sigma_s**2 / NOISE_HZ**2)
    ) / count
    score[~stats["component_visible"]] = 1e30
    if return_components:
        return phase, score
    best = np.argmin(score, axis=1)
    result = np.zeros(stats["mean"].shape[1])
    for satellite in np.unique(best):
        selected = (
            (best == satellite)
            & stats["active"]
            & (rss[np.arange(len(best)), best] / stats["count"] < 4000**2)
        )
        if np.any(selected):
            result[satellite] = np.median(phase[selected, satellite])
    return result
