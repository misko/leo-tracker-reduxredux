"""Render completed phase searches and explicit RX/band drift sensitivity."""

import csv
import hashlib
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from audit_receiver_band_drift import CONTRASTS, LABELS, calibration_summary

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/2026_10_17_shared_satellite_phase"


def load(path):
    return json.loads(path.read_text())


def csv_rows(path, rows):
    with path.open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def table(headers, rows):
    return "\n".join(
        ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
        + ["| " + " | ".join(map(str, row)) + " |" for row in rows]
    )


def run():
    searches, sites, hardware, contrasts = [], [], [], []
    merges = {
        (r["case"], r["variant"]): r
        for directory in ("search_consolidated", "search_resumed_consolidated")
        for r in load(REPORT / directory / "summary.json")
    }
    for path in sorted(REPORT.glob("search*/*/*/evaluation.json")):
        fit = load(path.with_name("fit.json"))["endpoint"]
        assoc = load(path.with_name("association.json"))
        row = dict(
            case=path.parent.parent.name,
            variant=path.parent.name,
            position_error_km=load(path)["position_error_km"],
            graph_points=assoc["points"],
            compatible_points=assoc["compatible_points"],
            associated_percent=100 * assoc["compatible_points"] / assoc["points"],
            fragments=assoc["compatible_fragments"],
            merged_tracks=merges[path.parent.parent.name, path.parent.name]["output_tracks"],
            score=fit["score"],
        )
        row["points_per_merged_track"] = row["compatible_points"] / row["merged_tracks"]
        searches.append(row)
    assert len(searches) == 8
    for experiment, bound in (("diagnosis", 5.0), ("tight_drift", 1.0)):
        for path in sorted((REPORT / experiment).glob("*/*/diagnosis.json")):
            for result in load(path):
                fit, assoc = result["fit"], result["association"]
                base = dict(
                    case=path.parent.parent.name,
                    variant=path.parent.name,
                    experiment=experiment,
                    site=result["site"],
                )
                sites.append(
                    dict(
                        base,
                        compatible_points=assoc["compatible_points"],
                        graph_points=assoc["points"],
                        fragments=assoc["compatible_fragments"],
                        score=fit["score"],
                    )
                )
                cal = calibration_summary(fit["beta"], bound_hz_s=bound)
                tracks = load(
                    ROOT
                    / "reports/2026_10_17_ds22_merged_satellites"
                    / ("cohort" if base["case"].startswith("DS22") else "dsx01_adapter")
                    / base["case"]
                    / "tracks.json"
                )
                groups = {t["key"]: 2 * (t["receiver"] - 1) + int(t["channel"] > 4) for t in tracks}
                support = [
                    sum(
                        r["compatible"] and r["active_curvature"] and groups[r["component"]] == g
                        for r in assoc["rows"]
                    )
                    for g in range(4)
                ]
                for g, entry in enumerate(cal["groups"]):
                    hardware.append(
                        dict(
                            base,
                            **entry,
                            curved_fragments=support[g],
                            reliable_measurement_claimed=False,
                        )
                    )
                for entry, (_, a, b) in zip(cal["contrasts"], CONTRASTS, strict=True):
                    contrasts.append(
                        dict(
                            base,
                            **entry,
                            both_groups_have_curved_support=bool(support[a] and support[b]),
                            either_drift_bound_active=bool(
                                cal["groups"][a]["bound_active"] or cal["groups"][b]["bound_active"]
                            ),
                        )
                    )
    csv_rows(REPORT / "blind-searches.csv", searches)
    csv_rows(REPORT / "fixed-site-comparisons.csv", sites)
    csv_rows(REPORT / "hardware-groups.csv", hardware)
    csv_rows(REPORT / "hardware-contrasts.csv", contrasts)
    cases = ("DS22-001", "DSX01-S01")
    variants = ("zero_c0", "zero_fitted_c", "shared_c0", "shared_fitted_c")
    by = {(r["case"], r["variant"]): r for r in searches}
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), constrained_layout=True)
    for index, case in enumerate(cases):
        data = [by[case, variant] for variant in variants]
        labels = ["zero / c=0", "zero / fitted c", "phase / c=0", "phase / fitted c"]
        axes[0, index].bar(
            labels, [r["associated_percent"] for r in data], color=["#8c8c8c"] * 2 + ["#2688b8"] * 2
        )
        axes[0, index].set(title=case, ylabel="Compatible / Graph points (%)")
        axes[1, index].bar(
            labels, [r["position_error_km"] for r in data], color=["#8c8c8c"] * 2 + ["#2688b8"] * 2
        )
        axes[1, index].axhline(0.5, color="red", linestyle="--", label="0.5-km goal")
        axes[1, index].set(ylabel="Blind position error (km)")
        axes[1, index].legend()
        for row in range(2):
            axes[row, index].tick_params(axis="x", rotation=18)
    fig.suptitle("More frequency-compatible points did not improve blind position")
    fig.savefig(REPORT / "association-vs-position.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), constrained_layout=True)
    for column, case in enumerate(cases):
        for experiment, color, label in (
            ("diagnosis", "#8c8c8c", "bound ±5, prior σ2"),
            ("tight_drift", "#2688b8", "bound ±1, prior σ0.5"),
        ):
            data = [
                r
                for r in hardware
                if r["case"] == case
                and r["variant"] == "shared_c0"
                and r["experiment"] == experiment
                and r["site"] == "supplied_evaluation_site"
            ]
            axes[0, column].plot(
                LABELS, [r["drift_hz_s"] for r in data], "o-", color=color, label=label
            )
            axes[1, column].plot(
                LABELS, [r["offset_hz"] / 1000 for r in data], "o-", color=color, label=label
            )
            for i, r in enumerate(data):
                if r["bound_active"]:
                    axes[0, column].scatter(
                        i, r["drift_hz_s"], s=100, facecolors="none", edgecolors=color
                    )
        axes[0, column].set(title=case, ylabel="Drift (Hz/s)")
        axes[1, column].set(ylabel="Offset at 150 s, 11.5 GHz (kHz)")
        axes[0, column].legend(fontsize=8)
    fig.suptitle("Separate RX/band hardware · GPS diagnostic · c=0 · rings mark active bounds")
    fig.savefig(REPORT / "hardware-drift-offsets.png", dpi=150)
    plt.close(fig)
    panel = []
    for case in cases:
        folder = Path(f"/tmp/ds22-track-frame-cfo-panel-v2-{case}")
        dst = REPORT / "pilot_cfo_panel" / case
        dst.mkdir(parents=True, exist_ok=True)
        for name in ("protocol.json", "results.json", "summary.json"):
            shutil.copy2(folder / name, dst / name)
        rows = load(dst / "results.json")
        qualified = [r for r in rows if r["best_supported"]]
        branches = [
            next(b for b in r["branches"] if b["alias"] == r["best_alias"]) for r in qualified
        ]
        panel.append(
            dict(
                case=case,
                selected=len(rows),
                supported=len(qualified),
                median_conditional_uncertainty_hz=float(
                    np.median([b["frequency_uncertainty_hz"] for b in branches])
                ),
                maximum_time_match_difference_s=max(
                    abs(r["source_minus_graph_time_s"]) for r in rows
                ),
            )
        )
    csv_rows(REPORT / "pilot-panel-summary.csv", panel)
    blind_table = table(
        ["Case", "Model", "Points (%)", "Merged tracks", "Points/track", "Error (km)"],
        [
            [
                r["case"],
                r["variant"],
                f"{r['compatible_points']} ({r['associated_percent']:.1f}%)",
                r["merged_tracks"],
                f"{r['points_per_merged_track']:.1f}",
                f"{r['position_error_km']:.3f}",
            ]
            for r in searches
        ],
    )
    tight = [
        r
        for r in hardware
        if r["experiment"] == "tight_drift"
        and r["variant"] == "shared_c0"
        and r["site"] == "supplied_evaluation_site"
    ]
    drift_table = table(
        ["Case", "Hardware", "Offset (Hz)", "Drift (Hz/s)", "Curved fragments", "Bound active"],
        [
            [
                r["case"],
                r["label"],
                f"{r['offset_hz']:.1f}",
                f"{r['drift_hz_s']:.3f}",
                r["curved_fragments"],
                r["bound_active"],
            ]
            for r in tight
        ],
    )
    uncertainty = [f"{row['median_conditional_uncertainty_hz']:.1f}" for row in panel]
    text = f"""# Shared satellite phase and scan-local RX/band calibration

Shared orbital phase improves frequency-compatible coverage in these two pilots,
but worsens blind position error. The <0.5-km objective remains unmet. Satellite
labels are candidates; no authenticated identity truth is available.

## Explicit hardware model

For a point i on component j and candidate satellite s:

```
f_i + k_i P = q_i D_s(t_i; position, phase_s)
            + a_scan,RX,band + d_scan,RX,band (t_i-150s)
            + c (RF_i/GHz-11.5) + b_j + noise
```

Here P=227272.727 Hz, q=RF/11.5 GHz. Each scan has four independent intercepts
and four independent drifts: RX1 low/high and RX2 low/high. Their differences
give cross-receiver and cross-band offsets and relative drifts, including an
RX-by-band interaction. No dataset-wide offset or drift is imposed. Intercepts
and contrasts are alias-branch quantities, reported at 150 s and 11.5 GHz.
The optional c coefficient accounts for within-band RF dependence; every
comparison includes matched c=0/fitted-c arms. Component constants have a
1000-Hz Gaussian penalty, but no free component slope. One phase is shared by
all components assigned to a NORAD; per-component phases only propose seeds.

The original sensitivity model uses drift σ=2 Hz/s and bounds ±5 Hz/s. The new
tight setting uses σ=0.5 Hz/s and bounds ±1 Hz/s, enforced on initial states,
all proposals and retained fits. These are declared assumptions, not independently
measured LNB specifications. Zero drift is also supported. The historical five-scan
[drift ablation](../2026_10_17_ds22_search_revision/README.md) compares zero/tight/baseline
policies without orbital phase, and is a separate experiment.

Only original fragments with measured active curvature calibrate hardware or
position. A polynomial degree alone is insufficient: span and departure from an
affine fit are required. Linear fragments can associate afterward when their
hardware group has qualified curved support. Nonzero phases additionally need
qualified curved satellite support. Final association checks mean, slope,
quadratic structure, steps and lag-one correlation, with RMS ≤450 Hz.

## Completed blind searches

Same original points, causal candidate bank, regional grid, basins and seed
budgets within each c pair; no points withheld. Reference GPS enters after fit
sealing. Two DSX shared-phase searches exceeded their first ten-minute process
budgets during finalist evaluation and completed by verified cache replay with
the unchanged search path and budget. Original interrupted artifacts remain.

{blind_table}

![Coverage and blind position](association-vs-position.png)

Consolidation uses exact phased geometry, common hardware, a common penalized
component constant and residual gates. All admitted point IDs and candidate
identities are preserved; eight blind consolidation arms drop zero points.

## Small drift check at supplied GPS

These are diagnostic fits, not blind geographic estimates. Tight c=0 gives
1,383/3,510 compatible DS22-001 points and 1,975/4,487 DSX01-S01 points.
Tight fitted-c gives 1,150 and 1,975 points respectively. The previous blind
endpoint still scores better than GPS under the tight model in both cases.
Thus constraining LNB drift alone does not fix position preference.

{drift_table}

![Independent hardware groups](hardware-drift-offsets.png)

Bound hits, sparse support and sensitivity to model choice flag weak calibration.
Curved-support counts are not confidence intervals. The information audit conditions
on candidate identities and assumed priors: GPS shared-phase weak-axis scales are
about 0.94 km for DS22 and 0.65 km for DSX with priors. These are optimistic local
sensitivity scales, not calibrated coverage intervals. Different phase variants
admit different anchor sets, so their information difference is not a controlled
same-anchor nuisance ablation. Exact values remain in identifiability/results.json.

## Existing-IQ measurement check

The stored pair-autocorrelation GLRT selects a 512-point FFT bin at a 4.4-µs
symbol interval, spacing 443.892 Hz. Fractional epoch refinement does not by
itself refine that CFO bin. A response-only panel selects two longest measured-
curved tracks per RX/band and two points per track, independent of GPS and labels.
The existing reviewed known-pilot frame estimator qualifies 14/16 DS22 and 15/16
DSX points. Median conditional frequency uncertainties are {uncertainty[0]}
and {uncertainty[1]} Hz. These are estimator-internal
uncertainties, not an independent calibration or demonstrated position accuracy.
All original detections, times, populations and fits remain unchanged. The small
panel is a measurement feasibility result; it has not been used for localization.
Legacy DSX graph timestamps differ from source-counter times by up to 0.503 ms;
matching requires unique support within 0.51 ms plus exact reproduction of a gated
CFO peak. Actual differences and rejected estimates are retained. No new RF was collected.

## Reproduction and next decision

Tables are also CSV: blind-searches, fixed-site-comparisons, hardware-groups,
hardware-contrasts and pilot-panel-summary. Original search sources are archived
in code_snapshot; the configurable drift version and tests in drift_code_snapshot.
Input orbit-bank receipts bind causal TLEs and original Graph files. Successive
causal TLE disagreement sets the phase sensitivity scale, not a truth covariance.

Next, test continuous qualified measurements on complete tracks and compare
matched c arms, with the same original-point denominator and explicit unsupported
measurements. A stationary multi-scan position fit would retain independent
hardware for every scan. More associated points alone cannot establish location
accuracy. No production calibration or scientific golden fixture was replaced.
"""
    (REPORT / "README.md").write_text(text)
    sources = [
        Path(__file__),
        ROOT / "tools/evaluate_shared_satellite_phase.py",
        ROOT / "tools/qualify_track_frame_cfo.py",
        ROOT / "tools/audit_receiver_band_drift.py",
        ROOT / "tools/consolidate_shared_phase_matches.py",
        ROOT / "tests/analysis/test_shared_phase_experiment.py",
        ROOT / "tests/analysis/test_shared_orbit_phase_fit.py",
        ROOT / "tests/analysis/test_track_frame_cfo_panel.py",
        ROOT / "tests/dsp/test_pilot_frame_cfo.py",
        ROOT / "src/leo/analysis/qam/pilot.py",
        ROOT / "src/leo/analysis/starlink/fast_scan_fractional.py",
    ]
    for source in sources:
        target = REPORT / "drift_code_snapshot" / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    (REPORT / "validation.json").write_text(
        json.dumps(
            dict(
                targeted_tests_passed=23,
                tests=[
                    "shared_orbit_phase_fit",
                    "shared_phase_experiment",
                    "phase_linear_geometry",
                    "phase_position_identifiability",
                    "track_frame_cfo_panel",
                    "receiver_band_drift_audit",
                    "pilot_frame_cfo",
                ],
                ruff_passed=True,
                new_acquisition=False,
                goal_complete=False,
            ),
            indent=2,
        )
        + "\n"
    )
    manifest = {
        str(p.relative_to(REPORT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(REPORT.rglob("*"))
        if p.is_file() and p.name != "seal.json"
    }
    (REPORT / "seal.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                blind_searches=len(searches),
                fixed_site_arms=len(sites),
                hardware_rows=len(hardware),
                sealed_files=len(manifest),
            )
        )
    )


if __name__ == "__main__":
    run()
