"""Render fixed-point model substitutions and the actual paired fit receipts."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
CASES = ("DS26-0197", "DS26-0223")
ARMS = ("c0", "fitted_c")
C0, FIT = "#087c82", "#626a96"


def load(name):
    return json.loads((HERE / name).read_bytes())


def waterfall():
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.5), constrained_layout=True)
    stages = [
        "lean_prediction",
        "site_only",
        "tle_only",
        "phase_only",
        "clock_replaced",
        "original_model_remainder",
    ]
    labels = ["Lean", "Site", "Causal TLE", "Orbit phase", "Radio clock", "Conditional"]
    for case, (match, position) in zip(CASES, axes, strict=True):
        dataset = load(f"{case}-components.json")["components"]
        oracle = load(f"{case}-oracle-refit.json")["arms"]
        for i, (arm, color) in enumerate(zip(ARMS, (C0, FIT), strict=True)):
            records = [x for x in dataset if x["arm"] == arm]
            n = sum(x["count"] for x in records)
            rms = [
                np.sqrt(sum(x["count"] * x["residual_rms_hz"][stage] ** 2 for x in records) / n)
                for stage in stages
            ]
            match.plot(range(len(stages)), rms, "o-", color=color, label=("c=0", "Fitted c")[i])
            v = oracle[arm]
            xy = np.arange(2) + 0.12 * (2 * i - 1)
            position.plot(
                xy,
                [v[step]["forced_error_km"] for step in ("fixed", "release_saturation")],
                "o-",
                color=color,
            )
        match.set(
            title=f"{case} · {n} added points",
            yscale="log",
            ylabel="Residual RMS (Hz)",
            xticks=range(len(stages)),
            xticklabels=labels,
        )
        position.set(
            title="Privileged same-owner refit",
            ylabel="Forced error to GNSS (km)",
            xticks=[0, 1],
            xticklabels=["Original bound", "Release saturated family"],
        )
    axes[0, 0].legend(fontsize=9)
    fig.savefig(HERE / "mechanism-and-forced-refit.png", dpi=160)
    plt.close(fig)


def blind_positions():
    rows = load("scores.json")
    keys = list(dict.fromkeys(r["id"] for r in rows))
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2), constrained_layout=True)
    for ax, arm in zip(axes, ARMS, strict=True):
        for i, (method, label, color) in enumerate(
            (
                ("native_joint_orbits", "Nominal joint", FIT),
                ("conditional_support_recovery", "Paired phase rescue", C0),
            )
        ):
            records = {r["id"]: r for r in rows if r["arm"] == arm and r["method"] == method}
            position = np.arange(len(keys)) + (i - 0.5) * 0.19
            ax.scatter(
                position, [records[k]["error_km"] for k in keys], color=color, s=34, label=label
            )
            forced = [
                records[k]["forced_error_km"] if records[k]["error_km"] is None else None
                for k in keys
            ]
            ax.scatter(position, forced, edgecolor=color, facecolor="none", s=35)
        ax.axvline(1.5, color=".7", lw=1)
        ax.axvline(5.5, color=".7", lw=1)
        ax.set(
            xticks=range(len(keys)),
            xticklabels=[k.replace("-omitted", "\n(omitted)") for k in keys],
            ylabel="Position error (km)",
            title="c=0" if arm == "c0" else "Fitted c",
        )
        ax.tick_params(axis="x", labelrotation=35, labelsize=8)
    axes[0].legend(fontsize=8)
    fig.suptitle(
        "Two diagnoses, four disjoint confirmations, one omitted tile\n"
        "Solid markers published · hollow markers forced"
    )
    fig.savefig(HERE / "blind-matched-positions.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    waterfall()
    blind_positions()
    files = sorted(p for p in HERE.iterdir() if p.is_file() and p.name != "artifact-lock.json")
    (HERE / "artifact-lock.json").write_text(
        json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}, indent=2)
        + "\n"
    )
