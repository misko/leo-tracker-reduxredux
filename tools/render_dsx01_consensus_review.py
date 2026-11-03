"""Render tables and scientific figures from completed four-variant experiments."""

from __future__ import annotations

import csv
import hashlib
import json
from itertools import combinations
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from compare_dsx01_graph_receivers import ROOT, load_tracks, wrap, write_csv
from evaluate_dsx01_consensus_calibration import DEST, METHODS
from prototype_multilane_tracklets import save_figure
from report_dsx01_learned_shifts import RELATIONS

NAMES = {
    "ransac": "RANSAC consensus",
    "compatibility": "Compatibility beam",
    "trimmed": "Trimmed least squares",
    "em": "EM-style mixture",
}


def partition_pairs(ownership):
    clusters = {}
    for key, owner in ownership.items():
        clusters.setdefault(owner, []).append(key)
    return {tuple(sorted(pair)) for keys in clusters.values() for pair in combinations(keys, 2)}


def markdown_table(rows, columns):
    def cell(value):
        if value is None:
            return "—"
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(value)

    return "\n".join(
        [
            "| " + " | ".join(label for _, label in columns) + " |",
            "| " + " | ".join("---" for _ in columns) + " |",
            *("| " + " | ".join(cell(row.get(key)) for key, _ in columns) + " |" for row in rows),
        ]
    )


