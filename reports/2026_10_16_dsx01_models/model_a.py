"""DSX-A: training-only coherent arcs propose physical satellite timing rescue.

Arc lines are proposal machinery only. The accepted objective, orbital RF model,
point clutter and shared detection budget remain the original shared-scan model.
"""
from dataclasses import replace
import time

import numpy as np
from scipy.optimize import minimize

from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import circular


def _subset(obs, rows):
    return replace(obs, window_ids=tuple(obs.window_ids[i] for i in rows),
        **{k: getattr(obs, k)[rows] for k in
           ("times_s", "measured_hz", "rf_hz", "receiver", "channel", "margin")})


def extract_tracks(obs, mask, correction, *, maximum_tracks=48, deadline=float("inf")):
    """Deterministic short-arc RANSAC, without consuming excluded measurements.

    Overlapping arcs and crossing membership are allowed; no observation is
    removed from the downstream point likelihood. Frequency is circular even
    during line fitting, so an alias-boundary crossing does not split a track.
    """
    mask = np.asarray(mask, bool)
    rows = np.flatnonzero(mask)
    t = obs.times_s[rows]
    y = circular(obs.measured_hz[rows] - np.asarray(correction)[rows])
    receiver, channel = obs.receiver[rows], obs.channel[rows]
    rng = np.random.default_rng(8041)
    found = []
    for rx, ch in sorted(set(zip(receiver.tolist(), channel.tolist()))):
        if time.monotonic() >= deadline:
            break
        group = np.flatnonzero((receiver == rx) & (channel == ch))
        group = group[np.argsort(t[group], kind="stable")]
        if len(group) < 8:
            continue
        # A fixed 24 s physical coherence horizon; no source/window identifiers.
        for left in np.arange(t[group[0]], t[group[-1]] + .001, 12.):
            if time.monotonic() >= deadline:
                break
            local = group[(t[group] >= left) & (t[group] <= left + 24.)]
            if len(local) < 8 or np.ptp(t[local]) < 6:
                continue
            pairs = []
            for a in range(len(local) - 1):
                for b in range(a + 1, min(len(local), a + 9)):
                    dt = t[local[b]] - t[local[a]]
                    if .4 <= dt <= 9:
                        pairs.append((local[a], local[b]))
            if len(pairs) > 96:
                pairs = [pairs[i] for i in sorted(rng.choice(len(pairs), 96, replace=False))]
            for a, b in pairs:
                slope = float(circular(y[b] - y[a]) / (t[b] - t[a]))
                if abs(slope) > 4000:
                    continue
                prediction = y[a] + slope * (t[local] - t[a])
                keep = abs(circular(y[local] - prediction)) < 275.
                for _ in range(2):
                    if keep.sum() < 8:
                        break
                    xx = t[local] - t[a]
                    yy = prediction + circular(y[local] - prediction)
                    coefficients = np.polyfit(xx[keep], yy[keep], 1)
                    prediction = np.polyval(coefficients, xx)
                    keep = abs(circular(y[local] - prediction)) < 275.
                selected = local[keep]
                if len(selected) < 8 or np.ptp(t[selected]) < 6:
                    continue
                track = rows[selected]
                found.append((len(track), float(np.ptp(t[selected])), track))
    found.sort(key=lambda item: (-item[0], -item[1], tuple(item[2])))
    tracks = []
    for _, _, track in found:
        members = set(track.tolist())
        if any(len(members.intersection(other)) / min(len(members), len(other)) > .65
               for other in tracks):
            continue
        tracks.append(track)
        if len(tracks) >= maximum_tracks:
            break
    return tracks


def _correction(model, vector, nuisance):
    base = model.original
    clock, group = base.split(nuisance[:model.base_nuisance_count])
    return (base.design @ vector[2:7] + base.baseline
            + base.group_design @ group + base.clock_design @ clock)


def _timing_vector(model, vector, shifts):
    out = vector.copy()
    out[7] = np.mean(shifts)
    out[8:] = model.basis.T @ (shifts - out[7])
    return out


