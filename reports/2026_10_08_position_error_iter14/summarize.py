"""Complete-cohort region comparison, before any downstream clock refits."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent


def main():
    selection = json.loads((HERE / "selection.json").read_text())
    assert selection["complete"] and selection["completed"] == 107
    cases = selection["cases"]
    aggregates = {}
    fig, axes = plt.subplots(2, 4, figsize=(17, 8), layout="constrained")
    for col, cohort in enumerate(("DS16", "DS17", "newer", "combined")):
        group = [
            c
            for c in cases
            if cohort == "combined"
            or (cohort == "DS16" and c["label"].startswith("S"))
            or (cohort == "DS17" and c["label"].startswith("DS17"))
            or (cohort == "newer" and c["label"].startswith("NEW"))
        ]
        aggregates[cohort] = {}
        for row, arm in enumerate(("fitted-c", "zero-c")):
            ax = axes[row, col]
            aggregates[cohort][arm] = {}
            before = np.array(
                [c["arms"][arm]["baseline"]["horizontal_error_m"] / 1000 for c in group]
            )
            for policy in ("baseline", "selected"):
                fits = [c["arms"][arm][policy] for c in group]
                errors = np.array([f["horizontal_error_m"] / 1000 for f in fits])
                aggregates[cohort][arm][policy] = dict(
                    count=len(group),
                    mean_km=float(errors.mean()),
                    median_km=float(np.median(errors)),
                    p95_km=float(np.percentile(errors, 95)),
                    worst_km=float(errors.max()),
                    worst_label=group[int(errors.argmax())]["label"],
                    improved=int(np.sum(errors < before - 0.001)),
                    worsened=int(np.sum(errors > before + 0.001)),
                    mean_rms_hz=float(np.mean([f["posterior_rms_hz"] for f in fits])),
                )
                ax.step(
                    np.sort(errors), np.arange(1, len(errors) + 1) / len(errors),
                    where="post", label=policy,
                )
            ax.set_xscale("symlog", linthresh=1)
            ax.axvline(1, color="black", linestyle="--", linewidth=1)
            ax.set(title=f"{cohort}: {arm}", xlabel="Position error (km)", ylabel="Fraction")
            ax.grid(alpha=0.2)
            ax.legend()
    changed = {
        arm: [c["label"] for c in cases if c["arms"][arm]["source"] == "additional"]
        for arm in ("fitted-c", "zero-c")
    }
    (HERE / "summary.json").write_text(
        json.dumps(dict(aggregates=aggregates, changed_labels=changed), indent=2) + "\n"
    )
    fig.savefig(HERE / "region-distributions.png", dpi=160)
    print(json.dumps(dict(changed_labels=changed, combined=aggregates["combined"]), indent=2))


if __name__ == "__main__":
    main()
