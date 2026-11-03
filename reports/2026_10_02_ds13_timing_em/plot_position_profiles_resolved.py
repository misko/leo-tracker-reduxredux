"""Plot position profiles while excluding unresolved fits from quantitative fields."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from evaluate_position_profiles import ROOT, assert_snapshot_unchanged, digest


DEFAULT_SUMMARY = ROOT / "position-profile-evaluation" / "summary.json"
DEFAULT_OUTPUT_DIR = ROOT / "position-profile-evaluation"
OUTPUT_STEM = "position-profile-compass-resolved"


def profile_plot_data(profile):
    positions = profile["positions"]
    truth_rows = [row for row in positions
                  if row.get("kind") in {"truth", "reference"}
                  or row.get("label") in {"truth", "reference"}]
    if len(truth_rows) != 1:
        raise ValueError("each profile must contain exactly one truth/reference position")
    truth = truth_rows[0]
    origin = np.asarray(truth["fixed_position_km"], dtype=float)
    radial = [row for row in positions
              if row.get("radius_m") is not None and float(row["radius_m"]) > 0]
    resolved = [row for row in radial if row.get("success") and row.get("ranking_resolved")]
    unresolved = [row for row in radial if row not in resolved]

    def points(rows):
        if not rows:
            return np.empty((0, 2), dtype=float)
        return np.asarray([np.asarray(row["fixed_position_km"], dtype=float) - origin
                           for row in rows])

    return {
        "truth": truth,
        "origin": origin,
        "resolved_rows": resolved,
        "unresolved_rows": unresolved,
        "resolved_points": points(resolved),
        "unresolved_points": points(unresolved),
        "resolved_delta_nll": np.asarray(
            [float(row["delta_nll_from_truth"]) for row in resolved], dtype=float
        ),
    }


def resolved_color_limit(profiles):
    values = np.concatenate([
        profile_plot_data(profile)["resolved_delta_nll"] for profile in profiles
    ])
    if len(values) == 0 or not np.all(np.isfinite(values)):
        raise ValueError("at least one finite resolved radial position is required")
    return max(float(np.max(np.abs(values))), 1.0)


def _radius_text(profile):
    lines = []
    for row in profile["radius_summaries"]:
        if row["delta_nll_min_converged"] is None:
            value = "unresolved"
        else:
            value = (f"resolved ΔNLL {row['delta_nll_min_converged']:.2f}"
                     f"…{row['delta_nll_max_converged']:.2f}")
        lines.append(f"{row['radius_m']:.0f} m: {value}")
    return "\n".join(lines)


def plot_resolved_summary(summary, output_dir):
    if summary.get("schema") != "ds13-position-profile-evaluation/v1":
        raise ValueError("unexpected position-profile evaluation schema")
    profiles = summary.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("evaluation has no profiles")
    output_dir = Path(output_dir)
    png_path = output_dir / f"{OUTPUT_STEM}.png"
    svg_path = output_dir / f"{OUTPUT_STEM}.svg"
    existing = [str(path) for path in (png_path, svg_path) if path.exists()]
    if existing:
        raise FileExistsError(f"resolved plot outputs already exist: {', '.join(existing)}")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.tri as tri
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize

    limit = resolved_color_limit(profiles)
    levels = np.linspace(-limit, limit, 21)
    figure, axes = plt.subplots(1, len(profiles), figsize=(7 * len(profiles), 6.5), squeeze=False)
    for axis, profile in zip(axes[0], profiles):
        data = profile_plot_data(profile)
        resolved_points = data["resolved_points"]
        unresolved_points = data["unresolved_points"]
        values = data["resolved_delta_nll"]
        if len(resolved_points) >= 3:
            triangulation = tri.Triangulation(resolved_points[:, 0], resolved_points[:, 1])
            axis.tricontourf(
                triangulation,
                values,
                levels=levels,
                cmap="coolwarm",
                extend="both",
                alpha=.58,
            )
        if len(resolved_points):
            axis.scatter(
                resolved_points[:, 0],
                resolved_points[:, 1],
                c=values,
                cmap="coolwarm",
                norm=Normalize(-limit, limit),
                edgecolors="black",
                s=58,
                zorder=4,
                label="Resolved profile",
            )
        if len(unresolved_points):
            axis.scatter(
                unresolved_points[:, 0],
                unresolved_points[:, 1],
                marker="x",
                color="dimgray",
                s=55,
                linewidths=1.5,
                zorder=5,
                label="Unresolved; excluded from field",
            )
        axis.scatter(0, 0, marker="*", color="black", s=180, zorder=6, label="Truth")
        for radius_m in (50.0, 100.0, 500.0):
            axis.add_patch(plt.Circle(
                (0, 0),
                radius_m / 1000.0,
                fill=False,
                color="black",
                alpha=.35,
                linestyle=":" if radius_m < 500 else "--",
            ))
        bad = profile.get("existing_bad_optimum")
        if bad is not None:
            displacement = np.asarray(bad["fixed_position_km"], dtype=float) - data["origin"]
            distance = float(np.linalg.norm(displacement))
            if distance > 0:
                edge = displacement / distance * .57
                axis.annotate(
                    "",
                    xy=edge,
                    xytext=(0, 0),
                    arrowprops={"arrowstyle": "-|>", "color": "goldenrod", "lw": 2},
                    zorder=5,
                )
                axis.scatter(*edge, marker="X", color="gold", edgecolors="black", s=90,
                             zorder=6, label=f"Old optimum direction ({distance:.2f} km)")
        axis.text(
            .02,
            .02,
            _radius_text(profile),
            transform=axis.transAxes,
            fontsize=8,
            va="bottom",
            bbox={"facecolor": "white", "alpha": .78, "edgecolor": "none"},
        )
        axis.set_title(
            f"…{profile['session'][-8:]}: {profile['resolved_ranking_count']}/"
            f"{profile['completed_position_count']} rankings resolved"
        )
        axis.set_xlim(-.63, .63)
        axis.set_ylim(-.63, .63)
        axis.set_aspect("equal", adjustable="box")
        axis.set_xlabel("East displacement from truth (km)")
        axis.set_ylabel("North displacement from truth (km)")
        axis.grid(alpha=.18)
        axis.legend(fontsize=8, loc="upper right")
    colorbar = figure.colorbar(
        ScalarMappable(norm=Normalize(-limit, limit), cmap="coolwarm"),
        ax=list(axes[0]),
        fraction=.035,
        pad=.03,
    )
    colorbar.set_label("Profiled total ΔNLL from truth (resolved fits only)")
    figure.suptitle("DS13 fixed-position profile: unresolved fits excluded from quantitative field")
    figure.text(
        .5,
        .018,
        "Crosses are finite retained outcomes without resolved optimization rankings. "
        "Stored GLRT peaks, not full GLRT surfaces; no confidence or holdout claim.",
        ha="center",
        fontsize=9,
    )
    figure.subplots_adjust(left=.07, right=.9, bottom=.1, top=.9, wspace=.2)
    figure.savefig(png_path, dpi=170)
    figure.savefig(svg_path)
    plt.close(figure)
    return png_path, svg_path


def render(summary_path=DEFAULT_SUMMARY, output_dir=DEFAULT_OUTPUT_DIR):
    summary_path = Path(summary_path)
    before = digest(summary_path)
    summary = json.loads(summary_path.read_text())
    assert_snapshot_unchanged(summary["source_hashes"])
    outputs = plot_resolved_summary(summary, output_dir)
    if digest(summary_path) != before:
        raise RuntimeError("sealed evaluation summary changed while plotting")
    assert_snapshot_unchanged(summary["source_hashes"])
    return outputs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    for output in render(args.summary, args.output_dir):
        print(output)


if __name__ == "__main__":
    main()
