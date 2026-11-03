"""Describe residual gates at the recorded candidates of the S01 prototype."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports/2026_10_17_s01_shared_satellite_prototypes"
OUTPUT = ROOT / "reports/2026_10_18_s01_ch2_t000_diagnosis/gate_distributions"
TARGET = "S01-RX1-CH2-T000"
GATES = {
    "rms": ("RMS", 450.0),
    "bias": ("Absolute curve offset", 3000.0),
    "mean": ("Residual mean statistic", 3.0),
    "slope": ("Residual slope statistic", 3.0),
    "quadratic": ("Constant + linear + quadratic trend, ΔBIC", 10.0),
    "step": ("Maximum interval-mean difference statistic", 4.0),
    "acf": ("Absolute lag-one correlation", None),
}


def metrics(row):
    d = row["diagnostics"]
    return dict(
        rms=row["rms_hz"],
        bias=abs(row["bias_hz"]),
        mean=d["mean_z"],
        slope=d["slope_z"],
        quadratic=d["quadratic_bic_gain"],
        step=d["maximum_step_z"],
        acf=abs(d["lag1_acf"]),
    )


def describe(arm):
    source = SOURCE / "family_extension" / arm
    rows = json.loads((source / "association.json").read_text())["rows"]
    parameters = json.loads((source / "parameters.json").read_text())
    lookup = {r["component"]: r for r in rows}
    owners = {r["candidate_norad"] for r in rows if r["compatible"] and r["active_curvature"]}
    records = []
    for r in rows:
        values = metrics(r)
        limits = {
            k: float(v[1]) if v[1] is not None else 4 / np.sqrt(r["points"])
            for k, v in GATES.items()
        }
        ratios = {k: values[k] / limits[k] for k in GATES}
        failed = [k for k in GATES if ratios[k] > 1]
        reason = "accepted" if r["compatible"] else "numeric_gate_failure"
        gap = None
        if not r["compatible"] and not failed:
            n = r["candidate_norad"]
            p = parameters.get(str(n))
            if p and p["theta"] != p["initial_theta"]:
                gaps = []
                for key in p["calibration_members"]:
                    a, b = r["times_s"], lookup[key]["times_s"]
                    gaps.append(max(0, min(a) - max(b), min(b) - max(a)))
                gap = min(gaps) if gaps else None
            if gap is not None and gap > 30:
                reason = "outside_30s_correction_neighborhood"
            elif n not in owners:
                reason = "no_accepted_curved_satellite_owner"
            else:
                reason = "other_gate_requires_inspection"
        records.append(
            dict(
                component=r["component"],
                points=r["points"],
                candidate_norad=r["candidate_norad"],
                accepted=r["compatible"],
                active_curvature=r["active_curvature"],
                values=values,
                limits=limits,
                ratios=ratios,
                failed_gates=failed,
                reason=reason,
                gap_to_correction_support_s=gap,
            )
        )
    summary = {}
    for gate in GATES:
        cohorts = {}
        for accepted, label in ((True, "accepted"), (False, "rejected")):
            cohort = [r for r in records if r["accepted"] == accepted]
            raw = np.array([r["values"][gate] for r in cohort])
            normalized = np.array([r["ratios"][gate] for r in cohort])
            cohorts[label] = dict(
                tracks=len(cohort),
                failing=int(np.sum(normalized > 1)),
                failing_points=sum(r["points"] for r in cohort if r["ratios"][gate] > 1),
                raw_quantiles=dict(
                    zip(
                        ("median", "p90", "maximum"),
                        map(float, np.quantile(raw, [0.5, 0.9, 1])),
                        strict=True,
                    )
                ),
                normalized_quantiles=dict(
                    zip(
                        ("median", "p90", "maximum"),
                        map(float, np.quantile(normalized, [0.5, 0.9, 1])),
                        strict=True,
                    )
                ),
                within_20_percent_of_limit=int(np.sum((normalized >= 0.8) & (normalized <= 1))),
            )
        summary[gate] = cohorts
    reasons = {
        reason: sum(r["reason"] == reason for r in records)
        for reason in sorted({r["reason"] for r in records})
    }
    assert sum(reasons.values()) == 170
    assert all(not r["failed_gates"] for r in records if r["accepted"])
    assert "other_gate_requires_inspection" not in reasons
    return dict(
        arm=arm,
        source_sha256=hashlib.sha256((source / "association.json").read_bytes()).hexdigest(),
        records=records,
        gate_summary=summary,
        rejection_reasons=reasons,
        accepted_near_any_structure_limit=sum(
            r["accepted"]
            and any(0.8 <= r["ratios"][g] <= 1 for g in ("slope", "quadratic", "step", "acf"))
            for r in records
        ),
        descriptions=dict(
            population=(
                "170 retained graph polynomial fragments; 311 outside-fragment GLRT excluded"
            ),
            accepted_candidate="best feasible candidate after all production prototype gates",
            rejected_candidate="lowest-score diagnostic nominee at frozen final candidate states",
            weighting="one vote per fragment, not per GLRT point",
            accepted_gates_pass_by_construction=True,
            gate_statistics_not_calibrated_identity_probabilities=True,
        ),
    )


def ecdf(ax, records, gate):
    for accepted, color, label in (
        (True, "seagreen", "Accepted (129)"),
        (False, "firebrick", "Rejected (41)"),
    ):
        values = np.sort([r["ratios"][gate] for r in records if r["accepted"] == accepted])
        ax.step(
            values,
            np.arange(1, len(values) + 1) / len(values),
            where="post",
            color=color,
            label=label,
            lw=2,
        )
        ax.plot(values, np.arange(1, len(values) + 1) / len(values), ".", color=color, ms=2)
    target = next(r for r in records if r["component"] == TARGET)
    ax.axvline(1, color="black", ls="--", lw=1, label="Failure boundary")
    ax.axvline(
        target["ratios"][gate],
        color="darkorange",
        lw=1.8,
        label=f"80-point target: {target['ratios'][gate]:.2f} × limit",
    )
    ax.set(
        title=GATES[gate][0],
        xlabel="Statistic / allowed limit",
        ylabel="Fraction of tracks ≤ value",
        ylim=(0, 1.04),
    )
    if gate == "quadratic" or max(r["ratios"][gate] for r in records) > 4:
        ax.set_xscale("symlog", linthresh=1)
    ax.grid(alpha=0.2)
    ax.legend(fontsize=7, loc="lower right")


def render(data):
    records = data["records"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    for ax, gate in zip(axes.flat, ("slope", "quadratic", "step", "acf"), strict=True):
        ecdf(ax, records, gate)
    fig.suptitle(
        "DSX01 S01 — residual-structure distributions at recorded satellite candidates\n"
        "Family extension, fitted c; ≤1 passes; accepted distributions are selected by these gates"
    )
    fig.savefig(OUTPUT / "structure_gate_distributions.png", dpi=170)
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), layout="constrained")
    for ax, gate in zip(axes, ("rms", "bias", "mean"), strict=True):
        ecdf(ax, records, gate)
    fig.suptitle("DSX01 S01 — magnitude, constant-offset and mean gates")
    fig.savefig(OUTPUT / "other_gate_distributions.png", dpi=170)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
    for accepted, color, label in (
        (True, "seagreen", "Accepted"),
        (False, "firebrick", "Rejected"),
    ):
        rows = [r for r in records if r["accepted"] == accepted]
        axes[0].scatter(
            [r["points"] for r in rows],
            [r["values"]["acf"] for r in rows],
            c=color,
            label=label,
            alpha=0.65,
            s=22,
        )
    x = np.arange(4, 81)
    axes[0].plot(x, 4 / np.sqrt(x), "k--", label="4 / √N limit")
    target = next(r for r in records if r["component"] == TARGET)
    axes[0].scatter(
        [80],
        [target["values"]["acf"]],
        marker="*",
        s=160,
        color="darkorange",
        edgecolor="black",
        label="80-point target",
        zorder=5,
    )
    axes[0].set(
        xlabel="GLRT points per fragment",
        ylabel="Absolute lag-one correlation",
        title="Short fragments have weaker correlation constraints",
        ylim=(0, 1.05),
    )
    labels = ("<16", "16–29", "30–49", "≥50")
    bounds = ((0, 16), (16, 30), (30, 50), (50, 999))
    accepted = [sum(r["accepted"] for r in records if lo <= r["points"] < hi) for lo, hi in bounds]
    rejected = [
        sum(not r["accepted"] for r in records if lo <= r["points"] < hi) for lo, hi in bounds
    ]
    axes[1].bar(labels, accepted, color="seagreen", label="Accepted")
    axes[1].bar(labels, rejected, bottom=accepted, color="firebrick", label="Rejected")
    axes[1].set(
        xlabel="GLRT points per fragment",
        ylabel="Polynomial fragments",
        title="Cohort sizes by fragment length",
    )
    for ax in axes:
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    fig.savefig(OUTPUT / "length_and_correlation.png", dpi=170)
    plt.close(fig)


def run():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    arms = {arm: describe(arm) for arm in ("c0", "fitted_c")}
    for arm, data in arms.items():
        (OUTPUT / f"{arm}.json").write_text(json.dumps(data, indent=2) + "\n")
    with (OUTPUT / "per_track.csv").open("w") as stream:
        fields = (
            "component",
            "points",
            "candidate_norad",
            "accepted",
            "reason",
            *[f"{g}_ratio" for g in GATES],
        )
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for r in arms["fitted_c"]["records"]:
            writer.writerow(
                {
                    **{k: r[k] for k in fields if k in r},
                    **{f"{g}_ratio": r["ratios"][g] for g in GATES},
                }
            )
    render(arms["fitted_c"])
    print(
        json.dumps(
            {
                arm: dict(
                    reasons=d["rejection_reasons"],
                    failed={g: s["rejected"]["failing"] for g, s in d["gate_summary"].items()},
                )
                for arm, d in arms.items()
            }
        )
    )


if __name__ == "__main__":
    run()
