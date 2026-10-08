"""Full frozen development cohort; do not substitute completed-only summaries."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent


def main():
    protocol = json.loads((HERE / "expansion-protocol.json").read_text())
    labels = protocol["labels"] + [
        "S10",
        "S16",
        "S24",
        "DS17-004",
        "DS17-045",
        "DS17-048",
        "DS17-051",
    ]
    assert len(labels) == len(set(labels)) == 65
    cases = []
    for label in labels:
        doc = json.loads((HERE / "probes" / f"{label}.json").read_text())
        lookup = {(r["variant"], r["arm"]): r for r in doc["candidates"]}
        cases.append(
            dict(
                label=label,
                arms={
                    arm: {
                        "control": lookup["matched-control", arm],
                        "joint": lookup["joint-wide", arm],
                    }
                    for arm in ("fitted-c", "zero-c")
                },
            )
        )
    aggregates = {}
    for cohort, members in {
        "DS16": [r for r in cases if r["label"].startswith("S")],
        "DS17-development": [r for r in cases if r["label"].startswith("DS17-")],
        "expansion-only": [r for r in cases if r["label"] in protocol["labels"]],
    }.items():
        aggregates[cohort] = {}
        for arm in ("fitted-c", "zero-c"):
            paired = [
                r
                for r in members
                if all(r["arms"][arm][k]["converged"] for k in ("control", "joint"))
            ]
            before = np.array([r["arms"][arm]["control"]["error_km"] for r in paired])
            after = np.array([r["arms"][arm]["joint"]["error_km"] for r in paired])
            aggregates[cohort][arm] = dict(
                total=len(members),
                paired_labels=[r["label"] for r in paired],
                mean_before_km=float(before.mean()),
                mean_after_km=float(after.mean()),
                median_before_km=float(np.median(before)),
                median_after_km=float(np.median(after)),
                p95_before_km=float(np.percentile(before, 95)),
                p95_after_km=float(np.percentile(after, 95)),
                worst_before_km=float(before.max()),
                worst_after_km=float(after.max()),
                improved=int((after < before - 0.001).sum()),
                worsened=int((after > before + 0.001).sum()),
                rms_before_hz=float(
                    np.mean([r["arms"][arm]["control"]["posterior_rms_hz"] for r in paired])
                ),
                rms_after_hz=float(
                    np.mean([r["arms"][arm]["joint"]["posterior_rms_hz"] for r in paired])
                ),
            )
    failed = [
        dict(label=r["label"], arm=arm, variant=v)
        for r in cases
        for arm in r["arms"]
        for v in ("control", "joint")
        if not r["arms"][arm][v]["converged"]
    ]
    (HERE / "cohort-summary.json").write_text(
        json.dumps(dict(aggregates=aggregates, failed=failed), indent=2) + "\n"
    )
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), layout="constrained")
    for ax, prefix, name in zip(
        axes,
        ["S", "DS17-"],
        ["DS16 (48 development scans)", "DS17 development (17 scans)"],
        strict=True,
    ):
        group = [r for r in cases if r["label"].startswith(prefix)]
        for variant in ("control", "joint"):
            errors = sorted(r["arms"]["fitted-c"][variant]["error_km"] for r in group)
            ax.step(
                errors, np.arange(1, len(errors) + 1) / len(errors), where="post", label=variant
            )
        ax.axvline(1, color="black", linestyle="--", linewidth=1)
        ax.set(title=name, xlabel="Position error (km)", ylabel="Fraction of scans")
        ax.grid(alpha=0.2)
        ax.legend()
    fig.savefig(HERE / "cohort-cdf.png", dpi=160)
    plt.close(fig)
    print(json.dumps(dict(aggregates=aggregates, failed=failed), indent=2))


if __name__ == "__main__":
    main()
