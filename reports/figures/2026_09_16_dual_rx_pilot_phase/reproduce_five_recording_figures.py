"""Scientific figures and measured summary for the five-recording survey."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).parent
TAGS = ["080532", "080805", "105915", "112754", "113026"]


def longest_run(rows, stride):
    best = []
    run = []
    for row in rows:
        if row["qualified"]:
            if run and row["center_s"] - run[-1]["center_s"] > stride * 1.1:
                run = []
            run.append(row)
            if len(run) > len(best):
                best = list(run)
        else:
            run = []
    return {
        "count": len(best),
        "first_center_s": best[0]["center_s"] if best else None,
        "last_center_s": best[-1]["center_s"] if best else None,
        "center_span_s": best[-1]["center_s"] - best[0]["center_s"] if best else 0,
    }


def main():
    summary = {"geometry_verified": False, "recordings": [], "double_differences": []}
    fig, axes = plt.subplots(2, 1, figsize=(11, 7.5), layout="constrained")
    labels = []
    for i, tag in enumerate(TAGS):
        coarse = json.loads((ROOT / f"{tag}-cohort-coherent-phase.json").read_text())
        fine = json.loads((ROOT / f"{tag}-cohort-fine-phase.json").read_text())
        q = [r for r in fine["windows"] if r["qualified"]]
        primary = [r for r in coarse["windows"] if r["track_id"] == fine["track"]["id"]]
        cr = [r["resultant_length"] for r in primary if "resultant_length" in r]
        fr = [r["resultant_length"] for r in fine["windows"] if "resultant_length" in r]
        cq = sorted(set(round(r["center_s"], 6) for r in coarse["windows"] if r["qualified"]))
        label = f"{tag[:2]}:{tag[2:4]}:{tag[4:]} / {coarse['radio_id'][-4:]}"
        labels.append(label)
        axes[0].scatter(
            cq,
            [i - 0.12] * len(cq),
            s=9,
            color="C0",
            label="150 ms accepted centers" if i == 0 else None,
        )
        axes[0].scatter(
            [r["center_s"] for r in q],
            [i + 0.12] * len(q),
            s=9,
            color="C1",
            label="20 ms accepted centers" if i == 0 else None,
        )
        for vals, offset, color in [(cr, -0.12, "C0"), (fr, 0.12, "C1")]:
            low, median, high = np.quantile(vals, [0.1, 0.5, 0.9])
            axes[1].errorbar(
                i + offset,
                median,
                yerr=[[median - low], [high - median]],
                fmt="o",
                color=color,
                capsize=4,
            )
        summary["recordings"].append(
            {
                "tag": tag,
                "capture": coarse["capture"],
                "radio_id": coarse["radio_id"],
                "edge": coarse["edge"],
                "applied_if_hz": coarse["applied_if_hz"],
                "paired_branch_tracks_tested": len(coarse["tracks"]),
                "coarse_track_windows": len(coarse["windows"]),
                "coarse_accepted_track_windows": sum(r["qualified"] for r in coarse["windows"]),
                "fine_track": fine["track"]["id"],
                "fine_interval_s": fine["interval_s"],
                "fine_window_s": 0.02,
                "fine_stride_s": 0.01,
                "fine_candidates": len(fine["windows"]),
                "fine_accepted": len(q),
                "fine_acceptance_percent": 100 * len(q) / len(fine["windows"]),
                "fine_longest_run": longest_run(fine["windows"], 0.01),
                "median_fine_R_accepted": float(np.median([r["resultant_length"] for r in q])),
                "median_coarse_R_fitted_primary": float(np.median(cr)),
                "median_fine_R_fitted_primary": float(np.median(fr)),
                "median_fine_pilot_control_ratios": np.median(
                    [r["pilot_control_ratios"] for r in q], axis=0
                ).tolist(),
                "median_apparent_relative_frequency_hz": float(
                    np.median([r["relative_frequency_hz"] for r in q])
                ),
                "frequency_alias_resolved": False,
            }
        )
    axes[0].set_yticks(range(5), labels)
    axes[0].invert_yaxis()
    axes[0].set_xlim(0, 60)
    axes[0].set_xlabel("Time from first sample (s)")
    axes[0].legend(fontsize=9)
    axes[0].set_title("Usable same-radio RX0/RX1 pilot measurements across all five recordings")
    axes[1].set_xticks(range(5), labels, fontsize=9)
    axes[1].set_ylim(0, 1.03)
    axes[1].set_ylabel("Phase concentration R")
    axes[1].set_title("Same selected track: median and 10–90% range of fitted windows")
    for ax in axes:
        ax.grid(alpha=0.2)
    fig.savefig(ROOT / "five-recording-coherent-phase-coverage.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), layout="constrained")
    files = ["105915-coherent-pilot-20ms.json", "113026-cohort-double-fine-phase.json"]
    for ax, tag, file in zip(axes, ["105915", "113026"], files, strict=True):
        d = json.loads((ROOT / file).read_text())
        q = [r for r in d["windows"] if r["both_qualified"]]
        t = np.array([r["center_s"] for r in q])
        phase = np.radians([r["differential_phase_deg"] for r in q])
        u = np.exp(1j * phase)
        slopes = np.arange(-90, 90.0001, 0.1)
        scores = np.array(
            [abs(np.mean(u * np.exp(-1j * np.radians(slope) * (t - t.mean())))) for slope in slopes]
        )
        slope = float(slopes[np.argmax(scores)])
        alpha = np.angle(np.mean(u * np.exp(-1j * np.radians(slope) * (t - t.mean()))))
        predicted = np.angle(np.exp(1j * (alpha + np.radians(slope) * (t - t.mean()))))
        residual = np.angle(np.exp(1j * (phase - predicted)))
        ax.scatter(
            t, np.degrees(phase), s=8, alpha=0.6, label="Accepted 20 ms double-difference phase"
        )
        ax.plot(t, np.degrees(predicted), color="C1", lw=2, label="Descriptive circular linear fit")
        time_label = f"{tag[:2]}:{tag[2:4]}:{tag[4:]}"
        counts = f"{len(q)}/{len(d['windows'])} accepted"
        ax.set_title(f"{time_label} / 5d4d: {counts}; {slope:.1f}°/s")
        ax.set_ylabel("Double-difference phase (deg)")
        ax.set_xlabel("Time from first sample (s)")
        ax.set_ylim(-180, 180)
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
        summary["double_differences"].append(
            {
                "tag": tag,
                "input_file": file,
                "accepted": len(q),
                "candidates": len(d["windows"]),
                "first_accepted_center_s": float(t[0]),
                "last_accepted_center_s": float(t[-1]),
                "descriptive_slope_deg_s": slope,
                "circular_fit_R": float(scores.max()),
                "circular_residual_rms_deg": float(np.degrees(np.sqrt(np.mean(residual**2)))),
                "geometric_interpretation_verified": False,
            }
        )
    fig.suptitle("Two simultaneous signals: receiver-phase double differences, geometry unverified")
    fig.savefig(ROOT / "five-recording-double-difference-phase.png", dpi=160)
    plt.close(fig)
    summary["fine_total_candidates"] = sum(v["fine_candidates"] for v in summary["recordings"])
    summary["fine_total_accepted"] = sum(v["fine_accepted"] for v in summary["recordings"])
    (ROOT / "five-recording-coherent-phase-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
