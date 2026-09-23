"""Report all frozen probes, retaining abstentions and random outer partitions."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/figures/2026_09_23_stream0_pilot_replication"


def main():
    rows = []
    for partition in ("train", "held"):
        directory = OUT / f"{partition}-v2"
        completion = json.loads((directory / "completion.json").read_text())
        assert len(completion["output_hashes"]) == 5
        for name, digest in completion["output_hashes"].items():
            path = directory / name
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
            probe = json.loads(path.read_text())
            row = {key: probe[key] for key in ("index", "time_s", "partition", "status")}
            row["receivers"] = {}
            for rx, data in probe.get("receivers", {}).items():
                exact = data["models"]["exact_ab"]
                gains = {
                    name: 100 * (model["held_sse"] - exact["held_sse"]) / data["held_energy"]
                    for name, model in data["models"].items()
                    if name != "exact_ab"
                }
                row["receivers"][rx] = dict(
                    gains_pp=gains,
                    minimum_gain_pp=min(gains.values()),
                    best_single_gain_pp=min(gains["single_a"], gains["single_b"]),
                    train_rank=exact["train_rank"],
                    held_rank=exact["held_rank"],
                    gram_condition=exact["gram_condition"],
                    residual_cfo_hz=exact["residual_cfo_hz"],
                )
            row["both_rx_support"] = len(row["receivers"]) == 2 and all(
                r["minimum_gain_pp"] > 0 for r in row["receivers"].values()
            )
            rows.append(row)
    rows.sort(key=lambda r: r["index"])
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, constrained_layout=True)
    for rx, ax in enumerate(axes):
        for i, row in enumerate(rows):
            if row["status"] != "eligible":
                ax.text(i, 0, "timing\nabstention", ha="center", va="bottom", fontsize=8)
                continue
            data = row["receivers"][str(rx)]
            color = "tab:blue" if row["partition"] == "held" else "tab:gray"
            ax.scatter(i, data["best_single_gain_pp"], color=color, marker="o")
            ax.scatter(i, data["minimum_gain_pp"], color=color, marker="x")
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_ylabel(f"RX{rx}: held energy gain (pp)")
        ax.grid(alpha=0.2)
    axes[-1].set_xticks(range(10), [f"{r['time_s']:.3f}\n{r['partition']}" for r in rows])
    axes[-1].set_xlabel("Probe time (s); categorical spacing; random outer assignment")
    fig.suptitle(
        "Frozen pilot method on stream 0 with local random calibration\n"
        "Circle: versus best single; cross: worst gain over all controls; blue: outer held"
    )
    fig.savefig(OUT / "replication.png", dpi=160)
    (OUT / "summary.json").write_text(json.dumps(rows, indent=2) + "\n")
    for row in rows:
        print(
            row["time_s"],
            row["partition"],
            row["status"],
            row["both_rx_support"],
            {
                rx: (r["best_single_gain_pp"], r["minimum_gain_pp"])
                for rx, r in row["receivers"].items()
            },
        )


if __name__ == "__main__":
    main()
