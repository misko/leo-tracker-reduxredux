"""Original profile/conditional gates and frozen-calibration track extension.

Receives fitted numerical objects only. No saved solutions, evaluation site,
historical workers or storage paths are inputs to these acceptance decisions.
"""
from collections import defaultdict

import numpy as np

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile, whitening


class EvaluationAdapter:
    def __init__(self, problem):
        self.problem = problem

    def __getattr__(self, name):
        return getattr(self.problem, name)

    def association_state(self, x):
        state = self.problem.state(x)
        state["marginal_orbit_coefficients"] = {j: [] for j in self.problem.supported}
        return state

    def predicted(self, x):
        return self.problem.conditional_frequency(x)


def nominated_metrics(scan, item, *, problem_factory):
    fit, method, arm = item["fit"], item["method"], item["arm"]
    seed = dict(rows=fit["rows"], state=fit["state"])
    args = (scan, seed, method, arm == "fitted_c", fit["east_north_km"])
    p = problem_factory(*args)
    p.alias = fit["aliases"]
    x = np.array(min(fit["fits"], key=lambda r: r["score"])["parameters"])
    state = p.association_state(x) if hasattr(p, "association_state") else p.decode(x)
    f, elevation = p.predicted(x)
    rows = []
    for i, row, block, alias in zip(p.members, p.rows, p.slices, p.alias, strict=True):
        t = scan.tracks[i]
        y = t["values"] - scan.hardware(t, state["beta"])
        if method == "receiver_smooth":
            y -= t["rf_hz"] / 11.5e9 * scan.rx_basis[i] @ state["smooth"][t["receiver"] - 1]
        predicted = t["rf_hz"] / 11.5e9 * f[block]
        cut = row["split_at"] if method == "penalized_split" else -1
        slices = (slice(None),) if cut <= 0 else (slice(0, cut), slice(cut, None))
        native, innovations, passing, aliases = [], [], True, []
        for part in slices:
            times = t["times"][part]
            w, volume = (
                (scan.ou[i] if method == "correlated_noise" else scan.white[i])
                if cut <= 0
                else whitening(times)
            )
            terms = profile(
                y[part],
                predicted[part],
                w,
                volume,
                bias_sigma=(
                    p.bias_sigma_for_member(i)
                    if hasattr(p, "bias_sigma_for_member")
                    else getattr(p, "curve_bias_sigma", 1000.0)
                ),
            )
            noise = batch_noise_screen(terms["innovations"], times)
            passing &= bool(
                terms["rms"][0] <= 450
                and abs(terms["bias"][0]) <= 3000
                and noise["noise_screen_pass"][0]
            )
            native.extend(terms["residual"][0])
            innovations.extend(terms["innovations"][0])
            aliases.append(int(terms["alias"][0]))
        rows.append(
            dict(
                component=t["key"],
                norad=row["candidate_norad"],
                candidate_index=row["candidate_index"],
                points=len(y),
                compatible=(
                    passing
                    and bool(elevation[block].min() >= 0)
                    and state.get("marginal_signal_probability", {}).get(
                        row["candidate_index"], 1.0
                    )
                    >= 0.5
                ),
                native_square_hz2=float(np.sum(np.array(native) ** 2)),
                innovation_square_hz2=float(np.sum(np.array(innovations) ** 2)),
                native_rms_hz=float(np.sqrt(np.mean(np.array(native) ** 2))),
                aliases_changed=sum(a != alias for a in aliases),
            )
        )
    while True:
        owners = defaultdict(set)
        shape_owners = defaultdict(set)
        for r, i in zip(rows, p.members, strict=True):
            if r["compatible"]:
                owners[r["candidate_index"]].add(scan.tracks[i]["channel"])
                shape_owners[r["candidate_index"]].add(
                    (scan.tracks[i]["receiver"], scan.tracks[i]["channel"])
                )
        changed = False
        for r in rows:
            if (
                r["compatible"]
                and r["candidate_index"] in state["extra"]
                and len(owners[r["candidate_index"]]) < 2
            ):
                r["compatible"] = False
                changed = True
            if (
                r["compatible"]
                and (
                    r["candidate_index"] in state.get("causal_shape_coefficients", {})
                    or r["candidate_index"] in state.get("mean_motion_offsets_rev_day", {})
                    or r["candidate_index"] in state.get("marginal_orbit_coefficients", {})
                )
                and len(shape_owners[r["candidate_index"]]) < 2
            ):
                r["compatible"] = False
                changed = True
        if not changed:
            break
    n = sum(r["points"] for r in rows)
    accepted = [r for r in rows if r["compatible"]]
    na = sum(r["points"] for r in accepted)
    return dict(
        curved_points=n,
        accepted_nominated_curved_points=na,
        all_curved_native_rms_hz=float(
            np.sqrt(sum(r["native_square_hz2"] for r in rows) / max(1, n))
        ),
        accepted_native_rms_hz=float(
            np.sqrt(sum(r["native_square_hz2"] for r in accepted) / max(1, na))
        ),
        accepted_innovation_rms_hz=float(
            np.sqrt(sum(r["innovation_square_hz2"] for r in accepted) / max(1, na))
        ),
        aliases_changed=sum(r["aliases_changed"] for r in rows),
        tracks=rows,
    )


def conditional_gate(residual, times):
    r = np.asarray(residual, float)
    screen = batch_noise_screen(r[None, :], times)
    return dict(
        compatible=bool(screen["noise_screen_pass"][0] and np.sqrt(np.mean(r * r)) <= 450),
        rms_hz=float(np.sqrt(np.mean(r * r))),
        mean_hz=float(np.mean(r)),
        diagnostics={key: value[0] for key, value in screen.items()},
    )


