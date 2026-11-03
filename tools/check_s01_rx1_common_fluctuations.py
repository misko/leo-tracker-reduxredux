"""Check shared RX1 fluctuations without using target/same-satellite references."""

import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from diagnose_s01_ch2_t000 import NORAD, OUTPUT, PROTOTYPES, TARGET
from inventory_clipped_phase_cohort import load_study

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def polynomial_residual(track):
    x = (track["times"] - np.mean(track["times"])) / 30
    coef = np.polynomial.polynomial.polyfit(x, track["values"], 4)
    return track["values"] - np.polynomial.polynomial.polyval(x, coef)


def run():
    study, *_ = load_study("DSX01-S01", True)
    old = {
        r["component"]: r
        for r in json.loads(
            (PROTOTYPES / "family_extension/fitted_c/association.json").read_text()
        )["rows"]
    }
    target = next(t for t in study.tracks if t["key"] == TARGET)
    times, residual = target["times"], polynomial_residual(target)
    comparisons, references = [], []
    for track in study.tracks:
        if track["key"] == TARGET or len(track["times"]) < 15 or np.ptp(track["times"]) < 20:
            continue
        other = polynomial_residual(track)
        ix = np.abs(times[:, None] - track["times"]).argmin(axis=1)
        valid = np.abs(times - track["times"][ix]) < 0.3
        if valid.sum() < 12:
            continue
        same_satellite = old[track["key"]]["candidate_norad"] == NORAD
        row = dict(
            component=track["key"],
            candidate_norad=old[track["key"]]["candidate_norad"],
            receiver=track["receiver"],
            points=int(valid.sum()),
            active_curvature=track["key"] in study.curved_keys,
            same_satellite=same_satellite,
            correlation=float(np.corrcoef(residual[valid], other[ix[valid]])[0, 1]),
            times_s=times[valid],
            target_residual_hz=residual[valid],
            other_residual_hz=other[ix[valid]],
        )
        comparisons.append(row)
        if track["receiver"] == 1 and not same_satellite and row["active_curvature"]:
            prediction = np.full(len(times), np.nan)
            prediction[valid] = other[ix[valid]] * target["rf_hz"] / track["rf_hz"]
            references.append(prediction)
    matrix = np.array(references)
    valid = np.isfinite(matrix).any(axis=0)
    prediction = np.full(len(times), np.nan)
    prediction[valid] = np.nanmedian(matrix[:, valid], axis=0)
    summary = dict(
        target=TARGET,
        comparison="independent fourth-degree detrending; no satellite TLE involved",
        maximum_nearest_time_difference_s=0.3,
        cross_satellite_rx1_references=len(references),
        reference_policy="all overlapping raw-curved RX1 fragments nominating other satellites",
        target_and_same_satellite_excluded_from_reference=True,
        points_with_reference=int(valid.sum()),
        target_rms_on_supported_points_hz=float(np.sqrt(np.mean(residual[valid] ** 2))),
        unit_gain_corrected_rms_on_same_points_hz=float(
            np.sqrt(np.mean((residual[valid] - prediction[valid]) ** 2))
        ),
        correction_gain="fixed RF ratio; no gain learned from target",
        association_or_calibration_updated=False,
        caution="polynomial detrending removes slow drift; this is a fluctuation diagnostic only",
        times_s=times,
        target_quartic_residual_hz=residual,
        supported_mask=valid,
        reference_prediction_hz=np.where(valid, prediction, 0),
        comparisons=comparisons,
    )
    write(OUTPUT / "receiver_common_fluctuations.json", summary)
    print(
        json.dumps(
            {
                k: v
                for k, v in summary.items()
                if k
                not in (
                    "times_s",
                    "target_quartic_residual_hz",
                    "supported_mask",
                    "reference_prediction_hz",
                    "comparisons",
                )
            }
        ),
        flush=True,
    )
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), layout="constrained")
    axes[0].plot(times, residual, "k.-", label="RX1 CH2 target, independent quartic removed")
    for row in comparisons:
        if row["receiver"] == 1 and not row["same_satellite"] and row["active_curvature"]:
            axes[0].plot(
                row["times_s"],
                row["other_residual_hz"],
                ".-",
                alpha=0.7,
                label=(
                    f"{row['component'][4:]} / {row['candidate_norad']}: r={row['correlation']:.2f}"
                ),
            )
    axes[0].set(title="RX1 fluctuations shared across different satellite candidates")
    axes[1].plot(times[valid], residual[valid], ".-", label="Target on supported timestamps")
    axes[1].plot(
        times[valid],
        prediction[valid],
        ".-",
        label="Other-satellite RX1 median; fixed unit RF gain",
    )
    axes[1].plot(times[valid], residual[valid] - prediction[valid], ".-", label="Difference")
    axes[1].set(
        title=f"Conditional cross-satellite transfer: {valid.sum()}/80 timestamps supported"
    )
    for ax in axes:
        ax.axhline(0, color="black", lw=0.6)
        ax.set(xlabel="Seconds from S01 start", ylabel="Quartic residual (Hz)")
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    fig.savefig(OUTPUT / "receiver_common_fluctuations.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    run()
