"""All-member density-weighting results with frozen fallbacks and gates."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    source = HERE.parent / "2026_10_08_position_error_iter13/summary.json"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == protocol["baseline_summary_sha256"]
    baseline = {r["label"]: r for r in json.loads(source.read_text())["cases"]}
    cases = []
    variants = ("previous-post200", *protocol["variants"])
    for label in protocol["labels"]:
        document = json.loads((HERE / "results" / f"{label}.json").read_text())
        assert document["source_sha256"] == protocol["inputs"][label]
        arms = {}
        for arm in ("fitted-c", "zero-c"):
            previous = baseline[label]["arms"][arm]["post-200"]
            rows = {"previous-post200": previous}
            for variant in protocol["variants"]:
                fit = next(
                    r for r in document["candidates"] if r["arm"] == arm and r["variant"] == variant
                )
                rows[variant] = dict(
                    error_km=fit["error_km"] if fit["converged"] else previous["error_km"],
                    rms_hz=fit["posterior_rms_hz"] if fit["converged"] else previous["rms_hz"],
                    converged=fit["converged"],
                    fallback=None if fit["converged"] else "previous-post200-operational",
                    raw_error_km=fit["error_km"],
                    stationarity=fit["stationarity"],
                    elapsed_s=fit["elapsed_s"],
                )
            arms[arm] = rows
        cases.append(dict(label=label, cohort=baseline[label]["cohort"], arms=arms))
    assert len(cases) == 107
    aggregates, paired = {}, {}
    fig, axes = plt.subplots(2, 4, figsize=(17, 8), layout="constrained")
    for col, cohort in enumerate(("DS16", "DS17", "newer", "combined")):
        group = [r for r in cases if cohort == "combined" or r["cohort"] == cohort]
        shared = [
            r
            for r in group
            if all(r["arms"][a][v]["converged"] for a in ("fitted-c", "zero-c") for v in variants)
        ]
        aggregates[cohort], paired[cohort] = (
            {},
            dict(
                count=len(shared), excluded=[r["label"] for r in group if r not in shared], arms={}
            ),
        )
        for row, arm in enumerate(("fitted-c", "zero-c")):
            aggregates[cohort][arm], paired[cohort]["arms"][arm] = {}, {}
            before = np.array([r["arms"][arm]["previous-post200"]["error_km"] for r in group])
            for variant in variants:
                fits = [r["arms"][arm][variant] for r in group]
                errors = np.array([f["error_km"] for f in fits])
                aggregates[cohort][arm][variant] = dict(
                    count=len(group),
                    mean_km=float(errors.mean()),
                    median_km=float(np.median(errors)),
                    p95_km=float(np.percentile(errors, 95)),
                    worst_km=float(errors.max()),
                    worst_label=group[int(errors.argmax())]["label"],
                    improved=int((errors < before - 0.001).sum()),
                    worsened=int((errors > before + 0.001).sum()),
                    convergence_rate=float(np.mean([f["converged"] for f in fits])),
                    fallback_labels=[
                        r["label"] for r in group if r["arms"][arm][variant]["fallback"]
                    ],
                    mean_rms_hz=float(np.mean([f["rms_hz"] for f in fits])),
                )
                paired[cohort]["arms"][arm][variant] = dict(
                    mean_km=float(np.mean([r["arms"][arm][variant]["error_km"] for r in shared]))
                    if shared
                    else None,
                    mean_rms_hz=float(np.mean([r["arms"][arm][variant]["rms_hz"] for r in shared]))
                    if shared
                    else None,
                )
                axes[row, col].step(
                    np.sort(errors),
                    np.arange(1, len(errors) + 1) / len(errors),
                    where="post",
                    label=variant,
                )
            axes[row, col].set(
                title=f"{cohort}: {arm}", xlabel="Position error (km)", ylabel="Fraction"
            )
            axes[row, col].axvline(1, color="black", linestyle="--", linewidth=1)
            axes[row, col].grid(alpha=0.2)
            axes[row, col].legend(fontsize=7)
    gates = {}
    frozen = protocol["gates"]
    before = aggregates["combined"]["fitted-c"]["previous-post200"]
    for variant in protocol["variants"]:
        result = aggregates["combined"]["fitted-c"][variant]
        checks = dict(
            mean=result["mean_km"] < frozen["pooled_fitted_mean_km_lt"],
            cohort_means=all(
                aggregates[c]["fitted-c"][variant]["mean_km"]
                <= frozen["each_cohort_mean_ratio_max_vs_previous_post200"]
                * aggregates[c]["fitted-c"]["previous-post200"]["mean_km"]
                for c in ("DS16", "DS17", "newer")
            ),
            p95=result["p95_km"] <= frozen["pooled_p95_ratio_max"] * before["p95_km"],
            worst=result["worst_km"] <= frozen["pooled_worst_ratio_max"] * before["worst_km"],
            convergence=result["convergence_rate"] >= frozen["fitted_convergence_min"],
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
    fig.savefig(HERE / "distributions.png", dpi=160)
    print(json.dumps(dict(gates=gates, development_choice=chosen), indent=2))


if __name__ == "__main__":
    main()
