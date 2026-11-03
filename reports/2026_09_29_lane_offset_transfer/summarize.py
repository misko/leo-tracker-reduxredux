import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    data = json.loads((HERE / "results.json").read_text())
    lines = [
        "| Panel | Cases | Same-RX supported | Own-offset error Hz | "
        "Shared-offset error Hz | Improved cases |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    panels = {}
    for r in data["rows"]:
        panels.setdefault(r["unit_id"], []).append(r)
    for panel, rows in sorted(panels.items()):
        valid = [r for r in rows if r["arms"]["same_rx"] is not None]
        own = np.array([r["own_error_hz"] for r in valid])
        shared = np.array([r["arms"]["same_rx"]["held_error_hz"] for r in valid])
        lines.append(
            f"| {panel} | {len(rows)} | {len(valid)} | {np.median(own):.2f} | "
            f"{np.median(shared):.2f} | {sum(shared < own - 1e-6)} |"
        )
    (HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
    fig, ax = plt.subplots(figsize=(8, 4))
    ds = ("DS7", "DS8", "DS9")
    for key, offset, label in (
        ("median_own_error_hz", -0.18, "Own training offset"),
        ("median_shared_error_hz", 0.18, "Other-candidate same-RX/RF offset"),
    ):
        ax.bar(
            np.arange(3) + offset,
            [data["summary"][d]["arms"]["same_rx"][key] for d in ds],
            width=0.34,
            label=label,
        )
    ax.set_xticks(np.arange(3), ds)
    ax.set_yscale("log")
    ax.set_ylabel("Median held circular absolute error (native Hz, log scale)")
    ax.set_title("Conditional lane-offset transfer; matched supported cases")
    ax.legend()
    fig.tight_layout()
    fig.savefig(HERE / "comparison.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
