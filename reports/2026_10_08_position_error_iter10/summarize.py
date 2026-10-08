"""Summarize every declared timing-consistency diagnostic and control."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    cases = []
    for label in protocol["labels"]:
        doc = json.loads((HERE / "results" / f"{label}.json").read_text())
        arms = {}
        for arm in ("fitted-c", "zero-c"):
            b = next(a["selected"] for a in doc["baseline_arms"] if a["name"] == arm)
            wide = next(
                r
                for r in doc["previous_candidates"]
                if r["variant"] == "joint-wide" and r["arm"] == arm
            )
            rows = dict(
                baseline=dict(
                    error_km=b["horizontal_error_m"] / 1000,
                    rms_hz=b["posterior_rms_hz"],
                    fallback=False,
                ),
                previous_joint=dict(
                    error_km=wide["error_km"]
                    if wide["converged"]
                    else b["horizontal_error_m"] / 1000,
                    rms_hz=wide["posterior_rms_hz"] if wide["converged"] else b["posterior_rms_hz"],
                    fallback=not wide["converged"],
                ),
            )
            for variant in protocol["variants"]:
                r = next(
                    r for r in doc["candidates"] if r["variant"] == variant and r["arm"] == arm
                )
                rows[variant] = dict(
                    error_km=r["error_km"] if r["converged"] else b["horizontal_error_m"] / 1000,
                    rms_hz=r["posterior_rms_hz"] if r["converged"] else b["posterior_rms_hz"],
                    raw_error_km=r["error_km"],
                    fallback=not r["converged"],
                    removed=r["removed"],
                )
            arms[arm] = rows
        cases.append(dict(label=label, arms=arms))
    aggregates = {}
    for arm in ("fitted-c", "zero-c"):
        aggregates[arm] = {}
        for variant in ("baseline", "previous_joint", *protocol["variants"]):
            rows = [c["arms"][arm][variant] for c in cases]
            errors = np.asarray([r["error_km"] for r in rows])
            control = np.asarray([c["arms"][arm]["warm-control"]["error_km"] for c in cases])
            aggregates[arm][variant] = dict(
                mean_km=float(errors.mean()),
                median_km=float(np.median(errors)),
                worst_km=float(errors.max()),
                mean_rms_hz=float(np.mean([r["rms_hz"] for r in rows])),
                fallback=sum(r["fallback"] for r in rows),
                improved_vs_control=int((errors < control - 0.001).sum()),
                worsened_vs_control=int((errors > control + 0.001).sum()),
            )
    (HERE / "summary.json").write_text(
        json.dumps(dict(cases=cases, aggregates=aggregates), indent=2) + "\n"
    )
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), layout="constrained")
    for ax, arm in zip(axes, ("fitted-c", "zero-c"), strict=True):
        for i, variant in enumerate(protocol["variants"]):
            ax.bar(
                np.arange(len(cases)) + (i - 1.5) * 0.2,
                [c["arms"][arm][variant]["error_km"] for c in cases],
                0.2,
                label=variant,
            )
        ax.set_xticks(np.arange(len(cases)), [c["label"] for c in cases], rotation=25)
        ax.set(title=arm, ylabel="Position error (km)")
        ax.axhline(1, color="black", linestyle="--", linewidth=1)
        ax.grid(axis="y", alpha=0.2)
        ax.legend()
    fig.savefig(HERE / "comparison.png", dpi=160)
    print(json.dumps(aggregates, indent=2))


if __name__ == "__main__":
    main()
