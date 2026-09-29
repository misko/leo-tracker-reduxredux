"""Report all completed drift allocations without choosing one by roof error."""
# ruff: noqa: E501 -- Markdown report prose and rows.

import json

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from study import HERE, read, save  # noqa: E402


def main():
    summary = read(HERE / "all-complete/summary.json")
    rows = summary["rows"]
    assert len(rows) == 54 and all(r["status"] != "Pending" for r in rows)
    arms = ("symmetric", "rx0_anchor", "rx1_anchor")
    totals, medians = {}, {}
    for arm in arms:
        chosen = [r for r in rows if r["arm"] == arm]
        valid = [r for r in chosen if r["status"] == "Audited"]
        totals[arm] = {
            "audited": len(valid),
            "qualified_starts": sum(r.get("qualified_starts", 0) for r in chosen),
            "geo_better": sum(r["error_m"] < r["baseline_error_m"] - 1e-6 for r in valid),
            "geo_tied": sum(abs(r["error_m"] - r["baseline_error_m"]) <= 1e-6 for r in valid),
            "held_better": sum(r["held_delta_nats"] > 1e-7 for r in valid),
            "held_tied": sum(abs(r["held_delta_nats"]) <= 1e-7 for r in valid),
            "subkm": sum(r["error_m"] < 1000 for r in valid),
            "worst_error_m": max((r["error_m"] for r in valid), default=None),
            "median_held_delta_nats": float(np.median([r["held_delta_nats"] for r in valid]))
            if valid
            else None,
        }
        medians[arm] = summary["medians_m"][arm]
    baseline = {}
    for ds in ("DS7", "DS8", "DS9"):
        baseline[ds] = {}
        for size in (4, 8):
            selected = [
                r
                for r in rows
                if r["arm"] == "symmetric" and r["dataset"] == ds and r["size"] == size
            ]
            assert len(selected) == 3 and all("baseline_error_m" in r for r in selected)
            baseline[ds][str(size)] = float(np.median([r["baseline_error_m"] for r in selected]))
    output = {"totals": totals, "medians_m": {"baseline": baseline, **medians}, "rows": rows}
    save(HERE / "ablation.json", output)
    lines = [
        "# Completed differential-drift geographic ablation",
        "",
        "All 54 declared combinations are terminal. No allocation is selected by reference error.",
        "Each median requires all three early/middle/late panel audits. Missing medians are explicit.",
        "",
        "| Model | DS7 / 4 m | DS7 / 8 m | DS8 / 4 m | DS8 / 8 m | DS9 / 4 m | DS9 / 8 m |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, by_ds in output["medians_m"].items():
        values = [by_ds[ds][str(n)] for ds in ("DS7", "DS8", "DS9") for n in (4, 8)]
        lines.append(
            "| "
            + arm
            + " | "
            + " | ".join("Incomplete" if v is None else f"{v:,.1f}" for v in values)
            + " |"
        )
    lines += [
        "",
        "| Allocation | Audited / 18 | Lower error | Error tie | Better held | Held tie | Sub-km | Worst error m |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, t in totals.items():
        lines.append(
            f"| {arm} | {t['audited']} | {t['geo_better']} | {t['geo_tied']} | {t['held_better']} | {t['held_tied']} | {t['subkm']} | {t['worst_error_m']:.1f} |"
        )
    lines += [
        "",
        "Tie tolerances are 1e-6 m and 1e-7 nats for numerical reporting only.",
        "Counts use audited results; nested panels and donor corrections are dependent.",
        "These previously explored, unsurveyed-reference errors are not blind accuracy or calibrated resolution.",
        "",
        "![Median errors](ablation.png)",
        "",
        "[Every panel, start and audit status](all-complete/README.md). [Machine-readable comparison](ablation.json).",
    ]
    with (HERE / "ABLATION.md").open("x") as f:
        f.write("\n".join(lines) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
    for ax, size in zip(axes, (4, 8), strict=True):
        for j, (arm, by_ds) in enumerate(output["medians_m"].items()):
            values = [by_ds[ds][str(size)] for ds in ("DS7", "DS8", "DS9")]
            ax.bar(
                np.arange(3) + (j - 1.5) * 0.19,
                [np.nan if v is None else v / 1000 for v in values],
                width=0.19,
                label=arm.replace("_", " "),
            )
        ax.axhline(1, color="grey", linestyle=":")
        ax.set_xticks(np.arange(3), ["DS7", "DS8", "DS9"])
        ax.set_title(f"{size}-scan median")
        ax.set_ylabel("Nominal error (km)")
    axes[1].legend(fontsize=8)
    fig.suptitle("Receiver drift allocation: all declared arms; no reference-selected winner")
    for suffix in ("png", "svg"):
        fig.savefig(HERE / ("ablation." + suffix), dpi=160)
    plt.close(fig)
    print(json.dumps({"totals": totals, "medians_m": output["medians_m"]}, indent=2))


if __name__ == "__main__":
    main()
