"""Evaluate frozen clock-prior interaction gates with all-member fallbacks."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    variants = ("previous-remove-5", *protocol["variants"])
    cases = []
    for label in protocol["labels"]:
        doc = json.loads((HERE / "results" / f"{label}.json").read_text())
        arms = {}
        for arm in ("fitted-c", "zero-c"):
            baseline = next(a["selected"] for a in doc["baseline_arms"] if a["name"] == arm)
            previous = next(r for r in doc["previous_candidates"] if r["arm"] == arm)
            previous_error = (
                previous["error_km"]
                if previous["converged"]
                else baseline["horizontal_error_m"] / 1000
            )
            previous_rms = (
                previous["posterior_rms_hz"]
                if previous["converged"]
                else baseline["posterior_rms_hz"]
            )
            rows = {
                "previous-remove-5": dict(
                    error_km=previous_error,
                    rms_hz=previous_rms,
                    converged=previous["converged"],
                    fallback=None if previous["converged"] else "baseline",
                )
            }
            for variant in protocol["variants"]:
                r = next(
                    r for r in doc["candidates"] if r["arm"] == arm and r["variant"] == variant
                )
                rows[variant] = dict(
                    error_km=r["error_km"] if r["converged"] else previous_error,
                    rms_hz=r["posterior_rms_hz"] if r["converged"] else previous_rms,
                    raw_error_km=r["error_km"],
                    converged=r["converged"],
                    stationarity=r["stationarity"],
                    fallback=None
                    if r["converged"]
                    else "previous-remove-5"
                    if previous["converged"]
                    else "baseline",
                )
            arms[arm] = rows
        cohort = (
            "DS17" if label.startswith("DS17") else "newer" if label.startswith("NEW") else "DS16"
        )
        cases.append(dict(label=label, cohort=cohort, arms=arms))
    assert len(cases) == 107
    aggregates, paired = {}, {}
    for cohort in ("DS16", "DS17", "newer", "combined"):
        group = [c for c in cases if cohort == "combined" or c["cohort"] == cohort]
        common = [
            c
            for c in group
            if all(c["arms"][a][v]["converged"] for a in ("fitted-c", "zero-c") for v in variants)
        ]
        paired[cohort] = dict(
            count=len(common), excluded=[c["label"] for c in group if c not in common], arms={}
        )
        aggregates[cohort] = {}
        for arm in ("fitted-c", "zero-c"):
            aggregates[cohort][arm] = {}
            paired[cohort]["arms"][arm] = {}
            before = np.array([c["arms"][arm]["previous-remove-5"]["error_km"] for c in group])
            for variant in variants:
                rows = [c["arms"][arm][variant] for c in group]
                errors = np.array([r["error_km"] for r in rows])
                aggregates[cohort][arm][variant] = dict(
                    count=len(rows),
                    mean_km=float(errors.mean()),
                    median_km=float(np.median(errors)),
                    p95_km=float(np.percentile(errors, 95)),
                    worst_km=float(errors.max()),
                    worst_label=group[int(errors.argmax())]["label"],
                    convergence_rate=float(np.mean([r["converged"] for r in rows])),
                    fallback_labels=[
                        c["label"] for c in group if c["arms"][arm][variant]["fallback"]
                    ],
                    improved=int((errors < before - 0.001).sum()),
                    worsened=int((errors > before + 0.001).sum()),
                    mean_rms_hz=float(np.mean([r["rms_hz"] for r in rows])),
                )
                paired[cohort]["arms"][arm][variant] = dict(
                    mean_km=float(np.mean([c["arms"][arm][variant]["error_km"] for c in common])),
                    mean_rms_hz=float(np.mean([c["arms"][arm][variant]["rms_hz"] for c in common])),
                )
    gates = {}
    before = aggregates["combined"]["fitted-c"]["previous-remove-5"]
    for variant in protocol["variants"]:
        r = aggregates["combined"]["fitted-c"][variant]
        checks = dict(
            mean_below_1=r["mean_km"] < 1,
            cohort_means=all(
                aggregates[c]["fitted-c"][variant]["mean_km"]
                <= 1.05 * aggregates[c]["fitted-c"]["previous-remove-5"]["mean_km"]
                for c in ("DS16", "DS17", "newer")
            ),
            p95=r["p95_km"] <= 1.1 * before["p95_km"],
            worst=r["worst_km"] <= 1.1 * before["worst_km"],
            convergence=r["convergence_rate"] >= 0.95,
        )
        gates[variant] = dict(checks=checks, passed=all(checks.values()))
    chosen = next((v for v in protocol["variants"] if gates[v]["passed"]), None)
    (HERE / "summary.json").write_text(
        json.dumps(
            dict(
                cases=cases,
                aggregates=aggregates,
                paired=paired,
                gates=gates,
                development_choice=chosen,
            ),
            indent=2,
        )
        + "\n"
    )
    fig, axes = plt.subplots(2, 4, figsize=(17, 8), layout="constrained")
    for col, cohort in enumerate(("DS16", "DS17", "newer", "combined")):
        for row, arm in enumerate(("fitted-c", "zero-c")):
            ax = axes[row, col]
            for variant in variants:
                errors = sorted(
                    c["arms"][arm][variant]["error_km"]
                    for c in cases
                    if cohort == "combined" or c["cohort"] == cohort
                )
                ax.step(
                    errors, np.arange(1, len(errors) + 1) / len(errors), where="post", label=variant
                )
            ax.axvline(1, color="black", linestyle="--", linewidth=1)
            ax.set(
                title=f"{cohort}: {arm}", xlabel="Position error (km)", ylabel="Fraction of scans"
            )
            ax.grid(alpha=0.2)
            ax.legend(fontsize=7)
    fig.savefig(HERE / "distributions.png", dpi=160)
    print(json.dumps(dict(gates=gates, development_choice=chosen), indent=2))


if __name__ == "__main__":
    main()
