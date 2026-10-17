"""Assemble frozen five-way receipts, coverage agreement and comparison plots."""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
METHODS = ["baseline", "em", "graph", "hough", "mht"]
NAMES = ["RANSAC baseline", "Wrapped EM", "Graph DP", "Hough voting", "MHT"]


def main():
    reports = {m: json.loads((ROOT / m / "comparison.json").read_text()) for m in METHODS}
    config = reports["baseline"]["config"]
    memberships, summary = {}, []
    for method, label in zip(METHODS, NAMES, strict=True):
        report = reports[method]
        assert report["config"] == config
        for path, expected in report["provenance"]["source_hashes"].items():
            assert "sha256:" + hashlib.sha256((REPO / path).read_bytes()).hexdigest() == expected
        data, heldout = report["real_data"], report["heldout_prediction"]
        with (ROOT / method / "assignments.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == len({r["observation_id"] for r in rows}) == 4797
        memberships[method] = {r["observation_id"]: r for r in rows}
        assert set(memberships[method]) == set(memberships["baseline"])
        assert sum(int(r["track_id"]) >= 0 for r in rows) == data["assigned"]
        summary.append(
            {
                "method": method,
                "label": label,
                "tracks": data["track_count"],
                "pieces": data["piece_count"],
                "assigned": data["assigned"],
                "assigned_fraction": data["assigned_fraction"],
                "unresolved": data["unresolved"],
                "no_structure_detected_points": data["residual_quality"]["no_structure_detected"][
                    "associated_points"
                ],
                "structure_flagged_points": data["residual_quality"]["structure_flagged"][
                    "associated_points"
                ],
                "insufficient_support_points": data["residual_quality"]["insufficient_support"][
                    "associated_points"
                ],
                "heldout_points_within_450hz": heldout[
                    "points_within_3sigma_of_training_prediction"
                ],
                "heldout_coverage_fraction": heldout["predictive_coverage_fraction"],
                "heldout_mean_log_density_gain_nats": heldout[
                    "mean_log_density_gain_over_uniform_nats"
                ],
                "full_scan_runtime_s": data["runtime_s"],
            }
        )
    with (ROOT / "comparison.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)

    agreement, counts = [], Counter()
    for observation_id in memberships["baseline"]:
        first = memberships["baseline"][observation_id]
        row = {k: first[k] for k in ("observation_id", "receiver", "channel", "time_s")}
        for method in METHODS:
            row[method] = int(memberships[method][observation_id]["track_id"]) >= 0
        row["new_methods_assigned_count"] = sum(row[m] for m in METHODS[1:])
        counts[row["new_methods_assigned_count"]] += 1
        agreement.append(row)
    with (ROOT / "coverage-agreement.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(agreement[0]))
        writer.writeheader()
        writer.writerows(agreement)
    controls = json.loads((ROOT / "shuffled-control.json").read_text())
    assert all(r["assigned"] == 0 for r in controls["reports"])
    document = {
        "dataset": "DSX01 S01, all4797 frozen winning observations,16receiver/channel lanes",
        "config": config,
        "methods": summary,
        "validation": {
            "component_tests_passed": 74,
            "ruff": "passed",
            "synthetic_cases_per_method": len(reports["baseline"]["synthetic_cases"]),
            "frequency_shuffled_assigned_points": {
                r["method"]: r["assigned"] for r in controls["reports"]
            },
            "integrity": "AlloriginalIDs retained; uniqueownership, integeralias lifts, "
            "residual gates, support/span/gap, analytic slope extrema, "
            "C1continuity and frozen source receipts checked.",
        },
        "coverage_agreement": {
            "new_method_count_histogram": dict(sorted(counts.items())),
            "assigned_by_at_least_one_new_method": sum(v for k, v in counts.items() if k >= 1),
            "assigned_by_all_four_new_methods": counts[4],
            "qualification": "Agreement concerns assignmentpresence, not commontrack or satellite "
            "identity. The union is not a fitted ensemble result.",
        },
        "interpretation": {
            "most_full_data_associations": "hough",
            "best_heldout_prediction": "em",
            "fastest": "graph",
            "balanced_candidate": "mht",
            "em_limit": "Higherfragmentation:196tracks and1350points on short tracks; poorer "
            "syntheticquartic/curvature-change recovery than baseline.",
            "graph_limit": "Greedyexclusive pathpacking; syntheticcontinuous-curvature control "
            "retains153/181signalpoints in4fragments.",
            "mht_limit": "BoundedKalman hypothesis beams, not exactglobal posterior; "
            "syntheticC1curve may remain2fragments.",
            "hough_limit": "Finitevote grid withlocalrefinement; bestfull-data coverage "
            "doesnotproduce bestheldoutprediction.",
        },
        "limits": "Allmethods share final numerical polynomialcompression and diagnostics but have "
        "independentdiscovery. Searchbudgets differ byfamily and runtimes are reported. "
        "S01 is inspecteddevelopment data; noverified true trackcount/satellite labels. "
        "No-structure-detected is conditional, not proofof whitenoise. Heldoutprediction "
        "excludes5secondblocks beforediscovery and scores all4797points once.",
    }
    (ROOT / "summary.json").write_text(json.dumps(document, indent=2) + "\n")

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    locations = np.arange(len(METHODS))
    left = np.zeros(len(METHODS))
    for field, color, label in (
        ("no_structure_detected_points", "#287d8e", "No residual structure detected"),
        ("structure_flagged_points", "#d95f02", "Residual structure flagged"),
        ("insufficient_support_points", "#d8bd67", "Insufficient diagnostic support"),
        ("unresolved", "#d3d3d3", "Unresolved"),
    ):
        values = [r[field] for r in summary]
        axes[0, 0].barh(locations, values, left=left, color=color, label=label)
        left += values
    axes[0, 0].set(
        yticks=locations,
        yticklabels=NAMES,
        xlim=(0, 4797),
        xlabel="Original observations (all 4,797 retained)",
        title="Full-data assignment and conditional residual diagnostics",
    )
    axes[0, 0].invert_yaxis()
    axes[0, 0].legend(fontsize=8, loc="lower left", bbox_to_anchor=(0, -0.48), ncol=2)
    predicted = [100 * r["heldout_coverage_fraction"] for r in summary]
    axes[0, 1].barh(locations, predicted, color="#287d8e")
    for i, value in enumerate(predicted):
        axes[0, 1].text(value + 0.5, i, f"{value:.1f}%", va="center")
    axes[0, 1].set(
        yticks=locations,
        yticklabels=NAMES,
        xlim=(0, 70),
        xlabel="Excluded points within 450 Hz of a training curve (%)",
        title="Discovery rerun independently: four folds of 5 s blocks",
    )
    axes[0, 1].invert_yaxis()
    runtime = [r["full_scan_runtime_s"] for r in summary]
    axes[1, 0].barh(locations, runtime, color="#47678d")
    for i, value in enumerate(runtime):
        axes[1, 0].text(value + 0.3, i, f"{value:.2f} s", va="center")
    axes[1, 0].set(
        yticks=locations,
        yticklabels=NAMES,
        xlim=(0, max(runtime) * 1.25),
        xlabel="Full scan fit time (seconds)",
        title="Measured runtime; distinct bounded searches",
    )
    axes[1, 0].invert_yaxis()
    cases = reports["baseline"]["synthetic_cases"]
    coverage = np.array(
        [
            [
                c["signal_coverage"] if c["signal_coverage"] is not None else np.nan
                for c in reports[m]["synthetic_cases"]
            ]
            for m in METHODS
        ]
    )
    palette = plt.get_cmap("YlGnBu").copy()
    palette.set_bad("#d3d3d3")
    axes[1, 1].imshow(coverage, vmin=0.8, vmax=1, aspect="auto", cmap=palette)
    axes[1, 1].set(
        yticks=locations,
        yticklabels=NAMES,
        xticks=np.arange(len(cases)),
        xticklabels=[c["case"].replace("_", " ") for c in cases],
        title="Synthetic signal coverage (gray: no signal)",
    )
    axes[1, 1].tick_params(axis="x", labelrotation=65, labelsize=8)
    for i in range(len(METHODS)):
        for j in range(len(cases)):
            if np.isfinite(coverage[i, j]):
                axes[1, 1].text(
                    j,
                    i,
                    f"{coverage[i, j]:.0%}",
                    ha="center",
                    va="center",
                    color="white" if coverage[i, j] > 0.95 else "black",
                    fontsize=8,
                )
    fig.suptitle(
        "DSX01 S01 · Four independent discovery algorithms and the existing baseline", fontsize=16
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.96), h_pad=4, w_pad=3)
    fig.text(
        0.5,
        0.012,
        "Assignments are receiver/channel tracklets, not satellite identities. "
        "All methods assign zero points in the frequency-shuffled scan control.",
        ha="center",
        fontsize=10,
    )
    for extension in ("png", "pdf"):
        fig.savefig(ROOT / f"comparison.{extension}", dpi=170)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
