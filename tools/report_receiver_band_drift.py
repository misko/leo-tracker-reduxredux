"""Render fixed-site drift sensitivity and independently scored position pilots."""
# ruff: noqa: E501

import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/2026_10_17_ds22_search_revision"
LABELS = ("RX1 low", "RX1 high", "RX2 low", "RX2 high")
POLICIES = ("zero", "tight", "baseline")
COLORS = ("#666666", "#2878b5", "#d95319")


def table(headers, rows):
    return "\n".join(
        ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
        + ["| " + " | ".join(map(str, row)) + " |" for row in rows]
    )


def render():
    rows = [
        row
        for path in sorted((REPORT / "drift_sensitivity").glob("*/summary.json"))
        for row in json.loads(path.read_text())
    ]
    if len(rows) != 30:
        raise ValueError("all five scans and all six matched arms required")
    scans = sorted({r["source_id"] for r in rows})
    by = {(r["source_id"], r["policy"], r["fitted_c"]): r for r in rows}
    fields = [
        "source_id",
        "policy",
        "fitted_c",
        "points",
        "compatible_points",
        "compatible_components",
        "associated_graph_percent",
        "bound_hz_s",
        "sigma_hz_s",
        "penalized_score",
    ]
    with (REPORT / "drift-association.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            out = {k: r[k] for k in fields if k != "associated_graph_percent"}
            out["associated_graph_percent"] = 100 * r["compatible_points"] / r["points"]
            writer.writerow(out)
    plt.rcParams.update({"font.size": 10})
    fig, axes = plt.subplots(2, 4, figsize=(16, 7), sharex=True, sharey=True)
    for c in (False, True):
        for g in range(4):
            ax = axes[int(c), g]
            for policy, color in zip(POLICIES, COLORS, strict=True):
                data = [by[s, policy, c] for s in scans]
                values = [
                    r["calibration"]["groups"][g]["drift_hz_s"]
                    if r["support"][g]["curved_components"] > 0
                    else np.nan
                    for r in data
                ]
                ax.plot(range(5), values, "o-", label=policy, color=color, alpha=0.8)
                for i, r in enumerate(data):
                    if r["calibration"]["groups"][g]["bound_active"] and np.isfinite(values[i]):
                        ax.scatter(i, values[i], s=85, facecolors="none", edgecolors=color)
            ax.axhline(0, color="black", linewidth=0.5)
            ax.set_title(f"{LABELS[g]} · {'fitted c' if c else 'c=0'}")
            ax.set_xticks(range(5), [s[-3:] for s in scans])
            ax.grid(alpha=0.2)
    axes[0, 0].set_ylabel("Drift (Hz/s)")
    axes[1, 0].set_ylabel("Drift (Hz/s)")
    axes[0, 0].legend()
    fig.suptitle(
        "Per-scan hardware drift sensitivity · rings mark active bounds; unsupported groups omitted"
    )
    fig.tight_layout()
    fig.savefig(REPORT / "receiver-band-drift.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(2, 4, figsize=(16, 7), sharex=True)
    endpoints = ((2, 0), (3, 1), (1, 0), (3, 2))
    for c in (False, True):
        for j, (left, right) in enumerate(endpoints):
            ax = axes[int(c), j]
            for policy, color in zip(POLICIES, COLORS, strict=True):
                data = [by[s, policy, c] for s in scans]
                values = [
                    r["calibration"]["contrasts"][j]["offset_hz"] / 1000
                    if all(r["support"][g]["curved_components"] > 0 for g in (left, right))
                    else np.nan
                    for r in data
                ]
                ax.plot(range(5), values, "o-", label=policy, color=color, alpha=0.8)
            ax.set_title(
                rows[0]["calibration"]["contrasts"][j]["label"] + (" · fitted c" if c else " · c=0")
            )
            ax.set_xticks(range(5), [s[-3:] for s in scans])
            ax.grid(alpha=0.2)
    axes[0, 0].set_ylabel("Native offset at 150 s (kHz)")
    axes[1, 0].set_ylabel("Native offset at 150 s (kHz)")
    axes[0, 0].legend()
    fig.suptitle(
        "Receiver and band contrasts modulo 227.273 kHz · 11.5 GHz reference; unsupported contrasts omitted"
    )
    fig.tight_layout()
    fig.savefig(REPORT / "receiver-band-offsets.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
    for c, ax in zip((False, True), axes, strict=True):
        for j, (policy, color) in enumerate(zip(POLICIES, COLORS, strict=True)):
            data = [by[s, policy, c] for s in scans]
            percentages = [100 * r["compatible_points"] / r["points"] for r in data]
            ax.bar(
                np.arange(5) + (j - 1) * 0.25, percentages, width=0.25, color=color, label=policy
            )
        ax.set_xticks(range(5), [s[-3:] for s in scans])
        ax.set_title("fitted c" if c else "c=0")
        ax.grid(axis="y", alpha=0.2)
    axes[0].set_ylabel("Satellite-compatible points / Graph points (%)")
    axes[0].legend()
    fig.suptitle(
        "Same observations, causal candidates and residual gates in every arm · identities unverified"
    )
    fig.tight_layout()
    fig.savefig(REPORT / "drift-association.png", dpi=150)
    plt.close(fig)
    counts, drifts, contrasts = [], [], []
    for s in scans:
        for policy in POLICIES:
            a, b = by[s, policy, False], by[s, policy, True]
            counts.append(
                [
                    s,
                    policy,
                    a["points"],
                    a["compatible_points"],
                    b["compatible_points"],
                    a["compatible_components"],
                    b["compatible_components"],
                ]
            )
            drifts.append(
                [s, policy]
                + [
                    "unsupported"
                    if a["support"][g]["curved_components"] == 0
                    else f"{a['calibration']['groups'][g]['drift_hz_s']:.3f}"
                    + ("*" if a["calibration"]["groups"][g]["bound_active"] else "")
                    for g in range(4)
                ]
            )
        a = by[s, "tight", False]
        contrasts.append(
            [s]
            + [
                f"{a['calibration']['contrasts'][j]['offset_hz']:.1f}"
                if all(a["support"][g]["curved_components"] > 0 for g in pair)
                else "unsupported"
                for j, pair in enumerate(endpoints)
            ]
        )
    search_rows = []
    for path in sorted(REPORT.glob("*/*/*/evaluation.json")):
        fit = json.loads(path.with_name("fit.json").read_text())
        evaluation = json.loads(path.read_text())
        search_rows.append(
            [
                path.parent.parent.name,
                path.parts[-4],
                "fitted c" if fit["fitted_c"] else "c=0",
                f"{evaluation['position_error_km']:.3f}",
                fit["evaluations"],
                f"{fit['score']:.0f}",
            ]
        )
    figure_cases = (
        ("pilots", "DS22-001", "DS22 hard merged"),
        ("fragments", "DS22-001", "DS22 fragments"),
        ("pilots_resumed", "DSX01-S01", "DSX01 hard merged"),
    )
    fig, axes = plt.subplots(2, 3, figsize=(13, 8), sharex=True, sharey=True)
    reference_east = (-122.48574968092912 + 122) * 111.32 * np.cos(np.deg2rad(37.5))
    reference_north = (37.849061591561885 - 37.5) * 111
    for col, (folder, case, label) in enumerate(figure_cases):
        for c in (False, True):
            ax = axes[int(c), col]
            path = REPORT / folder / case / ("fitted_c" if c else "c0") / "fit.json"
            if not path.exists():
                continue
            fit = json.loads(path.read_text())
            points = np.array([r["east_north_km"] for r in fit["trace"]])
            scores = np.array([r["score"] for r in fit["trace"]])
            dots = ax.scatter(
                points[:, 0],
                points[:, 1],
                c=scores / scores.min(),
                s=15,
                cmap="viridis_r",
                vmin=1,
                vmax=2,
                alpha=0.6,
            )
            ax.scatter(
                reference_east, reference_north, marker="*", c="black", s=120, label="Supplied GPS"
            )
            ax.scatter(*fit["east_north_km"], marker="x", c="red", s=70, label="Estimated site")
            ax.set_title(label + (" · fitted c" if c else " · c=0"))
            ax.set_xlim(-70, 0)
            ax.set_ylim(0, 70)
            ax.set_aspect("equal")
            ax.grid(alpha=0.2)
            fig.colorbar(dots, ax=ax, label="Discovery score / panel minimum", shrink=0.75)
    axes[0, 0].legend(fontsize=8)
    axes[0, 0].set_ylabel("North of regional center (km)")
    axes[1, 0].set_ylabel("North of regional center (km)")
    for ax in axes[1]:
        ax.set_xlabel("East of regional center (km)")
    fig.suptitle(
        "Zoom on independently searched basins · full search disk radius 250 km; GPS used after fitting"
    )
    fig.tight_layout()
    fig.savefig(REPORT / "position-search.png", dpi=150)
    plt.close(fig)
    aggregates = []
    for policy in POLICIES:
        a = [by[s, policy, False] for s in scans]
        b = [by[s, policy, True] for s in scans]
        aggregates.append(
            [
                policy,
                sum(r["points"] for r in a),
                sum(r["compatible_points"] for r in a),
                sum(r["compatible_points"] for r in b),
                sum(r["compatible_components"] for r in a),
                sum(r["compatible_components"] for r in b),
            ]
        )
    text = """# Per-scan receiver/band offsets and small LNB drift

All five DSX01 scans completed a matched zero / tight / baseline drift sweep,
each with c=0 and fitted c. These are fixed-site candidate compatibility fits
at the supplied GPS (37.849061591561885, -122.48574968092912), not independent
satellite identities or geographic estimates. Original Graph memberships,
trimmed merged groups, causal orbit candidates and gates remain fixed.

## Physical model and conventions

For original observation i in scan s and receiver/band group g:

`y_i + k_fragment * P = (RF_i / 11.5 GHz) * Doppler_sat(t_i, site) + a_sg + d_sg * (t_i - 150 s) + c_s * (RF_i/GHz - 11.5) + b_component + noise_i`.

There are four scan-local offsets a and four scan-local linear drifts d: RX1
low, RX1 high, RX2 low, RX2 high. This includes different drift for each band.
P=227272.727... native Hz. Aliases are integers per original fragment;
b is one Gaussian constant (sigma=1000 native Hz) per whole merged component,
with no component slope. It represents a declared carrier-bias hypothesis.
The c=0 and fitted-c arms have identical points, candidates, other priors and
160-seed calibration budgets. c has units Hz/GHz here.

Only individually measured-curved fragments calibrate hardware: duration at
least 20 s and RMS departure from their best affine fit at least 250 Hz.
Linear fragments can be associated after calibration. Passing residual tests
is a compatibility condition; it cannot authenticate a satellite identity.
The tests check mean, slope, quadratic improvement, steps and lag-one structure.

Offsets below are modeled **measured differences** at t=150 s, with the RF
coefficient referenced to 11.5 GHz, modulo P. To correct RX2 into RX1's frame,
subtract the RX2-minus-RX1 contrast and its time-dependent drift difference.
At actual RF, also apply the declared RF-dependent term. Cross-band physical
Doppler must be RF-scaled; an additive shift alone is insufficient.

## Small-drift sensitivity

Zero fixes all four drifts to 0. Tight uses a Gaussian prior sigma=0.5 Hz/s
and hard bounds +/-1 Hz/s. Baseline uses sigma=2 Hz/s and bounds +/-5 Hz/s.
These are sensitivity hypotheses, not measured hardware specifications.

![Drift sensitivity](receiver-band-drift.png)

The c=0 drift estimates below are in Hz/s. Asterisks indicate active hard
bounds. “Unsupported” means no curved component passed the calibration gate
for that group at the final fit; its stored numeric value is not a measurement.

"""
    text += table(["Scan", "Policy", *LABELS], drifts)
    text += "\n\n## Receiver and band offsets\n\n"
    text += "The tight, c=0 contrasts below are native Hz at 150 s. Policy stability is not a confidence interval.\n\n"
    text += table(
        ["Scan", "RX2−RX1 low", "RX2−RX1 high", "RX1 high−low", "RX2 high−low"], contrasts
    )
    text += "\n\n![Offset sensitivity](receiver-band-offsets.png)\n\n"
    text += "## Candidate association coverage\n\nThe denominator is the 18,338 original points assigned to Graph tracks. The earlier all-winning-GLRT denominator is 20,084. These hard-merged candidate results do not replace the safer fragment/consolidation results in the preceding report.\n\n"
    text += table(
        [
            "Policy",
            "Graph points",
            "Points c=0",
            "Points fitted c",
            "Components c=0",
            "Components fitted c",
        ],
        aggregates,
    )
    text += "\n\n![Association sensitivity](drift-association.png)\n\n"
    text += table(
        [
            "Scan",
            "Policy",
            "Graph points",
            "Points c=0",
            "Points fitted c",
            "Components c=0",
            "Components fitted c",
        ],
        counts,
    )
    text += "\n\n## Confidence and geographic evidence\n\n"
    text += "The drift estimates depend on the prior and frequently reach bounds. Scan 2 RX2 high has no qualified curved support. Scan 4 RX2 high has only one qualified curved component in the c=0 fits. Neither should calibrate cross-receiver/band joins without more evidence. Stable offsets across drift policies are encouraging, but identity/alias ambiguity and prior dependence remain. No bootstrap confidence interval or authenticated identity probability is claimed.\n\n"
    text += "The earlier failed DS22 endpoint scored worse than the supplied site when both were evaluated on identical full observations: 1,330,415,647 versus 748,858,313 (c=0, 1000-Hz component bias). Both compressed observations and a four-seed calibration retain that correct-site preference. The supplied site was used only for diagnosis; no state from that diagnostic seeds the new uniform regional search.\n\n"
    text += "The revised search uses an 81-point, 50-km regional grid, three separated basins and all original Graph observations throughout. Eight finalists use the full 160-seed calibration. Cached prepared orbital geometry agrees with the old implementation to about 1e-8 Hz and speeds up the measured geometry queries by about 4–5 times. This is a bounded regional experiment, not a global optimum certificate.\n\n"
    text += table(
        ["Case", "Search", "Arm", "Position error km", "Geographic queries", "Frequency score"],
        search_rows,
    )
    text += "\n\n![Position search diagnostics](position-search.png)\n\n"
    text += "\n\nFrequency-score improvement and association coverage do not demonstrate better localization. Position errors are computed only after each fit is frozen. The 0.5-km goal remains active and unachieved. Any incomplete or timed-out runs remain in their original directories; a resumed run replays verified cached objective scores with unchanged search policy and budgets.\n\n"
    text += "## Reproducibility\n\n`drift_sensitivity/*/protocol.json` binds causal banks, observations, source hashes, policies and seed budgets. Each arm retains component candidates, residual RMS and qualified curved support. `drift-association.csv` is the machine-readable comparison. `diagnosis/` retains all controlled search diagnostics; `geometry_parity.json` retains numerical parity and timing. Search traces, frozen endpoints and separate evaluation receipts are under `pilots/`, `fragments/` and any `pilots_resumed/`. The earlier sealed report remains unchanged.\n"
    text += "\nThe calibration budget requests 160 generated seeds plus the initial state (four plus the initial state during geographic discovery); feasible seed counts can be smaller. Both initial DSX01 position processes exceeded eight-minute limits. Both resumed fits sealed successfully; a post-fit distance-call argument error was repaired from unchanged frozen fits. `execution-history.json` records the failures and recovery. The archived original footer reproduces its recorded digest. `CHECKPOINT.md` records remaining work and the new read-only adaptive-input availability probe.\n"
    (REPORT / "README.md").write_text(text)
    files = {
        str(p.relative_to(REPORT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in REPORT.rglob("*")
        if p.is_file() and p.name != "artifact_manifest.json"
    }
    (REPORT / "artifact_manifest.json").write_text(json.dumps(files, indent=2) + "\n")


if __name__ == "__main__":
    render()
