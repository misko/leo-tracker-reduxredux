"""Render sealed anchor fits beside their original GLRT scores; no fit changes."""

import hashlib
import json
import runpy
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt

from leo.application.scanner_trajectory import project_scanner_candidates

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/2026_10_12_continuous_track_merge"
INPUT = Path("/srv/bulk/leo/fast-scan-tracking-inputs/fast-71516d43f9396e83ca99f4d42136a84a.json")
LOADER = Path("/opt/leo-fast-auto/20261011-r3/bin/fast_scan_standard_pipeline.py")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    anchors = json.loads((REPORT / "anchor-results.json").read_bytes())
    loader = runpy.run_path(str(LOADER))["load_tracking_input"]
    source = loader(json.loads(INPUT.read_bytes()))
    candidates = {c.candidate_id: c for c in project_scanner_candidates(source)}
    fig, axes = plt.subplots(4, 2, figsize=(15, 14), constrained_layout=True)
    checks = {}
    colors = ("#1478b5", "#e17c19")
    for column, (label, anchor) in enumerate(anchors.items()):
        input_path = Path(anchor["input"])
        assert sha(input_path) == anchor["sha256"]
        original = json.loads(input_path.read_bytes())
        assert sha(INPUT) == original["input_sha256"]
        receipt = anchor["variants"]["original-guard"]
        tracks = original["tracks"]
        labels = sorted({r["track"] for r in original["rows"]})
        raw = {
            p["candidate_id"]: p["normalized_dealiased_cfo_hz"]
            for track in tracks
            for p in track["points"]
        }
        records = {}
        for row in original["rows"]:
            row = dict(row)
            right = row["track"] == labels[1]
            row["frequency_hz"] = raw[row["candidate_id"]] + (
                receipt["alias_shift"] * original["normalized_alias_spacing_hz"] if right else 0
            )
            previous = records.get(row["source_group_id"])
            if previous is None or (-row["weight"], row["candidate_id"]) < (
                -previous["weight"],
                previous["candidate_id"],
            ):
                records[row["source_group_id"]] = row
        rows = sorted(records.values(), key=lambda r: (r["time_s"], r["source_group_id"]))
        times, measured, weights = [
            np.array([r[key] for r in rows]) for key in ("time_s", "frequency_hz", "weight")
        ]
        right = np.array([r["track"] == labels[1] for r in rows])
        boundary = receipt["boundary_s"]
        coefficients = np.array(receipt["coefficients"])

        def curve(t, boundary=boundary, coefficients=coefficients):
            return np.polynomial.polynomial.polyval((t - boundary) / 20, coefficients)

        residual = measured - curve(times)
        closure = float(np.sqrt(np.average(residual**2, weights=weights)))
        assert abs(closure - receipt["fitted_rms_hz"]) < 1e-6
        gap_left, gap_right = times[~right].max(), times[right].min()
        grid = np.linspace(times.min(), times.max(), 1200)
        lane = tracks[0]["lane_key"]
        axes[0, column].set_title(
            f"{label} · CH{lane[0]} RX{lane[2]} · {len(rows)} distinct windows"
        )
        for index in (0, 1):
            axis = axes[index, column]
            axis.plot(
                grid,
                curve(grid) / 1000,
                color="#151515",
                lw=1.8,
                label=f"One continuous degree-{receipt['degree']} curve",
            )
            for side, track_label in enumerate(labels):
                mask = right == bool(side)
                axis.scatter(
                    times[mask],
                    measured[mask] / 1000,
                    s=24,
                    color=colors[side],
                    edgecolors="white",
                    linewidths=0.3,
                    zorder=4,
                    label=f"T{track_label} measured GLRT CFO",
                )
            axis.set_ylabel("Alias-aligned CFO (kHz)\nnormalized to 11.2 GHz")
        axes[0, column].legend(fontsize=8)
        zoom = (boundary - 3.5, boundary + 3.5)
        axes[1, column].set_xlim(*zoom)
        limits = curve(np.array(zoom)) / 1000
        pad = 0.1 * np.ptp(limits)
        axes[1, column].set_ylim(limits.min() - pad, limits.max() + pad)
        axes[1, column].set_title("Join close-up · grey = no retained measurement")
        for side, track_label in enumerate(labels):
            mask = right == bool(side)
            axes[2, column].scatter(times[mask], residual[mask], s=25, color=colors[side])
            exact = [candidates[r["candidate_id"]].exact_score for r in rows]
            control = [candidates[r["candidate_id"]].control_score for r in rows]
            axes[3, column].scatter(
                times[mask],
                np.array(exact)[mask],
                s=25,
                color=colors[side],
                label=f"T{track_label} exact GLRT",
            )
        axes[3, column].scatter(
            times, control, marker="x", s=22, color="#555555", label="Control score", alpha=0.65
        )
        axes[3, column].legend(fontsize=8)
        axes[3, column].set_ylabel("Stored GLRT score")
        axes[3, column].set_title("Detection strength · passing track candidates only")
        axes[2, column].axhline(0, color="#202020", lw=1)
        axes[2, column].set_ylabel("Measured CFO − joined curve (Hz)")
        axes[2, column].set_title(
            f"RMS: fitted {closure:.1f} Hz; random-block held-out {receipt['held_rms_hz']:.1f} Hz"
        )
        for axis in axes[:, column]:
            axis.axvspan(gap_left, gap_right, color="grey", alpha=0.12)
            axis.grid(alpha=0.2)
            axis.set_xlabel("Seconds since capture start")
        checks[label] = {
            "original_sha256": anchor["sha256"],
            "distinct_windows": len(rows),
            "fitted_rms_hz": closure,
            "held_rms_hz": receipt["held_rms_hz"],
            "curve_degree": receipt["degree"],
            "maximum_absolute_residual_hz": float(np.max(np.abs(residual))),
            "measured_sample_gap_s": float(gap_right - gap_left),
            "boundary_step_hz": receipt["boundary_jump_hz"],
            "boundary_slope_change_hz_s": receipt["boundary_slope_change_hz_s"],
            "segments": receipt["segments"],
            "exact_score_range": [float(min(exact)), float(max(exact))],
            "control_score_range": [float(min(control)), float(max(control))],
        }
    fig.suptitle(
        "GLRT detections and continuous merge curves · b9e46bba\n"
        "Saved fits replayed exactly; only integer pilot aliases align the segments",
        fontsize=15,
    )
    output = REPORT / "glrt-scores-and-merge-curves.png"
    fig.savefig(output, dpi=160)
    plt.close(fig)
    provenance = {
        "input_sha256": sha(INPUT),
        "anchor_receipt_sha256": sha(REPORT / "anchor-results.json"),
        "loader_sha256": sha(LOADER),
        "script_sha256": sha(Path(__file__)),
        "image_sha256": sha(output),
        "refitted": False,
        "scope": "Only passing GLRT candidates in the two previously selected track pairs",
        "checks": checks,
    }
    (REPORT / "glrt-scores-and-merge-curves.json").write_text(
        json.dumps(provenance, indent=2) + "\n"
    )
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
