"""Full DS17 and combined development results without hiding the original catastrophe."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
VARIANTS = ("baseline_original", "baseline_region", "warm-control", "remove-5")


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    old = json.loads((HERE.parent / "2026_10_08_position_error_iter11/summary.json").read_text())
    cases = []
    for case in old["cases"]:
        if case["label"] == "DS17-008":
            continue
        arms = {}
        for arm, rows in case["arms"].items():
            arms[arm] = dict(
                baseline_original=rows["baseline"],
                baseline_region=rows["baseline"],
                **{v: rows[v] for v in ("warm-control", "remove-5")},
            )
        cases.append(
            dict(
                label=case["label"],
                cohort="DS17" if case["label"].startswith("DS17") else case["cohort"],
                arms=arms,
            )
        )
    original_rescue = json.loads(
        (HERE.parent / "2026_10_08_position_error_iter06/baselines/DS17-008.json").read_text()
    )
    for label in protocol["labels"]:
        folder = HERE.parent / "2026_10_08_position_error_iter10" if label == "DS17-008" else HERE
        path = folder / "results" / f"{label}.json"
        if label == "DS17-008":
            assert hashlib.sha256(path.read_bytes()).hexdigest() == protocol["reused_rescue_sha256"]
        doc = json.loads(path.read_text())
        arms = {}
        for arm in ("fitted-c", "zero-c"):
            b = next(a["selected"] for a in doc["baseline_arms"] if a["name"] == arm)
            original = (
                next(a["selected"] for a in original_rescue["arms"] if a["name"] == arm)
                if label == "DS17-008"
                else b
            )
            rows = {
                key: dict(
                    error_km=row["horizontal_error_m"] / 1000,
                    rms_hz=row["posterior_rms_hz"],
                    fallback=False,
                )
                for key, row in (("baseline_original", original), ("baseline_region", b))
            }
            for variant in ("warm-control", "remove-5"):
                r = next(
                    r for r in doc["candidates"] if r["arm"] == arm and r["variant"] == variant
                )
                rows[variant] = dict(
                    error_km=r["error_km"] if r["converged"] else b["horizontal_error_m"] / 1000,
                    rms_hz=r["posterior_rms_hz"] if r["converged"] else b["posterior_rms_hz"],
                    raw_error_km=r["error_km"],
                    fallback=not r["converged"],
                    removed=r["removed"],
                )
            arms[arm] = rows
        cases.append(
            dict(
                label=label,
                cohort="DS17",
                arms=arms,
                source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    assert len(cases) == len({c["label"] for c in cases}) == 107
    aggregates, paired = {}, {}
    for cohort in ("DS16", "DS17", "newer", "combined", "consumed-DS17-34"):
        group = [
            c
            for c in cases
            if cohort == "combined"
            or c["cohort"] == cohort
            or (cohort == "consumed-DS17-34" and c["label"] in protocol["labels"])
        ]
        common = [
            c
            for c in group
            if not any(
                c["arms"][arm][v]["fallback"]
                for arm in ("fitted-c", "zero-c")
                for v in ("warm-control", "remove-5")
            )
        ]
        paired[cohort] = dict(
            count=len(common), excluded=[c["label"] for c in group if c not in common], arms={}
        )
        aggregates[cohort] = {}
        for arm in ("fitted-c", "zero-c"):
            aggregates[cohort][arm] = {}
            paired[cohort]["arms"][arm] = {}
            before = np.asarray([c["arms"][arm]["baseline_original"]["error_km"] for c in group])
            control = np.asarray([c["arms"][arm]["warm-control"]["error_km"] for c in group])
            for variant in VARIANTS:
                rows = [c["arms"][arm][variant] for c in group]
                errors = np.asarray([r["error_km"] for r in rows])
                aggregates[cohort][arm][variant] = dict(
                    count=len(rows),
                    mean_km=float(errors.mean()),
                    median_km=float(np.median(errors)),
                    p95_km=float(np.percentile(errors, 95)),
                    worst_km=float(errors.max()),
                    worst_label=group[int(errors.argmax())]["label"],
                    fallback_labels=[
                        c["label"] for c in group if c["arms"][arm][variant]["fallback"]
                    ],
                    mean_rms_hz=float(np.mean([r["rms_hz"] for r in rows])),
                    improved_vs_baseline=int((errors < before - 0.001).sum()),
                    worsened_vs_baseline=int((errors > before + 0.001).sum()),
                    improved_vs_control=int((errors < control - 0.001).sum()),
                    worsened_vs_control=int((errors > control + 0.001).sum()),
                )
                if variant in ("warm-control", "remove-5"):
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
    fig, axes = plt.subplots(2, 4, figsize=(17, 8), layout="constrained")
    for col, cohort in enumerate(("DS16", "DS17", "newer", "combined")):
        for row, arm in enumerate(("fitted-c", "zero-c")):
            ax = axes[row, col]
            for variant in VARIANTS:
                values = sorted(
                    c["arms"][arm][variant]["error_km"]
                    for c in cases
                    if cohort == "combined" or c["cohort"] == cohort
                )
                ax.step(
                    values, np.arange(1, len(values) + 1) / len(values), where="post", label=variant
                )
            ax.set_xscale("symlog", linthresh=1)
            ax.axvline(1, color="black", linestyle="--", linewidth=1)
            ax.set(
                title=f"{cohort}: {arm}", xlabel="Position error (km)", ylabel="Fraction of scans"
            )
            ax.grid(alpha=0.2)
            ax.legend(fontsize=7)
    fig.savefig(HERE / "distributions.png", dpi=160)
    print(json.dumps(aggregates, indent=2))


if __name__ == "__main__":
    main()
