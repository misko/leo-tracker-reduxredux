"""Render archived evaluated points; never interpolate an unevaluated surface."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize


def main():
    root = Path(__file__).resolve().parent
    for path in sorted(root.glob("scan-*/positioning.json")):
        data = json.loads(path.read_text())
        fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
        values = [p[2] for label in ("server", "arm") for p in data[label]["points"]]
        norm = Normalize(min(values), max(values))
        for ax, label in zip(axes, ("server", "arm")):
            stage = data[label]
            points = stage["points"]
            assert len(points) == 400
            selected = stage["selected"]
            assert any(p[:2] == selected[:2] for p in points)
            sc = ax.scatter(*zip(*[p[:2] for p in points]), c=[p[2] for p in points],
                            s=28, cmap="viridis_r", norm=norm)
            ax.scatter(*selected[:2], marker="*", s=200, c="#ed4545",
                       edgecolors="black", label="Selected evaluated point", zorder=4)
            ax.set(title=f"{label.upper()} · 400 evaluated points\nSelected ({selected[0]:g}, {selected[1]:g}) km; {selected[2]:.2f} Hz",
                   xlabel="East offset from Sacramento prior (km)",
                   ylabel="North offset from Sacramento prior (km)",
                   xlim=(-260, 260), ylim=(-260, 260), aspect="equal")
            ax.grid(alpha=.15)
            ax.legend(loc="upper right", fontsize=8)
        fig.colorbar(sc, ax=axes, label="Capped weighted RMSE (Hz); lower is better", shrink=.8)
        fig.suptitle(data["session"] + " · regional positioning")
        fig.supxlabel("Both searches exhausted their budget; no converged position fix. Different track memberships/partitions.", fontsize=9)
        fig.savefig(path.with_name("positioning.png"), dpi=160)
        plt.close(fig)


if __name__ == "__main__":
    main()
