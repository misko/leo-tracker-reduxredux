"""Sealed search-only reporting; no prediction, fitting or reference imports."""

import hashlib
import json
import runpy
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
HELPER = runpy.run_path(str(HERE / "report_search.py"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    encoded = json.dumps(
        plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
    data = HELPER["build"](HERE / "results" / "DS18-022", digest)
    assert data["terminal_status"] == "complete" and data["point_failure_count"] == 0
    assert all(t["trace_sealed"] and t["sample_count"] == 400 for t in data["traces"].values())
    data["allocation_comparisons"] = {}
    for arm in ("fitted-c", "zero-c"):
        sets = [
            {(p["east"], p["north"]) for p in data["traces"][arm + "-" + mode]["sampled_points"]}
            for mode in ("native", "fixed")
        ]
        ranks = data["initial_grid_comparisons"][arm]["initial_rank_changes"]
        data["allocation_comparisons"][arm] = {
            "sample_overlap": len(sets[0] & sets[1]),
            "fixed_only_samples": len(sets[1] - sets[0]),
            "changed_initial_ranks": sum(p["rank_delta"] != 0 for p in ranks),
            "max_absolute_rank_change": max(abs(p["rank_delta"]) for p in ranks),
            "mean_absolute_rank_change": float(np.mean([abs(p["rank_delta"]) for p in ranks])),
        }
    snapshot = HERE / "SEARCH_SNAPSHOT.json"
    snapshot.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    fig, axes = plt.subplots(2, 2, figsize=(11, 10))
    colors = ("#a0aec0", "#f6ad55", "#68d391", "#4299e1")
    for axis, name in zip(
        axes.flat,
        ("fitted-c-native", "fitted-c-fixed", "zero-c-native", "zero-c-fixed"),
        strict=True,
    ):
        trace = data["traces"][name]
        deferred = trace["deferred_cells"]
        axis.scatter(
            [p["east"] for p in deferred],
            [p["north"] for p in deferred],
            marker="x",
            c="#d4d4d4",
            s=10,
            linewidths=0.4,
            label="Deferred heap center",
        )
        for depth, color in enumerate(colors):
            selected = [p for p in trace["sampled_points"] if p["depth"] == depth]
            axis.scatter(
                [p["east"] for p in selected],
                [p["north"] for p in selected],
                c=color,
                s=12,
                label=f"{40 / 2**depth:g}km samples",
            )
        regions = data["retained_regions"][name]
        axis.scatter(
            [p["east_km"] for p in regions],
            [p["north_km"] for p in regions],
            marker="*",
            c="black",
            s=110,
            label="Score-retained region",
        )
        axis.set(
            title=name,
            xlabel="Hypothesis east km",
            ylabel="Hypothesis north km",
            aspect="equal",
            xlim=(-280, 280),
            ylim=(-280, 280),
        )
        axis.grid(alpha=0.15)
    fig.legend(*axes[0, 0].get_legend_handles_labels(), fontsize=8, loc="lower center", ncol=3)
    fig.suptitle("DS18-022: refinement and retention under two scores\nNo reference overlay")
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(HERE / "search-allocation.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(9, 4))
    for axis, arm in zip(axes, ("fitted-c", "zero-c"), strict=True):
        comparison = data["initial_grid_comparisons"][arm]
        assert comparison["initial_rank_comparison_complete"]
        ranks = comparison["initial_rank_changes"]
        axis.scatter([r["native_rank"] for r in ranks], [r["fixed_rank"] for r in ranks], s=12)
        axis.plot([1, 121], [1, 121], "k:")
        axis.set(title=arm, xlabel="Native rank on initial121", ylabel="Fixed rank on initial121")
        axis.grid(alpha=0.15)
    fig.suptitle("Same initial lattice: rank changes precede refinement")
    fig.tight_layout()
    fig.savefig(HERE / "initial-ranks.png", dpi=150)
    plt.close(fig)
    lines = [
        HELPER["markdown"](data),
        "All four queues sealed at 400 points; native fitted trace reproduced its frozen "
        "400-point/score baseline. No point-evaluation exceptions occurred. Independent "
        "coarse qualification failures remain in search under the ordinary policy.",
        "",
        "| Discovery arm | Initial ranks changed | Mean/max absolute change | "
        "Sample overlap | Fixed-only samples |",
        "|---|---:|---:|---:|---:|",
    ]
    for arm, row in data["allocation_comparisons"].items():
        lines.append(
            f"| {arm} | {row['changed_initial_ranks']}/121 | "
            f"{row['mean_absolute_rank_change']:.3f}/{row['max_absolute_rank_change']} | "
            f"{row['sample_overlap']}/400 | {row['fixed_only_samples']} |"
        )
    lines += ["", "| Queue | Retained hypotheses (east,north km; spacing km) |", "|---|---|"]
    for name, regions in data["retained_regions"].items():
        points = "; ".join(
            f"({p['east_km']:g},{p['north_km']:g};{p['spacing_km']:g})" for p in regions
        )
        lines.append(f"| {name} | {points} |")
    lines += [
        "",
        "The fixed score reorders the same 121 initial points and changes fine-grid "
        "discovery and retained hypotheses. This establishes a queue/retention effect, "
        "not improved localization. Native/fixed raw scores are not comparable as evidence "
        "of improvement. Fixed is a restricted whole-bank plug-in rescore, not a refit.",
        "",
        "The 828.033s is persisted elapsed across two slices, including replay and "
        "rescoring. Native fitted coarse receipts and seeds reuse historical work; this "
        "is not four fresh equal-wall-time analyses or an embedded-speed benchmark.",
        "",
        "A bounded symmetric downstream test is warranted. Primary comparison: "
        "fitted-native versus fitted-fixed discovery, with both final c arms in each branch. "
        "Zero-discovery queues are separate sensitivities, not c=0 counterfactuals to fitted "
        "discovery. Preserve all three retained regions and apply identical recovery. "
        "No native/fixed union or favorable-region selection is justified. "
        "See [continuation plan](CONTINUATION_PLAN.md).",
        "",
        "![Allocation](search-allocation.png)",
        "",
        "![Initial ranks](initial-ranks.png)",
        "",
        "[Sealed metadata and receipt hashes](SEARCH_SNAPSHOT.json). This reporting code "
        "read no reference coordinates/errors, recording inputs or positioning winner "
        "outcomes and performed no model evaluations or fits.",
    ]
    report = HERE / "RESULTS.md"
    report.write_text("\n".join(lines) + "\n")
    artifacts = [
        snapshot,
        report,
        HERE / "search-allocation.png",
        HERE / "initial-ranks.png",
        HERE / "report_search.py",
        HERE / "publish_search.py",
        HERE / "protocol.json",
        HERE / "CONTINUATION_PLAN.md",
    ]
    (HERE / "SEARCH_INTEGRITY.json").write_text(
        json.dumps(
            {
                "protocol_digest": digest,
                "receipt_sha256": data["receipt_sha256"],
                "artifact_sha256": {p.name: sha(p) for p in artifacts},
                "scope": "Search-only; source/input closure inherited from frozen protocol",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
