"""Four bounded ensemble-calibration experiments on frozen DSX01 Graph fragments.

No historical calibration, orbital identity or RF-dependent learned coefficient is
used. Candidate correspondence and native alias choices are inferred anew. These
are exploratory data-association experiments, not identity ground truth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np
from audit_dsx01_offset_confidence import curvature
from compare_dsx01_graph_receivers import PERIOD, ROOT, load_tracks, write_csv
from numpy.polynomial import legendre as leg
from prototype_multilane_tracklets import (
    GROUP_LABELS,
    SIGMA,
    candidate_edges,
    core_arrays,
    fit_union,
    group,
    metrics,
    original_cost,
    ratio,
    render,
)
from validate_multilane_tracklets import audit_and_export, shift_lanes

DEST = ROOT / "reports/2026_10_17_dsx01_consensus_calibration"
METHODS = ("ransac", "compatibility", "trimmed", "em")
BOUND = np.r_[np.full(4, PERIOD / 2000), np.full(4, 3.0)]
LIMIT = 16.0


def solve_box(h, rhs, start=None, iterations=120):
    """Active-set minimization of an eight-dimensional bounded quadratic.

    Coordinates are kHz (drifts are kHz per 150 s). A tiny numerical ridge picks
    a representative of unresolved modes; it is excluded from reported information.
    """
    h = (h + h.T) / 2 + np.eye(8) * 1e-10
    x = np.zeros(8) if start is None else np.clip(np.asarray(start).copy(), -BOUND, BOUND)
    active = np.zeros(8, dtype=int)
    tolerance = 1e-9 * max(1.0, float(np.max(abs(rhs))))
    for _ in range(iterations):
        free, fixed = np.flatnonzero(active == 0), np.flatnonzero(active)
        trial = x.copy()
        if len(free):
            trial[free] = np.linalg.lstsq(
                h[np.ix_(free, free)],
                rhs[free] - h[np.ix_(free, fixed)] @ x[fixed],
                rcond=None,
            )[0]
        direction = trial - x
        alpha, hit = 1.0, None
        for j in free:
            if trial[j] > BOUND[j] + 1e-10 and direction[j] > 0:
                step = (BOUND[j] - x[j]) / direction[j]
            elif trial[j] < -BOUND[j] - 1e-10 and direction[j] < 0:
                step = (-BOUND[j] - x[j]) / direction[j]
            else:
                continue
            if step < alpha:
                alpha, hit = max(0.0, float(step)), int(j)
        x = np.clip(x + alpha * direction, -BOUND, BOUND)
        if hit is not None:
            active[hit] = 1 if direction[hit] > 0 else -1
            x[hit] = active[hit] * BOUND[hit]
            continue
        gradient = h @ x - rhs
        violations = np.where(active != 0, active * gradient, -np.inf)
        worst = int(np.argmax(violations))
        if violations[worst] <= tolerance:
            return x
        active[worst] = 0
    raise RuntimeError("Bounded calibration active-set solver did not converge")


def candidate_pool(tracks):
    """Profile nuisance curves using actual overlapping measurements.

    Native integer alias lifts precede known RF normalization. SVD compresses
    affine calibration information to two rows per candidate; interpolation
    samples are never counted as measurements.
    """
    pool = []
    for left, right in combinations(tracks, 2):
        if left["source_id"] != right["source_id"]:
            continue
        if (left["receiver"], left["channel"]) == (right["receiver"], right["channel"]):
            continue
        lo = max(left["start_s"], right["start_s"])
        hi = min(left["end_s"], right["end_s"])
        if hi - lo < 10:
            continue
        masks = [(t["times"] >= lo) & (t["times"] <= hi) for t in (left, right)]
        if min(int(m.sum()) for m in masks) < 12:
            continue
        if group(left) == group(right) and left["rf_hz"] == right["rf_hz"]:
            continue
        descriptions = [
            curvature(t["times"][m], t["values"][m])[0]
            for t, m in zip((left, right), masks, strict=True)
        ]
        degree = max(1, *(d.get("degree", 1) for d in descriptions))
        pair = {
            "left_key": left["key"],
            "right_key": right["key"],
            "start_s": lo,
            "end_s": hi,
            "left_lift": 0,
            "right_lift": 0,
        }
        _, y, q, _, x, z = core_arrays(pair, {left["key"]: left, right["key"]: right}, True)
        design = q[:, None] * leg.legvander(x, degree)
        rz = z - design @ np.linalg.lstsq(design, z, rcond=None)[0]
        ry = y - design @ np.linalg.lstsq(design, y, rcond=None)[0]
        u, singular, vh = np.linalg.svd(rz, full_matrices=False)
        rank = int(np.sum(singular > max(singular[0] * 1e-9, 1e-9)))
        if rank != 2:
            continue
        u = u[:, :2]
        a = singular[:2, None] * vh[:2] * 1000 / SIGMA
        b = u.T @ ry / SIGMA
        orthogonal = ry - u @ (u.T @ ry)
        shape_rms = float(np.sqrt(np.mean(orthogonal**2)))
        if shape_rms > 200:
            continue
        nleft = int(masks[0].sum())
        indicators = np.column_stack((np.arange(len(y)) < nleft, np.arange(len(y)) >= nleft))
        alias_design = u.T @ indicators * PERIOD / SIGMA
        branch_b, lifts = [], []
        seen = set()
        for ka in range(-2, 3):
            for kb in range(-4, 5):
                value = b + alias_design @ np.array([ka, kb])
                identity = tuple(np.round(value, 6))
                if identity not in seen:
                    branch_b.append(value)
                    lifts.append((ka, kb))
                    seen.add(identity)
        slopes = []
        for t, m in zip((left, right), masks, strict=True):
            slopes.append(
                float(
                    np.polyfit(t["times"][m] - (lo + hi) / 2, t["values"][m] / ratio(t, True), 1)[0]
                )
            )
        pool.append(
            {
                **pair,
                "a": a,
                "b": np.array(branch_b),
                "lifts": lifts,
                "mid_s": (lo + hi) / 2,
                "points": len(y),
                "degree": degree,
                "shape_rms_hz": shape_rms,
                "active_curvature": all(d["active"] for d in descriptions),
                "cell": (int((lo + hi) / 2 // 45), int(np.mean(slopes) // 400)),
                "groups": (group(left), group(right)),
            }
        )
    return pool


def pack(pool):
    a = np.array([p["a"] for p in pool]).reshape(-1, 2, 8)
    b = np.full((len(pool), 45, 2), np.inf)
    for i, p in enumerate(pool):
        b[i, : len(p["b"])] = p["b"]
    return a, b


def distances(pool, packed, beta):
    a, b = packed
    residual = b - np.einsum("nij,j->ni", a, beta)[:, None, :]
    squared = np.sum(residual**2, axis=2)
    branches = np.argmin(squared, axis=1)
    return squared[np.arange(len(pool)), branches], branches


def independent_selection(pool, chi2, limit=LIMIT):
    """Disjoint calibration observations with one vote per time/slope evidence cell."""
    used, cells, selected = set(), set(), []
    order = sorted(
        range(len(pool)),
        key=lambda i: (chi2[i] - 0.5 * pool[i]["active_curvature"], pool[i]["shape_rms_hz"]),
    )
    for i in order:
        p = pool[i]
        if chi2[i] > limit:
            continue
        if p["left_key"] in used or p["right_key"] in used or p["cell"] in cells:
            continue
        selected.append(i)
        used.update((p["left_key"], p["right_key"]))
        cells.add(p["cell"])
    return selected


def normal_fit(pool, packed, indices, branches, weights=None, start=None):
    a, b = packed
    if not len(indices):
        return np.zeros(8) if start is None else np.asarray(start).copy()
    w = np.ones(len(indices)) if weights is None else np.asarray(weights)
    aa = a[indices]
    bb = b[np.asarray(indices), branches[indices]]
    h = np.einsum("nki,nkj,n->ij", aa, aa, w)
    rhs = np.einsum("nki,nk,n->i", aa, bb, w)
    return solve_box(h, rhs, start)


def evaluate_beta(pool, packed, beta):
    chi2, branches = distances(pool, packed, beta)
    selected = independent_selection(pool, chi2)
    score = float(sum(1 - chi2[i] / LIMIT for i in selected))
    return score, selected, branches, chi2


def refine_consensus(pool, packed, beta, rounds=8):
    for _ in range(rounds):
        _, indices, branches, _ = evaluate_beta(pool, packed, beta)
        fitted = normal_fit(pool, packed, indices, branches, start=beta)
        if np.max(abs(fitted - beta)) < 0.001:
            return fitted
        beta = fitted
    return beta


def initial_hypotheses(pool, packed, seed=731, budget=72):
    rng = np.random.default_rng(seed)
    zero = np.zeros(8)
    _, branches = distances(pool, packed, zero)
    hypotheses = [zero]
    curved = [i for i, p in enumerate(pool) if p["active_curvature"]]
    priority = sorted(
        range(len(pool)), key=lambda i: (not pool[i]["active_curvature"], pool[i]["shape_rms_hz"])
    )
    for i in priority[:16]:
        hypotheses.append(normal_fit(pool, packed, [i], branches))
    for iteration in range(budget):
        population = curved if iteration % 2 == 0 and len(curved) >= 4 else range(len(pool))
        sampled = rng.choice(population, min(5, len(population)), replace=False).tolist()
        # Never reuse a fragment while constructing a calibration hypothesis.
        kept, used = [], set()
        for i in sampled:
            keys = {pool[i]["left_key"], pool[i]["right_key"]}
            if not used.intersection(keys):
                kept.append(i)
                used.update(keys)
        hypotheses.append(normal_fit(pool, packed, kept, branches))
    scored = sorted(
        ((evaluate_beta(pool, packed, x)[0], x) for x in hypotheses), key=lambda value: -value[0]
    )
    return [x for _, x in scored]


def ransac(pool, packed, starts):
    """Maximum consensus after bounded random-subset proposal and local refinement."""
    return [refine_consensus(pool, packed, b) for b in starts[:12]]


def compatibility(pool, packed, starts):
    """Beam search of jointly compatible correspondence sets, including skip branches."""
    proposals = []
    for initial in starts[:4]:
        _, _, initial_branches, initial_chi2 = evaluate_beta(pool, packed, initial)
        order = sorted(
            range(len(pool)), key=lambda i: (initial_chi2[i], not pool[i]["active_curvature"])
        )[:80]
        beam = [(0.0, initial, [], set(), set())]
        for candidate in order:
            p = pool[candidate]
            expanded = list(beam)
            for _, beta, chosen, used, cells in beam:
                keys = {p["left_key"], p["right_key"]}
                if keys.intersection(used) or p["cell"] in cells:
                    continue
                indices = chosen + [candidate]
                _, branches = distances(pool, packed, beta)
                fitted = normal_fit(pool, packed, indices, branches, start=beta)
                chi2, _ = distances(pool, packed, fitted)
                if max(chi2[indices]) > LIMIT:
                    continue
                score = len(indices) - float(np.sum(chi2[indices])) / LIMIT
                # Favor jointly explained sets; global support breaks short-set ties.
                expanded.append((score, fitted, indices, used | keys, cells | {p["cell"]}))
            expanded.sort(key=lambda row: -row[0])
            unique, next_beam = set(), []
            for row in expanded:
                identity = tuple(sorted(row[2]))
                if identity not in unique:
                    unique.add(identity)
                    next_beam.append(row)
                if len(next_beam) == 6:
                    break
            beam = next_beam
        proposals.extend(refine_consensus(pool, packed, row[1], 3) for row in beam[:3])
    return proposals


def trimmed(pool, packed, starts):
    """Least-trimmed-squares continuation on disjoint, family-balanced pair sets."""
    proposals = []
    target = max(6, min(18, len(pool) // 8))
    for initial in starts[:8]:
        beta = initial.copy()
        for _ in range(16):
            chi2, branches = distances(pool, packed, beta)
            indices = independent_selection(pool, chi2, limit=1e10)[:target]
            beta = normal_fit(pool, packed, indices, branches, start=beta)
        proposals.append(refine_consensus(pool, packed, beta))
    return proposals


def em(pool, packed, starts):
    """EM-style alias/match mixture with a uniform unmatched component.

    Capacity normalization is approximate; this is not claimed to maximize an
    exact one-to-one likelihood or to have a monotonic EM objective.
    """
    a, b = packed
    keys = sorted({p[k] for p in pool for k in ("left_key", "right_key")})
    incident = {
        key: np.array([i for i, p in enumerate(pool) if key in (p["left_key"], p["right_key"])])
        for key in keys
    }
    proposals = []
    for initial in starts[:8]:
        beta = initial.copy()
        for temperature in (4.0, 2.0, 1.0):
            for _ in range(8):
                residual = b - np.einsum("nij,j->ni", a, beta)[:, None, :]
                likelihood = np.exp(
                    -np.minimum(np.sum(residual**2, axis=2) / (2 * temperature), 700)
                )
                # Uniform mass over unique alias branches; unmatched mass is explicit.
                likelihood /= np.array([len(p["b"]) for p in pool])[:, None]
                alias_mass = likelihood.sum(axis=1)
                probability = alias_mass / (alias_mass + 0.015)
                for indices in incident.values():
                    probability[indices] /= max(1.0, float(probability[indices].sum()))
                cell_mass = Counter()
                for p, weight in zip(pool, probability, strict=True):
                    cell_mass[p["cell"]] += weight
                probability /= np.array([max(1.0, cell_mass[p["cell"]]) for p in pool])
                expectation = np.einsum("nb,nbk->nk", likelihood, np.where(np.isfinite(b), b, 0))
                expectation /= np.maximum(alias_mass[:, None], 1e-250)
                h = np.einsum("nki,nkj,n->ij", a, a, probability)
                rhs = np.einsum("nki,nk,n->i", a, expectation, probability)
                beta = solve_box(h, rhs, beta)
        proposals.append(refine_consensus(pool, packed, beta, 3))
    return proposals


OPTIMIZERS = {"ransac": ransac, "compatibility": compatibility, "trimmed": trimmed, "em": em}


def information(pool, packed, selected, branches):
    a, _ = packed
    if not selected:
        return np.zeros((8, 8)), np.zeros((8, 8)), 0, []
    stacked = a[selected].reshape(-1, 8)
    _, singular, vh = np.linalg.svd(stacked, full_matrices=False)
    rank = int(np.sum(singular > max(singular[0] * 1e-8, 1e-8)))
    basis = vh[:rank]
    cov = (basis.T / singular[:rank] ** 2) @ basis * 1e6
    projector = basis.T @ basis
    return cov, projector, rank, singular.tolist()


def fit_method(tracks, pool, packed, starts, method):
    start = time.perf_counter()
    candidates = OPTIMIZERS[method](pool, packed, starts)
    candidates = [refine_consensus(pool, packed, beta, rounds=24) for beta in candidates]
    candidates.sort(key=lambda b: -evaluate_beta(pool, packed, b)[0])
    best = candidates[0]
    score, selected, branches, chi2 = evaluate_beta(pool, packed, best)
    # Keep distinct high-scoring alternatives; this is a bounded search, not proof of uniqueness.
    modes = []
    for candidate in candidates:
        if evaluate_beta(pool, packed, candidate)[0] < 0.9 * score:
            continue
        if all(np.linalg.norm(candidate - old) > 0.25 for old in modes):
            modes.append(candidate)
        if len(modes) == 4:
            break
    cov, projector, rank, singular = information(pool, packed, selected, branches)
    cells = {pool[i]["cell"] for i in selected}
    time_bins = {cell[0] for cell in cells}
    span = float(np.ptp([pool[i]["mid_s"] for i in selected])) if selected else 0.0
    # A single pair can never promote its own calibration.
    validated_ensemble = len(selected) >= 6 and len(time_bins) >= 3 and span >= 120
    a, b = packed
    aa = a[selected]
    bb = b[np.asarray(selected, dtype=int), branches[selected]]
    h = np.einsum("nki,nkj->ij", aa, aa)
    rhs = np.einsum("nki,nk->i", aa, bb)
    gradient = h @ best - rhs
    step = np.clip(best - gradient / np.maximum(np.diag(h), 1e-12), -BOUND, BOUND) - best
    stationarity_hz = float(np.max(abs(step)) * 1000)
    validated_ensemble &= stationarity_hz <= 1.0
    deletions = []
    for cell in sorted(cells):
        retained = [i for i in selected if pool[i]["cell"] != cell]
        b = normal_fit(pool, packed, retained, branches, start=best)
        _, p, _, _ = information(pool, packed, retained, branches)
        deletions.append({"cell": cell, "beta": (b * 1000).tolist(), "projector": p.tolist()})
    nodes = []
    for g in range(4):
        support = [i for i in selected if g in pool[i]["groups"]]
        active_bound = abs(best[g + 4]) >= 2.999
        nodes.append(
            {
                "group": g,
                "label": GROUP_LABELS[g],
                "frame": 0,
                "anchors": len(support),
                "drift_bound_active": bool(active_bound),
                "calibration_supported": bool(
                    validated_ensemble and len(support) >= 3 and not active_bound
                ),
            }
        )
    records = []
    for i in selected:
        p = pool[i]
        records.append(
            {
                "left_key": p["left_key"],
                "right_key": p["right_key"],
                "mid_s": p["mid_s"],
                "cell": p["cell"],
                "groups": p["groups"],
                "active_curvature": p["active_curvature"],
                "points": p["points"],
                "degree": p["degree"],
                "shape_rms_hz": p["shape_rms_hz"],
                "chi2": float(chi2[i]),
                "left_lift": p["lifts"][branches[i]][0],
                "right_lift": p["lifts"][branches[i]][1],
            }
        )
    return {
        "source_id": tracks[0]["source_id"],
        "method": method,
        "beta": (best * 1000).tolist(),
        "groups": nodes,
        "score": score,
        "selected_pairs": records,
        "data_rank": rank,
        "redundancy_degrees_of_freedom": 2 * len(selected) - rank,
        "singular_values": singular,
        "conditional_covariance": cov.tolist(),
        "estimable_projector": projector.tolist(),
        "ensemble_eligible": validated_ensemble,
        "support_time_span_s": span,
        "evidence_cells": len(cells),
        "credible_modes": [(b * 1000).tolist() for b in modes],
        "deletions": deletions,
        "fit_seconds": time.perf_counter() - start,
        "coordinate_stationarity_hz": stationarity_hz,
        "historical_calibration_used": False,
    }


def calibration_contrast(a, b, times):
    vectors = np.zeros((len(times), 8))
    for track, sign in ((a, -1), (b, 1)):
        g, q = group(track), ratio(track, True)
        vectors[:, g] += sign / q
        vectors[:, g + 4] += sign * (times - 150) / (150 * q)
    return vectors


def alias_equivalent_change(vectors, delta, a, b):
    change = vectors @ delta
    offsets = np.array(
        [
            kb * PERIOD / ratio(b, True) - ka * PERIOD / ratio(a, True)
            for ka in range(-4, 5)
            for kb in range(-4, 5)
        ]
    )
    return float(np.min(np.max(abs(change[:, None] - offsets[None, :]), axis=0)))


def calibration_gate(a, b, calibration):
    times = np.array([max(a["start_s"], b["start_s"]), min(a["end_s"], b["end_s"])])
    vectors = calibration_contrast(a, b, times)
    # Same path and carrier share the hardware term exactly, including linear tracks.
    if np.max(abs(vectors)) < 1e-12:
        return True, "common_hardware"
    if not calibration["ensemble_eligible"]:
        return False, "insufficient_ensemble"
    projector = np.asarray(calibration["estimable_projector"])
    if np.max(abs(vectors - vectors @ projector)) > 1e-7:
        return False, "unobservable_calibration"
    covariance = np.asarray(calibration["conditional_covariance"])
    se = np.sqrt(np.maximum(0.0, np.einsum("ni,ij,nj->n", vectors, covariance, vectors)))
    if max(se) > 150:
        return False, "calibration_precision"
    beta = np.asarray(calibration["beta"])
    for deletion in calibration["deletions"]:
        p = np.asarray(deletion["projector"])
        if np.max(abs(vectors - vectors @ p)) > 1e-7:
            return False, "deletion_observability"
        if alias_equivalent_change(vectors, np.asarray(deletion["beta"]) - beta, a, b) > 300:
            return False, "deletion_instability"
    for mode in calibration["credible_modes"]:
        if alias_equivalent_change(vectors, np.asarray(mode) - beta, a, b) > 300:
            return False, "competing_calibration_mode"
    return True, "supported_contrast"


def fuse(tracks, calibration):
    """Freeze calibration, allow linear joins, and refit every whole-component union."""
    mapping = {t["key"]: t for t in tracks}
    beta = np.asarray(calibration["beta"])
    edges = candidate_edges(tracks, calibration, True)
    rejected, viable = Counter(), []
    for edge in edges:
        a, b = mapping[edge["left_key"]], mapping[edge["right_key"]]
        allowed, reason = calibration_gate(a, b, calibration)
        if not allowed:
            rejected[reason] += 1
            continue
        members = {edge["left_key"]: edge["left_lift"], edge["right_key"]: edge["right_lift"]}
        fit, reason = fit_union(members, mapping, beta, True)
        if fit:
            viable.append((fit["gain"], edge))
        else:
            rejected[reason] += 1
    owners = {key: key for key in mapping}
    groups = {key: {key: 0} for key in mapping}
    fits, accepted = {}, []
    for _, edge in sorted(viable, key=lambda row: -row[0]):
        oa, ob = owners[edge["left_key"]], owners[edge["right_key"]]
        if oa == ob:
            continue
        # Every new contrast within a component must be supported, not only its bridge.
        if any(
            not calibration_gate(mapping[a], mapping[b], calibration)[0]
            for a in groups[oa]
            for b in groups[ob]
        ):
            rejected["component_calibration"] += 1
            continue
        shift_a = edge["left_lift"] if len(groups[oa]) == 1 else 0
        left = {key: lift + shift_a for key, lift in groups[oa].items()}
        shift_b = left[edge["left_key"]] - edge["left_lift"] + edge["right_lift"]
        shift_b -= groups[ob][edge["right_key"]]
        members = {**left, **{key: lift + shift_b for key, lift in groups[ob].items()}}
        fit, reason = fit_union(members, mapping, beta, True)
        if not fit:
            rejected[f"component_{reason}"] += 1
            continue
        previous = sum(
            fits[o]["cost"] if o in fits else original_cost(mapping[o]) for o in (oa, ob)
        )
        if fit["cost"] >= previous:
            continue
        groups[oa] = fit["members"]
        del groups[ob]
        fits[oa] = fit
        fits.pop(ob, None)
        for key in fit["members"]:
            owners[key] = oa
        fit["calibration_supported"] = True
        accepted.append(
            {**edge, "incremental_gain": previous - fit["cost"], "component_size": len(members)}
        )
    assert len(groups) + len(accepted) == len(tracks)
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


def run_case(tracks, output, seed, draw=True, original_points=None):
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    pool = candidate_pool(tracks)
    packed = pack(pool)
    starts = initial_hypotheses(pool, packed, seed=731)
    shared_seconds = time.perf_counter() - started
    rows = []
    for method in METHODS:
        calibration = fit_method(tracks, pool, packed, starts, method)
        begun = time.perf_counter()
        result = fuse(tracks, calibration)
        fusion_seconds = time.perf_counter() - begun
        item = {
            "source_id": tracks[0]["source_id"],
            "method": method,
            "scaled": True,
            "calibration": calibration,
            "result": result,
        }
        folder = output / method
        folder.mkdir(exist_ok=True)
        exported = audit_and_export(tracks, item)
        write_csv(folder / "observations.csv", exported)
        (folder / "results.json").write_text(json.dumps(item, indent=2) + "\n")
        if draw:
            render(tracks, calibration, result, True, folder)
        row = {
            "dataset": "real" if seed is None else "time_shift_control",
            "seed": seed,
            **metrics(tracks[0]["source_id"], method, result),
            "calibration_pairs": len(calibration["selected_pairs"]),
            "curved_calibration_pairs": sum(
                p["active_curvature"] for p in calibration["selected_pairs"]
            ),
            "calibration_rank": calibration["data_rank"],
            "ensemble_eligible": calibration["ensemble_eligible"],
            "calibration_score": calibration["score"],
            "candidate_pairs": len(pool),
            "shared_candidate_seconds": shared_seconds,
            "calibration_seconds": calibration["fit_seconds"],
            "fusion_seconds": fusion_seconds,
            "compute_seconds": shared_seconds + calibration["fit_seconds"] + fusion_seconds,
            "calibration_observations": sum(p["points"] for p in calibration["selected_pairs"]),
            "boundary_observations_excluded": (original_points or result["associated_points"])
            - result["associated_points"],
            "cross_lane_links": sum(
                e["cross_channel"] or not e["same_rx"] for e in result["accepted_edges"]
            ),
            "within_lane_links": sum(
                not e["cross_channel"] and e["same_rx"] for e in result["accepted_edges"]
            ),
            "merged_residual_rms_hz": float(
                np.sqrt(np.mean([r["residual_native_hz"] ** 2 for r in exported if r["merged"]]))
            )
            if result["merged_groups"]
            else None,
            "linear_merged_groups": sum(g["degree"] <= 1 for g in result["merged_groups"]),
        }
        rows.append(row)
        print(
            tracks[0]["source_id"],
            seed,
            method,
            "pairs",
            row["calibration_pairs"],
            "rank",
            row["calibration_rank"],
            "tracks",
            row["output_tracks"],
            "seconds",
            round(row["calibration_seconds"] + fusion_seconds, 2),
            flush=True,
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", nargs="+", default=[f"S{i:02}" for i in range(1, 6)])
    parser.add_argument("--seeds", type=int, nargs="*", default=[41, 142, 243])
    parser.add_argument("--output", type=Path, default=DEST)
    parser.add_argument("--no-figures", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    tracks, hashes = load_tracks()
    rows = []
    for source in args.sources:
        cohort = [t for t in tracks if t["source_id"] == source]
        original_points = sum(len(t["times"]) for t in cohort)
        rows.extend(
            run_case(
                cohort,
                args.output / "real" / source,
                None,
                draw=not args.no_figures,
                original_points=original_points,
            )
        )
        for seed in args.seeds:
            control = [t for t in shift_lanes(cohort, seed) if len(t["times"]) >= 8]
            rows.extend(
                run_case(
                    control,
                    args.output / "controls" / f"{source}-{seed}",
                    seed,
                    draw=False,
                    original_points=original_points,
                )
            )
        write_csv(args.output / "scan-metrics.csv", rows)
    write_csv(args.output / "scan-metrics.csv", rows)
    sources = [
        Path(__file__),
        ROOT / "tools/audit_dsx01_offset_confidence.py",
        ROOT / "tools/prototype_multilane_tracklets.py",
        ROOT / "tools/compare_dsx01_graph_receivers.py",
        ROOT / "tools/validate_multilane_tracklets.py",
        ROOT / "tools/model_dsx01_receiver_tracklets.py",
        ROOT / "tools/tune_full_data_tracklets.py",
    ]
    (args.output / "provenance.json").write_text(
        json.dumps(
            {
                "input_sha256": hashes,
                "source_sha256": {
                    str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sources
                },
                "methods": METHODS,
                "sources": args.sources,
                "control_seeds": args.seeds,
                "noise_sigma_hz": SIGMA,
                "candidate_min_overlap_s": 10,
                "candidate_min_points_per_side": 12,
                "shared_hypothesis_random_budget": 72,
                "historical_calibration_used": False,
                "controls_relearn_calibration": True,
                "quadratic_solver": "active set; KKT residual checked on final selected pairs",
                "final_consensus_refinement_rounds": 24,
                "python_version": platform.python_version(),
                "machine": platform.machine(),
                "numpy_version": np.__version__,
                "control_tiny_fragments_excluded": True,
                "evidence_cell_proxy": "45 seconds x 400 Hz/s; not ground-truth emitter identities",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
