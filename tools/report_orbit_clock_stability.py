"""Evaluate a sealed orbit/clock replay; reference is never used in inference."""

import argparse
import hashlib
import json
import math
from pathlib import Path


def horizontal_error(model, reference):
    a, b = map(math.radians, [reference["latitude_deg"], reference["longitude_deg"]])
    c, d = map(math.radians, [model["latitude_deg"], model["longitude_deg"]])
    h = math.sin((c - a) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((d - b) / 2) ** 2
    return 12742017.6 * math.asin(math.sqrt(min(1.0, h)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["inference", "reference", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.inference.read_text())
    reference = json.loads(args.reference.read_text())
    args.output.mkdir(exist_ok=False)
    rows = [
        dict(
            selection=m["selection"],
            grouping=m["grouping"],
            fold=m["fold"],
            error_m=horizontal_error(m, reference),
            converged=m["converged"],
        )
        for m in source["stability"]
    ]
    full = {
        m["selection"]: horizontal_error(m["exact_clock_refit"], reference)
        for m in source["models"]
        if "exact_clock_refit" in m
    }
    result = dict(
        inference_sha256=hashlib.sha256(args.inference.read_bytes()).hexdigest(),
        reference_sha256=hashlib.sha256(args.reference.read_bytes()).hexdigest(),
        exact_full_error_m=full,
        deletion_results=rows,
    )
    (args.output / "evaluation.json").write_text(json.dumps(result, indent=2) + "\n")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True, layout="constrained")
    for ax, selection in zip(axes, ["all", "selected"], strict=True):
        for group, marker in [("norad", "o"), ("session", "s")]:
            subset = [r for r in rows if r["selection"] == selection and r["grouping"] == group]
            ax.scatter(
                [r["fold"] for r in subset],
                [r["error_m"] for r in subset],
                marker=marker,
                label="Remove satellite group" if group == "norad" else "Remove recording group",
            )
        ax.axhline(1000, color="black", ls="--", label="1 km")
        ax.axhline(full[selection], color="gray", label="All groups retained, exact orbit")
        ax.set(
            title=selection.capitalize() + " cohort",
            xlabel="Removed modulo-eight group",
            ylabel="Horizontal error (m)",
            xticks=range(8),
        )
        ax.grid(alpha=0.2)
    axes[0].legend(fontsize=8)
    fig.suptitle(
        "Retrospective nearest-epoch orbits + recorded shared clock bounds\n"
        + (
            "Reassociated identities frozen for sensitivity; "
            if "rerank_digest" in source
            else "Frozen wide-search identities; "
        )
        + "reference used only for evaluation"
    )
    fig.savefig(args.output / "stability.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()
