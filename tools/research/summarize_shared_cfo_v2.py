"""Audit and plot completed shared-CFO development comparisons without refitting."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "reports/figures/2026_09_23_shared_receiver_cfo_v2"
ORIGINAL = ROOT / "reports/figures/2026_09_23_joint_pilot_isolation"


def main():
    for name, digest in json.loads((DIRECTORY / "binding.json").read_text()).items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"frozen source changed: {name}")
    files = sorted(DIRECTORY.glob("probe-*.json"))
    if len(files) != 6:
        raise ValueError("six outcomes required")
    rows = []
    for file in files:
        row = json.loads(file.read_text())
        if "abstention" in row:
            rows.append(dict(time_s=row["time_s"], abstention=row["abstention"]))
            continue
        old = json.loads((ORIGINAL / file.name).read_text())
        nominal = np.array(
            [[r["tracking_cfo_hz"] for r in old["nominees"][str(rx)]] for rx in (0, 1)]
        )
        diagnostics = {}
        for arm in ("shared", "independent"):
            fit = row[arm]
            history = fit["training_objective_history"]
            if any(a < b - 1e-10 for a, b in zip(history, history[1:], strict=False)):
                raise ValueError("training objective worsened")
            residual = np.asarray(fit["residual_cfo_hz"])
            closure = float(np.diff(nominal[1] - nominal[0] + residual[1] - residual[0])[0])
            if arm == "shared" and abs(closure) > 1e-6:
                raise ValueError("shared fit violates offset equality")
            diagnostics[arm] = dict(
                closure_hz=closure,
                training_improvement=history[0] - history[-1],
                local_success=fit["local_success"],
                boundary_hit=fit["boundary_hit"],
                evaluations=fit["evaluations"],
            )
        losses = [
            (s["held_sse"] - i["held_sse"]) / e * 100
            for s, i, e in zip(
                row["shared"]["receivers"],
                row["independent"]["receivers"],
                row["held_energy_by_receiver"],
                strict=True,
            )
        ]
        rows.append(
            dict(
                time_s=row["time_s"],
                held_loss_percentage_points=losses,
                diagnostics=diagnostics,
                shared_minus_independent_train_sse=row["shared"]["train_sse"]
                - row["independent"]["train_sse"],
            )
        )
    measured = [r for r in rows if "abstention" not in r]
    fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)
    for rx, offset in ((0, -0.16), (1, 0.16)):
        ax.bar(
            np.arange(len(measured)) + offset,
            [r["held_loss_percentage_points"][rx] for r in measured],
            0.3,
            label=f"RX{rx}",
        )
    ax.set_xticks(range(len(measured)), [f"{r['time_s']:.3f}" for r in measured])
    for index, row in enumerate(measured):
        if row["shared_minus_independent_train_sse"] < -1e-10:
            ax.axvspan(index - 0.45, index + 0.45, color="gray", alpha=0.15)
            ax.text(
                index,
                0.96,
                "nesting check failed",
                transform=ax.get_xaxis_transform(),
                ha="center",
                va="top",
                fontsize=8,
            )
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Isolated probe time (s); 26.400 / 30.850 abstain on fixed aliases")
    ax.set_ylabel("Shared minus independent held SSE\n(% of received held energy)")
    ax.set_title(
        "Shared receiver CFO development comparison\n"
        "Positive favors source-specific offsets; reused random groups"
    )
    ax.legend()
    ax.grid(axis="y", alpha=0.2)
    fig.savefig(DIRECTORY / "shared-offset-held-loss.png", dpi=160)
    (DIRECTORY / "summary.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
