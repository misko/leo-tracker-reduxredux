"""Bounded, exploratory any-RX/channel fusion on frozen DSX01 Graph tracklets."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from compare_dsx01_graph_receivers import PERIOD, ROOT, load_tracks, predict, wrap, write_csv
from model_dsx01_receiver_tracklets import endpoint, noise_diagnostic, seed_anchors
from numpy.polynomial import legendre as leg

OUTPUT = ROOT / "reports/2026_10_17_dsx01_multilane_prototype"
REFERENCE_RF = 11.5e9
SIGMA = 150.0
GATE = 450.0
MAX_GAP = 10.0
BRANCHES = tuple(range(-2, 3))
DRIFT_BOUND = 20.0
GROUP_LABELS = ("RX1 low", "RX1 high", "RX2 low", "RX2 high")


def group(track):
    return 2 * (track["receiver"] - 1) + int(track["bank"] == "CH5-8")


def ratio(track, scaled):
    return track["rf_hz"] / REFERENCE_RF if scaled else 1.0


def nuisance(track, time, beta):
    g = group(track)
    return beta[g] + beta[g + 4] * (np.asarray(time) - 150) / 150


def shared_value(track, time, beta, scaled, lift=0):
    value, slope = endpoint(track, time)
    q = ratio(track, scaled)
    return (
        (value + lift * PERIOD - nuisance(track, time, beta)) / q,
        (slope - beta[group(track) + 4] / 150) / q,
    )


def overlap_pair(left, right, scaled):
    lo, hi = max(left["start_s"], right["start_s"]), min(left["end_s"], right["end_s"])
    if hi - lo < 8:
        return None
    masks = [(t["times"] >= lo) & (t["times"] <= hi) for t in (left, right)]
    if min(m.sum() for m in masks) < 4:
        return None
    t = np.linspace(lo, hi, 33)
    qa, qb = ratio(left, scaled), ratio(right, scaled)
    d = predict(right, t) / qb - predict(left, t) / qa
    if not np.isfinite(d).all():
        return None
    k = min(BRANCHES, key=lambda k: abs(np.mean(d) + k * PERIOD / qb))
    d += k * PERIOD / qb
    return {
        "left_key": left["key"],
        "right_key": right["key"],
        "source_id": left["source_id"],
        "start_s": lo,
        "end_s": hi,
        "mid_s": (lo + hi) / 2,
        "overlap_s": hi - lo,
        "offset_hz": float(np.mean(d)),
        "shape_rms_hz": float(np.std(d)),
        "left_lift": 0,
        "right_lift": k,
        "group_edge": tuple(sorted((group(left), group(right)))),
        "cross_band": left["bank"] != right["bank"],
    }


def calibration_anchors(tracks, scaled):
    """Strong historical RX anchors plus disjoint cross-channel modal anchors."""
    mapping = {t["key"]: t for t in tracks}
    forced = seed_anchors(tracks)
    kept, used = [], set()
    for old in forced:
        pair = overlap_pair(mapping[old["left_key"]], mapping[old["right_key"]], scaled)
        if pair:
            kept.append(pair)
            used.update((pair["left_key"], pair["right_key"]))
    by_edge = defaultdict(list)
    for a, b in combinations(tracks, 2):
        if a["source_id"] != b["source_id"] or (a["receiver"], a["channel"]) == (
            b["receiver"],
            b["channel"],
        ):
            continue
        if a["key"] in used or b["key"] in used:
            continue
        pair = overlap_pair(a, b, scaled)
        if pair and pair["shape_rms_hz"] <= 300:
            by_edge[pair["source_id"], pair["group_edge"]].append(pair)
    proposals = []
    for (_, edge), pairs in by_edge.items():
        if edge[0] == edge[1]:
            cluster = [p for p in pairs if abs(p["offset_hz"]) <= 6000]
        else:
            seed = max(
                pairs,
                key=lambda p: (
                    sum(abs(q["offset_hz"] - p["offset_hz"]) <= 4000 for q in pairs),
                    p["overlap_s"],
                ),
            )
            cluster = [p for p in pairs if abs(p["offset_hz"] - seed["offset_hz"]) <= 4000]
        proposals.extend(cluster)
    for pair in sorted(
        proposals, key=lambda p: (not p["cross_band"], p["shape_rms_hz"], -p["overlap_s"])
    ):
        if pair["left_key"] not in used and pair["right_key"] not in used:
            kept.append(pair)
            used.update((pair["left_key"], pair["right_key"]))
    return kept


def core_arrays(pair, mapping, scaled):
    times, values, qs, gs = [], [], [], []
    for side in ("left", "right"):
        track = mapping[pair[f"{side}_key"]]
        m = (track["times"] >= pair["start_s"]) & (track["times"] <= pair["end_s"])
        times.extend(track["times"][m])
        values.extend(track["values"][m] + pair[f"{side}_lift"] * PERIOD)
        qs.extend([ratio(track, scaled)] * int(m.sum()))
        gs.extend([group(track)] * int(m.sum()))
    t, y, q, g = np.array(times), np.array(values), np.array(qs), np.array(gs)
    x = (t - (t.min() + t.max()) / 2) / max(1.0, np.ptp(t) / 2)
    z = np.column_stack(
        [g == j for j in range(4)] + [(g == j) * (t - 150) / 150 for j in range(4)]
    ).astype(float)
    return t, y, q, g, x, z


def best_local(y, q, x, z, beta, weights):
    choices = []
    root = np.sqrt(weights)
    for degree in range(5):
        if len(y) < 2 * (degree + 1):
            continue
        design = q[:, None] * leg.legvander(x, degree)
        coeff = np.linalg.lstsq(design * root[:, None], (y - z @ beta) * root, rcond=None)[0]
        residual = y - z @ beta - design @ coeff
        cost = float(np.dot(weights, residual**2) / SIGMA**2 + (degree + 1) * np.log(len(y)))
        choices.append((cost, degree, design, coeff, residual))
    return min(choices, key=lambda c: c[0])


def fit_calibration(tracks, anchors, scaled):
    mapping = {t["key"]: t for t in tracks}
    beta = np.zeros(8)
    # Historical relative fits initialize the optimizer; all final offsets are joint fits.
    previous = json.loads(
        (ROOT / "reports/2026_10_17_dsx01_receiver_model/results.json").read_text()
    )
    source = tracks[0]["source_id"]
    relative_priors = []
    for c in previous["selected_calibration"]:
        if c["source_id"] == source:
            g = 2 + int(c["bank"] == "CH5-8")
            beta[g] = c["offset_at_150s_hz"]
            beta[g + 4] = c["relative_drift_hz_s"] * 150
            band = g - 2
            constraints = [
                (0, c["offset_at_150s_hz"], 300.0 if c["strong_calibration"] else 1000.0)
            ]
            if c["strong_calibration"]:
                constraints.append((4, c["relative_drift_hz_s"] * 150, 2 * 150.0))
            for index, target, sigma in constraints:
                vector = np.zeros(8)
                vector[g + index], vector[band + index] = 1.0, -1.0
                relative_priors.append((vector, target, sigma))
    band_pairs = [p for p in anchors if p["group_edge"] == (0, 1)]
    if band_pairs:
        beta[1] = np.median(
            [p["offset_hz"] * ratio(mapping[p["right_key"]], scaled) for p in band_pairs]
        )
        beta[3] += beta[1]
    # Initialize previously weak RX2 bands from cross-channel within-band consensus.
    for ga, gb in ((0, 2), (1, 3)):
        candidates = [p for p in anchors if p["group_edge"] == (ga, gb)]
        if candidates:
            beta[gb] = np.median(
                [
                    ratio(mapping[p["right_key"]], scaled)
                    * (p["offset_hz"] + beta[ga] / ratio(mapping[p["left_key"]], scaled))
                    for p in candidates
                ]
            )
    free = np.arange(8) if scaled else np.array([1, 2, 3, 5, 6, 7])
    prior = np.r_[np.full(4, 1 / 100000.0**2), np.full(4, 1 / (10 * 150.0) ** 2)]
    normal = np.zeros((len(free), len(free)))
    proposed_count = len(anchors)
    rejected_anchors = []
    for iteration in range(30):
        normal *= 0
        rhs = np.zeros(len(free))
        for pair in anchors:
            a, b = mapping[pair["left_key"]], mapping[pair["right_key"]]
            mid = pair["mid_s"]
            choices = []
            # Lifts apply in native Hz before RF normalization.
            for ka in BRANCHES if scaled else (0,):
                va, _ = shared_value(a, mid, beta, scaled, ka)
                vb, _ = endpoint(b, mid)
                kb = int(round((ratio(b, scaled) * va + nuisance(b, mid, beta) - vb) / PERIOD))
                if abs(kb) > 4:
                    continue
                trial = {**pair, "left_lift": ka, "right_lift": kb}
                arrays = core_arrays(trial, mapping, scaled)
                _, y, q, _, x, z = arrays
                local = best_local(y, q, x, z, beta, np.ones(len(y)))
                choices.append((local[0], trial, arrays, local))
            if not choices:
                continue
            _, best, arrays, local = min(choices, key=lambda c: c[0])
            pair.update(left_lift=best["left_lift"], right_lift=best["right_lift"])
            _, y, q, _, x, z = arrays
            w = np.minimum(1.0, 2.5 * SIGMA / np.maximum(abs(local[4]), 1e-9))
            if iteration >= 5:
                pair_rms = np.sqrt(np.mean(local[4] ** 2))
                w *= min(1.0, (350 / max(pair_rms, 1.0)) ** 4)
            local = best_local(y, q, x, z, beta, w)
            root = np.sqrt(w)
            wx, wy, wz = local[2] * root[:, None], y * root, z[:, free] * root[:, None]
            rz = wz - wx @ np.linalg.lstsq(wx, wz, rcond=None)[0]
            ry = wy - wx @ np.linalg.lstsq(wx, wy, rcond=None)[0]
            normal += rz.T @ rz
            rhs += rz.T @ ry
        posterior = normal + SIGMA**2 * np.diag(prior[free])
        for vector, target, sigma in relative_priors:
            v = vector[free]
            posterior += SIGMA**2 / sigma**2 * np.outer(v, v)
            rhs += SIGMA**2 / sigma**2 * v * target
        value = np.linalg.solve(posterior, rhs)
        # Coordinate descent solves the small positive quadratic under the declared box.
        for _ in range(100):
            old = value.copy()
            for j, parameter in enumerate(free):
                value[j] = (rhs[j] - posterior[j] @ value + posterior[j, j] * value[j]) / posterior[
                    j, j
                ]
                if parameter >= 4:
                    value[j] = np.clip(value[j], -DRIFT_BOUND * 150, DRIFT_BOUND * 150)
            if max(abs(value - old)) < 0.002:
                break
        change = np.max(abs(value - beta[free]))
        beta[free] = value
        if iteration == 15:
            retained = []
            for pair in anchors:
                _, y, q, _, x, z = core_arrays(pair, mapping, scaled)
                local = best_local(y, q, x, z, beta, np.ones(len(y)))
                if np.sqrt(np.mean(local[4] ** 2)) > 450 or max(abs(local[4])) > 1500:
                    rejected_anchors.append(pair)
                else:
                    retained.append(pair)
            if len(retained) >= 4:
                anchors[:] = retained
        if change < 0.02 and iteration >= 17:
            break
    # Anchor graph establishes which band/RX references are connected by data.
    parents = list(range(4))

    def find(i):
        while parents[i] != i:
            i = parents[i]
        return i

    for p in anchors:
        ga, gb = p["group_edge"]
        parents[find(gb)] = find(ga)
    counts = Counter(g for p in anchors for g in set(p["group_edge"]))
    data_cov = SIGMA**2 * np.linalg.pinv(normal)
    groups = []
    for g in range(4):
        supporting = [p for p in anchors if g in p["group_edge"]]
        channels = {
            mapping[p[f"{side}_key"]]["channel"]
            for p in supporting
            for side in ("left", "right")
            if group(mapping[p[f"{side}_key"]]) == g
        }
        time_span = float(np.ptp([p["mid_s"] for p in supporting])) if supporting else 0.0
        bound_hit = bool(abs(beta[g + 4] / 150) >= DRIFT_BOUND - 0.1)
        groups.append(
            {
                "group": g,
                "label": GROUP_LABELS[g],
                "frame": find(g),
                "anchors": counts[g],
                "offset_at_150s_hz": float(beta[g]),
                "drift_hz_s": float(beta[g + 4] / 150),
                "channels": len(channels),
                "anchor_center_span_s": time_span,
                "drift_bound_active": bound_hit,
                "calibration_supported": counts[g] >= 3
                and len(channels) >= 2
                and time_span >= 60
                and not bound_hit,
            }
        )
    rss, n, kpoly = 0.0, 0, 0
    for p in anchors:
        _, y, q, _, x, z = core_arrays(p, mapping, scaled)
        local = best_local(y, q, x, z, beta, np.ones(len(y)))
        rss += float(np.dot(local[4], local[4]))
        n += len(y)
        kpoly += local[1] + 1
    return {
        "source_id": source,
        "scaled": scaled,
        "beta": beta.tolist(),
        "groups": groups,
        "anchor_pairs": len(anchors),
        "proposed_anchor_pairs": proposed_count,
        "rejected_anchor_pairs": len(rejected_anchors),
        "core_observations": n,
        "core_rms_hz": float(np.sqrt(rss / n)),
        "data_normal_rank": int(np.linalg.matrix_rank(normal)),
        "free_calibration_parameters": len(free),
        "conditional_covariance": data_cov.tolist(),
        "polynomial_parameters": kpoly,
    }


def original_cost(track):
    r = track["values"] - predict(track, track["times"])
    k = sum(p["degree"] + 1 for p in track["pieces"])
    return float(
        np.dot(r, r) / SIGMA**2 + k * np.log(len(r)) + 18 + 10 * (len(track["pieces"]) - 1)
    )


def observation_arrays(members, mapping, beta, scaled):
    rows = []
    for key, lift in members.items():
        t = mapping[key]
        for i, time in enumerate(t["times"]):
            rows.append(
                (
                    time,
                    t["values"][i] + lift * PERIOD - nuisance(t, time, beta),
                    ratio(t, scaled),
                    t["receiver"],
                    t["channel"],
                    t["observation_ids"][i],
                    key,
                    t["values"][i],
                    lift,
                )
            )
    rows.sort(key=lambda r: r[0])
    return {
        "t": np.array([r[0] for r in rows]),
        "y": np.array([r[1] for r in rows]),
        "q": np.array([r[2] for r in rows]),
        "rx": np.array([r[3] for r in rows]),
        "ch": np.array([r[4] for r in rows]),
        "ids": [r[5] for r in rows],
        "keys": [r[6] for r in rows],
        "original_y": np.array([r[7] for r in rows]),
        "lifts": np.array([r[8] for r in rows]),
    }


def fit_union(members, mapping, beta, scaled):
    if len({mapping[k]["source_id"] for k in members}) != 1:
        raise ValueError("Cannot join different scans")
    a = observation_arrays(members, mapping, beta, scaled)
    t, y, q = a["t"], a["y"], a["q"]
    if len(set(a["ids"])) != len(t) or np.max(np.diff(t)) > MAX_GAP:
        return None, "gap_or_duplicate"
    ref, scale = float((t.min() + t.max()) / 2), max(1.0, np.ptp(t) / 2)
    x = (t - ref) / scale
    choices = []
    for d in range(5):
        if len(t) < 2 * (d + 1):
            continue
        design = q[:, None] * leg.legvander(x, d)
        coeff = np.linalg.lstsq(design, y, rcond=None)[0]
        r = y - design @ coeff
        cost = float(np.dot(r, r) / SIGMA**2 + (d + 1) * np.log(len(t)) + 18)
        choices.append((cost, d, coeff, r))
    cost, degree, coeff, residual = min(choices, key=lambda c: c[0])
    if np.max(abs(residual)) >= GATE:
        return None, "point_gate"
    derivative = leg.legder(coeff)
    roots = leg.legroots(leg.legder(derivative)) if degree > 1 else np.array([])
    roots = np.real(roots[np.isreal(roots)])
    extrema = np.r_[-1.0, 1.0, roots[(roots >= -1) & (roots <= 1)]]
    common_slopes = leg.legval(extrema, derivative) / scale
    for key in members:
        track = mapping[key]
        if max(abs(ratio(track, scaled) * common_slopes + beta[group(track) + 4] / 150)) > 8000:
            return None, "slope_gate"
    diagnostics = {"all": noise_diagnostic(t, residual)}
    # Stratification by lane prevents opposing per-channel biases from cancelling.
    lanes = sorted(set(zip(a["rx"].tolist(), a["ch"].tolist(), strict=True)))
    for rx, ch in lanes:
        m = (a["rx"] == rx) & (a["ch"] == ch)
        diagnostics[f"RX{rx}-CH{ch}"] = noise_diagnostic(t[m], residual[m])
    if any(d["flags"] for d in diagnostics.values()):
        return None, "residual_structure"
    gain = sum(original_cost(mapping[k]) for k in members) - cost
    if gain <= 0:
        return None, "complexity_cost"
    return {
        "members": dict(members),
        "degree": degree,
        "coefficients_hz": coeff.tolist(),
        "reference_time_s": ref,
        "time_scale_s": scale,
        "start_s": float(t.min()),
        "end_s": float(t.max()),
        "points": len(t),
        "rms_hz": float(np.sqrt(np.mean(residual**2))),
        "max_residual_hz": float(max(abs(residual))),
        "gain": float(gain),
        "cost": cost,
        "diagnostics": diagnostics,
        "fully_supported": all(
            d["status"] == "no_structure_detected" for d in diagnostics.values()
        ),
    }, "accepted"


def edge_kind(a, b):
    return {
        "same_rx": a["receiver"] == b["receiver"],
        "cross_channel": a["channel"] != b["channel"],
        "cross_band": a["bank"] != b["bank"],
    }


def candidate_edges(tracks, cal, scaled):
    beta = np.array(cal["beta"])
    frames = {g["group"]: g["frame"] for g in cal["groups"]}
    edges = []
    for a, b in combinations(tracks, 2):
        if a["source_id"] != b["source_id"] or frames[group(a)] != frames[group(b)]:
            continue
        lo, hi = max(a["start_s"], b["start_s"]), min(a["end_s"], b["end_s"])
        gap, mid = max(0.0, lo - hi), (lo + hi) / 2
        if gap > MAX_GAP:
            continue
        best = None
        for ka in BRANCHES if scaled else (0,):
            va, sa = shared_value(a, mid, beta, scaled, ka)
            raw_b, _ = endpoint(b, mid)
            kb = int(round((ratio(b, scaled) * va + nuisance(b, mid, beta) - raw_b) / PERIOD))
            if abs(kb) > 4:
                continue
            vb, sb = shared_value(b, mid, beta, scaled, kb)
            if hi > lo:
                t = np.linspace(lo, hi, 17)
                pa = (predict(a, t) + ka * PERIOD - nuisance(a, t, beta)) / ratio(a, scaled)
                pb = (predict(b, t) + kb * PERIOD - nuisance(b, t, beta)) / ratio(b, scaled)
                distance = float(np.sqrt(np.mean((pb - pa) ** 2)))
                if not np.isfinite(distance):
                    continue
            else:
                if abs(sb - sa) > 250:
                    continue
                distance = abs(vb - va)
            if best is None or distance < best[0]:
                best = (distance, ka, kb)
        if best is None or best[0] > (900 if hi > lo else 600 + 100 * gap):
            continue
        edges.append(
            {
                "left_key": a["key"],
                "right_key": b["key"],
                "left_lift": best[1],
                "right_lift": best[2],
                "kind": "overlap" if hi > lo else "sequential",
                "gap_s": gap,
                "connection_s": mid,
                **edge_kind(a, b),
            }
        )
    return edges


def stitch(tracks, cal, scaled):
    mapping, beta = {t["key"]: t for t in tracks}, np.array(cal["beta"])
    edges, viable, rejected = candidate_edges(tracks, cal, scaled), [], Counter()
    for edge in edges:
        members = {edge["left_key"]: edge["left_lift"], edge["right_key"]: edge["right_lift"]}
        fit, reason = fit_union(members, mapping, beta, scaled)
        if fit:
            viable.append((fit["gain"], edge))
        else:
            rejected[reason] += 1
    owners = {k: k for k in mapping}
    groups = {k: {k: 0} for k in mapping}
    fits, accepted = {}, []
    for _, edge in sorted(viable, key=lambda x: -x[0]):
        oa, ob = owners[edge["left_key"]], owners[edge["right_key"]]
        if oa == ob:
            continue
        # Preserve established component branches. Enumerate shifts for new pair components.
        proposals = []
        shifts = (0,) if len(groups[oa]) > 1 else (edge["left_lift"],)
        for shift_a in shifts:
            left = {k: v + shift_a for k, v in groups[oa].items()}
            delta = left[edge["left_key"]] - edge["left_lift"]
            shift_b = edge["right_lift"] + delta - groups[ob][edge["right_key"]]
            members = {**left, **{k: v + shift_b for k, v in groups[ob].items()}}
            fit, reason = fit_union(members, mapping, beta, scaled)
            if fit:
                previous = sum(
                    fits[o]["cost"] if o in fits else original_cost(mapping[o]) for o in (oa, ob)
                )
                if fit["cost"] < previous:
                    proposals.append((previous - fit["cost"], fit))
            else:
                rejected[f"component_{reason}"] += 1
        if not proposals:
            continue
        gain, fit = max(proposals, key=lambda x: x[0])
        groups[oa] = fit["members"]
        del groups[ob]
        fits[oa] = fit
        fits.pop(ob, None)
        for k in fit["members"]:
            owners[k] = oa
        accepted.append(
            {**edge, "incremental_gain": float(gain), "component_size": len(fit["members"])}
        )
    assert len(groups) + len(accepted) == len(tracks)
    calibration_supported = {g["group"]: g["calibration_supported"] for g in cal["groups"]}
    for fit in fits.values():
        fit["calibration_supported"] = all(
            calibration_supported[group(mapping[k])] for k in fit["members"]
        )
        fit["fully_supported"] &= fit["calibration_supported"]
    return {
        "input_tracks": len(tracks),
        "output_tracks": len(groups),
        "associated_points": sum(len(t["times"]) for t in tracks),
        "proposal_edges": len(edges),
        "pairwise_viable": len(viable),
        "accepted_edges": accepted,
        "merged_groups": list(fits.values()),
        "ownership": owners,
        "rejections": dict(rejected),
    }


def metrics(source, method, result):
    e, g = result["accepted_edges"], result["merged_groups"]
    return {
        "source_id": source,
        "method": method,
        "input_tracks": result["input_tracks"],
        "output_tracks": result["output_tracks"],
        "associated_points": result["associated_points"],
        "mean_points_per_track": result["associated_points"] / result["output_tracks"],
        "links": len(e),
        "overlap_links": sum(x["kind"] == "overlap" for x in e),
        "sequential_links": sum(x["kind"] == "sequential" for x in e),
        "same_rx_cross_channel_links": sum(x["same_rx"] and x["cross_channel"] for x in e),
        "different_rx_cross_channel_links": sum(not x["same_rx"] and x["cross_channel"] for x in e),
        "cross_band_links": sum(x["cross_band"] for x in e),
        "merged_groups": len(g),
        "fully_supported_groups": sum(x["fully_supported"] for x in g),
        "merged_points": sum(x["points"] for x in g),
    }


def save_figure(fig, directory, name):
    for ext in ("png", "pdf"):
        fig.savefig(directory / f"{name}.{ext}", dpi=140, bbox_inches="tight")
    plt.close(fig)


def render(tracks, cal, result, scaled, directory):
    mapping = {t["key"]: t for t in tracks}
    beta = np.array(cal["beta"])
    palette = plt.get_cmap("tab20")
    fig, axes = plt.subplots(1, 3, figsize=(19, 5), constrained_layout=True)
    for track in tracks:
        color = palette((track["channel"] - 1) / 8)
        axes[0].scatter(
            track["times"],
            wrap(track["values"]) / 1000,
            c=[color],
            s=7,
            marker="o" if track["receiver"] == 1 else "^",
            alpha=0.6,
        )
        y = (track["values"] - nuisance(track, track["times"], beta)) / ratio(track, scaled)
        axes[1].scatter(track["times"], y / 1000, color="#b9bdc2", s=5, alpha=0.4)
    for i, fit in enumerate(result["merged_groups"]):
        a = observation_arrays(fit["members"], mapping, beta, scaled)
        color = palette((i % 20) / 20)
        pred = leg.legval(
            (a["t"] - fit["reference_time_s"]) / fit["time_scale_s"], fit["coefficients_hz"]
        )
        axes[1].scatter(a["t"], a["y"] / a["q"] / 1000, color=color, s=10)
        t = np.linspace(fit["start_s"], fit["end_s"], 150)
        curve = leg.legval(
            (t - fit["reference_time_s"]) / fit["time_scale_s"], fit["coefficients_hz"]
        )
        axes[1].plot(t, curve / 1000, color=color, lw=1)
        axes[2].scatter(a["t"], a["y"] - a["q"] * pred, color=color, s=9, alpha=0.8)
    for ax, title, ylabel in zip(
        axes,
        (
            "Original GLRT · color=channel, marker=RX",
            "Calibrated shared groups · gray=unmerged",
            "Joined original-point residuals",
        ),
        ("CFO kHz (wrapped)", "Reference-frequency CFO kHz", "Residual Hz"),
        strict=True,
    ):
        ax.set(title=title, xlabel="Scan time (s)", ylabel=ylabel, xlim=(0, 300))
        ax.grid(alpha=0.2)
    axes[2].set_ylim(-500, 500)
    axes[2].axhline(0, color="#666666", lw=0.7)
    fig.suptitle(
        f"{cal['source_id']} · {'RF-scaled' if scaled else 'Direct CFO'} any-lane prototype · "
        f"{result['input_tracks']} → {result['output_tracks']} components\n"
        "All associated points retained; candidate groups include provisional support"
    )
    save_figure(fig, directory, "overview")


def render_examples(tracks, all_results, output):
    mapping = {t["key"]: t for t in tracks}
    examples = []
    for label, predicate in (
        ("Same RX, different channels", lambda e: e["same_rx"] and e["cross_channel"]),
        ("Across low/high bands", lambda e: e["cross_band"]),
        (
            "Sequential, different channels",
            lambda e: e["kind"] == "sequential" and e["cross_channel"],
        ),
    ):
        options = []
        for r in all_results:
            if not r["scaled"]:
                continue
            for fit in r["result"]["merged_groups"]:
                if any(
                    predicate(e)
                    and e["left_key"] in fit["members"]
                    and e["right_key"] in fit["members"]
                    for e in r["result"]["accepted_edges"]
                ):
                    options.append((fit["fully_supported"], fit["points"], fit, r["calibration"]))
        if options:
            _, _, fit, cal = max(options, key=lambda v: v[:2])
            examples.append((label, fit, cal))
    if not examples:
        return []
    fig, axes = plt.subplots(
        len(examples), 3, figsize=(18, 5 * len(examples)), squeeze=False, constrained_layout=True
    )
    for row, (label, fit, cal) in enumerate(examples):
        a = observation_arrays(fit["members"], mapping, np.array(cal["beta"]), True)
        pred = leg.legval(
            (a["t"] - fit["reference_time_s"]) / fit["time_scale_s"], fit["coefficients_hz"]
        )
        lanes = sorted(set(zip(a["rx"], a["ch"], strict=True)))
        for i, (rx, ch) in enumerate(lanes):
            mask = (a["rx"] == rx) & (a["ch"] == ch)
            color = plt.get_cmap("tab10")(i % 10)
            for col, y in enumerate(
                (a["original_y"] / 1000, a["y"] / a["q"] / 1000, a["y"] - a["q"] * pred)
            ):
                axes[row, col].scatter(
                    a["t"][mask],
                    y[mask],
                    color=color,
                    s=18,
                    marker="o" if rx == 1 else "^",
                    label=f"RX{rx} CH{ch}",
                )
        t = np.linspace(fit["start_s"], fit["end_s"], 200)
        curve = leg.legval(
            (t - fit["reference_time_s"]) / fit["time_scale_s"], fit["coefficients_hz"]
        )
        axes[row, 1].plot(t, curve / 1000, color="#444444", lw=1)
        axes[row, 2].axhline(0, color="#666666", lw=0.7)
        axes[row, 2].set_ylim(-500, 500)
        for col, title in enumerate(
            (
                "Original lifted CFO",
                "Corrected + RF-scaled common curve",
                f"Original-Hz residuals · RMS {fit['rms_hz']:.0f} Hz",
            )
        ):
            axes[row, col].set(
                title=title, xlabel="Scan time (s)", ylabel="Residual Hz" if col == 2 else "CFO kHz"
            )
            axes[row, col].grid(alpha=0.2)
        axes[row, 0].legend(fontsize=7)
        axes[row, 0].text(
            0.02,
            0.02,
            f"{cal['source_id']} · {label}\n"
            f"{len(fit['members'])} fragments · "
            f"{'supported' if fit['fully_supported'] else 'provisional'}",
            transform=axes[row, 0].transAxes,
            fontsize=8,
        )
    fig.suptitle(
        "Any-RX/channel candidate groups · no offset fitted per join\n"
        "Same calibration for each scan/RX/band; shared degree ≤4; checks per RX/channel"
    )
    save_figure(fig, output, "examples")
    return [
        {"label": label, "source_id": cal["source_id"], "members": fit["members"]}
        for label, fit, cal in examples
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    tracks, hashes = load_tracks()
    previous = ROOT / "reports/2026_10_17_dsx01_receiver_model/results.json"
    hashes[str(previous.relative_to(ROOT))] = hashlib.sha256(previous.read_bytes()).hexdigest()
    paths = [
        Path(__file__),
        ROOT / "tools/model_dsx01_receiver_tracklets.py",
        ROOT / "tools/compare_dsx01_graph_receivers.py",
        ROOT / "tools/tune_full_data_tracklets.py",
    ]
    sources = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    all_results, rows = [], []
    for scaled in (False, True):
        method = "rf_scaled" if scaled else "direct_cfo"
        for source in (f"S{i:02}" for i in range(1, 6)):
            scan = [t for t in tracks if t["source_id"] == source]
            anchors = calibration_anchors(scan, scaled)
            cal = fit_calibration(scan, anchors, scaled)
            result = stitch(scan, cal, scaled)
            item = {
                "source_id": source,
                "scaled": scaled,
                "calibration": cal,
                "anchors": anchors,
                "result": result,
            }
            all_results.append(item)
            record = metrics(source, method, result)
            rows.append(record)
            folder = args.output / method / source
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "results.json").write_text(json.dumps(item, indent=2) + "\n")
            if result["accepted_edges"]:
                write_csv(folder / "accepted-links.csv", result["accepted_edges"])
            render(scan, cal, result, scaled, folder)
            print(json.dumps(record), flush=True)
    write_csv(args.output / "per-scan.csv", rows)
    aggregate = []
    for method in ("direct_cfo", "rf_scaled"):
        subset = [r for r in rows if r["method"] == method]
        total = {
            k: sum(r[k] for r in subset)
            for k in subset[0]
            if k not in ("source_id", "method", "mean_points_per_track")
        }
        aggregate.append(
            {
                "method": method,
                **total,
                "mean_points_per_track": total["associated_points"] / total["output_tracks"],
            }
        )
    write_csv(args.output / "comparison.csv", aggregate)
    examples = render_examples(tracks, all_results, args.output)
    for path, value in {**hashes, **sources}.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == value, path
    summary = {
        "input_sha256": hashes,
        "source_sha256": sources,
        "reference_rf_hz": REFERENCE_RF,
        "native_alias_period_hz": PERIOD,
        "sigma_hz": SIGMA,
        "point_gate_hz": GATE,
        "max_gap_s": MAX_GAP,
        "offset_prior_sigma_hz": 100000,
        "drift_prior_sigma_hz_s": 10,
        "drift_bound_hz_s": DRIFT_BOUND,
        "historical_relative_offset_prior_sigma_hz": 300,
        "historical_relative_drift_prior_sigma_hz_s": 2,
        "aggregate": aggregate,
        "per_scan": rows,
        "examples": examples,
        "limitations": "Bounded inspected-data prototype; original Graph observations only; "
        "no identity labels or localization; fixed RF ratios, no learned RF c term. "
        "Calibration and aliases are locally selected; "
        "greedy branch freezing can miss valid unions.",
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    main()
