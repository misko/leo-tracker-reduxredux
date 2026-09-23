"""Descriptive whole-dwell comparisons for the sealed circular score."""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from tools.research.evaluate_independent_phase_v2 import DIRECTORY


def main():
    result = json.loads((DIRECTORY / "held-evaluation.json").read_text())
    models = result["models"]
    comparisons = []
    for reference, proposed in (
        ("glrt_candidate", "phase_candidate"),
        ("phase_constant_rate", "phase_candidate"),
        ("phase_wrong_time", "phase_candidate"),
        ("glrt_constant_rate", "glrt_candidate"),
        ("glrt_wrong_time", "glrt_candidate"),
    ):
        first = {
            row["visit_index"]: row["nll"]
            for row in models[reference]["visits"]
            if not row["abstention"]
        }
        second = {
            row["visit_index"]: row["nll"]
            for row in models[proposed]["visits"]
            if not row["abstention"]
        }
        common = sorted(set(first) & set(second))
        differences = np.asarray([first[key] - second[key] for key in common])
        rng = np.random.default_rng(20260925)
        bootstrap = np.mean(rng.choice(differences, size=(10000, len(common))), axis=1)
        comparisons.append(
            {
                "reference": reference,
                "proposed": proposed,
                "paired_held_visits": len(common),
                "mean_nll_gain": float(np.mean(differences)),
                "paired_visit_bootstrap_95_percentile": np.quantile(
                    bootstrap, [0.025, 0.975]
                ).tolist(),
            }
        )
    (DIRECTORY / "paired-comparisons.json").write_text(
        json.dumps(
            {
                "scope": "descriptive bootstrap; no post-held model tuning",
                "seed": 20260925,
                "resamples": 10000,
                "comparisons": comparisons,
            },
            indent=2,
        )
        + "\n"
    )
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
    labels = [name.replace("_", " ") for name in models]
    rms = [model["conditional_equal_visit_rms_hz"] for model in models.values()]
    axes[0].barh(
        labels, rms, color=["#446fa1" if name.startswith("glrt") else "#c26329" for name in models]
    )
    axes[0].invert_yaxis()
    axes[0].set_xlim(0, max(rms) * 1.2)
    axes[0].set_xlabel("Held circular CFO RMS (Hz); equal dwell weight")
    for i, value in enumerate(rms):
        axes[0].text(value + max(rms) * 0.015, i, f"{value:.1f}", va="center")
    times = {row["visit_index"]: row["observation_time_s"] for row in result["responses"]}
    for name in ("glrt_candidate", "phase_candidate", "phase_constant_rate", "phase_wrong_time"):
        rows = sorted(models[name]["visits"], key=lambda r: times[r["visit_index"]])
        rows = [row for row in rows if not row["abstention"]]
        axes[1].plot(
            [times[r["visit_index"]] for r in rows],
            [r["mean_principal_residual_hz"] for r in rows],
            "o-",
            label=name.replace("_", " "),
            alpha=0.8,
        )
    axes[1].axhline(0, color="0.5", linewidth=0.8)
    axes[1].set_xlabel("Seconds from capture start")
    axes[1].set_ylabel("Held dwell mean circular residual (Hz)")
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.2)
    coverage = models["phase_candidate"]
    fig.suptitle(
        "Acquired-only 2.5 MS/s arc — frozen random whole-dwell holdout\n"
        f"{coverage['covered_held_visits']}/{coverage['total_held_visits']} dwells covered; "
        "circular estimator score, no absolute alias/identity claim"
    )
    fig.savefig(DIRECTORY / "held-comparison.png", dpi=170)
    plt.close(fig)
    print(json.dumps(comparisons, indent=2))


if __name__ == "__main__":
    main()
