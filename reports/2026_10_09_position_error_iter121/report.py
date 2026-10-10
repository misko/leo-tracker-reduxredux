"""Postfreeze truth evaluation only; no changes to conditional fusion policy."""

import hashlib
import json
import math
import runpy
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def error(position, reference):
    a, b, c, d = map(math.radians, (*position, *reference))
    h = math.sin((a - c) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((b - d) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1, max(0, h))))


def metrics(values):
    v = np.asarray(values, dtype=float)
    return {
        "count": len(v),
        "mean_km": float(np.mean(v)),
        "median_km": float(np.median(v)),
        "p95_km": float(np.quantile(v, 0.95)),
        "worst_km": float(np.max(v)),
    }


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    assert all(
        hashlib.sha256(Path(p).read_bytes()).hexdigest() == h
        for p, h in plan["source_sha256"].items()
    )
    data = json.loads((HERE / "selected-positions.json").read_text())
    paths = json.loads((HERE / "causal-paths.json").read_text())
    base = ROOT / "reports/2026_10_09_position_error_iter107"
    port = runpy.run_path(str(base / "report.py"))
    members = json.loads((base / "protocol.json").read_text())["members"]
    original = {
        r["label"]: r
        for r in json.loads((base / "FULL193_COMPLETE_SNAPSHOT.json").read_text())["rows"]
    }
    truth = {}
    for m in members:
        doc = port["evaluation_document"](m)
        truth[port["member_label"](m)] = [
            doc["reference_latitude_deg"],
            doc["reference_longitude_deg"],
        ]
    lookup = {r["label"]: r for r in data["members"]}
    evaluated = {}
    max_parity = 0.0
    for mode, rows in paths["paths"].items():
        evaluated[mode] = []
        for row in rows:
            item = {
                "label": row["label"],
                "dataset": lookup[row["label"]]["dataset"],
                "capture_start_utc_ns": row["order_ns"],
                "arms": {},
            }
            for arm, fix in row["arms"].items():
                out = {
                    name: None if fix[name] is None else error(fix[name], truth[row["label"]])
                    for name in ("standalone", "mean", "median")
                }
                delta = abs(
                    out["standalone"] - original[row["label"]]["arms"][arm]["candidate"]["error_km"]
                )
                max_parity = max(max_parity, delta)
                assert delta < 1e-8, (row["label"], arm, delta)
                item["arms"][arm] = dict(
                    errors_km=out, fix_count=fix["fix_count"], held=fix["held"]
                )
            evaluated[mode].append(item)
    groups = ["full", *sorted({r["dataset"] for r in data["members"]})]
    summary = {
        mode: {
            g: {
                a: {
                    method: metrics(
                        [
                            r["arms"][a]["errors_km"][method]
                            for r in rows
                            if g == "full" or r["dataset"] == g
                        ]
                    )
                    for method in ("standalone", "mean", "median")
                }
                for a in ("fitted-c", "zero-c")
            }
            for g in groups
        }
        for mode, rows in evaluated.items()
    }
    payload = {
        "scope": plan["scope"],
        "standalone_parity_max_km": max_parity,
        "coverage": paths["coverage"],
        "metrics": summary,
        "updates": evaluated,
        "covariance_claim": False,
        "frequency_fit_changed": False,
    }
    (HERE / "evaluation.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(14, 8))
    for i, mode in enumerate(("primary", "secondary")):
        for j, arm in enumerate(("fitted-c", "zero-c")):
            rows = evaluated[mode]
            for method in ("standalone", "mean", "median"):
                axes[i, j].plot(
                    range(1, len(rows) + 1),
                    [r["arms"][arm]["errors_km"][method] for r in rows],
                    label=method,
                    lw=1,
                )
            axes[i, j].set(
                title=f"{mode}: {arm}",
                xlabel="Chronological update (cold start included)",
                ylabel="Position error km",
                yscale="log",
            )
            axes[i, j].legend()
    fig.suptitle("Conditional stationary retrospective fusion; 107 recovery candidate standalone")
    fig.tight_layout()
    fig.savefig(HERE / "comparison.png", dpi=140)
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(14, 8))
    for i, mode in enumerate(("primary", "secondary")):
        for j, arm in enumerate(("fitted-c", "zero-c")):
            rows = evaluated[mode]
            start = rows[0]["capture_start_utc_ns"]
            hours = [(r["capture_start_utc_ns"] - start) / 3.6e12 for r in rows]
            for method in ("standalone", "mean", "median"):
                axes[i, j].plot(
                    hours, [r["arms"][arm]["errors_km"][method] for r in rows], label=method, lw=1
                )
            previous = None
            for r, hour in zip(rows, hours, strict=True):
                if r["dataset"] != previous:
                    axes[i, j].axvline(hour, color="gray", alpha=0.3, lw=0.7)
                    axes[i, j].text(
                        hour,
                        0.98,
                        r["dataset"],
                        rotation=90,
                        va="top",
                        fontsize=7,
                        transform=axes[i, j].get_xaxis_transform(),
                    )
                    previous = r["dataset"]
            axes[i, j].set(
                title=f"{mode}: {arm}",
                xlabel="Hours since first capture (not availability latency)",
                ylabel="Position error km",
                yscale="log",
            )
            axes[i, j].legend()
    fig.tight_layout()
    fig.savefig(HERE / "elapsed-comparison.png", dpi=140)
    plt.close(fig)
    text = [
        "# Conditional stationary causal replay",
        "",
        "All 193 updates are included, with zero outages in either arm. This is a capture-order retrospective replay on consumed development data; stationarity is hypothetical, and online availability is unverified. Standalone means iteration107's research recovery candidate, not deployed B7. No frequency fit or single-scan algorithm changed.",
        "",
        "|Full-cohort fitted-c method|Mean error km|Median error km|",
        "|---|---:|---:|",
        "|Standalone recovery candidate|1.2548|0.8926|",
        "|Cumulative mean, one hypothetical episode|0.4882|0.5186|",
        "|Cumulative coordinate median, one hypothetical episode|0.4206|0.4477|",
        "|Cumulative coordinate median, dataset cold starts|0.4276|0.4024|",
        "",
        "Fusion is a different multi-scan estimator with additional measurements and warm-up. Its 0.4206 km mean does not achieve or redefine the 0.4 km standalone goal. Dataset resets are predetermined artificial comparators, not proven installation changes. No parameter was selected from these errors.",
        "",
        "![Cold-start updates](comparison.png)",
        "",
        "![Capture-time cold start and dataset boundaries](elapsed-comparison.png)",
        "",
        "|Reset|Dataset|Arm|Method|Count|Mean km|Median km|p95 km|Worst km|",
        "|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for mode, groupsummary in summary.items():
        for group, arms in groupsummary.items():
            for arm, methods in arms.items():
                for name, s in methods.items():
                    text.append(
                        f"|{mode}|{group}|{arm}|{name}|{s['count']}|{s['mean_km']:.4f}|{s['median_km']:.4f}|{s['p95_km']:.4f}|{s['worst_km']:.4f}|"
                    )
    text += [
        "",
        f"Standalone parity maximum {max_parity:.3g} km. Full per-update values and membership: [evaluation.json](evaluation.json).",
        "",
        "Cumulative means and medians reuse more scans; their errors never replace mean standalone error. Coordinate median is chart-dependent, no covariance is claimed, and no moving or polar generalization is supported. Shared biases and incorrect stationarity remain risks. The inference engine supports held-state outages, but this reporter requires present standalone endpoints for parity; the actual frozen cohort has zero outages, so no outage error is imputed.",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(text) + "\n")


if __name__ == "__main__":
    main()
