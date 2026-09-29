"""Compare own and donor offsets on exactly the same held-scored pair subset."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from study import HERE, read, save, verify


def main():
    verify(read(HERE / "seal.json")["sha256"])
    scans = read(HERE / "result.json")["scans"]
    rows = []
    for ds in ("DS7", "DS8", "DS9"):
        chosen = [p for s in scans if s["dataset"] == ds for p in s["pairs"] if p["selected"]]
        subset = [p["evaluation"] for p in chosen if "donor_offset_hz" in p["evaluation"]]
        rows.append(
            {
                "dataset": ds,
                "pairs": len(subset),
                "selected_without_alternatives": sum(
                    all(m is None for m in p["margins_nats_per_observation"].values())
                    for p in chosen
                ),
                "own_pass": sum(e["held_shape_pass"] for e in subset),
                "donor_pass": sum(e["donor_held_shape_pass"] for e in subset),
                "own_median_abs_hz": float(np.median([e["held_median_abs_hz"] for e in subset])),
                "donor_median_abs_hz": float(
                    np.median([e["donor_held_median_abs_hz"] for e in subset])
                ),
                "donor_better_pairs": sum(e["donor_minus_own_nats"] > 0 for e in subset),
            }
        )
    save(HERE / "transfer.json", {"datasets": rows})
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for i, key in enumerate(("own_median_abs_hz", "donor_median_abs_hz")):
        ax.bar(
            np.arange(3) + (i - 0.5) * 0.3,
            [r[key] for r in rows],
            width=0.3,
            label="Offset fitted to own training pair"
            if i == 0
            else "Offset from other training pairs",
        )
    ax.set_xticks(range(3), [f"{r['dataset']}\n{r['pairs']} identical pairs" for r in rows])
    ax.axhline(100, color="gray", linestyle="--", label="Median threshold")
    ax.set_ylabel("Median of pair held absolute-error medians (Hz)")
    ax.set_title("Common-offset transfer on matched held observations")
    ax.legend()
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    for suffix in ("png", "svg"):
        fig.savefig(HERE / f"offset-transfer.{suffix}", dpi=160)
    plt.close(fig)
    print(rows, flush=True)


if __name__ == "__main__":
    main()