def propose_timings(context, vector, nuisance, *, deadline=float("inf")):
    """Rank an eligible satellite's timing on whole arcs at actual observed RF."""
    model, obs = context.model, context.observations
    correction = _correction(model, vector, nuisance)
    tracks = extract_tracks(obs, context.train_mask, correction, deadline=deadline)
    shifts = vector[7] + model.basis @ vector[8:]
    if not tracks:
        return [], dict(track_count=0, profile_evaluations=0)
    sampled = [track[np.linspace(0, len(track)-1, min(16, len(track))).astype(int)]
               for track in tracks]
    rows = np.unique(np.concatenate(sampled))
    selected = _subset(obs, rows)
    positions = [np.searchsorted(rows, track) for track in sampled]
    measured = obs.measured_hz[rows] - correction[rows]
    # Respect the same interpolation support and the existing +/-20 s bounds.
    low = max(-8., float(context.bank.nodes_s[0] - obs.times_s.min()) + 1e-6)
    high = min(8., float(context.bank.nodes_s[-1] - obs.times_s.max()) - 1e-6)
    grid = np.arange(np.ceil(low * 4) / 4, high + .001, .25)
    count = len(context.bank.numbers)

    def arc_loss(tau):
        prediction, visible, _, _ = predict_orbits(context.bank, selected, context.prior,
            vector[:2], tau, derivatives=False)
        residual = abs(circular(measured[:, None] - prediction))
        result = []
        coherent = []
        for track, ix in zip(tracks, positions):
            rr = residual[ix]
            result.append(np.mean(np.minimum((rr / 125.)**2, 25.), axis=0) * len(track))
            coherent.append(np.mean((rr < 375.) & visible[ix], axis=0) >= .7)
        return np.asarray(result), np.asarray(coherent)

    baseline, _ = arc_loss(shifts)
    best_gain = np.zeros(count)
    best_shift = shifts.copy()
    supporting_arcs = np.zeros(count, int)
    evaluated = 1
    for value in grid:
        if time.monotonic() >= deadline:
            break
        loss, coherent = arc_loss(np.full(count, value))
        # All supporting arcs vote at one physical time; no per-arc offset.
        gain = np.maximum(baseline - loss, 0.) * coherent
        totals = gain.sum(axis=0)
        take = totals > best_gain
        best_gain[take] = totals[take]
        best_shift[take] = value
        supporting_arcs[take] = np.sum(coherent[:, take] & (gain[:, take] > 0), axis=0)
        evaluated += 1
    order = np.argsort(-best_gain, kind="stable")
    proposals = [dict(index=int(k), satellite=int(context.bank.numbers[k]),
        timing_s=float(best_shift[k]), gain=float(best_gain[k]),
        supporting_arcs=int(supporting_arcs[k])) for k in order[:8]
        if best_gain[k] > 25 and abs(best_shift[k] - shifts[k]) >= .2]
    return proposals, dict(track_count=len(tracks), track_observations=int(len(rows)),
        profile_evaluations=evaluated, proposals=proposals)


class _BudgetExhausted(Exception):
    pass


def fit(context, *, max_evaluations=180, max_seconds=120):
    """Rescue timing, recover shared q, then refit the original joint objective."""
    from common import refit

    begun = time.monotonic()
    deadline = min(begun + max_seconds, getattr(context, 'deadline', float('inf')))
    max_seconds = max(0., deadline - begun)
    model = context.model
    vector, nuisance = context.vector.copy(), context.nuisance.copy()
    initial = float(model.evaluate_joint(vector, nuisance)[0])
    # Proposal work gets at most 35% of elapsed budget; final refit retains 50%.
    proposals, diagnostics = propose_timings(context, vector, nuisance,
        deadline=begun + .35 * max_seconds)
    current = initial
    evaluations = 1
    trials = []
    shifts = vector[7] + model.basis @ vector[8:]
    changes = []
    if proposals:
        all_shifts = shifts.copy()
        for row in proposals:
            all_shifts[row['index']] = row['timing_s']
        changes.append(("combined", all_shifts))
        for row in proposals[:3]:
            one = shifts.copy()
            one[row['index']] = row['timing_s']
            changes.append((str(row['satellite']), one))
    q_start = model.base_nuisance_count
    q_limits = model.group_limits[model.original.group_count:]
    for label, proposed_shifts in changes:
        if evaluations >= max(1, max_evaluations // 2) or time.monotonic() >= begun + .5 * max_seconds:
            break
        vv = _timing_vector(model, context.vector, proposed_shifts)
        if abs(vv[7]) > 10.:
            continue
        best = [float('inf'), nuisance.copy()]
        allowed = min(16, max_evaluations // 2 - evaluations)
        local_calls = 0

        def objective(tail):
            nonlocal evaluations, local_calls
            if (local_calls >= allowed or time.monotonic() >= begun + .5 * max_seconds):
                raise _BudgetExhausted
            nn = nuisance.copy()
            nn[q_start:] = tail
            e = model.evaluate_joint(vv, nn)
            evaluations += 1
            local_calls += 1
            if e[0] < best[0]:
                best[:] = [float(e[0]), nn.copy()]
            return e[0], e[2][q_start:]

        try:
            if len(q_limits):
                minimize(objective, nuisance[q_start:], jac=True, method="L-BFGS-B",
                    bounds=list(zip(-q_limits, q_limits)),
                    options=dict(maxiter=12, maxfun=allowed, ftol=1e-8))
            else:
                objective(nuisance[q_start:])
        except _BudgetExhausted:
            pass
        accepted = best[0] < current - 1e-7
        trials.append(dict(proposal=label, objective=best[0] if np.isfinite(best[0]) else None,
            accepted=accepted, evaluations=local_calls))
        if accepted:
            current, vector, nuisance = best[0], vv, best[1]
    remaining = max_evaluations - evaluations
    if remaining > 1 and time.monotonic() < deadline - .1:
        fitted = refit(context, vector, nuisance, max_evaluations=remaining,
            max_seconds=max(.01, deadline - time.monotonic()),
            fixed_c=getattr(context, 'fixed_c', False))
        fv, fn = fitted['vector'], fitted['nuisance']
        final_value = float(fitted.get('diagnostics', {}).get('objective', current))
        if final_value <= current + 1e-7:
            vector, nuisance, current = fv, fn, final_value
        diagnostics['joint_refit'] = fitted.get('diagnostics', {})
    diagnostics.update(initial_objective=initial, final_objective=current,
        rescue_trials=trials, rescue_evaluations=evaluations,
        evaluations=evaluations + diagnostics.get('joint_refit', {}).get('evaluations', 0),
        elapsed_s=float(time.monotonic() - begun),
        final_common_timing_s=float(vector[7]),
        final_relative_timing_s=(model.basis @ vector[8:]).tolist(),
        qualification='Training-only automatic arc proposals; final original point-mixture objective; no track frequency parameters.')
    return dict(vector=vector, nuisance=nuisance, diagnostics=diagnostics)
