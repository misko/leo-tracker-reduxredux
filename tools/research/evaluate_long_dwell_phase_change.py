"""Evaluate a frozen sparse holdout of the corrected 105915 phase track."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "reports/figures/2026_09_16_dual_rx_pilot_phase/105915-coherent-pilot-20ms.json"
OUT = ROOT / "reports/figures/2026_09_23_long_dwell_phase_change"
SEED = 20260923


def wrap(x):
    return np.angle(np.exp(1j * np.asarray(x)))


def sparse_indices(count: int, selected: int = 16) -> np.ndarray:
    return np.rint(np.linspace(0, count - 1, selected)).astype(int)


def split_indices(count: int, seed: int = SEED) -> tuple[np.ndarray, np.ndarray]:
    order = np.random.default_rng(seed).permutation(count)
    return np.sort(order[: count // 2]), np.sort(order[count // 2 :])


def fit_circular_affine(time_s, phase_rad, reference_s):
    x = np.asarray(time_s) - reference_s
    y = np.asarray(phase_rad)
    initial = np.polyfit(x, np.unwrap(y), 1)[::-1]
    fit = least_squares(lambda beta: wrap(y - beta[0] - beta[1] * x), initial)
    return fit.x


def circular_abs_error(phase, prediction):
    return np.abs(wrap(np.asarray(phase) - np.asarray(prediction)))


def main():
    artifact = json.loads(INPUT.read_text())
    windows = artifact["windows"]
    chosen = sparse_indices(len(windows))
    train_local, held_local = split_indices(len(chosen))
    train_set = set(train_local)
    rows = []
    for local, source_index in enumerate(chosen):
        window = windows[int(source_index)]
        rows.append(
            {
                "group": int(local),
                "source_index": int(source_index),
                "partition": "train" if local in train_set else "held",
                "center_s": window["center_s"],
                "qualified": window["both_qualified"],
                "phase_rad": np.radians(window["differential_phase_deg"])
                if window["both_qualified"]
                else None,
                "failure": None if window["both_qualified"] else "one_or_both_sources_failed",
            }
        )
    train = [r for r in rows if r["partition"] == "train" and r["qualified"]]
    held = [r for r in rows if r["partition"] == "held" and r["qualified"]]
    reference = float(np.mean([r["center_s"] for r in train]))
    beta = fit_circular_affine(
        [r["center_s"] for r in train], [r["phase_rad"] for r in train], reference
    )
    constant = np.angle(np.mean(np.exp(1j * np.array([r["phase_rad"] for r in train]))))
    held_t = np.array([r["center_s"] for r in held])
    held_y = np.array([r["phase_rad"] for r in held])
    prediction = beta[0] + beta[1] * (held_t - reference)
    rng = np.random.default_rng(SEED + 1)
    permuted_t = held_t[rng.permutation(len(held_t))]
    wrong_time = beta[0] + beta[1] * (permuted_t - reference)
    errors = circular_abs_error(held_y, prediction)
    constant_errors = circular_abs_error(held_y, constant)
    wrong_errors = circular_abs_error(held_y, wrong_time)
    result = {
        "schema": "long-dwell-phase-change/v1",
        "input": str(INPUT.relative_to(ROOT)),
        "seed": SEED,
        "selection": "16 fixed evenly spaced artifact rows before qualification",
        "rows": rows,
        "fit": {
            "reference_s": reference,
            "intercept_rad": float(beta[0]),
            "rate_rad_per_s": float(beta[1]),
            "rate_deg_per_s": float(np.degrees(beta[1])),
        },
        "held": {
            "selected": 8,
            "qualified": len(held),
            "coverage": len(held) / 8,
            "affine_median_abs_error_deg": float(np.degrees(np.median(errors))),
            "constant_median_abs_error_deg": float(np.degrees(np.median(constant_errors))),
            "wrong_time_median_abs_error_deg": float(np.degrees(np.median(wrong_errors))),
            "affine_errors_deg": np.degrees(errors).tolist(),
        },
        "interpretation": (
            "conditional restored-model phase predictability; no source identity, "
            "geometry, or position claim"
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    fig, ax = plt.subplots(figsize=(9, 4.8), layout="constrained")
    for partition, marker in (("train", "o"), ("held", "s")):
        q = [r for r in rows if r["partition"] == partition and r["qualified"]]
        ax.scatter(
            [r["center_s"] for r in q],
            [np.degrees(r["phase_rad"]) for r in q],
            marker=marker,
            label=f"{partition} qualified",
        )
    failed = [r for r in rows if not r["qualified"]]
    ax.scatter(
        [r["center_s"] for r in failed],
        [0] * len(failed),
        marker="x",
        color="black",
        label="abstained",
    )
    grid = np.linspace(min(r["center_s"] for r in rows), max(r["center_s"] for r in rows), 300)
    ax.plot(
        grid,
        np.degrees(wrap(beta[0] + beta[1] * (grid - reference))),
        label="train-fit wrapped affine",
    )
    ax.set(xlabel="Time from capture start (s)", ylabel="Restored double-difference phase (deg)")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.savefig(OUT / "phase-v-time.png", dpi=160)
    print(json.dumps(result["held"], indent=2))


if __name__ == "__main__":
    main()
