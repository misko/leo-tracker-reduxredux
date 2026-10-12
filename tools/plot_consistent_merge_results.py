"""Compact sealed evaluations and plot the completed protected-merge cases."""

import json
from pathlib import Path

import matplotlib
from continuous_merge_consistency_study import LOCAL, REPORT
from continuous_merge_study import sha, write

matplotlib.use("Agg")
from matplotlib import pyplot as plt


def main():
    cases = [
        ("DS20", "fast-014c72ff95ab599c51ba3b3ec9b92cb8", "baseline-shape-consistent"),
        ("DS16", "scan-fw-0e40d0535caa0b16", "baseline-consistent"),
    ]
    rows, sources = [], {}
    for dataset, session, suffix in cases:
        position = LOCAL / dataset / session / "positions"
        authority = position / ("evaluation-" + suffix + ".json")
        evaluation = json.loads(authority.read_bytes())
        sources[str(authority)] = sha(authority)
        for variant, arms in evaluation["results"].items():
            assert arms["fitted-c"]["satellites"] == arms["zero-c"]["satellites"]
            for arm, result in arms.items():
                selected = result["selected"]
                rows.append(
                    {
                        "dataset": dataset,
                        "session_id": session,
                        "variant": variant,
                        "arm": arm,
                        "horizontal_error_m": selected["horizontal_error_m"],
                        "objective": selected["objective"],
                        "frequency_nll": result["likelihood_nll"],
                        "posterior_rms_hz": selected["posterior_rms_hz"],
                        "accepted_stage": result["accepted_stage"],
                        "candidate_count": len(result["satellites"]),
                        "seal_sha256": evaluation["seal_sha256"],
                    }
                )
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    for axis, (dataset, _, _) in zip(axes, cases, strict=True):
        variants = (
            ("baseline", "shape", "consistent") if dataset == "DS20" else ("baseline", "consistent")
        )
        for side, (arm, color) in enumerate((("fitted-c", "#2675ad"), ("zero-c", "#e48621"))):
            values = [
                next(
                    r["horizontal_error_m"]
                    for r in rows
                    if r["dataset"] == dataset and r["variant"] == v and r["arm"] == arm
                )
                / 1000
                for v in variants
            ]
            bars = axis.bar(
                [i + (side - 0.5) * 0.32 for i in range(len(variants))],
                values,
                width=0.32,
                color=color,
                label=arm,
            )
            axis.bar_label(bars, fmt="%.3f", fontsize=9)
        axis.set_xticks(range(len(variants)), variants)
        axis.set_ylabel("Horizontal reference error (km)")
        axis.set_title(dataset + " · fixed development example")
        highest = max(r["horizontal_error_m"] for r in rows if r["dataset"] == dataset) / 1000
        axis.set_ylim(0, highest * 1.25)
        axis.grid(axis="y", alpha=0.2)
        axis.legend(fontsize=9)
    fig.suptitle(
        "Protected initialization avoids candidate loss; position improvement remains unproven"
    )
    path = REPORT / "first-position-errors.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    write(
        REPORT / "first-position-results.json",
        {
            "evaluation_authorities": sources,
            "script_sha256": sha(Path(__file__)),
            "image_sha256": sha(path),
            "rows": rows,
            "scope": (
                "Two exposed development recordings; c arms have common stationary "
                "B7 stage and bank within mode"
            ),
        },
    )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
