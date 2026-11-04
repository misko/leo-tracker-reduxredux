"""Paired rejection/refitting and independently calibrated track salvage.

This is the conservative policy after initial search, before family-weighted
history fitting and later recovery. All evidence is passed as numerical inputs.
"""

import copy

import numpy as np

from leo.analysis.localization_v3.acceptance import conditional_gate, extend_associations
from leo.analysis.localization_v3.retained_position import (
    PositionNormal,
    fit_position,
    repaired_fit,
)
from leo.analysis.localization_v3.tracks import active_curvature as raw_curvature
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile, whitening

ARMS = ("c0", "fitted_c")


def conservative_recovery(
    scan, initial, observations, *, max_rounds=4, rounds=5, iterations=48, on_round=None
):
    """Retain exactly the original exclusion/salvage policy and failure states.

    ``scan`` must use the genuine-previous causal prior, not the initial-search
    context with cached modes from the original previous-epoch catalogue.
    """
    if any(
        not isinstance(n, int) or isinstance(n, bool) or n < 1
        for n in (max_rounds, rounds, iterations)
    ):
        raise ValueError("Positive integer refit budgets required")
    winner = next(
        c for c in initial["choices"] if c["hypothesis"] == initial["selected_hypothesis"]
    )
    node = copy.deepcopy(winner["node"])
    p = PositionNormal(scan, node, scan.radio_sigma_hz, False)
    keep = np.ones(len(p.values), bool)
    failed = {
        r["component"] for r in winner["arms"]["c0"]["metrics"]["tracks"] if not r["compatible"]
    }
    for row, sl in zip(p.rows, p.slices, strict=True):
        if row["component"] in failed:
            keep[sl] = False
    if not keep.any():
        return dict(status="no_passing_calibration", GPS_used=False)
    p, keep, pair, before_history, stable = fit_and_gate(
        scan,
        node,
        keep,
        "exclude_refit",
        max_rounds=max_rounds,
        rounds=rounds,
        iterations=iterations,
        on_round=on_round,
    )
    trims = []
    if stable and not keep.all():
        node, keep, trims = salvage(scan, node, keep, rounds=rounds, iterations=iterations)
        p, keep, pair, after_history, stable = fit_and_gate(
            scan,
            node,
            keep,
            "salvage_refit",
            max_rounds=max_rounds,
            rounds=rounds,
            iterations=iterations,
            on_round=on_round,
        )
    else:
        after_history = []
    original_ids = {o["observation_id"] for o in observations}
    for arm in ARMS:
        saved = pair[arm]["record"]
        p = PositionNormal(
            scan,
            node,
            scan.radio_sigma_hz,
            arm == "fitted_c",
            reference=np.asarray(saved["phase_reference"]),
            keep=keep,
        )
        p.phase_sigma = np.asarray(saved["phase_widths_s"])
        x = saved["fit"]["parameters"]
        extended = extend_associations(p, x, pair[arm]["metrics"])
        pair[arm]["association"] = coverage(extended["tracks"], scan.tracks, original_ids)
        pair[arm]["association_tracks"] = extended["tracks"]
    return dict(
        status="complete" if stable else "gate_refit_unstable",
        arms=pair,
        final_node=node,
        final_mask=keep,
        initial_failed_components=sorted(failed),
        trims=trims,
        exclusion_history=before_history,
        post_salvage_history=after_history,
        paired_masks_aliases_and_identities=True,
        GPS_used=False,
        future_TLE_used=False,
    )


def selected_supports(n):
    """Whole, prefix and suffix hypotheses; no hand-written breakpoint time."""
    supports = {(0, n)} | {(a, n) for a in range(1, n - 11)} | {(0, b) for b in range(12, n)}
    return sorted((a, b) for a, b in supports if b - a >= 12)


