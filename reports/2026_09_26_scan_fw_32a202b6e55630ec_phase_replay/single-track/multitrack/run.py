"""Run bounded multi-mode increment-transfer diagnostics on extracted observations."""

from __future__ import annotations

import csv
import itertools
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from model import calibrated_donor_prediction

HERE = Path(__file__).resolve().parent
INPUT = HERE / "data/observations.csv"


def _load() -> list[dict[str, str]]:
    with INPUT.open(newline="") as stream:
        return [
            row
            for row in csv.DictReader(stream)
            if row.get("valid", "1").lower() not in {"0", "false"}
        ]


def _phase_score(predicted: np.ndarray, observed: np.ndarray, held: np.ndarray) -> dict[str, float]:
    error = np.angle(np.exp(1j * (predicted[held] - observed[held])))
    return {
        "n": int(np.count_nonzero(held)),
        "rmse_rad": float(np.sqrt(np.mean(error**2))),
        "rmse_degrees": float(np.degrees(np.sqrt(np.mean(error**2)))),
        "median_absolute_error_rad": float(np.median(np.abs(error))),
        "circular_resultant": float(np.abs(np.mean(np.exp(1j * error)))),
    }


def _wrapped_increment_score(predicted: np.ndarray, observed: np.ndarray) -> dict[str, float]:
    predicted_increment = np.angle(np.exp(1j * np.diff(predicted)))
    observed_increment = np.angle(np.exp(1j * np.diff(observed)))
    error = np.angle(np.exp(1j * (predicted_increment - observed_increment)))
    return {
        "n": int(len(error)),
        "rmse_rad": float(np.sqrt(np.mean(error**2))),
        "rmse_degrees": float(np.degrees(np.sqrt(np.mean(error**2)))),
        "circular_resultant": float(np.abs(np.mean(np.exp(1j * error)))),
    }


def main() -> None:
    rows = _load()
    grouped: dict[str, dict[str, list[dict[str, str]]]] = {}
    for row in rows:
        grouped.setdefault(row["group_id"], {}).setdefault(row["mode"], []).append(row)
    results: list[dict[str, object]] = []
    plotted = None
    for group, by_mode in sorted(grouped.items()):
        modes = sorted(by_mode)
        if len(modes) < 2:
            continue
        series = {}
        for mode in modes:
            ordered = sorted(by_mode[mode], key=lambda row: float(row["time_s"]))
            t = np.array([float(row["time_s"]) for row in ordered])
            p = np.array([float(row["phase_rad"]) for row in ordered])
            series[mode] = (t, p)
        if not np.array_equal(series[modes[0]][0], series[modes[1]][0]):
            continue
        t = series[modes[0]][0]
        # Freeze calibration after four dense windows (about 28 ms).
        train = np.arange(len(t)) < 4
        held = ~train
        if np.count_nonzero(held) < 3:
            continue
        for donor, target in itertools.permutations(modes, 2):
            donor_y, target_y = series[donor][1], series[target][1]
            predicted, difference_coefficients = calibrated_donor_prediction(
                t, donor_y, target_y, train, difference_degree=1
            )
            target_train = np.unwrap(target_y[train])
            target_coefficients = np.polynomial.polynomial.polyfit(t[train], target_train, 1)
            independent = np.angle(
                np.exp(1j * np.polynomial.polynomial.polyval(t, target_coefficients))
            )
            constant = np.full_like(t, np.angle(np.mean(np.exp(1j * target_y[train]))), dtype=float)
            wrong_donor = np.roll(donor_y, max(1, np.count_nonzero(held) // 3))
            origin = float(np.mean(t[train]))
            scale = float(np.ptp(t[train]))
            x = (t - origin) / scale
            wrong = np.angle(
                np.exp(
                    1j
                    * (wrong_donor + np.polynomial.polynomial.polyval(x, difference_coefficients))
                )
            )
            results.append(
                {
                    "group_id": group,
                    "donor_mode": donor,
                    "held_mode": target,
                    "n_training_phase_windows": int(np.count_nonzero(train)),
                    "n_held_phase_windows": int(np.count_nonzero(held)),
                    "frozen_difference_coefficients": difference_coefficients.tolist(),
                    "simultaneous_donor_frozen_difference": _phase_score(predicted, target_y, held),
                    "target_only_linear_frequency_forecast": _phase_score(
                        independent, target_y, held
                    ),
                    "target_only_constant_phase": _phase_score(constant, target_y, held),
                    "wrong_time_donor_control": _phase_score(wrong, target_y, held),
                    "held_increment_transfer": _wrapped_increment_score(
                        predicted[held], target_y[held]
                    ),
                    "held_phase_offset_fit": False,
                    "uses_current_donor_phase": True,
                }
            )
            if plotted is None:
                plotted = (group, donor, target, t, predicted, target_y, train, held)
    payload = {
        "model_scope": (
            "conditional common-instrument diagnostic; modes are not confirmed distinct emitters"
        ),
        "phase_quantity": (
            "target phase from current donor plus training-frozen difference; "
            "no held-mode phase offset"
        ),
        "gauge_warning": "common and mode-specific smooth terms have a polynomial rank nullspace",
        "retune_warning": (
            "groups are evaluated separately; phase and cycle branches are not stitched "
            "across retunes"
        ),
        "baseline_warning": (
            "79 degree baseline orientation alone does not determine orbital geometry"
        ),
        "results": results,
    }
    (HERE / "metrics.json").write_text(json.dumps(payload, indent=2) + "\n")
    if plotted is not None:
        group, donor, target, t, predicted, yt, train, held = plotted
        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.plot(t * 1e3, yt, ".-", label=f"observed {target}")
        ax.plot(t * 1e3, predicted, ".-", label=f"current {donor} + frozen difference")
        boundary = (t[3] + t[4]) * 500
        ax.axvspan(np.min(t) * 1e3, boundary, alpha=0.12, label="training")
        ax.axvspan(boundary, np.max(t) * 1e3, alpha=0.08, label="held time")
        ax.set(
            xlabel="visit-relative time (ms)",
            ylabel="wrapped phase (rad)",
            title=f"{group}: simultaneous mode transfer",
        )
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(HERE / "increment-transfer.png", dpi=160)
        plt.close(fig)
    print(json.dumps({"groups": len(grouped), "directed_evaluations": len(results)}, indent=2))


if __name__ == "__main__":
    main()
