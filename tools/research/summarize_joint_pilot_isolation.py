"""Summarize frozen replay responses without refitting or selecting models."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "reports/figures/2026_09_23_joint_pilot_isolation"


def main():
    binding = json.loads((DIRECTORY / "binding.json").read_text())
    for name, expected in binding.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"frozen input changed: {name}")
    files = sorted(DIRECTORY.glob("probe-*.json"))
    if len(files) != 6:
        raise ValueError("all six frozen opportunities required")
    rows = []
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True, constrained_layout=True)
    names = (
        "single_a",
        "single_b",
        "exact_a_rolled_b",
        "rolled_a_exact_b",
        "both_rolled",
        "swapped_epochs",
    )
    for file in files:
        probe = json.loads(file.read_text())
        assert (
            probe["receivers"]["0"]["train_indices_sha256"]
            == (probe["receivers"]["1"]["train_indices_sha256"])
        )
        assert (
            probe["receivers"]["0"]["held_indices_sha256"]
            == (probe["receivers"]["1"]["held_indices_sha256"])
        )
        for rx in (0, 1):
            data = probe["receivers"][str(rx)]
            exact = data["models"]["exact_ab"]
            gains = {
                name: (data["models"][name]["held_sse"] - exact["held_sse"])
                / data["held_energy"]
                * 100
                for name in names
            }
            rows.append(
                dict(
                    time_s=probe["time_s"],
                    receiver=rx,
                    exact_explained_energy_percent=(1 - exact["held_sse"] / data["held_energy"])
                    * 100,
                    incremental_energy_percentage_points=gains,
                    train_rank=exact["train_rank"],
                    held_rank=exact["held_rank"],
                    gram_condition=exact["gram_condition"],
                    residual_cfo_hz=exact["residual_cfo_hz"],
                    boundary_hit=any(abs(f) == 2500 for f in exact["residual_cfo_hz"]),
                )
            )
    for rx, ax in enumerate(axes):
        selected = [r for r in rows if r["receiver"] == rx]
        x = np.arange(len(selected))
        for offset, name in enumerate(names):
            ax.plot(
                x + (offset - 2.5) * 0.04,
                [r["incremental_energy_percentage_points"][name] for r in selected],
                "o",
                label=name,
            )
        ax.axhline(0, color="black", lw=0.8)
        ax.set_ylabel(f"RX{rx}: incremental held energy\n(percentage points)")
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8, ncol=2)
    axes[-1].set_xticks(range(6), [f"{r['time_s']:.3f}" for r in rows if r["receiver"] == 0])
    axes[-1].set_xlabel("Isolated probe time in recording (s); spacing is categorical")
    fig.suptitle(
        "Joint exact pilots versus nested and equal-capacity controls\n"
        "Positive favors joint exact; random held physical groups; discovery data"
    )
    fig.savefig(DIRECTORY / "held-incremental-energy.png", dpi=160)
    (DIRECTORY / "summary.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
