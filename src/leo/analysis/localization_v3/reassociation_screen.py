"""Owned family-omitted candidate nomination and predictive screening."""

import numpy as np
from scipy.optimize import minimize

from leo.analysis.localization_v3.phase_reference import phase_refresh
from leo.analysis.localization_v3.reassociation_context import build, objective
from leo.analysis.localization_v3.reassociation_predictive import fit_predict, masks
from leo.analysis.localization_v3.screen_geometry import phase_frequency_grids
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.track_recovery_diagnostics import profile_rate

ARMS = ("c0", "fitted_c")


def refit(d, arm, start, omit=None, phase_scale=1.0, rounds=5):
    old = d["problems"][arm][0]
    reference = old.reference.copy()
    x = np.array(start)
    history = []
    for epoch in range(rounds):
        p, dd = build(d, arm, reference, omit, phase_scale)
        opt = minimize(
            lambda v, p=p, dd=dd: objective(p, dd, v),
            x,
            method="L-BFGS-B",
            bounds=[(-12.5, 12.5)] * 2,
            options=dict(maxiter=35, maxfun=140, eps=0.001, ftol=1e-10, gtol=0.0001, maxls=15),
        )
        x = opt.x
        updated, check = phase_refresh(p.state(x)["phases"][p.labels], reference, limit_s=30)
        history.append(
            dict(
                success=bool(opt.success),
                message=str(opt.message),
                nfev=opt.nfev,
                x=x.copy(),
                **check,
            )
        )
        if check["phase_change_s"] <= 0.01:
            break
        if epoch < rounds - 1:
            reference = updated
    c = p.calculate(x)
    return dict(
        x=x,
        latlon=d["scan"].search_region.latlon(x),
        error_m=None,
        objective=objective(p, dd, x),
        rms_hz=float(np.sqrt(np.mean(c["conditional_residual_hz"][p.keep] ** 2))),
        history=history,
        reference=p.reference,
        active_points=int(p.keep.sum()),
        phase_closed=check["phase_change_s"] <= 0.01,
        optimizer_success=bool(opt.success),
        boundary=bool(np.any(abs(x) > 12.49)),
        diagnostic_only=True,
        omitted_norad=omit,
        phase_scale=phase_scale,
    )


