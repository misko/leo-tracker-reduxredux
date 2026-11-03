import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    data = json.loads((HERE / "results.json").read_text())
    lines = [
        "| Dataset | Returned/planned | Common NMSE | Joint NMSE | Joint improves | "
        "Slope bounds | Median absolute frequency change Hz |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for ds, s in data["summary"].items():
        lines.append(
            f"| {ds} | {s['returned']}/{s['planned']} | {s['mean_nmse']['common']:.6f} | "
            f"{s['mean_nmse']['joint']:.6f} | {s['improved']} | {s['slope_boundaries']} | "
            f"{s['median_absolute_frequency_shift_hz']:.3f} |"
        )
    lines += [
        "",
        "Lower held pilot NMSE is better; every returned excerpt has equal weight.",
        "",
        "| Excerpt | RX | Status | Common f Hz | Joint f Hz | Slope ppm | Held NMSE gain |",
        "|---|---:|---|---:|---:|---:|---:|",
    ]
    valid = []
    for r in data["rows"]:
        prefix = f"| {r['unit_id']} | {r['receiver_id']} | {r['status']}"
        if r["status"] != "ok":
            lines.append(prefix + " | — | — | — | — |")
            continue
        valid.append(r)
        f, slope = r["selected"]["parameters"]
        gain = np.mean(r["common_frame_nmse"]) - np.mean(r["joint_frame_nmse"])
        mark = " (bound)" if r["slope_boundary"] else ""
        lines.append(
            prefix
            + f" | {r['common_frequency_hz']:.3f} | {f:.3f} | {slope:.3f}{mark} | {gain:.6f} |"
        )
    (HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
    fig, ax = plt.subplots(figsize=(8, 5))
    for ds in ("DS7", "DS8", "DS9"):
        group = [r for r in valid if r["panel_id"].startswith(ds)]
        ax.scatter(
            [r["frequency_shift_hz"] for r in group],
            [np.mean(r["common_frame_nmse"]) - np.mean(r["joint_frame_nmse"]) for r in group],
            label=ds,
            alpha=0.75,
        )
    ax.axhline(0, color="black", linewidth=0.7)
    ax.axvline(0, color="black", linewidth=0.7)
    ax.set_xlabel("Joint minus common frequency estimate (Hz)")
    ax.set_ylabel("Held pilot NMSE reduction (positive is better)")
    ax.set_title("Carrier-dependent phase model on all ranked excerpts")
    ax.legend()
    fig.tight_layout()
    fig.savefig(HERE / "comparison.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
