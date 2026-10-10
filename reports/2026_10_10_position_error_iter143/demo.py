"""Synthetic production-B7 clock block demonstration, not positioning evidence."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from clock_step import step
from test_clock_step import fixture


def main():
    rows = []
    for arm in ("fitted-c", "zero-c"):
        model, vector, clock = fixture(arm)
        result = step(model, vector, clock, arm)
        rows.append(dict(
            arm=arm,
            accepted=result["accepted"],
            exact_evaluations=result["exact_evaluations"],
            objective_before=result["objective_before"],
            objective_after=result["objective_after"],
            surrogate_stationarity=result["quadratic"]["stationarity"],
            free_dimensions=result["quadratic"]["free_dimensions"],
            locked_dimensions=result["quadratic"]["locked_dimensions"],
        ))
    here = Path(__file__).resolve().parent
    (here / "synthetic.json").write_text(json.dumps(dict(
        scope="Synthetic B7 model only; no accuracy, speed or convergence claim", rows=rows
    ), indent=2, allow_nan=False) + "\n")
    fig, ax = plt.subplots(figsize=(7, 4), constrained_layout=True)
    for i, row in enumerate(rows):
        ax.bar(i, row["objective_after"] - row["objective_before"], color=("#287c8e", "#d88645")[i])
    ax.set_xticks(range(2), [r["arm"] for r in rows])
    ax.set(title="Synthetic B7: one receiver-clock block update",
           ylabel="Exact objective change (after − before)")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.grid(axis="y", alpha=0.2)
    fig.savefig(here / "synthetic.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