def retained_metrics(p, x):
    """Apply the existing profile/conditional gates only to active observations.

    The 36-point salvage retains the original nuisance design. Masked prefix
    points must neither fail the suffix gate nor be counted as accepted suffix.
    """
    scan, state = p.scan, p.state(x)
    result = p.calculate(x)
    frequency, elevation = p.conditional_frequency(x)
    rows = []
    for row, i, sl, alias in zip(p.rows, p.members, p.slices, p.alias, strict=True):
        t, active = scan.tracks[i], p.keep[sl]
        if not active.any():
            continue
        times = t["times"][active]
        q = t["rf_hz"] / 11.5e9
        y = t["values"] - scan.hardware(t, state["beta"])
        y -= q * scan.rx_basis[i] @ state["smooth"][t["receiver"] - 1]
        terms = profile(y[active], q * frequency[sl][active], *whitening(times))
        noise = batch_noise_screen(terms["innovations"], times)
        conditional = conditional_gate(result["conditional_residual_hz"][sl][active], times)
        passing = bool(
            terms["rms"][0] <= 450
            and abs(terms["bias"][0]) <= 3000
            and noise["noise_screen_pass"][0]
            and conditional["compatible"]
            and int(terms["alias"][0]) == alias
            and elevation[sl][active].min() >= 0
        )
        rows.append(
            dict(
                component=t["key"],
                norad=row["candidate_norad"],
                candidate_index=row["candidate_index"],
                points=int(active.sum()),
                compatible=passing,
                observation_ids=np.asarray(t["observation_ids"])[active].tolist(),
                conditional_residual_gate=conditional,
                profile_rms_hz=float(terms["rms"][0]),
                profile_bias_hz=float(terms["bias"][0]),
                aliases_changed=int(int(terms["alias"][0]) != alias),
            )
        )
    while True:
        owners = {}
        by_key = {t["key"]: t for t in scan.tracks}
        for row in rows:
            if row["compatible"]:
                t = by_key[row["component"]]
                owners.setdefault(row["candidate_index"], set()).add((t["receiver"], t["channel"]))
        changed = False
        for row in rows:
            if (
                row["compatible"]
                and row["candidate_index"] in p.supported
                and len(owners[row["candidate_index"]]) < 2
            ):
                row["compatible"] = False
                changed = True
        if not changed:
            break
    return dict(tracks=rows, accepted_points=sum(r["points"] for r in rows if r["compatible"]))


def coverage(accepted_tracks, tracks, original_ids):
    """Count unique measurements; never divide additional peaks by winner count."""
    by_key = {t["key"]: t for t in tracks}
    owned = []
    for row in accepted_tracks:
        if row["compatible"]:
            owned.extend(row.get("observation_ids", by_key[row["component"]]["observation_ids"]))
    if len(owned) != len(set(owned)):
        raise ValueError("a physical measurement has multiple accepted owners")
    associated = set(owned)
    return dict(
        original_winning_GLRT_points=len(original_ids),
        associated_original_winners=len(associated & original_ids),
        associated_original_percent=100 * len(associated & original_ids) / len(original_ids),
        associated_additional_peaks=len(associated - original_ids),
        associated_distinct_measurements=len(associated),
        associated_tracks=sum(bool(r["compatible"]) for r in accepted_tracks),
        associated_observation_ids=sorted(associated),
    )


def causal_fit(scan, node, keep, arm, *, rounds=5, iterations=48):
    return fit_position(scan, node, keep, [], arm, "native", rounds=rounds, iterations=iterations)


def fit_and_gate(scan, node, keep, stage, max_rounds=4, *, rounds=5, iterations=48, on_round=None):
    """Monotone paired-arm rejection with equal data and budgets in each pair."""
    history = []
    for epoch in range(max_rounds):
        pair, rejected = ({}, set())
        for arm in ARMS:
            p, record = causal_fit(scan, node, keep, arm, rounds=rounds, iterations=iterations)
            metrics = retained_metrics(p, record["fit"]["parameters"])
            pair[arm] = dict(record=record, metrics=metrics)
            rejected.update(r["component"] for r in metrics["tracks"] if not r["compatible"])
        history.append(
            dict(epoch=epoch, active_points=int(keep.sum()), rejected_components=sorted(rejected))
        )
        if on_round is not None:
            on_round(stage, history[-1])
        if not rejected:
            return (p, keep, pair, history, True)
        if epoch == max_rounds - 1:
            break
        next_keep = keep.copy()
        for row, sl in zip(p.rows, p.slices, strict=True):
            if row["component"] in rejected:
                next_keep[sl] = False
        if not next_keep.any():
            return (p, keep, pair, history, False)
        assert np.all(~next_keep | keep)
        keep = next_keep
    return (p, keep, pair, history, False)


