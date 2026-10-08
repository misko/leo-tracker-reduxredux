"""Retain previous winners and report score-selected cross-arm continuations."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((HERE.parent / name).read_bytes()).hexdigest() == digest
    previous = json.loads(
        (HERE.parent / "2026_10_08_position_error_iter37/summary.json").read_text()
    )
    summary = []
    table = [
        "| Case | Sigma s | c | Before km | After km | Before score | After score | Source |",
        "|---|---:|---|---:|---:|---:|---:|---|",
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    for k, label in enumerate(protocol["cases"]):
        data = json.loads((HERE / "results" / f"{label}.json").read_text())
        for row in data["candidates"]:
            assert row["converged"] == (row["stationarity"] <= 0.001)
            assert max(abs(row["vector"][3]), abs(row["vector"][5])) <= 60 + 1e-7
            if row["arm"] == "zero-c":
                assert row["vector"][6] == 0
        for j, sigma in enumerate((2, 0.75)):
            before, after = [], []
            for arm in ("fitted-c", "zero-c"):
                old = next(
                    r["selected"]
                    for r in previous["selected"]
                    if r["label"] == label and r["sigma"] == sigma and r["arm"] == arm
                )
                new = sorted(
                    [
                        r
                        for r in data["candidates"]
                        if r["sigma"] == sigma and r["arm"] == arm and r["converged"]
                    ],
                    key=lambda r: (r["objective"], r["source_arm"] != arm),
                )
                winner = new[0] if new and new[0]["objective"] < old["objective"] else old
                source = winner.get("source_arm", "previous")
                before.append(old["error_km"])
                after.append(winner["error_km"])
                summary.append(
                    dict(label=label, sigma=sigma, arm=arm, before=old, after=winner, source=source)
                )
                table.append(
                    f"| {label} | {sigma} | {arm} | {old['error_km']:.6f} | "
                    f"{winner['error_km']:.6f} | {old['objective']:.6f} | "
                    f"{winner['objective']:.6f} | {source} |"
                )
            x = np.arange(2)
            axes[k, j].bar(x - 0.18, before, 0.36, label="Previous score winner")
            axes[k, j].bar(x + 0.18, after, 0.36, label="Including cross-arm continuation")
            axes[k, j].set_xticks(x, ["fitted-c", "zero-c"])
            axes[k, j].set(title=f"{label} / sigma {sigma} s", ylabel="Position error (km)")
            axes[k, j].axhline(1, color="grey", linestyle="--", linewidth=0.8)
            axes[k, j].legend(fontsize=7)
    fig.suptitle("Nested-model search audit: select by converged objective within each prior")
    fig.savefig(HERE / "cross-arm.png", dpi=150)
    (HERE / "comparison.md").write_text("\n".join(table) + "\n")
    (HERE / "selected.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("\n".join(table))


if __name__ == "__main__":
    main()
