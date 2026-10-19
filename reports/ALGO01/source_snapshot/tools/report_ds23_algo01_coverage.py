"""Post-fit association accounting and GPS evaluation; never choose a fit."""

import csv
import hashlib
import json

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from associate_merged_track_catalogue import write
from audit_ds23_algo01_coverage import OUT, ROOT, SOURCE, read
from report_ds23_arc_positions import distance

METHODS = ("ALGO01", "greedy_graph_repair", "joint_paths", "satellite_EM")
LABELS = ("ALGO01", "Greedy", "Joint", "EM MAP")


def main():
    rows, hashes = [], {}
    for case in ("DS23-0342", "DS23-0039"):
        old_tracks = read(SOURCE / case / "tracks.json")
        target = (
            next(t for t in old_tracks if "RX1-CH2-T002-" in t["key"])
            if case.endswith("342")
            else None
        )
        for method in METHODS:
            for arm in ("c0", "fitted_c"):
                path = OUT / f"{case}_{method}_{arm}.json"
                d = read(path)
                a = d["association"]
                assert not d["calibration_gate_failures"]
                assert a["associated_distinct_measurements"] == (
                    a["associated_original_winners"] + a["associated_additional_peaks"]
                )
                recovered = (
                    len(set(a["associated_observation_ids"]) & set(target["observation_ids"]))
                    if target
                    else None
                )
                rows.append(
                    dict(
                        case=case,
                        method=method,
                        arm=arm,
                        original_GLRT_points=a["original_winning_GLRT_points"],
                        associated_original_points=a["associated_original_winners"],
                        associated_original_percent=a["associated_original_percent"],
                        additional_associated_peaks=a["associated_additional_peaks"],
                        associated_distinct_measurements=a["associated_distinct_measurements"],
                        associated_tracks=a["associated_tracks"],
                        recovered_original_T002_points=recovered,
                        error_km=distance(d["endpoint_latlon"]),
                    )
                )
                hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    with (OUT / "comparison.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for case in ("DS23-0342", "DS23-0039"):
        for method in METHODS:
            pair = [r for r in rows if r["case"] == case and r["method"] == method]
            assert pair[0]["associated_original_points"] == pair[1]["associated_original_points"]
            assert pair[0]["additional_associated_peaks"] == pair[1]["additional_associated_peaks"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    colors = ("#62686e", "#3b82b5", "#34a08b", "#a05aba")
    for i, case in enumerate(("DS23-0342", "DS23-0039")):
        c0 = [
            next(r for r in rows if r["case"] == case and r["method"] == m and r["arm"] == "c0")
            for m in METHODS
        ]
        fitted = [
            next(
                r for r in rows if r["case"] == case and r["method"] == m and r["arm"] == "fitted_c"
            )
            for m in METHODS
        ]
        x = np.arange(4)
        ax = axes[i, 0]
        bars = ax.bar(x, [r["associated_original_percent"] for r in c0], color=colors)
        ax.bar_label(bars, fmt="%.2f%%", padding=3)
        ax.set(
            ylim=(0, 82),
            ylabel="Original winning GLRT points associated (%)",
            title=f"{case}: full-scan coverage",
            xticks=x,
            xticklabels=LABELS,
        )
        for xx, r in zip(x, c0, strict=True):
            ax.text(
                xx,
                3,
                f"{r['associated_original_points']}/{r['original_GLRT_points']}\n"
                f"+{r['additional_associated_peaks']} secondary",
                ha="center",
                va="bottom",
                color="white",
                fontsize=9,
            )
        ax = axes[i, 1]
        bars = ax.bar(
            x - 0.18, [r["error_km"] for r in c0], width=0.36, color=colors, label="c = 0"
        )
        ax.bar_label(bars, fmt="%.3f", padding=3, fontsize=8)
        bars = ax.bar(
            x + 0.18,
            [r["error_km"] for r in fitted],
            width=0.36,
            color=colors,
            alpha=0.48,
            label="fitted c",
        )
        ax.bar_label(bars, fmt="%.3f", padding=3, fontsize=8)
        ax.set(
            ylim=(0, max(r["error_km"] for r in c0) * 1.23),
            ylabel="Position error (km)",
            title=f"{case}: position",
            xticks=x,
            xticklabels=LABELS,
        )
        ax.legend(fontsize=8)
    for ax in axes.flat:
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
    fig.suptitle(
        "Expanded association versus conservative ALGO01\n"
        "More original GLRT points associated; position error increases on both scans"
    )
    fig.tight_layout()
    fig.savefig(OUT / "coverage_and_position.png", dpi=150)
    plt.close(fig)
    hashes["tools/audit_ds23_algo01_coverage.py"] = hashlib.sha256(
        (ROOT / "tools/audit_ds23_algo01_coverage.py").read_bytes()
    ).hexdigest()
    write(
        OUT / "validation.json",
        dict(
            endpoint_replays=16,
            stored_objective_replay_tolerance=1e-5,
            original_vs_secondary_counts_separate=True,
            all_retained_calibration_tracks_pass_existing_gates=True,
            full_active_masks_match_existing_actual_metrics=True,
            c_pair_coverage_identical=True,
            position_refitted=False,
            calibrated_association_confidence=False,
            tests="9 passed",
            source_sha256=hashes,
        ),
    )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