def actual_metrics(p, fit, arm, x):
    adapter = EvaluationAdapter(p)
    original = nominated_metrics(
        p.scan,
        dict(fit=fit, method="receiver_smooth", arm=arm),
        problem_factory=lambda *args: adapter,
    )
    result = p.calculate(x)
    rows = []
    for row, i, sl in zip(original["tracks"], p.members, p.slices, strict=True):
        gate = conditional_gate(result["conditional_residual_hz"][sl], p.scan.tracks[i]["times"])
        rows.append(
            dict(
                row,
                original_profile_compatible=row["compatible"],
                profile_native_square_hz2=row["native_square_hz2"],
                native_square_hz2=float(np.sum(result["conditional_residual_hz"][sl] ** 2)),
                native_rms_hz=gate["rms_hz"],
                conditional_residual_gate=gate,
                compatible=row["compatible"] and gate["compatible"] and row["aliases_changed"] == 0,
            )
        )
    while True:
        owners = {}
        for row, i in zip(rows, p.members, strict=True):
            if row["compatible"]:
                t = p.scan.tracks[i]
                owners.setdefault(row["candidate_index"], set()).add((t["receiver"], t["channel"]))
        changed = False
        for row in rows:
            if (
                row["compatible"]
                and row["candidate_index"] in p.supported
                and len(owners.get(row["candidate_index"], set())) < 2
            ):
                row["compatible"] = False
                changed = True
        if not changed:
            break
    n = sum(row["points"] for row in rows if row["compatible"])
    return dict(
        original_profile_metrics=original,
        tracks=rows,
        accepted_points=n,
        accepted_tracks=sum(row["compatible"] for row in rows),
        accepted_native_rms_hz=float(
            np.sqrt(sum(row["native_square_hz2"] for row in rows if row["compatible"]) / max(1, n))
        ),
    )


def extend_associations(p, x, metrics):
    """Attach remaining graph tracks using frozen calibration, never linear votes."""
    scan, state = p.scan, p.state(x)
    accepted = {r["component"]: dict(r, association_source="curved_calibration")
                for r in metrics["tracks"] if r["compatible"]}
    labels = sorted({r["candidate_index"] for r in accepted.values()})
    supported_groups = {(scan.tracks[i]["receiver"], int(scan.tracks[i]["channel"] > 4))
                        for i in p.members if scan.tracks[i]["key"] in accepted}
    predictions, elevations, available = [], [], []
    result = p.calculate(x)
    begin = p.hardware.shape[1] + p.smooth.shape[1] + len(p.labels)
    for j in labels:
        phase = np.array([state["phases"][j]])
        if abs(phase[0]) > 15:
            continue
        bank = dict(time_s=scan.sky["time_s"],
                    position_km=scan.sky["position_km"][[j]],
                    velocity_km_s=scan.sky["velocity_km_s"][[j]])
        local = p.labels.index(j)
        f, e = paired_phase_frequency(bank, scan.times, np.zeros(len(scan.times), int),
                                      phase, *scan.search_region.latlon(x))
        if j in p.supported:
            k = p.supported.index(j)
            modes = dict(time_s=p.mode_bank["time_s"],
                         position_km=p.mode_bank["position_km"][3 * local:3 * local + 3],
                         velocity_km_s=p.mode_bank["velocity_km_s"][3 * local:3 * local + 3])
            derivative = paired_frequency_modes(bank, modes, scan.times,
                np.zeros(len(scan.times), int), phase, *scan.search_region.latlon(x))
            f += derivative @ result["coefficient"][begin + 3 * k:begin + 3 * k + 3]
        available.append(j)
        predictions.append(f)
        elevations.append(e)
    f, elevation = np.array(predictions), np.array(elevations)
    for i, t in enumerate(scan.tracks):
        if t["key"] in accepted or not available:
            continue
        group = t["receiver"], int(t["channel"] > 4)
        if group not in supported_groups:
            continue
        ix = scan.index[i]
        y = (t["values"] - scan.hardware(t, state["beta"])
             - t["rf_hz"] / 11.5e9 * scan.rx_basis[i] @ state["smooth"][t["receiver"] - 1])
        terms = profile(y, t["rf_hz"] / 11.5e9 * f[:, ix], *scan.white[i])
        noise = batch_noise_screen(terms["innovations"], t["times"])
        good = ((terms["rms"] <= 450) & (abs(terms["bias"]) <= 3000)
                & noise["noise_screen_pass"] & (elevation[:, ix].min(axis=1) >= 0))
        if not good.any():
            continue
        k = int(np.argmin(np.where(good, terms["cost"], np.inf)))
        j = available[k]
        accepted[t["key"]] = dict(component=t["key"], norad=int(scan.norads[j]),
            candidate_index=j, points=len(y), native_rms_hz=float(terms["rms"][k]),
            compatible=True, active_curvature=i in scan.curved,
            association_source="frozen_calibration_extension", bias_hz=float(terms["bias"][k]))
    points = sum(r["points"] for r in accepted.values())
    return dict(accepted_points=points, accepted_tracks=len(accepted),
                accepted_satellites=len({r["candidate_index"] for r in accepted.values()}),
                tracks=list(accepted.values()), linear_tracks_never_calibrate=True,
                original_curved_gate_points=metrics["accepted_points"],
                added_points=points - metrics["accepted_points"])
