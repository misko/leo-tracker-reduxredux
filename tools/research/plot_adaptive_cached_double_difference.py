"""Plot nearest-frame source differences from cached, unrefitted phase exports."""

import json

import matplotlib.pyplot as plt
import numpy as np

from tools.research.replay_adaptive_multiscale_phase_refined import DIRECTORY


def main():
    rows = json.loads((DIRECTORY / "frame-phase.json").read_text())["rows"]
    fits = {
        r["visit_index"]: r["sources"]
        for r in json.loads((DIRECTORY / "results.json").read_text())["rows"]
        if r["duration_ms"] == 120 and r["mode"] == "frozen_timing"
    }
    visits = sorted({row["visit_index"] for row in rows})
    fig, axes = plt.subplots(
        len(visits), 2, figsize=(14, 11), sharex=True, sharey=True, layout="constrained"
    )
    pairs = []
    for axs, visit in zip(axes, visits, strict=True):
        a, b = [
            next(r for r in rows if r["visit_index"] == visit and r["source"] == name)
            for name in ("A", "B")
        ]
        ta, tb = np.asarray(a["time_s"]), np.asarray(b["time_s"])
        nearest = np.abs(ta[:, None] - tb[None, :]).argmin(axis=1)
        keep = abs(ta - tb[nearest]) < 0.5 / 750
        ia, ib = np.flatnonzero(keep), nearest[keep]
        if len(np.unique(ib)) != len(ib):
            raise ValueError("nearest-frame match is not one-to-one")
        phase = np.angle(
            np.exp(
                1j
                * (
                    np.asarray(b["phase_transported_to_center_rad"])[ib]
                    - np.asarray(a["phase_transported_to_center_rad"])[ia]
                )
            )
        )
        held = ~np.asarray(a["train"])[ia] & ~np.asarray(b["train"])[ib]
        weights = np.sqrt(np.asarray(a["weights"])[ia] * np.asarray(b["weights"])[ib])
        times = (ta[ia] + tb[ib]) / 2
        gap = abs(ta[ia] - tb[ib])
        without_rate_removal = np.angle(
            np.exp(
                1j
                * (
                    phase
                    + 2
                    * np.pi
                    * (
                        fits[visit]["B"]["residual_product_hz"] * (tb[ib] - 0.06)
                        - fits[visit]["A"]["residual_product_hz"] * (ta[ia] - 0.06)
                    )
                )
            )
        )
        for ax, values, label in zip(
            axs,
            (without_rate_removal, phase),
            ("Before separate rate removal", "After separate rate removal"),
            strict=True,
        ):
            ax.scatter(
                times[~held] * 1000,
                np.degrees(values[~held]),
                s=21,
                facecolors="none",
                edgecolors="0.55",
                label="Includes training frame",
            )
            ax.scatter(
                times[held] * 1000,
                np.degrees(values[held]),
                s=23,
                color="tab:blue",
                label="Both frames held",
            )
            resultant = abs(np.average(np.exp(1j * values[held]), weights=weights[held]))
            ax.set(
                title=f"{visit} · {label} · weighted held R={resultant:.2f}",
                ylim=(-180, 180),
                yticks=[-180, -90, 0, 90, 180],
                xlim=(0, 120),
            )
            ax.grid(alpha=0.2)
        pairs.append(
            {
                "visit_index": visit,
                "time_s": times.tolist(),
                "time_separation_s": gap.tolist(),
                "both_held": held.tolist(),
                "paired_weights": weights.tolist(),
                "held_resultant_before_weighted": float(
                    abs(np.average(np.exp(1j * without_rate_removal[held]), weights=weights[held]))
                ),
                "held_resultant_before_unweighted": float(
                    abs(np.mean(np.exp(1j * without_rate_removal[held])))
                ),
                "conditional_double_difference_rad": phase.tolist(),
                "before_separate_rate_removal_rad": without_rate_removal.tolist(),
            }
        )
    axes[0, 0].legend(fontsize=8, loc="upper right")
    for ax in axes[-1]:
        ax.set_xlabel("Time within adaptive dwell (ms)")
    fig.supylabel("Wrapped source B−A receiver-phase difference (deg)")
    fig.suptitle(
        "Adaptive dwells: two-source phase differences\n"
        "Nearest frames (79–97 µs apart) · conditional carrier branches · no new fit"
    )
    fig.savefig(DIRECTORY / "double-difference-within-dwells.png", dpi=170)
    (DIRECTORY / "frame-double-difference.json").write_text(
        json.dumps(
            {
                "description": (
                    "Derived nearest-frame diagnostic, conditional on saved source/rate branches"
                ),
                "maximum_allowed_time_separation_s": 0.5 / 750,
                "rows": pairs,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
