#!/usr/bin/env python3
"""Evaluate sealed receive-clock sensitivity results; never used by fitting."""

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]


def load_sealed(path, seal):
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != seal.read_text().strip():
        raise ValueError("Inference seal mismatch")
    data = json.loads(raw)
    if data.get("complete") is not True:
        raise ValueError("Incomplete inference")
    rows = data["rows"]
    # Normalize report field names only after authenticating the raw inference.
    if "clock_winner_point_id" in data:
        data["winner_point_id"] = data["clock_winner_point_id"]
    for row in rows:
        for source, target in (
            ("baseline_training_loss", "tau0_training_capped_loss"),
            ("clock_training_loss", "training_capped_loss"),
            ("clock_held_loss", "held_capped_loss"),
        ):
            if source in row:
                row[target] = row[source]
    index = {r["point_id"]: r for r in rows}
    if len(index) != len(rows) or not rows:
        raise ValueError("Empty or duplicate inference points")
    source = ROOT / "reports/2026_09_24_local_cone_grid/inference.json"
    if (
        data["bindings"]["local_grid"]
        != "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    ):
        raise ValueError("Geographic-grid binding mismatch")
    original = {p["point_id"]: p for p in json.loads(source.read_text())["points"]}
    if set(original) != set(index):
        raise ValueError("Geographic point set changed")
    for row in rows:
        previous = original[row["point_id"]]
        if any(row[k] != previous[k] for k in ("latitude_deg", "longitude_deg")):
            raise ValueError("Geographic coordinates changed")
        if not math.isfinite(row["tau_s"]) or not -5 <= row["tau_s"] <= 5:
            raise ValueError("Invalid time shift")
        old_loss = previous["methods"]["baseline"]["training_capped_loss"]
        if abs(old_loss - row["tau0_training_capped_loss"]) > 1e-8:
            raise ValueError("Zero-shift baseline parity failed")
        cost = row["training_capped_loss"]
        if not math.isfinite(cost) or not 0 <= cost <= old_loss + 1e-8:
            raise ValueError("Invalid shared-clock training loss")
    winner = index[data["winner_point_id"]]
    if winner["training_capped_loss"] > min(r["training_capped_loss"] for r in rows) + 1e-12:
        raise ValueError("Winner not selected by training loss")
    return data, digest


def reference_helper():
    path = ROOT / "reports/2026_09_24_local_cone_grid/evaluate.py"
    spec = importlib.util.spec_from_file_location("clock_postseal_reference", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate(path, seal, output):
    data, digest = load_sealed(path, seal)
    reference = reference_helper()
    baseline = min(data["rows"], key=lambda r: (r["tau0_training_capped_loss"], r["point_id"]))
    clock = next(r for r in data["rows"] if r["point_id"] == data["winner_point_id"])
    rows = []
    for name, row, prefix in (
        ("No clock correction", baseline, "tau0_"),
        ("Shared clock sensitivity", clock, ""),
    ):
        rows.append(
            {
                "method": name,
                "point_id": row["point_id"],
                "latitude_deg": row["latitude_deg"],
                "longitude_deg": row["longitude_deg"],
                "tau_s": 0.0 if prefix else row["tau_s"],
                "training_loss": row[prefix + "training_capped_loss"],
                "held_loss": row[prefix + "held_capped_loss"],
                "error_km": reference.distance_km(
                    (row["latitude_deg"], row["longitude_deg"]), reference.REFERENCE
                ),
                "boundary_hit": False if prefix else row["boundary_hit"],
            }
        )
    result = {
        "schema": "shared-clock-postseal-evaluation/v1",
        "inference_sha256": digest,
        "evaluation_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "reference_used_for_fit": False,
        "rows": rows,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "evaluation.json").write_text(json.dumps(result, indent=2) + "\n")
    plot(data, baseline, clock, reference.REFERENCE, output / "clock_comparison.png")
    lines = [
        "# Shared receive-clock sensitivity on the frozen local grid",
        "",
        "The same 165 geographic points and twelve TRAIN scans were used. One time shift is "
        "shared across all satellites, tracks, and receivers; constant per-track frequency "
        "offsets remain fitted on training rows. Positive tau means predictions are evaluated "
        "later than the recorded timestamp. The ±5-second range is an uncalibrated sensitivity "
        "bound, not an established clock-error prior.",
        "",
        "| Method | Shared shift (s) | TRAIN loss | Held loss | Reference error (km) |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['method']} | {row['tau_s']:+.2f} | {row['training_loss']:.6f} | "
            f"{row['held_loss']:.6f} | {row['error_km']:.3f} |"
        )
    lines += [
        "",
        f"Boundary hits occurred at {data['boundary_hit_count']} of {len(data['rows'])} locations. "
        "A boundary solution is not an identified interior clock estimate. Tau-grid spacing "
        "is not an uncertainty estimate. Orbit-prediction mismatch can also drive the fitted "
        "shift; this experiment does not establish a receiver clock fault.",
        "",
        "All point and time-shift selections use TRAIN losses. Reference errors and the black "
        "reference marker were added after the inference seal was verified. This is a local "
        "TRAIN comparison, not independent generalization or a global geographic optimum.",
        "",
        "![Clock comparison](clock_comparison.png)",
        "",
        f"Inference SHA256: `{digest}`. Detailed values are in `evaluation.json`; "
        "per-point training profiles and selected associations are in `inference.json`.",
    ]
    (output / "REPORT.md").write_text("\n".join(lines) + "\n")
    return result


def plot(data, baseline, clock, reference, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FormatStrFormatter, MaxNLocator

    fig, axes = plt.subplots(2, 2, figsize=(13, 10), constrained_layout=True)
    rows = data["rows"]
    panels = (
        ("tau0_training_capped_loss", "No clock correction: TRAIN loss", baseline),
        ("training_capped_loss", "Shared-clock fit: TRAIN loss", clock),
        ("tau_s", "Selected shift at each location (seconds)", clock),
    )
    for ax, (field, title, selected) in zip(axes.flat, panels, strict=False):
        artist = ax.scatter(
            [r["longitude_deg"] for r in rows],
            [r["latitude_deg"] for r in rows],
            c=[r[field] for r in rows],
            s=27,
            cmap="coolwarm" if field == "tau_s" else "viridis_r",
        )
        ax.scatter(
            selected["longitude_deg"],
            selected["latitude_deg"],
            color="red",
            marker="*",
            s=150,
            edgecolors="white",
            label="TRAIN winner",
        )
        ax.scatter(
            reference[1],
            reference[0],
            color="black",
            marker="x",
            s=80,
            label="Reference (post-seal)",
        )
        ax.set(title=title, xlabel="Longitude", ylabel="Latitude")
        ax.set_aspect(1 / math.cos(math.radians(reference[0])))
        ax.xaxis.set_major_locator(MaxNLocator(4))
        ax.xaxis.set_major_formatter(FormatStrFormatter("%.2f"))
        fig.colorbar(artist, ax=ax)
    ax = axes[1, 1]
    pairs = sorted(zip(clock["profile_tau_s"], clock["profile_training_loss"], strict=True))
    ax.plot([p[0] for p in pairs], [p[1] for p in pairs], ".-")
    ax.axvline(clock["tau_s"], color="red", linestyle="--", label="Selected shift")
    ax.set(
        title="TRAIN profile at clock-selected location",
        xlabel="Shared receive-time shift (seconds)",
        ylabel="All-track capped loss",
    )
    ax.grid(alpha=0.2)
    axes[0, 0].legend(fontsize=8)
    ax.legend()
    fig.savefig(path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--seal", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=HERE)
    args = parser.parse_args()
    evaluate(args.inference, args.seal, args.output_dir)
