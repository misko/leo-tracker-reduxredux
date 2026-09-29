"""Matched four-cell ablation; no new fits or geographic selection."""
# ruff: noqa: E501 -- Markdown report rows.

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from study import CONE, HERE, ROOT, TREND, digest, read, save, verify


def main():
    bindings = read(HERE / "all-complete/evidence-sha256.json")["sha256"]
    verify(bindings)
    summary = read(HERE / "all-complete/summary.json")
    assert len(summary["rows"]) == 36 and all(r["status"] != "Pending" for r in summary["rows"])
    rows = []
    for row in summary["rows"]:
        if row["arm"] != "corr10":
            continue
        key = row["unit"].removesuffix("_corr10")
        other = next(r for r in summary["rows"] if r["unit"] == key + "_corr10_c40")
        values = {}
        for label, item, folder in (
            ("q020", row, TREND / "runs" / (key + "_q020")),
            ("soft40", other, CONE / "runs" / (key + "_c40")),
        ):
            path = folder / "held/result.json"
            name = str(path.relative_to(ROOT))
            assert bindings[name] == digest(path)
            held = read(path)
            assert held["audit_passed"]
            values[label] = {
                "valid": True,
                "error_m": item["baseline_error_m"],
                "held_nats": held["held_log_score"],
            }
        for label, item in (("corr10", row), ("corr10_soft40", other)):
            values[label] = {
                "valid": item["status"] == "Pass",
                "error_m": item["error_m"],
                "held_nats": item["audit"]["held_log_score"] if item["audit"] else None,
            }
        rows.append(
            {"panel": key, "dataset": row["dataset"], "size": row["size"], "models": values}
        )
    assert len(rows) == 18
    models = ["q020", "soft40", "corr10", "corr10_soft40"]
    medians = []
    for model in models:
        for ds in ("DS7", "DS8", "DS9"):
            for size in (4, 8):
                subset = [
                    r["models"][model] for r in rows if r["dataset"] == ds and r["size"] == size
                ]
                assert len(subset) == 3
                medians.append(
                    {
                        "model": model,
                        "dataset": ds,
                        "size": size,
                        "error_m": float(np.median([r["error_m"] for r in subset]))
                        if all(r["valid"] for r in subset)
                        else None,
                    }
                )
    comparisons = []
    for a, b in (
        ("q020", "soft40"),
        ("q020", "corr10"),
        ("soft40", "corr10_soft40"),
        ("corr10", "corr10_soft40"),
    ):
        matched = [r for r in rows if r["models"][a]["valid"] and r["models"][b]["valid"]]
        comparisons.append(
            {
                "from": a,
                "to": b,
                "audited_pairs": len(matched),
                "geo_better": sum(
                    r["models"][b]["error_m"] < r["models"][a]["error_m"] for r in matched
                ),
                "held_better": sum(
                    r["models"][b]["held_nats"] > r["models"][a]["held_nats"] for r in matched
                ),
                "median_held_change_nats": float(
                    np.median(
                        [r["models"][b]["held_nats"] - r["models"][a]["held_nats"] for r in matched]
                    )
                )
                if matched
                else None,
            }
        )
    save(HERE / "ablation.json", {"rows": rows, "medians": medians, "comparisons": comparisons})
    lines = [
        "# Correlation and receiver-cone ablation",
        "",
        "All four cells use the same normalized q=0.20 trend mixture, panels, masks and one-timing-per-scan geometry. "
        "q020 and soft40 are published zero-correlation controls; the two corr10 cells are the new ten-second covariance fits. "
        "The correlation change applies to both signal and background. Soft40 changes training candidate priors with shared nominal axes. "
        "Held density is normalized in the same frequency-contrast coordinates. No setting was selected by reference error.",
        "",
        "Median horizontal errors in metres, requiring all three block audits. These are comparisons to an exposed unsurveyed reference.",
        "",
        "| Model | DS7 four | DS7 eight | DS8 four | DS8 eight | DS9 four | DS9 eight |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for model in models:
        values = [r["error_m"] for r in medians if r["model"] == model]
        lines.append(
            "| "
            + model
            + " | "
            + " | ".join(f"{v:,.1f}" if v is not None else "Incomplete" for v in values)
            + " |"
        )
    lines += [
        "",
        "| Change | Audited pairs | Lower geographic error | Better held prediction | Median held change (nats) |",
        "|---|---:|---:|---:|---:|",
    ]
    for c in comparisons:
        value = (
            f"{c['median_held_change_nats']:+.3f}"
            if c["median_held_change_nats"] is not None
            else "Undefined"
        )
        lines.append(
            f"| {c['from']} → {c['to']} | {c['audited_pairs']} | {c['geo_better']} | {c['held_better']} | {value} |"
        )
    lines += [
        "",
        "Counts across nested panels and model contrasts are dependent. Higher predictive density is not proof of better geographic accuracy. "
        "All per-panel cells and failed-audit status remain in ablation.json; medians never silently omit an invalid block.",
        "",
        "![Matched eight-scan median errors](ablation.png)",
        "",
        "[All cells](ablation.json), [full fits and audits](all-complete/README.md).",
        "",
    ]
    with (HERE / "ABLATION.md").open("x") as f:
        f.write("\n".join(lines))
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for i, model in enumerate(models):
        values = [r["error_m"] for r in medians if r["model"] == model and r["size"] == 8]
        ax.bar(
            np.arange(3) + (i - 1.5) * 0.18,
            [np.nan if v is None else v for v in values],
            width=0.18,
            label=model,
        )
    ax.axhline(1000, color="gray", linestyle="--", label="1 km")
    ax.set_xticks(range(3), ["DS7", "DS8", "DS9"])
    ax.set_ylabel("Median eight-scan error (m)")
    ax.set_title("Matched ablation; exposed unsurveyed reference")
    ax.legend(ncol=3)
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    for suffix in ("png", "svg"):
        fig.savefig(HERE / f"ablation.{suffix}", dpi=160)
    plt.close(fig)
    print({"medians": medians, "comparisons": comparisons}, flush=True)


if __name__ == "__main__":
    main()
