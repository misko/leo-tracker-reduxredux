"""Place unchanged paired-frame phase differences on the full scan clock."""

import hashlib
import json

import matplotlib.pyplot as plt
import numpy as np

from tools.research.replay_adaptive_multiscale_phase_refined import DIRECTORY, ROOT


def main():
    binding_path = ROOT / "reports/figures/2026_09_23_adaptive_phase_300s/binding.json"
    phase_path = DIRECTORY / "frame-double-difference.json"
    binding = json.loads(binding_path.read_text())
    cached = json.loads(phase_path.read_text())
    by_visit = {row["visit_index"]: row for row in binding["rows"]}
    eligible = {r["visit_index"] for r in binding["rows"] if len(r["phase_blind_pairs"]) >= 2}
    if eligible != {r["visit_index"] for r in cached["rows"]}:
        raise ValueError("cached frame phases do not cover the current two-source inventory")
    points = []
    for row in cached["rows"]:
        bound = by_visit[row["visit_index"]]
        for local_time, held, before, after in zip(
            row["time_s"],
            row["both_held"],
            row["before_separate_rate_removal_rad"],
            row["conditional_double_difference_rad"],
            strict=True,
        ):
            points.append(
                {
                    "visit_index": row["visit_index"],
                    "channel": bound["channel"],
                    "scan_time_s": bound["time_s"] + local_time,
                    "both_held": held,
                    "before_rad": before,
                    "after_rad": after,
                }
            )
    times = np.asarray([r["scan_time_s"] for r in points])
    held = np.asarray([r["both_held"] for r in points])
    fig, axes = plt.subplots(2, 2, figsize=(15, 9), sharey=True, layout="constrained")
    for column, (key, title) in enumerate(
        (
            ("before_rad", "Before separate source-rate removal"),
            ("after_rad", "After separate source-rate removal"),
        )
    ):
        phase = np.degrees([r[key] for r in points])
        for level, limits in enumerate(((0, 300), (134.5, 146.5))):
            ax = axes[level, column]
            ax.scatter(
                times[~held],
                phase[~held],
                s=17,
                facecolors="none",
                edgecolors="0.55",
                alpha=0.7,
                label="Includes training frame",
            )
            ax.scatter(
                times[held],
                phase[held],
                s=17,
                color="#0072B2",
                alpha=0.8,
                label="Both frames held out",
            )
            ax.set(
                xlim=limits,
                ylim=(-180, 180),
                yticks=[-180, -90, 0, 90, 180],
                xlabel="Elapsed scan time (seconds)",
                title=title if level == 0 else f"Same points: occupied interval · {title}",
            )
            ax.grid(alpha=0.2)
            if level == 0:
                ax.axvspan(134.5, 146.5, color="0.5", alpha=0.08)
                ax.text(
                    0.02,
                    0.06,
                    "No eligible two-source measurements outside the five dwells.\n"
                    "Blank time is missing data, not zero phase.",
                    transform=ax.transAxes,
                    fontsize=9,
                )
            else:
                for label_index, row in enumerate(cached["rows"]):
                    ax.text(
                        by_visit[row["visit_index"]]["time_s"] + 0.06,
                        165 if label_index % 2 == 0 else 145,
                        str(row["visit_index"]),
                        ha="center",
                        fontsize=8,
                    )
    axes[0, 0].legend(loc="upper left", fontsize=9)
    for ax in axes[:, 0]:
        ax.set_ylabel("Wrapped (RX1−RX0)B − (RX1−RX0)A (degrees)")
    fig.suptitle(
        "Full 300-second adaptive scan: the same frame-level two-source differences\n"
        "scan-hop-28d7592ea614f624 · 445 frame pairs in 5 dwells · all channel 4 · no new fit"
    )
    output = binding_path.parent
    fig.savefig(output / "frame-double-difference-full-scan.png", dpi=170)
    (output / "frame-double-difference-full-scan.json").write_text(
        json.dumps(
            {
                "binding_sha256": hashlib.sha256(binding_path.read_bytes()).hexdigest(),
                "cached_phase_sha256": hashlib.sha256(phase_path.read_bytes()).hexdigest(),
                "transformation": (
                    "scan_time_s = visit device-counter start + cached local frame time"
                ),
                "phase_values_changed": False,
                "points": points,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
