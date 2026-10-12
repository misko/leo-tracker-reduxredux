"""Report sealed conditional refinements using a common singleton fit metric."""

import json
from pathlib import Path

import matplotlib
import numpy as np
from continuous_merge_consistency_study import LOCAL, REPORT
from continuous_merge_positions import load_prepared
from continuous_merge_study import sha, write
from shared_track_refinement_study import restore

from leo.contracts.regional_position import PositionOrbitBank

matplotlib.use("Agg")
from matplotlib import pyplot as plt


def main():
    rows, audits, sources = [], [], {}
    for dataset, sid in (
        ("DS20", "fast-014c72ff95ab599c51ba3b3ec9b92cb8"),
        ("DS16", "scan-fw-0e40d0535caa0b16"),
    ):
        case = LOCAL / dataset / sid
        output = case / "shared-refinement"
        protocol = json.loads((output / "protocol.json").read_bytes())
        evaluation = json.loads((output / "evaluation.json").read_bytes())
        prepared = load_prepared(Path(protocol["original_case"]) / "baseline.json")
        terminal = json.loads((case / "positions/baseline/terminal.json").read_bytes())
        final = next(f for f in terminal["result"]["finals"] if f["arm"] == "fitted-c")
        with np.load(case / "positions/bank.npz") as z:
            bank = PositionOrbitBank(**{k: z[k] for k in z.files})
        control, _, _ = restore(prepared, bank, final, protocol["groups"]["joined"], 0.0)
        soft, _, _ = restore(prepared, bank, final, protocol["groups"]["joined"], 0.5)
        sources[str(output / "evaluation.json")] = sha(output / "evaluation.json")
        for r in evaluation["rows"]:
            path = output / (r["variant"] + "-" + r["arm"] + ".json")
            saved = json.loads(path.read_bytes())
            vector, clock = (
                np.array(saved["fit"]["vector"]),
                np.array(saved["fit"]["clock_coefficients"]),
            )
            total, _, _, terms = control.evaluate_joint(vector, clock)
            mass = float(terms.responsibilities.sum())
            rows.append(
                {
                    "dataset": dataset,
                    "session_id": sid,
                    **r,
                    "singleton_objective": float(total),
                    "singleton_frequency_nll": terms.nll,
                    "singleton_signal_mass": mass,
                    "singleton_posterior_rms_hz": float(
                        np.sqrt(np.sum(terms.responsibilities * terms.residual_hz**2) / mass)
                    ),
                    "satellites": protocol["source_satellites"],
                    "fit_sha256": sha(path),
                    "evaluation_seal_sha256": evaluation["seal_sha256"],
                }
            )
        for arm in ("fitted-c", "zero-c"):
            values = {}
            for variant in ("joined", "forced"):
                saved = json.loads((output / (variant + "-" + arm + ".json")).read_bytes())
                values[variant] = float(
                    soft.evaluate_joint(
                        np.array(saved["fit"]["vector"]),
                        np.array(saved["fit"]["clock_coefficients"]),
                    )[0]
                )
            audits.append(
                {
                    "dataset": dataset,
                    "arm": arm,
                    "soft_objective_at_soft_solution": values["joined"],
                    "soft_objective_at_forced_solution": values["forced"],
                    "forced_seed_has_lower_soft_score": values["forced"] < values["joined"] - 1e-6,
                }
            )
    variants = ("independent", "parents", "joined", "forced")
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for row_index, dataset in enumerate(("DS20", "DS16")):
        for side, (arm, color) in enumerate((("fitted-c", "#2675ad"), ("zero-c", "#e48621"))):
            values = [
                next(
                    r
                    for r in rows
                    if r["dataset"] == dataset and r["variant"] == v and r["arm"] == arm
                )
                for v in variants
            ]
            x = np.arange(4) + (side - 0.5) * 0.32
            bars = axes[row_index, 0].bar(
                x,
                [r["horizontal_error_m"] / 1000 for r in values],
                width=0.32,
                color=color,
                label=arm,
            )
            axes[row_index, 0].bar_label(bars, fmt="%.3f", fontsize=8)
            original = values[0]["singleton_frequency_nll"]
            axes[row_index, 1].bar(
                x,
                [r["singleton_frequency_nll"] - original for r in values],
                width=0.32,
                color=color,
                label=arm,
            )
        for axis in axes[row_index]:
            axis.set_xticks(np.arange(4), variants)
            axis.grid(axis="y", alpha=0.2)
            axis.legend(fontsize=8)
        highest = max(r["horizontal_error_m"] for r in rows if r["dataset"] == dataset) / 1000
        axes[row_index, 0].set_ylim(0, 1.25 * highest)
        axes[row_index, 0].set_ylabel(dataset + " · position error (km)")
        axes[row_index, 1].set_ylabel(
            "Common singleton NLL change\npositive = worse independent fit"
        )
    fig.suptitle(
        "Conditional shared-track refinements · common observations, bank, priors and budgets"
    )
    image_path = REPORT / "shared-refinement-comparison.png"
    fig.savefig(image_path, dpi=160)
    plt.close(fig)
    write(
        REPORT / "shared-refinement-results.json",
        {
            "rows": rows,
            "continuation_audits": audits,
            "evaluation_authorities": sources,
            "script_sha256": sha(Path(__file__)),
            "image_sha256": sha(image_path),
            "scope": (
                "Sealed exposed-data local refinements; original singleton metric "
                "separates fit from mark-correlation score"
            ),
        },
    )
    print(json.dumps(audits, indent=2))
    print(
        json.dumps(
            [
                {
                    k: r[k]
                    for k in (
                        "dataset",
                        "variant",
                        "arm",
                        "horizontal_error_m",
                        "singleton_frequency_nll",
                    )
                }
                for r in rows
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
