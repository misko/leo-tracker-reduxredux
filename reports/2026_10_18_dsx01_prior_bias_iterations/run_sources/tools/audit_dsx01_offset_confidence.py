"""Curvature and calibration sensitivity audit of frozen DSX01 candidate joins.

These are conditional diagnostics, not identity probabilities or confidence intervals
covering alias selection. No original fit, assignment, or published result is changed.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from itertools import product
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from compare_dsx01_graph_receivers import ROOT, load_tracks, write_csv
from numpy.polynomial import legendre as leg
from prototype_multilane_tracklets import (
    OUTPUT,
    SIGMA,
    calibration_anchors,
    core_arrays,
    fit_calibration,
    ratio,
)
from report_dsx01_learned_shifts import RELATIONS
from validate_multilane_tracklets import shift_lanes

DEST = ROOT / "reports/2026_10_17_dsx01_offset_confidence"


def curvature(times, values, sigma=SIGMA):
    """Measure non-affine signal on actual samples, including a noise DOF correction.

    Fixed screening rule: >=20 points, >=150 Hz debiased nonlinear RMS,
    delta chi-square >=25 and BIC improvement >=10 over an affine model.
    Selection among degrees 1..4 is included in the BIC comparison. The rule is
    an effect-size screen, not a calibrated multiple-comparison significance test.
    """
    times, values = np.asarray(times), np.asarray(values)
    n = len(times)
    if n < 4 or np.ptp(times) == 0:
        return {"n": n, "active": False, "reason": "insufficient_samples"}, None
    reference, scale = (times.min() + times.max()) / 2, np.ptp(times) / 2
    x = (times - reference) / scale
    affine = leg.legvander(x, 1)
    line = affine @ np.linalg.lstsq(affine, values, rcond=None)[0]
    sse_line = float(np.sum((values - line) ** 2))
    choices = []
    for degree in range(1, min(4, n // 2 - 1) + 1):
        design = leg.legvander(x, degree)
        coeff = np.linalg.lstsq(design, values, rcond=None)[0]
        fitted = design @ coeff
        sse = float(np.sum((values - fitted) ** 2))
        choices.append((sse / sigma**2 + (degree + 1) * np.log(n), degree, coeff, fitted, sse))
    cost, degree, coeff, fitted, sse = min(choices, key=lambda item: item[0])
    nonlinear = fitted - affine @ np.linalg.lstsq(affine, fitted, rcond=None)[0]
    amplitude = float(np.sqrt(max(0.0, np.mean(nonlinear**2) - (degree - 1) * sigma**2 / n)))
    delta_chi2 = (sse_line - sse) / sigma**2
    bic_gain = sse_line / sigma**2 + 2 * np.log(n) - cost
    active = n >= 20 and amplitude >= 150 and delta_chi2 >= 25 and bic_gain >= 10
    return {
        "n": n,
        "degree": degree,
        "nonlinear_rms_hz": amplitude,
        "delta_chi2": float(delta_chi2),
        "bic_gain": float(bic_gain),
        "active": bool(active),
        "reason": "active" if active else "short" if n < 20 else "weak_curvature",
    }, (coeff, reference, scale)


def pair_evidence(pair, mapping):
    a, b = (mapping[pair[f"{side}_key"]] for side in ("left", "right"))
    lo, hi = max(a["start_s"], b["start_s"]), min(a["end_s"], b["end_s"])
    row = {"left_key": a["key"], "right_key": b["key"], "overlap_s": max(0.0, hi - lo)}
    metrics, fits = [], []
    for side, track in zip(("left", "right"), (a, b), strict=True):
        mask = (track["times"] >= lo) & (track["times"] <= hi)
        metric, fit = curvature(track["times"][mask], track["values"][mask])
        metrics.append(metric)
        fits.append(fit)
        row.update({f"{side}_{k}": v for k, v in metric.items()})
    row["both_active"] = all(m["active"] for m in metrics)
    row["either_active"] = any(m["active"] for m in metrics)
    row["curvature_mismatch_hz"] = None
    row["curvature_compatible"] = False
    if all(f is not None for f in fits):
        times = np.linspace(lo, hi, 65)
        shapes = [
            leg.legval((times - f[1]) / f[2], f[0]) / ratio(t, True)
            for t, f in zip((a, b), fits, strict=True)
        ]
        # Additive offsets, drifts and native alias lifts are affine and vanish here.
        design = np.column_stack((np.ones(len(times)), times - times.mean()))
        diff = shapes[1] - shapes[0]
        residual = diff - design @ np.linalg.lstsq(design, diff, rcond=None)[0]
        mismatch = float(np.sqrt(np.mean(residual**2)))
        row["curvature_mismatch_hz"] = mismatch
        row["curvature_compatible"] = bool(row["both_active"] and mismatch <= 150)
    return row


def curved_data_fit(anchors, mapping):
    """Conditional, prior-free calibration; linear pairs contribute no observations.

    Pair identities and native alias branches remain frozen hypotheses. Degree four
    profiles out the nuisance curves conservatively. Enumerating all 81 active
    drift-bound configurations solves the small constrained least-squares problem.
    The unbounded covariance describes precision conditional on these hypotheses;
    it does not cover alias discovery, identity selection, or active-bound effects.
    """
    blocks_z, blocks_y, kept = [], [], []
    for pair in anchors:
        if not pair_evidence(pair, mapping)["curvature_compatible"]:
            continue
        _, y, q, _, x, z = core_arrays(pair, mapping, True)
        design = q[:, None] * leg.legvander(x, 4)
        blocks_z.append(z - design @ np.linalg.lstsq(design, z, rcond=None)[0])
        blocks_y.append(y - design @ np.linalg.lstsq(design, y, rcond=None)[0])
        kept.append((pair["left_key"], pair["right_key"]))
    if not kept:
        return None
    z, y = np.vstack(blocks_z), np.concatenate(blocks_y)
    unrestricted = np.linalg.lstsq(z, y, rcond=None)[0]
    candidates = []
    for state in product((0, -1, 1), repeat=4):
        fixed = np.array([4 + j for j, side in enumerate(state) if side], dtype=int)
        free = np.array([j for j in range(8) if j not in fixed])
        beta = np.zeros(8)
        beta[fixed] = [state[j - 4] * 20 * 150 for j in fixed]
        beta[free] = np.linalg.lstsq(z[:, free], y - z[:, fixed] @ beta[fixed], rcond=None)[0]
        if np.max(np.abs(beta[4:])) > 3000 + 1e-6:
            continue
        candidates.append((float(np.sum((y - z @ beta) ** 2)), beta))
    best_cost = min(c[0] for c in candidates)
    # Pick the minimum-norm representative when unresolved gauges give equal fits.
    beta = min((b for cost, b in candidates if cost <= best_cost + 1e-6), key=np.linalg.norm)
    _, singular, vh = np.linalg.svd(z, full_matrices=False)
    rank = int(np.linalg.matrix_rank(z))
    basis = vh[:rank]
    covariance = SIGMA**2 * (basis.T / singular[:rank] ** 2) @ basis
    return {
        "beta": beta.tolist(),
        "unrestricted_beta": unrestricted.tolist(),
        "data_rank": rank,
        "estimable_projector": (basis.T @ basis).tolist(),
        "conditional_covariance": covariance.tolist(),
        "anchors": kept,
        "observations": len(y),
        "drift_bound_nodes": [j for j in range(4) if abs(beta[j + 4]) >= 2999.9],
        "core_rms_hz": float(np.sqrt(best_cost / len(y))),
        "historical_priors": False,
        "linear_calibration_observations": 0,
    }


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    tracks, input_hashes = load_tracks()
    anchors_out, edges_out, shifts_out, counts_out, refits = [], [], [], [], {}
    provenance = dict(input_hashes)
    for filename in (
        "tools/prototype_multilane_tracklets.py",
        "tools/compare_dsx01_graph_receivers.py",
        "tools/model_dsx01_receiver_tracklets.py",
        "tools/validate_multilane_tracklets.py",
        "reports/2026_10_17_dsx01_receiver_model/results.json",
    ):
        provenance[filename] = hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()
    for index in range(1, 6):
        source = f"S{index:02}"
        cohort = [t for t in tracks if t["source_id"] == source]
        mapping = {t["key"]: t for t in cohort}
        path = OUTPUT / "rf_scaled" / source / "results.json"
        provenance[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        item = json.loads(path.read_text())
        cal = item["calibration"]
        curved_only = curved_data_fit(item["anchors"], mapping)
        # JSON round trips tuples as lists; preserve prototype initialization semantics.
        for anchor in item["anchors"]:
            anchor["group_edge"] = tuple(anchor["group_edge"])
        evidence = [pair_evidence(p, mapping) for p in item["anchors"]]
        strong = [
            copy.deepcopy(p)
            for p, e in zip(item["anchors"], evidence, strict=True)
            if e["curvature_compatible"]
        ]
        for p, e in zip(item["anchors"], evidence, strict=True):
            anchors_out.append({"source_id": source, "group_edge": str(p["group_edge"]), **e})
        # Sensitivity refit retains the original prior, alias search and budget.
        # A stable refit is not independent evidence: historical priors reuse data.
        print(source, "anchors", len(evidence), "curved", len(strong), flush=True)
        refit = fit_calibration(cohort, strong, True) if len(strong) >= 4 else None
        full_replay = fit_calibration(cohort, copy.deepcopy(item["anchors"]), True)
        proposed_replay = fit_calibration(cohort, calibration_anchors(cohort, True), True)
        np.testing.assert_allclose(proposed_replay["beta"], cal["beta"], atol=0.05, rtol=0)
        refits[source] = {
            "calibration": refit,
            "retained_anchors": strong,
            "full_retained_anchor_restart": full_replay,
            "prior_free_fixed_hypothesis_curved_fit": curved_only,
            "original_proposals_reproduction_max_beta_difference": float(
                np.max(np.abs(np.asarray(proposed_replay["beta"]) - cal["beta"]))
            ),
        }
        for name, ga, gb in RELATIONS:
            v = np.zeros(8)
            v[ga], v[gb] = 1, -1
            vd = np.roll(v, 4) / 150
            beta = np.asarray(cal["beta"])
            cov = np.asarray(cal["conditional_covariance"])
            direct = [
                e
                for p, e in zip(item["anchors"], evidence, strict=True)
                if set(p["group_edge"]) == {ga, gb}
            ]
            row = {
                "source_id": source,
                "relationship": name,
                "offset_hz": float(v @ beta),
                "drift_hz_s": float(vd @ beta),
                "conditional_offset_se_hz": float(np.sqrt(max(0, v @ cov @ v))),
                "conditional_drift_se_hz_s": float(np.sqrt(max(0, vd @ cov @ vd))),
                "direct_anchors": len(direct),
                "direct_both_active": sum(e["both_active"] for e in direct),
                "direct_curvature_compatible": sum(e["curvature_compatible"] for e in direct),
                "any_node_at_bound": any(cal["groups"][g]["drift_bound_active"] for g in (ga, gb)),
                "full_restart_offset_change_hz": float(
                    v @ (np.asarray(full_replay["beta"]) - beta)
                ),
                "full_restart_drift_change_hz_s": float(
                    vd @ (np.asarray(full_replay["beta"]) - beta)
                ),
            }
            if refit:
                rb = np.asarray(refit["beta"])
                row.update(
                    curved_refit_offset_change_hz=float(v @ (rb - beta)),
                    curved_refit_drift_change_hz_s=float(vd @ (rb - beta)),
                    curved_refit_data_rank=refit["data_normal_rank"],
                    curved_refit_bound_nodes=sum(g["drift_bound_active"] for g in refit["groups"]),
                )
            if curved_only:
                cb = np.asarray(curved_only["beta"])
                cc = np.asarray(curved_only["conditional_covariance"])
                projector = np.asarray(curved_only["estimable_projector"])
                estimable = bool(np.linalg.norm(v - projector @ v) < 1e-7)
                row.update(
                    prior_free_estimable=estimable,
                    prior_free_offset_hz=float(v @ cb) if estimable else None,
                    prior_free_drift_hz_s=float(vd @ cb) if estimable else None,
                    prior_free_offset_se_hz=float(np.sqrt(max(0, v @ cc @ v)))
                    if estimable
                    else None,
                    prior_free_drift_se_hz_s=float(np.sqrt(max(0, vd @ cc @ vd)))
                    if estimable
                    else None,
                    prior_free_bound_nodes=str(curved_only["drift_bound_nodes"]),
                )
            shifts_out.append(row)
        real_edges = [pair_evidence(p, mapping) for p in item["result"]["accepted_edges"]]
        for p, e in zip(item["result"]["accepted_edges"], real_edges, strict=True):
            edges_out.append({"source_id": source, "kind": p["kind"], **e})
        counts_out.append(
            {
                "source_id": source,
                "dataset": "real",
                "seed": "",
                "joins": len(real_edges),
                "both_active": sum(e["both_active"] for e in real_edges),
                "curvature_compatible": sum(e["curvature_compatible"] for e in real_edges),
            }
        )
        for seed in (41, 142, 243):
            cp = OUTPUT / "controls" / f"rf_scaled-{source}-{seed}.json"
            provenance[str(cp.relative_to(ROOT))] = hashlib.sha256(cp.read_bytes()).hexdigest()
            control = json.loads(cp.read_text())
            cm = {t["key"]: t for t in shift_lanes(cohort, seed)}
            control_edges = control.get("result", control)["accepted_edges"]
            ce = [pair_evidence(p, cm) for p in control_edges]
            counts_out.append(
                {
                    "source_id": source,
                    "dataset": "time_shift_control",
                    "seed": seed,
                    "joins": len(ce),
                    "both_active": sum(e["both_active"] for e in ce),
                    "curvature_compatible": sum(e["curvature_compatible"] for e in ce),
                }
            )
    for name, rows in (
        ("anchors", anchors_out),
        ("accepted-edges", edges_out),
        ("offset-evidence", shifts_out),
        ("screening-counts", counts_out),
    ):
        # Some rows have unavailable fit metrics; emit the union of columns explicitly.
        keys = list(dict.fromkeys(k for row in rows for k in row))
        write_csv(DEST / f"{name}.csv", [{k: row.get(k) for k in keys} for row in rows])
    (DEST / "curved-anchor-refits.json").write_text(json.dumps(refits, indent=2) + "\n")
    provenance["source_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (DEST / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    for ax, rows, title in (
        (axes[0], anchors_out, "Calibration anchor overlaps"),
        (axes[1], edges_out, "Accepted candidate joins"),
    ):
        for source in (f"S{i:02}" for i in range(1, 6)):
            subset = [
                r
                for r in rows
                if r["source_id"] == source
                and "left_nonlinear_rms_hz" in r
                and "right_nonlinear_rms_hz" in r
            ]
            ax.scatter(
                [r["left_nonlinear_rms_hz"] for r in subset],
                [r["right_nonlinear_rms_hz"] for r in subset],
                label=source,
                alpha=0.65,
                s=20,
            )
        ax.axvline(150, color="grey", ls="--")
        ax.axhline(150, color="grey", ls="--")
        ax.set_xscale("symlog", linthresh=20)
        ax.set_yscale("symlog", linthresh=20)
        ax.set(
            xlabel="Left: measured nonlinear RMS (Hz)",
            ylabel="Right: measured nonlinear RMS (Hz)",
            title=title,
        )
        ax.set_xlim(left=0)
        ax.set_ylim(bottom=0)
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    fig.suptitle(
        "Curvature beyond the best straight line on actual overlap samples\n"
        "Dashed: 150 Hz effect-size threshold; sample support and shape compatibility also required"
    )
    fig.savefig(DEST / "active-curvature.png", dpi=160)
    plt.close(fig)
    totals = Counter()
    for row in counts_out:
        key = "real" if row["dataset"] == "real" else str(row["seed"])
        for field in ("joins", "both_active", "curvature_compatible"):
            totals[key, field] += row[field]
    print(dict(totals), flush=True)


if __name__ == "__main__":
    main()