def screen(d, n, nums, bank):
    base = d["problems"]["fitted_c"][0]
    tracks = [
        (i, base.keep[s])
        for r, i, s in zip(base.rows, base.members, base.slices, strict=True)
        if r["candidate_norad"] == n and base.keep[s].any()
    ]
    ts = np.concatenate([d["scan"].tracks[i]["times"][use] for i, use in tracks])
    q = np.concatenate(
        [np.full(sum(use), d["scan"].tracks[i]["rf_hz"] / 11500000000.0) for i, use in tracks]
    )
    groups = np.concatenate([np.full(sum(use), k) for k, (i, use) in enumerate(tracks)])
    parts = masks(ts, groups)
    pp = np.linspace(-30, 30, 151)
    cavity = {}
    values = {}
    nominees = {n}
    coarse_by_arm = {a: [] for a in ARMS}
    longest = sorted(range(len(tracks)), key=lambda k: -sum(tracks[k][1]))[:2]
    for a in ARMS:
        cav = refit(d, a, d["problems"]["fitted_c"][1], omit=n, rounds=15)
        cavity[a] = cav
        p, _ = build(d, a, np.array(cav["reference"]), omit=n)
        x = np.array(cav["x"])
        state = p.state(x)
        values[a] = np.concatenate(
            [
                (
                    tr["values"]
                    - p.scan.hardware(tr, state["beta"])
                    - tr["rf_hz"]
                    / 11500000000.0
                    * p.scan.rx_basis[i]
                    @ state["smooth"][tr["receiver"] - 1]
                )[use]
                for i, use in tracks
                for tr in [p.scan.tracks[i]]
            ]
        )
    positions = [d["scan"].search_region.latlon(np.array(cavity[a]["x"])) for a in ARMS]
    for k in longest:
        ii = np.flatnonzero(groups == k)
        ii = ii[np.unique(np.linspace(0, len(ii) - 1, min(16, len(ii))).astype(int))]
        best = {a: np.full(len(nums), np.inf) for a in ARMS}
        for phi in np.arange(-30, 31, 2):
            grids = phase_frequency_grids(bank, ts[ii], positions, phase_seconds=phi)
            for a, (f, e) in zip(ARMS, grids, strict=True):
                cost = (
                    profile_rate(
                        values[a][ii], f * q[ii], ts[ii], rate_sigma_hz_s=0.5, bias_sigma_hz=300
                    )["cost"]
                    + (phi / 5) ** 2
                )
                best[a] = np.minimum(best[a], np.where(e.min(axis=1) >= 0, cost, np.inf))
        for a in ARMS:
            finalists = [int(j) for j in np.argsort(best[a])[:2] if np.isfinite(best[a][j])]
            nominees.update(int(nums[j]) for j in finalists)
            coarse_by_arm[a].append(
                dict(
                    arm=a,
                    track=d["scan"].tracks[tracks[k][0]]["key"],
                    nominees=[dict(norad=int(nums[j]), score=float(best[a][j])) for j in finalists],
                )
            )
    # Preserve the original arm-major receipt order despite shared interpolation.
    coarse = [row for a in ARMS for row in coarse_by_arm[a]]
    raw = {}
    whole = {}
    folds = []
    for a in ARMS:
        raw[a] = {}
        whole[a] = {}
        for v in sorted(nominees):
            j = int(np.flatnonzero(nums == v)[0])
            bb = dict(
                time_s=bank["time_s"],
                position_km=np.broadcast_to(
                    bank["position_km"][j], (len(pp), *bank["position_km"][j].shape)
                ),
                velocity_km_s=np.broadcast_to(
                    bank["velocity_km_s"][j], (len(pp), *bank["velocity_km_s"][j].shape)
                ),
            )
            f, e = paired_phase_frequency(
                bb,
                np.tile(ts, len(pp)),
                np.repeat(np.arange(len(pp)), len(ts)),
                pp,
                *d["scan"].search_region.latlon(np.array(cavity[a]["x"])),
            )
            if np.min(e) < 0:
                continue
            raw[a][v] = values[a][None, :] - f.reshape(len(pp), -1) * q
            whole[a][v] = fit_predict(
                raw[a][v], ts, q, groups, np.ones(len(ts), bool), np.ones(len(ts), bool), pp
            )
    common = sorted(set(raw["c0"]) & set(raw["fitted_c"]))
    if n not in common:
        return dict(
            status="incumbent_not_visible_over_complete_phase_grid",
            cavity=cavity,
            coarse=coarse,
            nominees=common,
        )
    for part in parts:
        for a in ARMS:
            fitted = {
                v: fit_predict(raw[a][v], ts, q, groups, part["train"], part["test"], pp)
                for v in common
            }
            folds.append(dict(arm=a, fold=part["fold"], fits=fitted))
    ranked = sorted(
        [v for v in common if v != n],
        key=lambda v: sum(whole[a][v]["training_score"] for a in ARMS),
    )[:2]
    proposals = []

    def predictive_ok(v):
        results = {}
        for a in ARMS:
            gains = [
                r["fits"][n]["predictive_score"] - r["fits"][v]["predictive_score"]
                for r in folds
                if r["arm"] == a
            ]
            results[a] = dict(
                gains=gains,
                mean=float(np.mean(gains)) if gains else None,
                wins=sum(g > 0 for g in gains),
                pass_check=len(gains) == 5
                and np.mean(gains) > 0
                and (sum(g > 0 for g in gains) >= 4),
            )
        return results

    keys = [d["scan"].tracks[i]["key"] for i, u in tracks]
    for v in ranked:
        proposals.append(
            dict(
                name=f"{n}_to_{v}",
                norad=v,
                mapping=dict.fromkeys(keys, v),
                aliases={
                    key: whole["fitted_c"][v]["alias_by_group"][k] for k, key in enumerate(keys)
                },
                phases={str(v): whole["fitted_c"][v]["phase_map_s"]},
                allowed_families=[n, v],
                predictive=predictive_ok(v),
                penalty=float(2 * np.log(max(2, len(common)))),
            )
        )
    mapping = {}
    stability = []
    for k, key in enumerate(keys):
        winners = [min(common, key=lambda v: r["fits"][v]["training_track_cost"][k]) for r in folds]
        counts = {v: winners.count(v) for v in common}
        win = max(common, key=lambda v: counts[v])
        stable = bool(
            len(winners) == 10
            and all(
                sum(
                    min(common, key=lambda v: r["fits"][v]["training_track_cost"][k]) == win
                    for r in folds
                    if r["arm"] == a
                )
                >= 4
                for a in ARMS
            )
        )
        mapping[key] = win if stable else n
        stability.append(dict(component=key, counts=counts, stable=stable, label=mapping[key]))
    if len(set(mapping.values())) > 1:
        predictive = {}
        phases = {}
        aliases = {}
        for a in ARMS:
            gains = []
            for part in parts:
                score = 0.0
                for v in set(mapping.values()):
                    mask = np.isin(groups, [k for k, key in enumerate(keys) if mapping[key] == v])
                    r = fit_predict(
                        raw[a][v][:, mask],
                        ts[mask],
                        q[mask],
                        groups[mask],
                        part["train"][mask],
                        part["test"][mask],
                        pp,
                    )
                    score += r["predictive_score"]
                original = next(r for r in folds if r["arm"] == a and r["fold"] == part["fold"])[
                    "fits"
                ][n]["predictive_score"]
                gains.append(original - score)
            predictive[a] = dict(
                gains=gains,
                mean=float(np.mean(gains)) if gains else None,
                wins=sum(g > 0 for g in gains),
                pass_check=len(gains) == 5
                and np.mean(gains) > 0
                and (sum(g > 0 for g in gains) >= 4),
            )
        for v in set(mapping.values()):
            mask = np.isin(groups, [k for k, key in enumerate(keys) if mapping[key] == v])
            r = fit_predict(
                raw["fitted_c"][v][:, mask],
                ts[mask],
                q[mask],
                groups[mask],
                np.ones(sum(mask), bool),
                np.ones(sum(mask), bool),
                pp,
            )
            phases[str(v)] = r["phase_map_s"]
            aliases.update({keys[k]: alias for k, alias in r["alias_by_group"].items()})
        proposals.append(
            dict(
                name=f"{n}_stable_partition",
                norad=n,
                mapping=mapping,
                aliases=aliases,
                phases=phases,
                allowed_families=sorted(set(mapping.values()) | {n}),
                predictive=predictive,
                penalty=float(
                    2 * np.log(max(2, len(common)))
                    + 2 * (len(set(mapping.values())) - 1) * np.log(len(ts))
                ),
                prediction_limit=(
                    "mapping selected across these same folds; development diagnostic, "
                    "cannot meet independent predictive acceptance"
                ),
            )
        )
    result = dict(
        status="screened",
        cavity=cavity,
        coarse=coarse,
        nominees=common,
        whole=whole,
        folds=folds,
        partitions=parts,
        proposals=proposals,
        stability=stability,
        points=len(ts),
        tracks=keys,
        scope=(
            "conditional prediction with family-omitted position/calibration; "
            "discovery uses full family data"
        ),
    )
    return result
