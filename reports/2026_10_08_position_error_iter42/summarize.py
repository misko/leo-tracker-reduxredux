"""Separate normalization and added-candidate score effects at fixed solutions."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
MODES = ("native", "normalization_only", "union")


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((HERE.parent / name).read_bytes()).hexdigest() == digest
    rows = json.loads((HERE / "results.json").read_text())["rows"]
    assert len(rows) == 68
    winners, gaps = [], []
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    table = [
        "| Scope | c | Scoring variant | Winner | Error km | Score |",
        "|---|---|---|---|---:|---:|",
    ]
    for arm_index, arm in enumerate(("fitted-c", "zero-c")):
        errors, differences = [], []
        for mode in MODES:
            for scope in ("regional", "joint"):
                subset = [r for r in rows if r["arm"] == arm and r["scope"] == scope]
                winner = min(subset, key=lambda r: (r["modes"][mode]["penalized_score"], r["name"]))
                winners.append(dict(scope=scope, arm=arm, mode=mode, winner=winner))
                table.append(
                    f"| {scope} | {arm} | {mode} | {winner['name']} | "
                    f"{winner['error_km']:.6f} | "
                    f"{winner['modes'][mode]['penalized_score']:.6f} |"
                )
                if scope == "regional":
                    errors.append(winner["error_km"])
            joint = {r["name"]: r for r in rows if r["scope"] == "joint" and r["arm"] == arm}
            difference = (
                joint["recovered-joint"]["modes"][mode]["penalized_score"]
                - joint["ordinary-joint"]["modes"][mode]["penalized_score"]
            )
            differences.append(difference)
            gaps.append(dict(arm=arm, mode=mode, recovered_minus_ordinary=difference))
        x = np.arange(3) + (arm_index - 0.5) * 0.35
        axes[0].bar(x, errors, 0.35, label=arm)
        axes[1].bar(x, differences, 0.35, label=arm)
    for ax in axes:
        ax.set_xticks(np.arange(3), ["Native", "Normalization only", "Common 145 bank"])
        ax.legend()
    axes[0].set(title="Lowest rescored regional solution", ylabel="Position error (km)")
    axes[1].set(title="Recovered minus ordinary joint score", ylabel="Score difference")
    axes[1].axhline(0, color="grey", linewidth=0.8)
    fig.suptitle("Fixed-vector diagnostics only: negative gap favors the recovered joint solution")
    fig.savefig(HERE / "bank-effects.png", dpi=150)
    (HERE / "comparison.md").write_text("\n".join(table) + "\n")
    (HERE / "summary.json").write_text(
        json.dumps(dict(winners=winners, gaps=gaps), indent=2) + "\n"
    )
    print("\n".join(table))
    print(json.dumps(gaps, indent=2))


if __name__ == "__main__":
    main()
