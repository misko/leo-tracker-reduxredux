"""Fit scan/band relative receiver calibration and investigate tracklet stitching.

No orbit labels, localization model or RF-dependent c coefficient is used.
Original Graph observations are preserved; only conservative fusion is attempted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from compare_dsx01_graph_receivers import (
    OUTPUT as PREVIOUS,
)
from compare_dsx01_graph_receivers import (
    PERIOD,
    ROOT,
    candidates,
    load_tracks,
    modal_pairs,
    predict,
    shifted_receivers,
    wrap,
    write_csv,
)
from numpy.polynomial import legendre as leg
from tune_full_data_tracklets import full_residual_diagnostics

OUTPUT = ROOT / "reports/2026_10_17_dsx01_receiver_model"
SIGMA = 150.0
GATE = 450.0
DRIFT_SIGMA = 10.0
MAX_GAP = 10.0
MAX_SLOPE = 8000.0
BANDS = ("CH1-4", "CH5-8")


def seed_anchors(tracks):
    groups = defaultdict(list)
    for pair in candidates(tracks):
        groups[pair["source_id"], pair["bank"]].append(pair)
    return [p for group in groups.values() for p in modal_pairs(group)]


def core_data(anchors, mapping):
    """Original observations in overlap only; each anchor uses distinct tracklets."""
    cores, used = [], set()
    for pair in anchors:
        left, right = mapping[pair["left_key"]], mapping[pair["right_key"]]
        mid = pair["mid_s"]
        lift = (
            round(
                (
                    predict(left, np.array([mid]))[0]
                    + pair["offset_hz"]
                    - predict(right, np.array([mid]))[0]
                )
                / PERIOD
            )
            * PERIOD
        )
        times, values, receivers = [], [], []
        for track in (left, right):
            m = (track["times"] >= pair["start_s"]) & (track["times"] <= pair["end_s"])
            ids = np.array(track["observation_ids"])[m]
            assert not (set(ids) & used)
            used.update(ids)
            times.extend(track["times"][m])
            values.extend(track["values"][m] + (lift if track["receiver"] == 2 else 0))
            receivers.extend([track["receiver"]] * m.sum())
        times, values = np.array(times), np.array(values)
        ref, scale = float((times.min() + times.max()) / 2), max(1.0, np.ptp(times) / 2)
        cores.append(
            {
                **pair,
                "t": times,
                "y": values,
                "rx": np.array(receivers),
                "x": (times - ref) / scale,
                "reference_time_s": ref,
                "time_scale_s": scale,
            }
        )
    return cores


def calibration_design(core, bands, family):
    n = len(core["t"])
    columns = [(core["rx"] == 2) * float(core["bank"] == b) for b in bands]
    if family == "shared_drift":
        columns.append((core["rx"] == 2) * (core["t"] - 150) / 150)
    elif family == "band_drift":
        columns.extend(
            [(core["rx"] == 2) * float(core["bank"] == b) * (core["t"] - 150) / 150 for b in bands]
        )
    design = np.column_stack(columns).astype(float)
    assert len(design) == n
    return design


def profile_core(core, z, beta, weights):
    target = core["y"] - z @ beta
    choices = []
    # Degree cost is shared with the scientific tracklet experiments.
    for degree in range(0, min(4, len(target) // 2 - 1) + 1):
        x = leg.legvander(core["x"], degree)
        root_w = np.sqrt(weights)
        coeff = np.linalg.lstsq(x * root_w[:, None], target * root_w, rcond=None)[0]
        residual = target - x @ coeff
        cost = np.dot(weights, residual**2) / SIGMA**2 + (degree + 1) * np.log(len(target))
        choices.append((cost, degree, x, coeff, residual))
    return min(choices, key=lambda c: c[0])


def fit_calibration(cores, family):
    """Variable projection of latent polynomial coefficients; relative RX gauge.

    Two receiver hardware slopes cannot be split from an unknown curve slope.
    RX1's offset and drift are zero references independently within each band.
    """
    bands = sorted({c["bank"] for c in cores})
    offset_count = len(bands)
    n_beta = offset_count + (
        1 if family == "shared_drift" else offset_count if family == "band_drift" else 0
    )
    beta = np.zeros(n_beta)
    for i, band in enumerate(bands):
        beta[i] = np.median([c["offset_hz"] for c in cores if c["bank"] == band])
    prior = np.zeros(n_beta)
    prior[offset_count:] = 1 / (DRIFT_SIGMA * 150) ** 2
    designs = [calibration_design(c, bands, family) for c in cores]
    weights = [np.ones(len(c["t"])) for c in cores]
    normal = np.zeros((n_beta, n_beta))
    profiles = []
    for _ in range(30):
        normal = np.zeros((n_beta, n_beta))
        rhs = np.zeros(n_beta)
        profiles = []
        for core, z, w in zip(cores, designs, weights, strict=True):
            profile = profile_core(core, z, beta, w)
            profiles.append(profile)
            x = profile[2]
            root = np.sqrt(w)
            wx, wz, wy = x * root[:, None], z * root[:, None], core["y"] * root
            rz = wz - wx @ np.linalg.lstsq(wx, wz, rcond=None)[0]
            ry = wy - wx @ np.linalg.lstsq(wx, wy, rcond=None)[0]
            normal += rz.T @ rz
            rhs += rz.T @ ry
        new_beta = np.linalg.solve(normal + SIGMA**2 * np.diag(prior), rhs)
        change = np.max(np.abs(new_beta - beta))
        beta = new_beta
        weights = []
        for core, z in zip(cores, designs, strict=True):
            residual = profile_core(core, z, beta, np.ones(len(core["t"])))[4]
            weights.append(np.minimum(1.0, 2.5 * SIGMA / np.maximum(np.abs(residual), 1e-9)))
        if change < 0.005:
            break
    profiles = [
        profile_core(c, z, beta, w) for c, z, w in zip(cores, designs, weights, strict=True)
    ]
    rss = sum(float(np.dot(p[4], p[4])) for p in profiles)
    n = sum(len(c["t"]) for c in cores)
    k = n_beta + sum(p[1] + 1 for p in profiles)
    polynomial_cost = sum(
        (p[1] + 1) * np.log(len(c["t"])) for c, p in zip(cores, profiles, strict=True)
    )
    score = rss / SIGMA**2 + n_beta * np.log(n) + polynomial_cost + float(np.dot(prior, beta**2))
    covariance = SIGMA**2 * np.linalg.pinv(normal)
    results = []
    for i, band in enumerate(bands):
        group = [c for c in cores if c["bank"] == band]
        j = offset_count if family == "shared_drift" else offset_count + i
        slope = 0.0 if family == "constant" else beta[j] / 150
        sigma_at = []
        for time in (0, 150, 300):
            vector = np.zeros(n_beta)
            vector[i] = 1
            if family != "constant":
                vector[j] = (time - 150) / 150
            sigma_at.append(float(np.sqrt(max(0, vector @ covariance @ vector))))
        results.append(
            {
                "source_id": group[0]["source_id"],
                "bank": band,
                "family": family,
                "offset_at_150s_hz": float(beta[i]),
                "relative_drift_hz_s": float(slope),
                "conditional_offset_se_hz": sigma_at[1],
                "conditional_drift_se_hz_s": 0.0
                if family == "constant"
                else float(np.sqrt(max(0, covariance[j, j])) / 150),
                "conditional_max_endpoint_se_hz": max(sigma_at),
                "anchors": len(group),
                "channels": len({c["channel"] for c in group}),
                "anchor_center_span_s": float(np.ptp([c["mid_s"] for c in group])),
                "strong_calibration": bool(
                    len(group) >= 3
                    and len({c["channel"] for c in group}) >= 2
                    and np.ptp([c["mid_s"] for c in group]) >= 60
                    and max(sigma_at) < 300
                ),
                "core_observations": sum(len(c["t"]) for c in group),
            }
        )
    return {
        "source_id": cores[0]["source_id"],
        "family": family,
        "observations": n,
        "parameters": k,
        "calibration_parameters": n_beta,
        "rms_hz": float(np.sqrt(rss / n)),
        "penalized_score": float(score),
        "data_normal_rank": int(np.linalg.matrix_rank(normal)),
        "groups": results,
        "core_diagnostics": [
            {
                "left_key": c["left_key"],
                "right_key": c["right_key"],
                "degree": p[1],
                "rms_hz": float(np.sqrt(np.mean(p[4] ** 2))),
                "max_absolute_hz": float(np.max(np.abs(p[4]))),
            }
            for c, p in zip(cores, profiles, strict=True)
        ],
    }


def correction(track, calibration, times):
    if track["receiver"] == 1:
        return np.zeros_like(np.asarray(times), dtype=float)
    return calibration["offset_at_150s_hz"] + calibration["relative_drift_hz_s"] * (
        np.asarray(times) - 150
    )


def endpoint(track, time):
    """Bounded gap proposal evaluation; not used for residual scoring."""
    piece = min(
        track["pieces"], key=lambda p: min(abs(time - p["start_s"]), abs(time - p["end_s"]))
    )
    x = (time - piece["reference_time_s"]) / piece["time_scale_s"]
    value = leg.legval(x, piece["coefficients_hz"])
    slope = leg.legval(x, leg.legder(piece["coefficients_hz"])) / piece["time_scale_s"]
    return float(value), float(slope)


def proposal_edges(tracks, calibration):
    groups = defaultdict(list)
    for track in tracks:
        groups[track["source_id"], track["channel"]].append(track)
    edges = []
    for (source, _), group in groups.items():
        for left in [t for t in group if t["receiver"] == 1]:
            for right in [t for t in group if t["receiver"] == 2]:
                cal = calibration.get((source, left["bank"]))
                if cal is None or not cal["strong_calibration"]:
                    continue
                lo = max(left["start_s"], right["start_s"])
                hi = min(left["end_s"], right["end_s"])
                gap = max(0.0, lo - hi)
                if gap > MAX_GAP:
                    continue
                mid = (lo + hi) / 2
                if hi > lo:
                    times = np.linspace(lo, hi, 33)
                    delta = wrap(
                        predict(right, times) - correction(right, cal, times) - predict(left, times)
                    )
                    if not np.isfinite(delta).all() or np.sqrt(np.mean(delta**2)) > 900:
                        continue
                else:
                    a, sa = endpoint(left, mid)
                    b, sb = endpoint(right, mid)
                    b -= float(correction(right, cal, mid))
                    sb -= cal["relative_drift_hz_s"]
                    if abs(wrap(b - a)) > 600 + 100 * gap or abs(sb - sa) > 250:
                        continue
                a, _ = endpoint(left, mid)
                b, _ = endpoint(right, mid)
                lift = int(round((a - b + float(correction(right, cal, mid))) / PERIOD))
                edges.append(
                    {
                        "left_key": left["key"],
                        "right_key": right["key"],
                        "kind": "overlap" if hi > lo else "sequential",
                        "gap_s": gap,
                        "connection_s": mid,
                        "right_minus_left_lift": lift,
                    }
                )
    return edges


def group_arrays(members, mapping, calibration):
    times, values, receivers, identities, keys = [], [], [], [], []
    for key, lift in members.items():
        track = mapping[key]
        cal = calibration[track["source_id"], track["bank"]]
        times.extend(track["times"])
        values.extend(track["values"] + lift * PERIOD - correction(track, cal, track["times"]))
        receivers.extend([track["receiver"]] * len(track["times"]))
        identities.extend(track["observation_ids"])
        keys.extend([key] * len(track["times"]))
    order = np.argsort(times, kind="stable")
    return {
        "t": np.array(times)[order],
        "y": np.array(values)[order],
        "rx": np.array(receivers)[order],
        "ids": np.array(identities)[order],
        "keys": np.array(keys)[order],
    }


def noise_diagnostic(times, residual):
    d = full_residual_diagnostics(times, residual, SIGMA)
    x = times - np.mean(times)
    linear_z = float(abs(np.dot(x, residual)) / (SIGMA * max(1e-9, np.linalg.norm(x))))
    d["linear_component_z"] = linear_z
    if linear_z > 3.5:
        d["flags"].append("linear_residual_component")
        d["status"] = "structure_flagged"
    return d


def fit_group(members, mapping, calibration):
    a = group_arrays(members, mapping, calibration)
    t, y = a["t"], a["y"]
    if len(set(a["ids"])) != len(t) or np.max(np.diff(t)) > MAX_GAP:
        return None, "gap_or_duplicate"
    ref, scale = float((t.min() + t.max()) / 2), max(1.0, np.ptp(t) / 2)
    x = (t - ref) / scale
    choices = []
    for degree in range(5):
        if len(t) < 2 * (degree + 1):
            continue
        coeff = leg.legfit(x, y, degree)
        residual = y - leg.legval(x, coeff)
        cost = float(np.dot(residual, residual) / SIGMA**2 + (degree + 1) * np.log(len(t)) + 18)
        choices.append((cost, degree, coeff, residual))
    cost, degree, coeff, residual = min(choices, key=lambda c: c[0])
    if np.max(np.abs(residual)) >= GATE:
        return None, "point_gate"
    derivative = leg.legder(coeff)
    extrema = leg.legroots(leg.legder(derivative)) if degree > 1 else np.array([])
    extrema = np.real(extrema[np.isreal(extrema)])
    extrema = np.r_[-1.0, 1.0, extrema[(extrema >= -1) & (extrema <= 1)]]
    if np.max(np.abs(leg.legval(extrema, derivative))) / scale > MAX_SLOPE:
        return None, "slope_gate"
    diagnostics = {"all": noise_diagnostic(t, residual)}
    for rx in (1, 2):
        mask = a["rx"] == rx
        diagnostics[f"rx{rx}"] = noise_diagnostic(t[mask], residual[mask])
    if any(d["flags"] for d in diagnostics.values()):
        return None, "residual_structure"
    old_cost = 0.0
    for key in members:
        track = mapping[key]
        original_residual = track["values"] - predict(track, track["times"])
        old_cost += np.dot(original_residual, original_residual) / SIGMA**2 + 18
        old_cost += sum((p["degree"] + 1) * np.log(len(p["indices"])) for p in track["pieces"])
        old_cost += 10 * (len(track["pieces"]) - 1)
    gain = float(old_cost - cost)
    if gain <= 0:
        return None, "complexity_cost"
    return {
        "members": members,
        "degree": degree,
        "coefficients_hz": coeff.tolist(),
        "reference_time_s": ref,
        "time_scale_s": scale,
        "start_s": float(t.min()),
        "end_s": float(t.max()),
        "points": len(t),
        "rms_hz": float(np.sqrt(np.mean(residual**2))),
        "max_absolute_residual_hz": float(np.max(np.abs(residual))),
        "diagnostics": diagnostics,
        "gain": gain,
        "cost": cost,
        "fully_supported": all(
            d["status"] == "no_structure_detected" for d in diagnostics.values()
        ),
    }, "accepted"


def stitch(tracks, calibration):
    mapping = {t["key"]: t for t in tracks}
    edges = proposal_edges(tracks, calibration)
    rejected, viable = Counter(), []
    for edge in edges:
        members = {edge["left_key"]: 0, edge["right_key"]: edge["right_minus_left_lift"]}
        fit, reason = fit_group(members, mapping, calibration)
        if fit is None:
            rejected[reason] += 1
        else:
            viable.append((fit["gain"], edge))
    owners = {key: key for key in mapping}
    groups = {key: {key: 0} for key in mapping}
    fits, accepted = {}, []
    for _, edge in sorted(viable, key=lambda v: -v[0]):
        left_owner, right_owner = owners[edge["left_key"]], owners[edge["right_key"]]
        if left_owner == right_owner:
            continue
        left, right = groups[left_owner], groups[right_owner]
        difference = (
            left[edge["left_key"]] + edge["right_minus_left_lift"] - right[edge["right_key"]]
        )
        members = {**left, **{key: lift + difference for key, lift in right.items()}}
        fit, reason = fit_group(members, mapping, calibration)
        if fit is None:
            rejected[f"component_{reason}"] += 1
            continue
        incremental = fit["cost"]
        for owner in (left_owner, right_owner):
            if owner in fits:
                incremental -= fits[owner]["cost"]
            else:
                key = next(iter(groups[owner]))
                track = mapping[key]
                rr = track["values"] - predict(track, track["times"])
                incremental -= (
                    np.dot(rr, rr) / SIGMA**2
                    + 18
                    + sum((p["degree"] + 1) * np.log(len(p["indices"])) for p in track["pieces"])
                    + 10 * (len(track["pieces"]) - 1)
                )
        if incremental >= 0:
            rejected["component_complexity_cost"] += 1
            continue
        groups[left_owner] = members
        del groups[right_owner]
        fits[left_owner] = fit
        fits.pop(right_owner, None)
        for key in members:
            owners[key] = left_owner
        accepted.append(
            {**edge, "component_size": len(members), "incremental_gain": float(-incremental)}
        )
    assert len(groups) + len(accepted) == len(tracks)
    assert sum(len(mapping[k]["times"]) for group in groups.values() for k in group) == sum(
        len(t["times"]) for t in tracks
    )
    return {
        "input_tracks": len(tracks),
        "output_tracks": len(groups),
        "associated_points": sum(len(t["times"]) for t in tracks),
        "proposal_edges": len(edges),
        "pairwise_viable_edges": len(viable),
        "accepted_edges": accepted,
        "rejections": dict(rejected),
        "merged_groups": list(fits.values()),
        "ownership": owners,
    }


def draw_results(tracks, calibration, result, models, output):
    mapping = {t["key"]: t for t in tracks}
    fig, axes = plt.subplots(5, 2, figsize=(15, 16), constrained_layout=True)
    for row, source in enumerate(f"S{i:02}" for i in range(1, 6)):
        model = next(m for m in models if m["source_id"] == source and m["selected"])
        for col, band in enumerate(BANDS):
            ax = axes[row, col]
            cal = calibration.get((source, band))
            if cal is None:
                ax.text(0.5, 0.5, "No overlap calibration", transform=ax.transAxes, ha="center")
            else:
                anchors = [c for c in model["cores"] if c["bank"] == band]
                for c in anchors:
                    ax.plot(c["times"], c["delta"] / 1000, color="#356e9b", alpha=0.3)
                    ax.scatter(c["mid_s"], c["offset_hz"] / 1000, s=25, color="#356e9b")
                times = np.array([0.0, 300.0])
                ax.plot(
                    times,
                    (cal["offset_at_150s_hz"] + cal["relative_drift_hz_s"] * (times - 150)) / 1000,
                    color="#bd493c",
                )
                ax.set_title(
                    f"{source} {band} · Δ150={cal['offset_at_150s_hz'] / 1000:+.3f} kHz · "
                    f"{cal['relative_drift_hz_s']:+.2f} Hz/s\n"
                    f"{cal['anchors']} anchors · "
                    f"{'supported' if cal['strong_calibration'] else 'weak; no stitching'}"
                )
            ax.set(xlabel="Seconds into scan", ylabel="RX2 − RX1 (kHz)", xlim=(0, 300))
            ax.grid(alpha=0.2)
    fig.suptitle(
        "One relative calibration per scan and band · fitted to original GLRT points\n"
        "Blue: frozen-curve anchor differences; red: selected shared receiver calibration"
    )
    save_plot(fig, output, "scan-band-calibration")
    examples = []
    for kind in ("sequential", "overlap"):
        choices = []
        for group in result["merged_groups"]:
            keys = set(group["members"])
            relevant = [
                e
                for e in result["accepted_edges"]
                if e["kind"] == kind and e["left_key"] in keys and e["right_key"] in keys
            ]
            if relevant:
                choices.append(
                    (
                        group["fully_supported"],
                        len(keys),
                        group["points"],
                        group,
                        max(relevant, key=lambda e: e["gap_s"]),
                    )
                )
        if choices:
            examples.append(max(choices, key=lambda c: c[:3])[3:])
    if examples:
        fig, axes = plt.subplots(
            len(examples),
            3,
            figsize=(17, 5 * len(examples)),
            squeeze=False,
            constrained_layout=True,
        )
        for row, (group, edge) in enumerate(examples):
            arrays = group_arrays(group["members"], mapping, calibration)
            pred = leg.legval(
                (arrays["t"] - group["reference_time_s"]) / group["time_scale_s"],
                group["coefficients_hz"],
            )
            first = mapping[next(iter(group["members"]))]
            for rx, color in ((1, "#306c9c"), (2, "#d58332")):
                mask = arrays["rx"] == rx
                times, values = arrays["t"][mask], arrays["y"][mask]
                cal = calibration[first["source_id"], first["bank"]]
                before = values + (
                    cal["offset_at_150s_hz"] + cal["relative_drift_hz_s"] * (times - 150)
                    if rx == 2
                    else 0
                )
                axes[row, 0].scatter(times, before / 1000, color=color, label=f"RX{rx}", s=17)
                axes[row, 1].scatter(times, values / 1000, color=color, label=f"RX{rx}", s=17)
                axes[row, 2].scatter(times, values - pred[mask], color=color, label=f"RX{rx}", s=17)
            times = np.linspace(arrays["t"].min(), arrays["t"].max(), 300)
            curve = leg.legval(
                (times - group["reference_time_s"]) / group["time_scale_s"],
                group["coefficients_hz"],
            )
            axes[row, 1].plot(times, curve / 1000, color="#494949", lw=1)
            axes[row, 2].axhline(0, color="#555555", lw=0.8)
            axes[row, 2].axhline(GATE, color="#555555", linestyle="--", lw=0.6)
            axes[row, 2].axhline(-GATE, color="#555555", linestyle="--", lw=0.6)
            title = (
                f"{first['source_id']} CH{first['channel']} · {edge['kind']} · "
                f"{len(group['members'])} fragments · "
                f"{'fully supported' if group['fully_supported'] else 'provisional'}"
            )
            for col, name in enumerate(
                (
                    "Before RX correction",
                    "Corrected + shared polynomial",
                    f"Original-point residuals · RMS {group['rms_hz']:.0f} Hz",
                )
            ):
                axes[row, col].set(
                    title=f"{title}\n{name}",
                    xlabel="Seconds into scan",
                    ylabel="Residual (Hz)" if col == 2 else "Lifted CFO (kHz)",
                )
                axes[row, col].grid(alpha=0.2)
                axes[row, col].legend()
        fig.suptitle(
            "Graph receiver stitching · all original member points retained\n"
            "Calibration is shared across the scan/band; no offset is fitted per join"
        )
        save_plot(fig, output, "stitching-examples")
    return [{"members": list(g["members"]), "edge": e} for g, e in examples]


def save_plot(fig, output, name):
    for extension in ("png", "pdf"):
        fig.savefig(output / f"{name}.{extension}", dpi=140, bbox_inches="tight")
    plt.close(fig)


def export_components(tracks, calibration, result, output):
    mapping = {t["key"]: t for t in tracks}
    fit_by_owner = {
        result["ownership"][next(iter(g["members"]))]: g for g in result["merged_groups"]
    }
    rows, components = [], []
    for owner in sorted(set(result["ownership"].values())):
        fit = fit_by_owner.get(owner)
        keys = sorted(k for k, value in result["ownership"].items() if value == owner)
        first = mapping[keys[0]]
        components.append(
            {
                "source_id": first["source_id"],
                "channel": first["channel"],
                "component": owner,
                "input_fragments": len(keys),
                "points": sum(len(mapping[k]["times"]) for k in keys),
                "merged": fit is not None,
                "quality": (
                    "no_structure_detected" if fit["fully_supported"] else "insufficient_support"
                )
                if fit
                else first["quality_status"],
            }
        )
        for key in keys:
            track = mapping[key]
            cal = calibration.get((track["source_id"], track["bank"]))
            delta = correction(track, cal, track["times"]) if cal else np.zeros(len(track["times"]))
            lift = fit["members"][key] if fit else 0
            corrected = track["values"] + lift * PERIOD - delta
            residual = track["values"] - predict(track, track["times"])
            if fit:
                residual = corrected - leg.legval(
                    (track["times"] - fit["reference_time_s"]) / fit["time_scale_s"],
                    fit["coefficients_hz"],
                )
            for i, oid in enumerate(track["observation_ids"]):
                rows.append(
                    {
                        "source_id": track["source_id"],
                        "receiver": track["receiver"],
                        "channel": track["channel"],
                        "observation_id": oid,
                        "time_s": track["times"][i],
                        "original_track": key,
                        "component": owner,
                        "additional_alias_lift": lift,
                        "calibration_available": cal is not None,
                        "calibration_supported": bool(cal and cal["strong_calibration"]),
                        "relative_rx_correction_hz": float(delta[i]),
                        "original_lifted_cfo_hz": track["values"][i],
                        "corrected_lifted_cfo_hz": float(corrected[i]),
                        "residual_hz": float(residual[i]),
                        "merged": fit is not None,
                    }
                )
    assert len(rows) == len({r["observation_id"] for r in rows}) == 18338
    assert len(components) == result["output_tracks"]
    write_csv(output / "fused-observations.csv", rows)
    write_csv(output / "components.csv", components)
    return rows


def scan_gallery(tracks, calibration, result, output):
    mapping = {t["key"]: t for t in tracks}
    for source in (f"S{i:02}" for i in range(1, 6)):
        fig, axes = plt.subplots(8, 3, figsize=(18, 22), constrained_layout=True)
        source_tracks = [t for t in tracks if t["source_id"] == source]
        for row, channel in enumerate(range(1, 9)):
            for track in [t for t in source_tracks if t["channel"] == channel]:
                color = "#306c9c" if track["receiver"] == 1 else "#d58332"
                cal = calibration.get((source, track["bank"]))
                valid = cal is not None and cal["strong_calibration"]
                delta = correction(track, cal, track["times"]) if valid else 0
                axes[row, 0].scatter(
                    track["times"], wrap(track["values"]) / 1000, color=color, s=6, alpha=0.7
                )
                axes[row, 1].scatter(
                    track["times"],
                    wrap(track["values"] - delta) / 1000,
                    color=color if valid else "#aaaaaa",
                    s=6,
                    alpha=0.7,
                )
            groups = [
                g
                for g in result["merged_groups"]
                if mapping[next(iter(g["members"]))]["source_id"] == source
                and mapping[next(iter(g["members"]))]["channel"] == channel
            ]
            for group in groups:
                a = group_arrays(group["members"], mapping, calibration)
                predicted = leg.legval(
                    (a["t"] - group["reference_time_s"]) / group["time_scale_s"],
                    group["coefficients_hz"],
                )
                times = np.linspace(group["start_s"], group["end_s"], 200)
                curve = (
                    wrap(
                        leg.legval(
                            (times - group["reference_time_s"]) / group["time_scale_s"],
                            group["coefficients_hz"],
                        )
                    )
                    / 1000
                )
                curve[np.r_[False, abs(np.diff(curve)) > PERIOD / 2000]] = np.nan
                axes[row, 1].plot(times, curve, color="#262626", lw=0.7)
                for rx, color in ((1, "#306c9c"), (2, "#d58332")):
                    m = a["rx"] == rx
                    axes[row, 2].scatter(
                        a["t"][m], a["y"][m] - predicted[m], color=color, s=9, alpha=0.8
                    )
            for col in (0, 1):
                axes[row, col].set_ylim(-PERIOD / 2000, PERIOD / 2000)
            axes[row, 2].set_ylim(-500, 500)
            axes[row, 2].axhline(0, color="#777777", lw=0.6)
            for col in range(3):
                axes[row, col].set(
                    xlim=(0, 300),
                    xlabel="Scan time (s)",
                    ylabel=f"CH{channel} · " + ("residual Hz" if col == 2 else "CFO kHz"),
                )
                axes[row, col].grid(alpha=0.2)
            if not groups:
                axes[row, 2].text(
                    0.5,
                    0.5,
                    "No accepted join",
                    transform=axes[row, 2].transAxes,
                    ha="center",
                    color="#777777",
                )
        for col, title in enumerate(
            (
                "Original associated GLRT",
                "RX2 calibrated · shared curves",
                "Original-point residuals of joined groups",
            )
        ):
            axes[0, col].set_title(title)
        fig.suptitle(
            f"{source} · all eight channels · Graph tracklets\n"
            "Blue RX1 / orange RX2; gray = weak or absent calibration; "
            "CFO wrapped at the pilot alias; 1,746 dataset-wide unassociated points unchanged"
        )
        save_plot(fig, output, f"{source}-all-channels")


def sequential_calibration_hypotheses(tracks, primary_calibration, output):
    """Explore missing/weak bands without promoting extrapolated joins to truth."""
    mapping = {t["key"]: t for t in tracks}
    grouped = defaultdict(list)
    for left in tracks:
        if left["receiver"] != 1:
            continue
        source, band = left["source_id"], left["bank"]
        if primary_calibration.get((source, band), {}).get("strong_calibration", False):
            continue
        for right in tracks:
            if (right["source_id"], right["receiver"], right["channel"]) != (
                source,
                2,
                left["channel"],
            ):
                continue
            lo = max(left["start_s"], right["start_s"])
            hi = min(left["end_s"], right["end_s"])
            gap = lo - hi
            if not 0 < gap <= MAX_GAP:
                continue
            mid = (lo + hi) / 2
            va, sa = endpoint(left, mid)
            vb, sb = endpoint(right, mid)
            if abs(sb - sa) > 250:
                continue
            grouped[source, band].append(
                {
                    "source_id": source,
                    "bank": band,
                    "channel": left["channel"],
                    "left_key": left["key"],
                    "right_key": right["key"],
                    "mid_s": mid,
                    "gap_s": gap,
                    "offset_hz": float(wrap(vb - va)),
                    "shape_rms_hz": 0.0,
                    "overlap_s": -gap,
                    "endpoint_slope_difference_hz_s": sb - sa,
                }
            )
    all_candidates = [p for group in grouped.values() for p in group]
    if all_candidates:
        write_csv(output / "sequential-offset-candidates.csv", all_candidates)
    reports = []
    for (source, band), group in sorted(grouped.items()):
        selected = modal_pairs(group)
        if len(selected) < 3 or len({p["channel"] for p in selected}) < 2:
            continue
        cores, lifts = [], {}
        for pair in selected:
            left, right = mapping[pair["left_key"]], mapping[pair["right_key"]]
            mid = pair["mid_s"]
            va, _ = endpoint(left, mid)
            vb, _ = endpoint(right, mid)
            lift = int(round((va + pair["offset_hz"] - vb) / PERIOD))
            lifts[right["key"]] = lift
            t = np.r_[left["times"], right["times"]]
            y = np.r_[left["values"], right["values"] + lift * PERIOD]
            rx = np.r_[np.ones(len(left["times"]), int), np.full(len(right["times"]), 2)]
            ref, scale = (t.min() + t.max()) / 2, max(1.0, np.ptp(t) / 2)
            cores.append(
                {
                    **pair,
                    "t": t,
                    "y": y,
                    "rx": rx,
                    "x": (t - ref) / scale,
                    "reference_time_s": ref,
                    "time_scale_s": scale,
                }
            )
        models = [fit_calibration(cores, family) for family in ("constant", "band_drift")]
        chosen = min(models, key=lambda m: m["penalized_score"])
        cal = chosen["groups"][0]
        cal_map = {(source, band): cal}
        checks = []
        fig, axes = plt.subplots(
            len(cores), 2, figsize=(13, 4 * len(cores)), constrained_layout=True, squeeze=False
        )
        for row, core in enumerate(cores):
            members = {core["left_key"]: 0, core["right_key"]: lifts[core["right_key"]]}
            fit, reason = fit_group(members, mapping, cal_map)
            checks.append(
                {
                    "left_key": core["left_key"],
                    "right_key": core["right_key"],
                    "gap_s": core["gap_s"],
                    "joint_fit_gate": reason,
                    "fully_supported": bool(fit and fit["fully_supported"]),
                }
            )
            z = (core["rx"] == 2) * (
                cal["offset_at_150s_hz"] + cal["relative_drift_hz_s"] * (core["t"] - 150)
            )
            beta = np.array([cal["offset_at_150s_hz"], cal["relative_drift_hz_s"] * 150])
            design = calibration_design(core, [band], "band_drift")
            profile = profile_core(core, design, beta, np.ones(len(core["t"])))
            for rx, color in ((1, "#306c9c"), (2, "#d58332")):
                mask = core["rx"] == rx
                axes[row, 0].scatter(
                    core["t"][mask],
                    (core["y"] - z)[mask] / 1000,
                    color=color,
                    s=16,
                    label=f"RX{rx}",
                )
                axes[row, 1].scatter(core["t"][mask], profile[4][mask], color=color, s=16)
            t = np.linspace(core["t"].min(), core["t"].max(), 200)
            curve = leg.legval((t - core["reference_time_s"]) / core["time_scale_s"], profile[3])
            axes[row, 0].plot(t, curve / 1000, color="#555555", lw=1)
            axes[row, 0].set(
                title=f"CH{core['channel']} · gap {core['gap_s']:.2f}s · {reason}",
                xlabel="Scan time (s)",
                ylabel="Corrected CFO (kHz)",
            )
            axes[row, 0].legend()
            axes[row, 1].axhline(0, color="#777777", lw=0.6)
            axes[row, 1].axhspan(-450, 450, color="#6aac78", alpha=0.1)
            axes[row, 1].set(
                title="Original-point residuals", xlabel="Scan time (s)", ylabel="Residual Hz"
            )
            for ax in axes[row]:
                ax.grid(alpha=0.2)
        fig.suptitle(
            f"{source} {band} · sequential-only calibration hypothesis\n"
            "Exploratory curve-continuation assumption; excluded from primary results"
        )
        save_plot(fig, output, f"{source}-sequential-calibration-hypothesis")
        reports.append(
            {
                "source_id": source,
                "bank": band,
                "selected_model": chosen,
                "checks": checks,
                "used_in_primary_stitching": False,
            }
        )
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    source_paths = [
        Path(__file__),
        ROOT / "tools/compare_dsx01_graph_receivers.py",
        ROOT / "tools/tune_full_data_tracklets.py",
    ]
    source_hashes = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths
    }
    tracks, hashes = load_tracks()
    mapping = {t["key"]: t for t in tracks}
    anchors = seed_anchors(tracks)
    cores = core_data(anchors, mapping)
    models, selected_calibration = [], {}
    for source in sorted({c["source_id"] for c in cores}):
        subset = [c for c in cores if c["source_id"] == source]
        fits = [
            fit_calibration(subset, family) for family in ("constant", "shared_drift", "band_drift")
        ]
        selected = min(fits, key=lambda f: f["penalized_score"])
        for fit in fits:
            fit["selected"] = fit is selected
            fit["cores"] = [c for c in anchors if c["source_id"] == source]
        models.extend(fits)
        selected_calibration.update({(source, g["bank"]): g for g in selected["groups"]})
    result = stitch(tracks, selected_calibration)
    per_scan = []
    for source in (f"S{i:02}" for i in range(1, 6)):
        original = [t for t in tracks if t["source_id"] == source]
        merged = [
            g
            for g in result["merged_groups"]
            if mapping[next(iter(g["members"]))]["source_id"] == source
        ]
        edges = [
            e for e in result["accepted_edges"] if mapping[e["left_key"]]["source_id"] == source
        ]
        per_scan.append(
            {
                "source_id": source,
                "input_tracks": len(original),
                "output_tracks": len(original) - len(edges),
                "associated_points": sum(len(t["times"]) for t in original),
                "overlap_links": sum(e["kind"] == "overlap" for e in edges),
                "sequential_links": sum(e["kind"] == "sequential" for e in edges),
                "merged_groups": len(merged),
                "fully_supported_merged_groups": sum(g["fully_supported"] for g in merged),
                "merged_points": sum(g["points"] for g in merged),
            }
        )
    controls = []
    for shift in (57, 113, 179):
        shifted = shifted_receivers(tracks, shift_s=shift)
        # Circular shift can split a track: give each retained segment a distinct key.
        counts = Counter()
        for track in shifted:
            if track["receiver"] == 2:
                original_key = track["key"]
                counts[original_key] += 1
                track["key"] = f"{original_key}-C{counts[original_key]}"
        null = stitch(shifted, selected_calibration)
        controls.append(
            {
                "control": f"fixed calibration; RX2 circular shift {shift}s",
                "input_tracks": null["input_tracks"],
                "output_tracks": null["output_tracks"],
                "overlap_links": sum(e["kind"] == "overlap" for e in null["accepted_edges"]),
                "sequential_links": sum(e["kind"] == "sequential" for e in null["accepted_edges"]),
                "fully_supported_merged_groups": sum(
                    g["fully_supported"] for g in null["merged_groups"]
                ),
            }
        )
    write_csv(
        output / "calibration-models.csv",
        [{k: v for k, v in m.items() if not isinstance(v, (list, dict))} for m in models],
    )
    write_csv(output / "scan-band-calibration.csv", list(selected_calibration.values()))
    write_csv(output / "per-scan-stitching.csv", per_scan)
    if result["accepted_edges"]:
        write_csv(output / "accepted-links.csv", result["accepted_edges"])
    write_csv(output / "temporal-controls.csv", controls)
    examples = draw_results(tracks, selected_calibration, result, models, output)
    export_components(tracks, selected_calibration, result, output)
    scan_gallery(tracks, selected_calibration, result, output)
    sequential_hypotheses = sequential_calibration_hypotheses(tracks, selected_calibration, output)
    for name, expected in hashes.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    for name, expected in source_hashes.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    report = {
        "model": "y=shared_curve(t)+receiver_band_offset+receiver_band_drift*(t-150)+noise",
        "gauge": "RX1 offset/drift zero independently per band; all calibration relative RX2-RX1",
        "previous_analysis": str(PREVIOUS.relative_to(ROOT)),
        "input_sha256": hashes,
        "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_sha256": source_hashes,
        "noise_sigma_hz": SIGMA,
        "point_gate_hz": GATE,
        "maximum_gap_s": MAX_GAP,
        "drift_prior_sigma_hz_s": DRIFT_SIGMA,
        "anchors": len(anchors),
        "core_observations": sum(len(c["t"]) for c in cores),
        "models": [{k: v for k, v in m.items() if k != "cores"} for m in models],
        "selected_calibration": list(selected_calibration.values()),
        "stitching": result,
        "per_scan": per_scan,
        "controls": controls,
        "examples": examples,
        "sequential_calibration_hypotheses": sequential_hypotheses,
        "limitations": (
            "Selected in-sample matches; descriptive diagnostics; alias branches and identities "
            "not independently validated. Short receiver supports are provisional. "
            "No final production merger or localization result."
        ),
    }
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "calibration": list(selected_calibration.values()),
                "per_scan": per_scan,
                "rejections": result["rejections"],
                "controls": controls,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
