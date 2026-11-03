import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    results = json.loads((HERE / "results.json").read_text())
    lines = [
        "| Dataset | Returned/planned | Cached trajectory NMSE | Long trajectory NMSE | Improved | Mean gain |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for ds, s in results["summary"].items():
        means = s["means"]
        lines.append(
            f"| {ds} | {s['returned']}/{s['planned']} | {means['cached_trajectory']:.6f}"
            f" | {means['long_trajectory']:.6f} | {s['improved']} | {s['mean_gain']:.6f} |"
        )
    lines += [
        "",
        "Lower NMSE is better; positive gain favors long-pilot training estimates.",
        "",
        "| Panel | RX | Status | Cached trajectory NMSE | Long trajectory NMSE | Held cached NMSE | Held local-long NMSE | Slope change Hz/s |",
        "|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    valid = []
    for r in results["rows"]:
        prefix = f"| {r['panel_id']} | {r['receiver_id']} | {r['status']}"
        if r["status"] != "ok":
            lines.append(prefix + " | — | — | — | — | — |")
            continue
        valid.append(r)
        values = " | ".join(
            f"{np.mean(r['arms'][a]['frame_nmse']):.6f}"
            for a in ("cached_trajectory", "long_trajectory", "cached_held", "local_long_held")
        )
        lines.append(prefix + f" | {values} | {r['slope_change_hz_s']:.3f} |")
    (HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
    gains = [
        np.mean(r["arms"]["cached_trajectory"]["frame_nmse"])
        - np.mean(r["arms"]["long_trajectory"]["frame_nmse"])
        for r in valid
    ]
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(np.arange(len(valid)), gains, color=["#25826c" if g > 0 else "#b44d3f" for g in gains])
    ax.set_yticks(np.arange(len(valid)), [f"{r['panel_id']} RX{r['receiver_id']}" for r in valid])
    ax.axvline(0, color="black", linewidth=0.7)
    ax.set_xlabel("Held-visit pilot NMSE reduction: cached versus long-pilot trajectory")
    ax.set_title("Two earlier visits predict a later held visit; positive is better")
    fig.tight_layout()
    fig.savefig(HERE / "comparison.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
