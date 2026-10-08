"""Complete-cohort clock-prior sensitivity, including convergence fallbacks."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
VARIANTS = ("baseline", "joint-wide", "joint-200", "joint-400")


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    cases = []
    for label in protocol["labels"]:
        doc = json.loads((HERE / "results" / f"{label}.json").read_text())
        rows = doc["previous_candidates"] + doc["candidates"]
        arms = {}
        for arm in ("fitted-c", "zero-c"):
            baseline = next(a["selected"] for a in doc["baseline_arms"] if a["name"] == arm)
            arm_rows = {
                "baseline": dict(
                    error_km=baseline["horizontal_error_m"] / 1000,
                    rms_hz=baseline["posterior_rms_hz"],
                    fallback=False,
                )
            }
            for variant in VARIANTS[1:]:
                row = next(r for r in rows if r["arm"] == arm and r["variant"] == variant)
                arm_rows[variant] = dict(
                    error_km=row["error_km"]
                    if row["converged"]
                    else arm_rows["baseline"]["error_km"],
                    rms_hz=row["posterior_rms_hz"]
                    if row["converged"]
                    else arm_rows["baseline"]["rms_hz"],
                    fallback=not row["converged"],
                    raw_error_km=row["error_km"],
                    stationarity=row["stationarity"],
                )
            arms[arm] = arm_rows
        cohort = (
            "diagnostic"
            if label == "DS17-008"
            else "DS17-development"
            if label.startswith("DS17")
            else "newer"
            if label.startswith("NEW")
            else "DS16"
        )
        cases.append(dict(label=label, cohort=cohort, arms=arms))
    aggregates = {}
    for cohort in ("DS16", "DS17-development", "newer", "diagnostic"):
        aggregates[cohort] = {}
        group = [c for c in cases if c["cohort"] == cohort]
        for arm in ("fitted-c", "zero-c"):
            aggregates[cohort][arm] = {}
            baseline = np.array([c["arms"][arm]["baseline"]["error_km"] for c in group])
            for variant in VARIANTS:
                rows = [c["arms"][arm][variant] for c in group]
                errors = np.array([r["error_km"] for r in rows])
                aggregates[cohort][arm][variant] = dict(
                    count=len(rows),
                    mean_km=float(errors.mean()),
                    median_km=float(np.median(errors)),
                    p95_km=float(np.percentile(errors, 95)),
                    worst_km=float(errors.max()),
                    mean_rms_hz=float(np.mean([r["rms_hz"] for r in rows])),
                    improved=int((errors < baseline - 0.001).sum()),
                    worsened=int((errors > baseline + 0.001).sum()),
                    fallback=sum(r["fallback"] for r in rows),
                    worst_label=group[int(errors.argmax())]["label"],
                )
    strict_shared = {}
    for cohort in aggregates:
        group = [c for c in cases if c["cohort"] == cohort]
        paired = [
            c
            for c in group
            if not any(
                c["arms"][arm][variant]["fallback"]
                for arm in ("fitted-c", "zero-c")
                for variant in VARIANTS[1:]
            )
        ]
        strict_shared[cohort] = dict(
            count=len(paired),
            excluded=[c["label"] for c in group if c not in paired],
            arms={
                arm: {
                    variant: dict(
                        mean_km=float(
                            np.mean([c["arms"][arm][variant]["error_km"] for c in paired])
                        ),
                        mean_rms_hz=float(
                            np.mean([c["arms"][arm][variant]["rms_hz"] for c in paired])
                        ),
                    )
                    for variant in VARIANTS[1:]
                }
                for arm in ("fitted-c", "zero-c")
            },
        )
    (HERE / "summary.json").write_text(
        json.dumps(dict(cases=cases, aggregates=aggregates, strict_shared=strict_shared), indent=2)
        + "\n"
    )
    fig, axes = plt.subplots(2, 3, figsize=(13, 7), layout="constrained")
    for col, cohort in enumerate(("DS16", "DS17-development", "newer")):
        for row, arm in enumerate(("fitted-c", "zero-c")):
            ax = axes[row, col]
            for variant in VARIANTS:
                values = sorted(
                    c["arms"][arm][variant]["error_km"] for c in cases if c["cohort"] == cohort
                )
                ax.step(
                    values, np.arange(1, len(values) + 1) / len(values), where="post", label=variant
                )
            ax.axvline(1, color="black", linestyle="--", linewidth=1)
            ax.set(
                title=f"{cohort}: {arm}", xlabel="Position error (km)", ylabel="Fraction of scans"
            )
            ax.grid(alpha=0.2)
            ax.legend(fontsize=8)
    fig.savefig(HERE / "distributions.png", dpi=160)
    print(json.dumps(aggregates, indent=2))


if __name__ == "__main__":
    main()
