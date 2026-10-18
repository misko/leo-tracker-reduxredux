"""Sparse derivatives for the original conditional graph objectives.

Each observation depends on one satellite: all phase derivatives can therefore
be evaluated together in two geometry calls. Radio/prior derivatives need no
orbit evaluations. Curve projection and its robust transform are differentiated
exactly. This changes numerical work, not the existing residual objective.
"""

import numpy as np

from leo.analysis.research.retained_track_likelihood import PERIOD


def radio_raw(p, x):
    state = p.decode(x)
    blocks = []
    for i, alias in zip(p.members, p.alias, strict=True):
        t = p.scan.tracks[i]
        raw = t["values"] + alias * PERIOD - p.scan.hardware(t, state["beta"])
        if p.method == "receiver_smooth":
            raw = (
                raw - t["rf_hz"] / 11.5e9 * p.scan.rx_basis[i] @ state["smooth"][t["receiver"] - 1]
            )
        blocks.append(raw)
    return np.concatenate(blocks)


def priors(p, x):
    state = p.decode(x)
    result = [
        np.array([x[p.pairs[0][0]], x[p.pairs[0][1]], x[p.pairs[1][0]], x[p.pairs[1][1]]]),
        state["phases"][p.labels] / p.scan.sigma[p.labels],
    ]
    result += [
        extra / (10 if p.method == "family_rate" else 1e-4) for extra in state["extra"].values()
    ]
    if p.method == "receiver_smooth":
        result.append(state["smooth"].ravel() / 200)
    return np.concatenate(result)


def robust_derivative(z, jacobian, count):
    energy = float(z @ z / count)
    if energy <= 1e-12:
        return jacobian
    scale = np.sqrt(np.log1p(energy) / energy)
    derivative = (
        -0.25
        if energy < 1e-6
        else 0.5 * scale * (1 / ((1 + energy) * np.log1p(energy)) - 1 / energy)
    )
    return scale * jacobian + z[:, None] * (2 * derivative / count * (z @ jacobian))[None, :]


def jacobian(p, x, *, step=1e-3):
    x = np.asarray(x, float)
    width = len(x)
    n = len(p.flat_times)
    q = np.concatenate(
        [
            np.full(sl.stop - sl.start, p.scan.tracks[i]["rf_hz"] / 11.5e9)
            for i, sl in zip(p.members, p.slices, strict=True)
        ]
    )
    frequency, elevation = p.predicted(x)
    raw = radio_raw(p, x) - q * frequency
    cached = getattr(p, "regional_linear_derivatives", None)
    design = np.zeros((n, width)) if cached is None else cached[0].copy()
    elev_design = np.zeros_like(design)
    prior_design = np.zeros((len(priors(p, x)), width)) if cached is None else cached[1]
    groups = {}
    for k, (key, _) in enumerate(p.coordinates):
        plus, minus = x.copy(), x.copy()
        plus[k], minus[k] = min(p.upper[k], x[k] + step), max(p.lower[k], x[k] - step)
        delta = plus[k] - minus[k]
        if cached is None:
            prior_design[:, k] = (priors(p, plus) - priors(p, minus)) / delta
        if key[0] in ("beta", "smooth", "RX_drift_mean_hz_s", "RX_drift_band_contrast_hz_s"):
            if cached is None:
                design[:, k] = (radio_raw(p, plus) - radio_raw(p, minus)) / delta
        else:
            group = (key[0], key[2] if key[0] == "extra" else 0)
            groups.setdefault(group, []).append(k)
    if cached is None:
        p.regional_linear_derivatives = (design.copy(), prior_design.copy())
    for (kind, _), columns in groups.items():
        plus, minus = x.copy(), x.copy()
        plus[columns] = np.minimum(p.upper[columns], x[columns] + step)
        minus[columns] = np.maximum(p.lower[columns], x[columns] - step)
        fp, ep = p.predicted(plus)
        fm, em = p.predicted(minus)
        for k in columns:
            key = p.coordinates[k][0]
            use = (
                np.ones(n, bool)
                if kind in ("east", "north")
                else p.flat_labels == p.local_j[key[1]]
            )
            delta = plus[k] - minus[k]
            design[use, k] = -q[use] * (fp[use] - fm[use]) / delta
            elev_design[use, k] = (ep[use] - em[use]) / delta
    blocks = []
    for i, row, sl in zip(p.members, p.rows, p.slices, strict=True):
        t = p.scan.tracks[i]
        w = (p.scan.ou if p.method == "correlated_noise" else p.scan.white)[i][0]
        cut = row["split_at"] if p.method == "penalized_split" else -1
        cuts = (slice(None),) if cut <= 0 else (slice(0, cut), slice(cut, None))
        zs, js = [], []
        for part in cuts:
            y, du = raw[sl][part], design[sl][part]
            ww = w if cut <= 0 else np.eye(len(y)) / 150
            z, j = ww @ y, ww @ du
            one = ww @ np.ones(len(y))
            denominator = one @ one + 1 / 1000**2
            bias, db = one @ z / denominator, one @ j / denominator
            zs.append(np.r_[z - bias * one, bias / 1000])
            js.append(np.vstack((j - one[:, None] * db[None, :], db[None, :] / 1000)))
        z, j = np.concatenate(zs), np.vstack(js)
        blocks.append(
            robust_derivative(z, j, len(t["times"])) * np.sqrt(min(1, 50 / len(t["times"])))
        )
        blocks.append(-elev_design[sl] / 2 * (elevation[sl] < 0)[:, None])
    return np.vstack([*blocks, prior_design])


def fit(p, initial, *, fixed_xy=None, iterations=32):
    x = np.clip(np.asarray(initial, float), p.lower, p.upper)
    if fixed_xy is not None:
        x[:2] = fixed_xy
    columns = np.arange(len(x)) if fixed_xy is None else np.arange(2, len(x))
    r = p.residual(x)
    score = float(r @ r)
    history = [dict(parameters=x.copy(), score=score)]
    damping = 0.01
    stopped = "iteration_budget"
    for _ in range(iterations):
        j = jacobian(p, x)[:, columns]
        normal, gradient = j.T @ j, j.T @ r
        diagonal = np.maximum(np.diag(normal), 1e-6)
        accepted = False
        for _ in range(9):
            delta = np.linalg.solve(normal + damping * np.diag(diagonal), -gradient)
            trial = x.copy()
            trial[columns] = np.clip(x[columns] + delta, p.lower[columns], p.upper[columns])
            rr = p.residual(trial)
            candidate = float(rr @ rr)
            if candidate < score - 1e-9:
                improvement = score - candidate
                x, r, score = trial, rr, candidate
                history.append(dict(parameters=x.copy(), score=score))
                damping = max(1e-7, damping / 3)
                accepted = True
                if np.linalg.norm(delta) < 1e-4 and improvement < 1e-5:
                    stopped = "small_step_and_improvement"
                break
            damping *= 5
        if not accepted:
            stopped = "no_accepted_damped_step"
            break
        if stopped == "small_step_and_improvement":
            break
    return dict(parameters=x, score=score, history=history, stopped=stopped)
