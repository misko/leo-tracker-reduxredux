"""Compare replacement and additive region policies on every predeclared scan."""

import json
from pathlib import Path

import matplotlib
import numpy as np
from additive_policy import select

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    labels = ["DS17-008"] + protocol["regression_labels"] + protocol["newer_labels"]
    cases = []
    for label in labels:
        baseline = json.loads((HERE / "baselines" / f"{label}.json").read_text())
        candidate = json.loads((HERE / "results" / label / "separation-25.json").read_text())
        old = {a["name"]: a["selected"] for a in baseline["arms"]}
        new = {a["name"]: a["selected"] for a in candidate["methods"][0]["arms"]}
        arms = {}
        for arm in ("fitted-c", "zero-c"):
            chosen, source = select(old[arm], new[arm])
            assert old[arm] is not None and new[arm] is not None
            arms[arm] = dict(
                source=source, baseline=old[arm], replacement=new[arm], additive=chosen
            )
        cases.append(dict(label=label, session_id=baseline["session_id"], arms=arms))
    aggregates = {}
    for cohort, members in [
        ("regression", protocol["regression_labels"]),
        ("newer", protocol["newer_labels"]),
    ]:
        aggregates[cohort] = {}
        for arm in ("fitted-c", "zero-c"):
            rows = [c["arms"][arm] for c in cases if c["label"] in members]
            aggregates[cohort][arm] = {}
            before = np.array([r["baseline"]["horizontal_error_m"] / 1000 for r in rows])
            for variant in ("baseline", "replacement", "additive"):
                errors = np.array([r[variant]["horizontal_error_m"] / 1000 for r in rows])
                aggregates[cohort][arm][variant] = dict(
                    count=len(rows),
                    mean_km=float(errors.mean()),
                    median_km=float(np.median(errors)),
                    p95_km=float(np.percentile(errors, 95)),
                    worst_km=float(errors.max()),
                    improved=int((errors < before - 0.001).sum()),
                    worsened=int((errors > before + 0.001).sum()),
                    mean_frequency_rms_hz=float(
                        np.mean([r[variant]["posterior_rms_hz"] for r in rows])
                    ),
                )
    (HERE / "summary.json").write_text(
        json.dumps(dict(cases=cases, aggregates=aggregates), indent=2) + "\n"
    )
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), layout="constrained")
    for ax, members, title in zip(
        axes,
        [protocol["regression_labels"], protocol["newer_labels"]],
        ["Ten development regressions", "Eight newer frozen recordings"],
        strict=True,
    ):
        group = [c for c in cases if c["label"] in members]
        x = np.arange(len(group))
        for i, variant in enumerate(("baseline", "replacement", "additive")):
            ax.bar(
                x + (i - 1) * 0.25,
                [c["arms"]["fitted-c"][variant]["horizontal_error_m"] / 1000 for c in group],
                0.25,
                label=variant,
            )
        ax.set_xticks(x, [c["label"] for c in group], rotation=30, ha="right")
        ax.set(title=title, ylabel="Fitted-c position error (km)")
        ax.axhline(1, color="black", linestyle="--", linewidth=1)
        ax.legend()
        ax.grid(axis="y", alpha=0.2)
    fig.savefig(HERE / "comparison.png", dpi=160)
    plt.close(fig)
    diagnostic = cases[0]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
    for i, arm in enumerate(("fitted-c", "zero-c")):
        row = diagnostic["arms"][arm]
        axes[0].bar(
            np.arange(2) + (i - 0.5) * 0.35,
            [row[v]["horizontal_error_m"] / 1000 for v in ("baseline", "additive")],
            0.35, label=arm,
        )
        axes[1].plot(
            [0, 1], [row[v]["selection_score"] for v in ("baseline", "additive")],
            "o-", label=arm,
        )
    for ax in axes:
        ax.set_xticks([0, 1], ["Baseline", "Preserved regions"])
        ax.legend()
        ax.grid(axis="y", alpha=0.2)
    axes[0].set_ylabel("Position error (km)")
    axes[1].set_ylabel("Selection score (lower is better)")
    fig.suptitle("DS17-008: final fitting rescues a discarded region")
    fig.savefig(HERE / "catastrophic.png", dpi=160)
    plt.close(fig)
    print(json.dumps(aggregates, indent=2))


if __name__ == "__main__":
    main()
