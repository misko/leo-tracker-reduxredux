"""Expose training-only source-branch closure before opening held waveforms."""

import gzip
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from tools.research.fit_independent_phase import FIGURE, phase_cfo


def main():
    with gzip.open(FIGURE / "train-frames.json.gz", "rt") as stream:
        replay = json.load(stream)
    rows = []
    for row in replay["rows"]:
        observation = row["observation"]
        measured, _ = phase_cfo(row)
        rows.append(
            {
                "visit_index": observation["visit_index"],
                "time_s": observation["time_s"],
                "glrt_hz": observation["normalized_cfo_hz"],
                "phase_hz": measured,
                "difference_hz": measured - observation["normalized_cfo_hz"],
            }
        )
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    for key, label in (("glrt_hz", "Bound GLRT CFO"), ("phase_hz", "Seed-corrected pilot CFO")):
        axes[0].plot([r["time_s"] for r in rows], [r[key] / 1000 for r in rows], "o-", label=label)
    axes[0].set_ylabel("Normalized CFO (kHz)")
    axes[0].legend()
    axes[1].scatter([r["time_s"] for r in rows], [r["difference_hz"] / 1000 for r in rows])
    axes[1].axhline(0, color="0.5", linewidth=0.8)
    for row in rows:
        if abs(row["difference_hz"]) > 100_000:
            axes[1].annotate(
                str(row["visit_index"]),
                (row["time_s"], row["difference_hz"] / 1000),
                xytext=(5, 7),
                textcoords="offset points",
            )
    axes[1].set_ylabel("Pilot minus bound GLRT CFO (kHz)")
    for ax in axes:
        ax.set_xlabel("Seconds from capture start")
        ax.grid(alpha=0.2)
    fig.suptitle(
        "Independent 2.5 MS/s training arc: two unresolved branch mismatches\n"
        "All 15 fitting dwells shown; 12 random held dwells remain unopened"
    )
    fig.savefig(FIGURE / "training-alias-audit.png", dpi=170)
    plt.close(fig)
    (FIGURE / "training-alias-audit.json").write_text(
        json.dumps({"scope": "training only; no held IQ opened", "rows": rows}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
