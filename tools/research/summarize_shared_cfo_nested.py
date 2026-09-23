"""Verify known-solution nesting and summarize every retained development fit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "reports/figures/2026_09_23_shared_receiver_cfo_nested"


def main():
    for name, digest in json.loads((DIRECTORY / "binding.json").read_text()).items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError("frozen input changed")
    files = sorted(DIRECTORY.glob("probe-*.json"))
    if len(files) != 6:
        raise ValueError("six outcomes required")
    rows = []
    for file in files:
        data = json.loads(file.read_text())
        if "abstention" in data:
            rows.append(data)
            continue
        independent, shared = data["independent"], data["shared"]
        best = min(data["candidates"], key=lambda k: data["candidates"][k]["train_sse"])
        assert best == data["selected_independent"]
        assert independent["train_sse"] <= shared["train_sse"] + 1e-10
        rows.append(
            dict(
                time_s=data["time_s"],
                selected_independent=best,
                shared_minus_independent_train_sse=shared["train_sse"] - independent["train_sse"],
                independent_closure_hz=data["independent_closure_hz"],
                held_loss_percentage_points=data["held_loss_percentage_points"],
                initializer_reproduction_error=data["candidates"]["shared_seed_refinement"][
                    "training_objective_history"
                ][0]
                - shared["train_sse"],
            )
        )
    eligible = [r for r in rows if "abstention" not in r]
    fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)
    for rx, offset in ((0, -0.16), (1, 0.16)):
        ax.bar(
            np.arange(len(eligible)) + offset,
            [r["held_loss_percentage_points"][rx] for r in eligible],
            0.3,
            label=f"RX{rx}",
        )
    ax.set_xticks(range(len(eligible)), [f"{r['time_s']:.3f}" for r in eligible])
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Isolated probe time (s); two fixed-alias abstentions retained")
    ax.set_ylabel("Shared minus best-known independent held SSE\n(% of received held energy)")
    ax.set_title(
        "Known-solution nesting satisfied in all four comparisons\n"
        "Reused random groups: development, not fresh validation"
    )
    ax.legend()
    ax.grid(axis="y", alpha=0.2)
    fig.savefig(DIRECTORY / "held-loss.png", dpi=160)
    (DIRECTORY / "summary.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