def main():
    rows = list(csv.DictReader((DEST / "scan-metrics.csv").open()))
    assert len(rows) == 80, "Expected 20 real and 60 calibration-relearned control cases"
    manifest = {}
    tracks, _ = load_tracks()
    raw_path = ROOT / "reports/2026_10_16_dsx01_fast_association_losses/context-observations.jsonl"
    raw = [json.loads(line) for line in raw_path.read_text().splitlines()]
    assert len(raw) == 20084
    totals, shifts, scans, pairwise, track_rows = [], [], [], [], []
    real = {}
    for method in METHODS:
        items = []
        for source in (f"S{i:02}" for i in range(1, 6)):
            path = DEST / "real" / source / method / "results.json"
            item = json.loads(path.read_text())
            real[source, method] = item
            items.append(item)
            result, cal = item["result"], item["calibration"]
            row = next(
                r
                for r in rows
                if r["source_id"] == source and r["method"] == method and r["dataset"] == "real"
            )
            assert result["output_tracks"] == int(row["output_tracks"])
            assert len(result["accepted_edges"]) == int(row["links"])
            assert result["associated_points"] == int(row["associated_points"])
            selected_keys = [p[k] for p in cal["selected_pairs"] for k in ("left_key", "right_key")]
            assert len(selected_keys) == len(set(selected_keys))
            assert not cal["historical_calibration_used"]
            if cal["ensemble_eligible"]:
                assert cal["coordinate_stationarity_hz"] <= 1.0
            for fit in result["merged_groups"]:
                owner = result["ownership"][next(iter(fit["members"]))]
                track_rows.append(
                    {
                        "method": method,
                        "source_id": source,
                        "group_index": sum(r["method"] == method for r in track_rows),
                        "component": owner,
                        "points": fit["points"],
                        "fragments": len(fit["members"]),
                        "degree": fit["degree"],
                        "rms_native_hz": fit["rms_hz"],
                        "max_residual_native_hz": fit["max_residual_hz"],
                        "fully_supported": fit["fully_supported"],
                        "members": ";".join(sorted(fit["members"])),
                    }
                )
            scans.append(
                {
                    "scan": source,
                    "method": NAMES[method],
                    "tracks": result["output_tracks"],
                    "links": len(result["accepted_edges"]),
                    "cross_lane_links": int(row["cross_lane_links"]),
                    "calibration_pairs": len(cal["selected_pairs"]),
                    "linear_calibration_pairs": sum(
                        p["degree"] <= 1 for p in cal["selected_pairs"]
                    ),
                    "curved_calibration_pairs": sum(
                        p["active_curvature"] for p in cal["selected_pairs"]
                    ),
                    "rank": cal["data_rank"],
                    "redundancy_dof": cal["redundancy_degrees_of_freedom"],
                    "ensemble_eligible": cal["ensemble_eligible"],
                }
            )
            beta = np.array(cal["beta"])
            covariance = np.array(cal["conditional_covariance"])
            projector = np.array(cal["estimable_projector"])
            for name, ga, gb in RELATIONS:
                v = np.zeros(8)
                v[ga], v[gb] = 1, -1
                vd = np.roll(v, 4) / 150
                estimable = np.linalg.norm(v - v @ projector) < 1e-7
                shifts.append(
                    {
                        "source_id": source,
                        "method": method,
                        "relationship": name,
                        "offset_at_150s_hz": float(v @ beta) if estimable else None,
                        "drift_hz_s": float(vd @ beta) if estimable else None,
                        "estimable": bool(estimable),
                        "conditional_offset_se_hz": float(np.sqrt(max(0, v @ covariance @ v)))
                        if estimable
                        else None,
                        "conditional_drift_se_hz_s": float(np.sqrt(max(0, vd @ covariance @ vd)))
                        if estimable
                        else None,
                        "ensemble_eligible": cal["ensemble_eligible"],
                        "either_node_bound": any(
                            cal["groups"][g]["drift_bound_active"] for g in (ga, gb)
                        ),
                    }
                )
        fits = [fit for item in items for fit in item["result"]["merged_groups"]]
        associated = sum(item["result"]["associated_points"] for item in items)
        final_tracks = sum(item["result"]["output_tracks"] for item in items)
        merged_points = sum(fit["points"] for fit in fits)
        assert associated == 18338
        method_rows = [r for r in rows if r["method"] == method and r["dataset"] == "real"]
        controls = [r for r in rows if r["method"] == method and r["dataset"] != "real"]
        null_cross = [
            sum(int(r["cross_lane_links"]) for r in controls if int(r["seed"]) == seed)
            for seed in (41, 142, 243)
        ]
        null_within = [
            sum(int(r["within_lane_links"]) for r in controls if int(r["seed"]) == seed)
            for seed in (41, 142, 243)
        ]
        totals.append(
            {
                "method": method,
                "name": NAMES[method],
                "associated_points": associated,
                "percent_associated": 100 * associated / len(raw),
                "tracks": final_tracks,
                "mean_points_per_track": associated / final_tracks,
                "links": 676 - final_tracks,
                "cross_lane_links": sum(int(r["cross_lane_links"]) for r in method_rows),
                "merged_points": merged_points,
                "percent_all_points_in_merged_groups": 100 * merged_points / len(raw),
                "rms_native_hz": float(
                    np.sqrt(sum(f["rms_hz"] ** 2 * f["points"] for f in fits) / merged_points)
                ),
                "merged_groups": len(fits),
                "fully_supported_groups": sum(f["fully_supported"] for f in fits),
                "linear_merged_groups": sum(f["degree"] <= 1 for f in fits),
                "linear_calibration_pairs": sum(
                    p["degree"] <= 1
                    for item in items
                    for p in item["calibration"]["selected_pairs"]
                ),
                "null_cross_lane_links": "/".join(map(str, null_cross)),
                "null_within_lane_links": "/".join(map(str, null_within)),
                "null_cross_lane_max": max(null_cross),
                "median_compute_seconds": float(
                    np.median([float(r["compute_seconds"]) for r in method_rows])
                ),
                "median_shared_setup_seconds": float(
                    np.median([float(r["shared_candidate_seconds"]) for r in method_rows])
                ),
                "median_calibration_seconds": float(
                    np.median([float(r["calibration_seconds"]) for r in method_rows])
                ),
                "median_fusion_seconds": float(
                    np.median([float(r["fusion_seconds"]) for r in method_rows])
                ),
            }
        )
    pairsets = {
        method: set().union(
            *(
                partition_pairs(real[source, method]["result"]["ownership"])
                for source in (f"S{i:02}" for i in range(1, 6))
            )
        )
        for method in METHODS
    }
    for a, b in combinations(METHODS, 2):
        common, union = len(pairsets[a] & pairsets[b]), len(pairsets[a] | pairsets[b])
        pairwise.append(
            {
                "method_a": a,
                "method_b": b,
                "fragment_pairs_a": len(pairsets[a]),
                "fragment_pairs_b": len(pairsets[b]),
                "common_fragment_pairs": common,
                "jaccard": common / union if union else 1.0,
            }
        )
    common_core = []
    for source in (f"S{i:02}" for i in range(1, 6)):
        buckets = {}
        for track in (t for t in tracks if t["source_id"] == source):
            signature = tuple(real[source, m]["result"]["ownership"][track["key"]] for m in METHODS)
            buckets.setdefault(signature, []).append(track)
        for members in buckets.values():
            if len(members) >= 2:
                common_core.append(
                    {
                        "source_id": source,
                        "fragments": len(members),
                        "points": sum(len(t["times"]) for t in members),
                        "lanes": len({(t["receiver"], t["channel"]) for t in members}),
                        "members": ";".join(sorted(t["key"] for t in members)),
                    }
                )
    write_csv(DEST / "method-comparison.csv", totals)
    write_csv(DEST / "calibration-shifts.csv", shifts)
    write_csv(DEST / "real-scan-summary.csv", scans)
    write_csv(DEST / "pairwise-partitions.csv", pairwise)
    write_csv(DEST / "merged-track-metrics.csv", track_rows)
    write_csv(DEST / "common-membership-core.csv", common_core)

    colors = plt.get_cmap("tab10")(np.arange(4))
    labels = [r["name"] for r in totals]
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    panels = [
        ("tracks", "Final candidate components", "Components"),
        ("merged_points", "GLRT points in joined components", "Original GLRT points"),
        ("rms_native_hz", "Joined-point native residual RMS", "Hz"),
        ("cross_lane_links", "Joins across RX/channels", "Accepted links"),
    ]
    for ax, (field, title, ylabel) in zip(axes.flat, panels, strict=True):
        values = [r[field] for r in totals]
        ax.bar(np.arange(4), values, color=colors)
        for i, value in enumerate(values):
            ax.text(
                i,
                value,
                f"{value:.1f}" if field == "rms_native_hz" else str(value),
                ha="center",
                va="bottom",
                fontsize=9,
            )
        ax.set(title=title, ylabel=ylabel, xticks=np.arange(4), xticklabels=labels)
        ax.tick_params(axis="x", labelrotation=18, labelsize=8)
        ax.grid(axis="y", alpha=0.2)
    axes[0, 0].axhline(676, ls="--", color="grey", label="Original Graph fragments")
    axes[0, 0].legend(fontsize=8)
    axes[1, 1].scatter(
        np.arange(4),
        [r["null_cross_lane_max"] for r in totals],
        marker="x",
        color="black",
        s=60,
        label="Maximum per full control replay",
    )
    axes[1, 1].legend(fontsize=8)
    fig.suptitle(
        "DSX01 · four ensemble-calibration variants · all five scans\n"
        "18,338 / 20,084 points associated in every variant; fusion changes grouping"
    )
    save_figure(fig, DEST, "comparison")
    fig, ax = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
    bottom = np.zeros(4)
    for field, label in (
        ("median_shared_setup_seconds", "Candidates + shared hypotheses"),
        ("median_calibration_seconds", "Variant calibration"),
        ("median_fusion_seconds", "Frozen-calibration fusion"),
    ):
        values = np.array([r[field] for r in totals])
        ax.bar(np.arange(4), values, bottom=bottom, label=label)
        bottom += values
    ax.set(
        xticks=np.arange(4),
        xticklabels=labels,
        ylabel="Seconds per scan",
        title="Observed host compute time · sum of phase medians\n"
        "Each method charged full shared setup; excludes plotting and serialization",
    )
    ax.legend(fontsize=8)
    save_figure(fig, DEST, "runtime")

    fig, axes = plt.subplots(2, 2, figsize=(14, 8), constrained_layout=True)
    for ax, method in zip(axes.flat, METHODS, strict=True):
        for index in range(1, 6):
            selected = [
                r for r in track_rows if r["method"] == method and r["source_id"] == f"S{index:02}"
            ]
            ax.scatter(
                [r["group_index"] for r in selected],
                [r["rms_native_hz"] for r in selected],
                s=16,
                label=f"S{index:02}",
                alpha=0.8,
            )
        ax.axhline(150, color="grey", ls="--", lw=1)
        ax.set(
            title=NAMES[method],
            xlabel="Joined component index (see track metrics CSV)",
            ylabel="Native residual RMS (Hz)",
            ylim=(0, 300),
        )
        ax.grid(alpha=0.2)
        ax.legend(fontsize=7, ncols=5)
    fig.suptitle(
        "Every joined component's native residual RMS · all five scans\n"
        "Remaining singleton fragments retain their original Graph fits"
    )
    save_figure(fig, DEST, "track-rms")

    # S01 native GLRT view includes all raw observations, including unresolved points.
    fig, axes = plt.subplots(4, 1, figsize=(16, 15), sharex=True, constrained_layout=True)
    cohort = [t for t in tracks if t["source_id"] == "S01"]
    native = [r for r in raw if r["source_id"] == "S01"]
    known = {oid for t in cohort for oid in t["observation_ids"]}
    missing = [r for r in native if r["observation_id"] not in known]
    for ax, method in zip(axes, METHODS, strict=True):
        result = real["S01", method]["result"]
        owners = result["ownership"]
        merged_owners = {owners[next(iter(f["members"]))] for f in result["merged_groups"]}
        palette = {
            owner: plt.get_cmap("turbo")(i / max(1, len(merged_owners) - 1))
            for i, owner in enumerate(sorted(merged_owners))
        }
        for t in cohort:
            owner = owners[t["key"]]
            ax.scatter(
                t["times"],
                wrap(t["values"]) / 1000,
                s=5,
                color=palette.get(owner, "#bfc3c7"),
                alpha=0.65,
                marker="o" if t["receiver"] == 1 else "^",
            )
        ax.scatter(
            [r["time_s"] for r in missing],
            wrap(np.array([r["measured_cfo_hz"] for r in missing])) / 1000,
            color="black",
            marker="x",
            s=8,
            alpha=0.45,
            label="Unassociated GLRT",
        )
        ax.set(
            title=(
                f"{NAMES[method]} · {result['input_tracks']} → {result['output_tracks']} components"
            ),
            ylabel="Wrapped native CFO (kHz)",
            xlim=(0, 300),
        )
        ax.grid(alpha=0.2)
    axes[-1].set_xlabel("Seconds within S01")
    axes[0].legend(fontsize=8)
    fig.suptitle(
        "S01 · all 4,797 original GLRT points\n"
        "Color = joined component; gray = separate Graph fragment; black × = unresolved\n"
        "Circles RX1, triangles RX2; all eight channels overlaid"
    )
    save_figure(fig, DEST, "S01-native-glrt")

    table = markdown_table(
        totals,
        [
            ("name", "Variant"),
            ("percent_associated", "% associated"),
            ("tracks", "Components"),
            ("mean_points_per_track", "GLRT / component"),
            ("cross_lane_links", "Cross-lane joins"),
            ("merged_points", "Points in joins"),
            ("rms_native_hz", "Native RMS (Hz)"),
            ("null_cross_lane_links", "Control cross-lane joins, three seeds"),
            ("median_compute_seconds", "Median host compute (s/scan)"),
        ],
    )
    scan_table = markdown_table(
        scans,
        [
            ("scan", "Scan"),
            ("method", "Variant"),
            ("tracks", "Components"),
            ("cross_lane_links", "Cross-lane joins"),
            ("calibration_pairs", "Cal pairs"),
            ("linear_calibration_pairs", "Linear cal pairs"),
            ("curved_calibration_pairs", "Both curved"),
            ("rank", "Rank / 8"),
            ("redundancy_dof", "Redundancy DOF"),
        ],
    )
    pairwise_table = markdown_table(
        pairwise,
        [
            ("method_a", "Variant A"),
            ("method_b", "Variant B"),
            ("common_fragment_pairs", "Common co-clustered fragment pairs"),
            ("jaccard", "Co-membership Jaccard"),
        ],
    )
    support_rows = []
    for method in METHODS:
        support = [r for r in scans if r["method"] == NAMES[method]]
        total = sum(r["calibration_pairs"] for r in support)
        linear = sum(r["linear_calibration_pairs"] for r in support)
        curved = sum(r["curved_calibration_pairs"] for r in support)
        support_rows.append(
            {
                "method": NAMES[method],
                "pairs": total,
                "linear": linear,
                "curved": curved,
                "weak": total - linear - curved,
            }
        )
    support_table = markdown_table(
        support_rows,
        [
            ("method", "Variant"),
            ("pairs", "Calibration pairs"),
            ("linear", "Both degree ≤1"),
            ("weak", "Weak/one-sided curvature"),
            ("curved", "Both actively curved"),
        ],
    )
    links = "\n".join(
        f"| S{i:02} | "
        + " | ".join(f"[{NAMES[m]}](real/S{i:02}/{m}/overview.png)" for m in METHODS)
        + " |"
        for i in range(1, 6)
    )
    report = f"""# DSX01: four shared ensemble-calibration variants

## Motivation

Learn scan-specific receiver/band offsets and drifts without allowing one linear
track pair to justify its own calibration. Several different linear trajectories
can provide evidence when one shared correction explains them all. Curved tracks
remain valuable identity evidence. Every method allows unmatched hypotheses.

## Problem

Local residual whiteness and an overdetermined numerical fit do not establish
correct correspondence. Alias choices, candidate selection, correlated channel
copies and weak calibration directions must be included in the evaluation.

## Solution

Four separate optimizers share the same original observations, candidate pool,
native alias bounds, physical drift limits and final fusion checks:

1. **RANSAC consensus:** random disjoint subsets generate shared-calibration
   hypotheses, followed by maximum-consensus selection and hard local refinement.
2. **Compatibility beam:** bounded search over jointly consistent correspondence
   sets, with skip branches, fragment exclusivity and six retained beam states.
   This is an approximate beam search, not an exact maximum-clique/JCBB solver.
3. **Trimmed least squares:** repeated selection of the best disjoint, evidence-cell
   balanced subset and shared bounded least-squares fitting, followed by consensus.
4. **EM-style mixture:** soft correspondence/unique-alias probabilities, explicit
   unmatched mass, approximate fragment capacities and evidence-cell balancing.
   The final hard consensus is validated identically to the other methods. Capacity
   normalization means this is not exact one-to-one EM with a monotonic objective.

## Results

{table}

**Trimmed least squares is the preliminary candidate for further work:** it
produces 456 components and 10,176 points in joined groups, with no cross-lane
joins observed in the three full control replays. RANSAC has the lowest measured
host compute time. EM has the lowest joined-point RMS, but its selected point set
differs, so that is not evidence of better identity accuracy.

Compatibility produces two cross-channel joins in the S05, seed-243 control.
That false-consensus case has six selected calibration pairs, data rank eight,
four redundant affine constraints and good numerical stationarity. It directly
demonstrates that an overdetermined, noise-compatible fit can still choose wrong
correspondences. These controls were retained; acceptance thresholds were not
retuned to erase the observed failure. Three negative-control replays are too few
to certify any method's physical identity accuracy.

All variants retain the same **18,338 / 20,084 = 91.31%** Graph-associated points.
The remaining **1,746** detections are unresolved in all four. This experiment
changes fragment grouping, not original point association. GLRT/component includes
both joined components and separate original fragments. Joined-point RMS values
cover different selected observations and cannot establish better identity accuracy.

![Five-scan comparison](comparison.png)

{scan_table}

{support_table}

On DSX01 only a few selected calibration overlaps are strictly linear by BIC.
Many others have weak or one-sided curvature, while 38–44 pairs per variant
have strong curvature in both tracks. These are mixed-ensemble results; the
pure-linear identifiability claim is independently exercised by the synthetic
seven-pair experiment. Polynomial degree alone does not supply identity confidence.

The original Graph baseline has 676 fragments. The earlier exploratory RF-scaled
prototype had 465 components under different calibration and acceptance rules;
that count is a historical reference, not a matched accuracy benchmark.

![Every joined component's RMS](track-rms.png)

The [per-track table](merged-track-metrics.csv) identifies every plotted component,
its original members, point count, degree, RMS, maximum residual and support status.

{pairwise_table}

Co-membership compares all unordered pairs of original fragments in a shared final
component, including transitive membership. It does not confuse different choices
of tree edges with different partitions, and does not use satellite identity labels.
All four variants agree on {len(common_core)} non-singleton membership groups,
containing {sum(r["points"] for r in common_core)} original GLRT points. This
[shared membership view](common-membership-core.csv) is a post-hoc intersection
of partitions, not a fifth fitted method or proof of physical identity.

## Method and safeguards

Each scan has four additive hardware paths: RX1 low/high and RX2 low/high. All
eight native offset/drift coordinates are shared over the scan. Fit native
`y = q * p(t) + a[path] + d[path] * (t - 150)` with known carrier ratio `q` and
degree 0–4 complexity-penalized shared curves. Native integer aliases are applied
before RF scaling. There is no learned RF coefficient, satellite/orbital identity,
historical calibration prior, permanent holdout, new RF collection or localization.

Calibration candidates require at least 10 seconds of actual overlap and 12
original points on each side. Independently BIC-selected degrees determine the
nuisance shared polynomial. Profiling that polynomial compresses each candidate
to two whitened affine constraints; interpolation does not add measurements.
An orthogonal residual RMS above 200 Hz rejects incompatible nonlinear shapes.
Both strongly curved and linear candidates are allowed.

All methods use one common deterministic bank: zero initialization, up to 16
single-pair seeds and 72 random subset seeds. Random subsets alternate between
curvature-prioritized and unrestricted pools. RANSAC refines 12 starts; beam search
uses four starts and at most 80 candidate expansions per start; trimming and EM
use eight starts. These are bounded research budgets, not claims of exhaustive
search or identical optimizer work. Every variant then receives the same maximum
24-round hard-consensus polishing step.

Offsets occupy the canonical ±113,636.36 Hz box; each native path drift is bounded
to ±20 Hz/s. An active-set solver minimizes the eight-coordinate bounded quadratic;
final selected-set coordinate stationarity must be within 1 Hz before calibration
promotion. Bound contact is reported in the shift
table and is not evidence for the physical bound value. The numerical ridge only
chooses representatives of unresolved modes and is excluded from reported data
information. Full rank alone is insufficient.

Calibration support is capped to one selected pair per **45 s × 400 Hz/s**
time/slope evidence cell; no fragment or calibration observation is reused.
These cells are a proxy for independent track families, not known emitter labels.
Promotion requires at least six selected pairs in three time bins spanning at
least 120 seconds. The redundancy DOF is `2 * pairs - data rank`; because matches
and aliases were selected, this is not a chi-square significance test.

Before a join, its particular hardware contrast must be observable, have formal
conditional standard error ≤150 Hz at both overlap/gap ends, remain within 300 Hz
under each selected-cell deletion, and agree within 300 Hz across discovered
calibration modes scoring at least 90% of the winner. Deletions also check rank
loss; remaining correspondence and alias choices stay fixed in these conditional
deletion fits. All selected observations return to the final fit. Native
alias-equivalent changes are compared consistently. The mode search
is bounded; stability is not proof that no other mode exists. Same-path/same-RF
hardware cancels and does not require calibration promotion.

Calibration is then frozen. Every whole-component join, including linear joins,
must improve complexity cost, keep all original residuals below 450 Hz, have no
gap above 10 seconds or slope above 8,000 Hz/s, and pass pooled and per-RX/channel
residual structure checks. Every newly introduced pairwise hardware contrast is
also checked, preventing a weak path from entering indirectly through a bridge.
Fusion is greedy and preserves established native alias branches within a
component. It can miss valid alternative or larger unions; these component counts
are not proven global optima.

## Controls and practical interpretation

There are **60 full control fits**: four methods × five scans × three lane-time
shift seeds (41, 142, 243). Each control independently regenerates candidate
matches, hypotheses and calibration before fusion, using the same budgets.
Tiny wrap-boundary fragments below eight points are excluded; excluded observation
counts are recorded per case. Other measurements, RF metadata and native CFO
values are preserved by the shift transformation.

Cross-RX/channel joins are the relevant false-consensus diagnostic. Same-channel
continuations survive a lane-time shift by construction and are reported separately
in [the numerical comparison](method-comparison.csv). Three replays do not yield a
calibrated false-discovery rate. Residual tests also have finite power, especially
on short fragments. No count here is a verified number of physical transmitters.

The comparison should favor repeatable cross-lane support with low control
consensus, rather than simply the smallest component count. Method disagreements
are available as [pairwise fragment co-membership comparisons](pairwise-partitions.csv).

![Observed host compute](runtime.png)

Runtime is measured on this host, excludes plotting/export, and charges every
method the full shared candidate/hypothesis setup. Sum-of-phase medians in the
figure can differ from the median total in the table. These are not embedded
benchmarks.

## Visual review

![S01 all native GLRT points colored by joined component](S01-native-glrt.png)

Per-scan panels below show the 18,338 Graph-associated observations, calibrated
candidate groups and native residuals. Gray points are separate Graph fragments,
not the 1,746 unresolved GLRT detections. The S01 figure above includes all raw
detections and shows its unresolved points explicitly.

| Scan | RANSAC | Compatibility | Trimmed | EM |
|---|---|---|---|---|
{links}

## Reproduction and validation

```bash
.venv/bin/python tools/evaluate_dsx01_consensus_calibration.py
.venv/bin/python tools/render_dsx01_consensus_review.py
.venv/bin/python -m pytest -q tests/analysis/test_dsx01_consensus_calibration.py
```

Synthetic tests cover each optimizer's recovery and joining of seven independent
linear pairs with native aliases, single-pair abstention, correlated-copy vote
limits, cross-band alias arithmetic, unobservable paths and short temporal support.
The bounded solver is independently checked against exhaustive enumeration of
active drift-bound configurations on a coupled quadratic. The 13 new cases plus
the existing offset, multilane, receiver and cohort suites total 50 passing tests.
Every real/control output is independently audited for original-point ownership,
native residual arithmetic, degrees, gaps, analytic slope extrema and stored flags.

- [Aggregate method table](method-comparison.csv)
- [Twenty real scan summaries](real-scan-summary.csv)
- [All 80 real/control metric rows](scan-metrics.csv)
- [All 80 receiver/band contrast estimates and conditional precision](calibration-shifts.csv)
- [Every joined track's original members and residual metrics](merged-track-metrics.csv)
- [Input/source hashes and search configuration](provenance.json)
- [Complete artifact hashes](artifact-manifest.json)

Per-case results store calibration alternatives, selected original pairs and
native aliases, cell deletion fits, rejection counts, final ownership and shared
polynomials. Per-case observations CSVs preserve every eligible input observation.
The original published analyses and fixtures are unchanged.
"""
    (DEST / "README.md").write_text(report)
    for path in sorted(DEST.rglob("*")):
        if path.is_file() and path.name not in ("artifact-manifest.json", "render-provenance.json"):
            manifest[str(path.relative_to(DEST))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (DEST / "artifact-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (DEST / "render-provenance.json").write_text(
        json.dumps(
            {
                "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "raw_observation_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                "artifact_count": len(manifest),
                "real_cases": 20,
                "control_cases": 60,
            },
            indent=2,
        )
        + "\n"
    )
    print(table)
    print(f"Validated and rendered {len(manifest)} artifact hashes.")


if __name__ == "__main__":
    main()
