"""Full development cohorts with explicit numerical fallbacks and paired RF arms."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "2026_10_08_position_error_iter10"


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    variants = ["baseline", "previous_joint", *protocol["variants"]]
    cases = []
    for label in protocol["labels"]:
        path = (
            (SOURCE if label in protocol["reused_results"] else HERE) / "results" / f"{label}.json"
        )
        if label in protocol["reused_results"]:
            assert (
                hashlib.sha256(path.read_bytes()).hexdigest() == protocol["reused_results"][label]
            )
        doc = json.loads(path.read_text())
        arms = {}
        for arm in ("fitted-c", "zero-c"):
            baseline = next(a["selected"] for a in doc["baseline_arms"] if a["name"] == arm)
            before = dict(
                error_km=baseline["horizontal_error_m"] / 1000,
                rms_hz=baseline["posterior_rms_hz"],
                fallback=False,
            )
            rows = dict(baseline=before)
            for variant in variants[1:]:
                pool = (
                    doc["previous_candidates"] if variant == "previous_joint" else doc["candidates"]
                )
                name = "joint-wide" if variant == "previous_joint" else variant
                r = next(r for r in pool if r["arm"] == arm and r["variant"] == name)
                rows[variant] = dict(
                    error_km=r["error_km"] if r["converged"] else before["error_km"],
                    rms_hz=r["posterior_rms_hz"] if r["converged"] else before["rms_hz"],
                    fallback=not r["converged"],
                    raw_error_km=r["error_km"],
                    stationarity=r["stationarity"],
                    removed=r.get("removed", []),
                )
            arms[arm] = rows
        cohort = (
            "diagnostic"
            if label == "DS17-008"
            else "DS17-development"
            if label.startswith("DS17")
            else "newer"
            if label.startswith("NEW")
            else "DS16"
        )
        cases.append(
            dict(
                label=label,
                cohort=cohort,
                arms=arms,
                result_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    aggregates, paired = {}, {}
    for cohort in ("DS16", "DS17-development", "newer", "diagnostic"):
        group = [c for c in cases if c["cohort"] == cohort]
        common = [
            c
            for c in group
            if not any(
                c["arms"][arm][v]["fallback"]
                for arm in ("fitted-c", "zero-c")
                for v in protocol["variants"]
            )
        ]
        paired[cohort] = dict(
            labels=[c["label"] for c in common],
            excluded=[c["label"] for c in group if c not in common],
            arms={},
        )
        aggregates[cohort] = {}
        for arm in ("fitted-c", "zero-c"):
            aggregates[cohort][arm] = {}
            paired[cohort]["arms"][arm] = {}
            baseline = np.array([c["arms"][arm]["baseline"]["error_km"] for c in group])
            control = np.array([c["arms"][arm]["warm-control"]["error_km"] for c in group])
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
                    fallback=sum(r["fallback"] for r in rows),
                    fallback_labels=[
                        c["label"] for c in group if c["arms"][arm][variant]["fallback"]
                    ],
                    improved_vs_baseline=int((errors < baseline - 0.001).sum()),
                    worsened_vs_baseline=int((errors > baseline + 0.001).sum()),
                    improved_vs_control=int((errors < control - 0.001).sum()),
                    worsened_vs_control=int((errors > control + 0.001).sum()),
                    mean_rms_hz=float(np.mean([r["rms_hz"] for r in rows])),
                )
                if common and variant in protocol["variants"]:
                    paired[cohort]["arms"][arm][variant] = dict(
                        mean_km=float(
                            np.mean([c["arms"][arm][variant]["error_km"] for c in common])
                        ),
                        mean_rms_hz=float(
                            np.mean([c["arms"][arm][variant]["rms_hz"] for c in common])
                        ),
                    )
    (HERE / "summary.json").write_text(
        json.dumps(dict(cases=cases, aggregates=aggregates, paired=paired), indent=2) + "\n"
    )
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), layout="constrained")
    for col, cohort in enumerate(("DS16", "DS17-development", "newer")):
        for row, arm in enumerate(("fitted-c", "zero-c")):
            ax = axes[row, col]
            for variant in ("baseline", *protocol["variants"]):
                errors = sorted(
                    c["arms"][arm][variant]["error_km"] for c in cases if c["cohort"] == cohort
                )
                ax.step(
                    errors, np.arange(1, len(errors) + 1) / len(errors), where="post", label=variant
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