def salvage(scan, node, keep, *, rounds=5, iterations=48):
    """Apply the published all-catalogue shortlist and independently gated trim."""
    p, fitted, _, _ = repaired_fit(
        scan, node, "c0", "unit", keep, rounds=rounds, iterations=iterations
    )
    x = fitted["parameters"]
    state = p.state(x)
    repaired, retained, diagnostics = (copy.deepcopy(node), keep.copy(), [])
    for k, (i, sl) in enumerate(zip(p.members, p.slices, strict=True)):
        if keep[sl].any():
            continue
        track = scan.tracks[i]
        t, values = (track["times"], track["values"])
        q = track["rf_hz"] / 11500000000.0
        radio = scan.hardware(track, state["beta"])
        radio += q * scan.rx_basis[i] @ state["smooth"][track["receiver"] - 1]
        y, noise = (values - radio, p.point_noise[sl])
        f, elevation, derivative = phase_linear_frequency(
            prepare_phase_geometry(scan.sky, t), *scan.search_region.latlon(x)
        )
        coarse_phase = np.linspace(-10, 10, 81)
        prediction = q * (f[:, None] + derivative[:, None] * coarse_phase[None, :, None])
        terms = profile(y, prediction.reshape(-1, len(t)), np.diag(1 / noise))
        cost = terms["cost"].reshape(len(scan.norads), -1) + coarse_phase[None, :] ** 2 / 9
        cost[elevation.max(axis=1) < 0] = np.inf
        shortlist = set(map(int, np.argsort(cost.min(axis=1))[:30]))
        for lo in np.arange(t[0], t[-1], 20):
            m = (t >= lo) & (t < lo + 20)
            if m.sum() < 8:
                continue
            terms = profile(
                y[m], prediction[:, :, m].reshape(-1, int(m.sum())), np.diag(1 / noise[m])
            )
            cost = terms["cost"].reshape(len(scan.norads), -1) + coarse_phase[None, :] ** 2 / 9
            cost[elevation[:, m].max(axis=1) < 0] = np.inf
            shortlist.update(map(int, np.argsort(cost.min(axis=1))[:10]))
        shortlist.add(p.rows[k]["candidate_index"])
        alternatives = []
        grid = np.linspace(-15, 15, 121)
        supports = [
            (a, b)
            for a, b in selected_supports(len(t))
            if t[b - 1] - t[a] >= 20 and raw_curvature(dict(times=t[a:b], values=values[a:b]))
        ]
        for j in sorted(shortlist):
            bank = dict(
                time_s=scan.sky["time_s"],
                position_km=np.repeat(scan.sky["position_km"][[j]], len(grid), axis=0),
                velocity_km_s=np.repeat(scan.sky["velocity_km_s"][[j]], len(grid), axis=0),
            )
            ff, ee = paired_phase_frequency(
                bank,
                np.tile(t, len(grid)),
                np.repeat(np.arange(len(grid)), len(t)),
                grid,
                *scan.search_region.latlon(x),
            )
            ff, ee = (ff.reshape(len(grid), -1), ee.reshape(len(grid), -1))
            for a, b in supports:
                terms = profile(y[a:b], q * ff[:, a:b], np.diag(1 / noise[a:b]))
                cost = terms["cost"] + grid**2 / 9
                cost[ee[:, a:b].min(axis=1) < 0] = np.inf
                best = int(np.argmin(cost))
                residual = terms["residual"][best]
                screen = batch_noise_screen(residual[None], t[a:b])
                if (
                    terms["rms"][best] > 450
                    or abs(terms["bias"][best]) > 3000
                    or (not np.isfinite(cost[best]))
                    or (not screen["noise_screen_pass"][0])
                    or (np.max(abs(residual) / noise[a:b]) > 6)
                ):
                    continue
                alternatives.append(
                    dict(
                        start_index=a,
                        stop_index=b,
                        points=b - a,
                        candidate_index=j,
                        norad=int(scan.norads[j]),
                        phase_s=float(grid[best]),
                        cost=float(cost[best]),
                        alias=int(terms["alias"][best]),
                        rms_hz=float(terms["rms"][best]),
                        max_external_radio_sigma=float(np.max(abs(residual) / noise[a:b])),
                    )
                )
        alternatives.sort(key=lambda a: (-a["points"], a["cost"]))
        chosen = alternatives[0] if alternatives else None
        diagnostics.append(
            dict(
                component=track["key"],
                candidate_count=len(shortlist),
                supports_tested=len(supports),
                selected=chosen,
                alternatives=alternatives[:5],
            )
        )
        if chosen:
            repaired["seed"]["rows"][k].update(
                candidate_index=chosen["candidate_index"], candidate_norad=chosen["norad"]
            )
            repaired["aliases"][k] = chosen["alias"]
            retained[sl.start + chosen["start_index"] : sl.start + chosen["stop_index"]] = True
    return (repaired, retained, diagnostics)
