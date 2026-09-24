#!/usr/bin/env python3
"""Post-seal reference evaluation and maps; never imported by the search."""

import argparse
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
METHODS = ("baseline", "cone_10", "cone_20", "cone_25", "cone_30", "cone_40", "cone_50")
REFERENCE = (37.84903264307456, -122.4856541910174)


def loss(method):
    return float(method.get("training_capped_loss", method.get("training_loss")))


def load_sealed(path, seal):
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != seal.read_text().strip():
        raise ValueError("Inference digest does not match seal")
    data = json.loads(raw)
    if data.get("complete") is not True:
        raise ValueError("Inference is incomplete")
    points = data["points"]
    index = {p["point_id"]: p for p in points}
    if len(index) != len(points) or not points:
        raise ValueError("Empty or duplicate point IDs")
    if set(data["winners"]) != set(METHODS):
        raise ValueError("Incomplete method set")
    for point in points:
        point["lat"] = point["latitude_deg"]
        point["lon"] = point["longitude_deg"]
        if not (-90 <= point["lat"] <= 90 and -180 <= point["lon"] <= 180):
            raise ValueError("Invalid coordinate")
        for method in METHODS:
            value = loss(point["methods"][method])
            if not math.isfinite(value) or not 0 <= value <= 1 + 1e-12:
                raise ValueError("Invalid training loss")
    for method, winner in data["winners"].items():
        point = index[winner["point_id"]]
        if loss(point["methods"][method]) > min(loss(p["methods"][method]) for p in points) + 1e-12:
            raise ValueError("Winner was not selected by minimum training loss")
    return data, actual


def distance_km(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    h = min(1.0, max(0.0, h))
    return 6371.0088 * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))


def old_winners():
    cells = json.loads((ROOT / "reports/2026_09_23_train_fixed_cone/locations.json").read_text())[
        "cells"
    ]
    index = {c["cell_id"]: c for c in cells}
    rows = json.loads((ROOT / "reports/2026_09_23_staged_cone_to90/results.json").read_text())[
        "results"
    ]
    result = {}
    for method in METHODS:
        if method == "baseline":
            selected = min(rows, key=lambda r: r["baseline_training_capped_loss"])
        else:
            width = int(method.split("_")[1])

            def score(row, width=width):
                return next(
                    s["training_capped_loss"]
                    for s in row["scenarios"]
                    if s["full_fov_deg"] == width and s["mapping"] == [0, 1]
                )

            selected = min(rows, key=score)
        cell = index[selected["cell_id"]]
        result[method] = {
            "cell_id": cell["cell_id"],
            "error_km": distance_km((cell["latitude_deg"], cell["longitude_deg"]), REFERENCE),
        }
    return result


def evaluate(path, seal, output_dir):
    data, digest = load_sealed(path, seal)
    # Reference coordinates and prior-error comparisons are used only after gating.
    old = old_winners()
    index = {p["point_id"]: p for p in data["points"]}
    rows = []
    for method in METHODS:
        point = index[data["winners"][method]["point_id"]]
        error = distance_km((point["lat"], point["lon"]), REFERENCE)
        rows.append(
            {
                "method": method,
                "point_id": point["point_id"],
                "latitude_deg": point["lat"],
                "longitude_deg": point["lon"],
                "training_loss": loss(point["methods"][method]),
                "old_cell": old[method]["cell_id"],
                "old_error_km": old[method]["error_km"],
                "new_error_km": error,
                "change_km": error - old[method]["error_km"],
            }
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    output = {
        "schema": "local-cone-grid-postseal-evaluation/v1",
        "inference_sha256": digest,
        "evaluation_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "reference_latitude_deg": REFERENCE[0],
        "reference_longitude_deg": REFERENCE[1],
        "reference_used_for_inference": False,
        "evaluated_point_count": len(index),
        "rows": rows,
    }
    (output_dir / "evaluation.json").write_text(json.dumps(output, indent=2) + "\n")
    plot(data, rows, output_dir / "fine_grid.png")
    lines = [
        "# Local cone-grid position comparison",
        "",
        "Each method selected its location using TRAIN loss only. Reference errors and the "
        "black reference marker were added after the inference seal was verified. This is a "
        "local TRAIN diagnostic, not independent validation or a global optimum.",
        "",
        "| Method | Old error (km) | Finer-grid error (km) | Change (km; negative is better) |",
        "|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {label(row['method'])} | {row['old_error_km']:.3f} | "
            f"{row['new_error_km']:.3f} | {row['change_km']:+.3f} |"
        )
    lines.extend(
        [
            "",
            f"Evaluated {len(index)} geographic points. Finest requested spacing is 1.25 km; "
            "a selected grid centre's error is not a calibrated uncertainty or a resolution "
            "guarantee. Scores on the maps include unmatched-track penalties.",
            "",
            "![Training score maps](fine_grid.png)",
            "",
            f"Inference SHA256: `{digest}`. "
            "Machine-readable post-seal comparison: `evaluation.json`.",
        ]
    )
    (output_dir / "REPORT.md").write_text("\n".join(lines) + "\n")
    return output


def label(method):
    return "Ordinary Doppler" if method == "baseline" else method.split("_")[1] + "° full FOV"


def plot(data, rows, target):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FormatStrFormatter, MaxNLocator

    fig, axes = plt.subplots(3, 3, figsize=(16, 14), constrained_layout=True)
    points = data["points"]
    for ax, row in zip(axes.flat, rows, strict=False):
        method = row["method"]
        artist = ax.scatter(
            [p["lon"] for p in points],
            [p["lat"] for p in points],
            c=[loss(p["methods"][method]) for p in points],
            cmap="viridis_r",
            s=24,
        )
        ax.scatter(
            row["longitude_deg"],
            row["latitude_deg"],
            marker="*",
            s=200,
            color="red",
            edgecolors="white",
            label="TRAIN winner",
            zorder=4,
        )
        ax.scatter(
            REFERENCE[1],
            REFERENCE[0],
            marker="x",
            s=90,
            color="black",
            linewidths=2,
            label="Reference (post-seal)",
            zorder=5,
        )
        for region in data.get("regions", []):
            ax.scatter(
                region["center_longitude_deg"],
                region["center_latitude_deg"],
                marker="o",
                s=85,
                facecolors="none",
                edgecolors="gray",
                zorder=4,
            )
            ax.annotate(
                str(region["region"]),
                (region["center_longitude_deg"], region["center_latitude_deg"]),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=7,
                color="gray",
            )
        ax.set(
            title=f"{label(method)} · error {row['new_error_km']:.3f} km",
            xlabel="Longitude (degrees)",
            ylabel="Latitude (degrees)",
        )
        ax.set_aspect(1 / math.cos(math.radians(REFERENCE[0])))
        ax.xaxis.set_major_locator(MaxNLocator(4))
        ax.xaxis.set_major_formatter(FormatStrFormatter("%.2f"))
        ax.tick_params(axis="x", labelsize=8, labelrotation=25)
        ax.grid(alpha=0.15)
        fig.colorbar(artist, ax=ax, label="All-track TRAIN capped loss")
    for ax in list(axes.flat)[len(rows) :]:
        ax.axis("off")
    axes.flat[0].legend(fontsize=8)
    fig.suptitle(
        "Local refinement around the two frozen estimates · near-zenith restriction retained\n"
        "Points are evaluated locations; no interpolation between unevaluated cells",
        fontsize=14,
    )
    fig.savefig(target, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--seal", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=HERE)
    args = parser.parse_args()
    evaluate(args.inference, args.seal, args.output_dir)
