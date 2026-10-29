"""Package completed CH7/8 experiments; never rerun inference or accept tracks."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np


def main(study, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output.mkdir(parents=True, exist_ok=True)
    records, hashes = {}, {}
    for folder in ("high-channels-v2", "shared-corrections-v1",
                   "band-corrections-v1", "shared-feasible-v1"):
        for path in sorted((study / folder).glob("*.json")):
            raw = path.read_bytes()
            key = str(path.relative_to(study))
            records[key] = json.loads(raw)
            hashes[key] = hashlib.sha256(raw).hexdigest()
    compressed = gzip.compress(json.dumps(records, separators=(",", ":")).encode(), mtime=0)
    (output / "receipts.json.gz").write_bytes(compressed)
    trials = {k: v for k, v in records.items() if "paired_valid" in v}
    summary = {}
    for name, trial in trials.items():
        summary[name] = dict(paired_valid=trial["paired_valid"], arms={})
        for arm, row in trial["arms"].items():
            summary[name]["arms"][arm] = dict(
                objective=row["negative_twice_elbo"],
                position_east_north_km=row["endpoint_east_north_km"],
                targets=[dict(component=t["gate"]["component"],
                              **t["gate"]["conditional_residual_gate"])
                         for t in row["targets"]],
                failed_curves=[g["component"] for g in row["gates"]["tracks"]
                               if not g["compatible"]],
            )
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    source_root = Path(__file__).resolve().parents[1]
    sources = [Path(__file__), *[source_root / "tools" / name for name in (
        "probe_graph_shared_high_channels.py", "probe_graph_shared_corrections.py",
        "refine_graph_shared_curves.py")]]
    (output / "provenance.json").write_text(json.dumps(dict(
        input_sha256=hashes, packaged_source_sha256={str(p.relative_to(source_root)):
            hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        note="Hashes describe publication sources, not contemporaneous execution snapshots. "
             "Earlier controls preceded additions of optional covariance modes.",
        accepted_recovery=False, uses_evaluation_position=False,
        study_path=str(study)), indent=2) + "\n")

    original = records["high-channels-v2/57701_original.json"]
    fast = records["shared-corrections-v1/fast_smooth.json"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    for col, ch in enumerate((7, 8)):
        target = original["arms"]["fitted_c"]["targets"][col]
        t = np.asarray(target["times_s"])
        y = np.asarray(target["values_hz"])
        residual = np.asarray(target["conditional_residual_hz"])
        axes[0, col].scatter(t, y / 1000, s=17, color="#b91c1c", label="Original GLRT graph points")
        axes[0, col].plot(t, (y-residual) / 1000, color="black", lw=1,
                         label="57701 orbit + fitted nuisance terms")
        axes[0, col].set_title(f"RX1 CH{ch}: {len(t)} points, {np.ptp(t):.1f} s")
        axes[0, col].set_ylabel("Graph CFO (kHz; fixed alias convention)")
        for result, label, color in ((original, "Existing model", "#b91c1c"),
                                     (fast, "Faster shared receiver drift", "#2563eb")):
            target = result["arms"]["fitted_c"]["targets"][col]
            axes[1, col].plot(target["times_s"], target["conditional_residual_hz"],
                              ".-", ms=4, label=label, color=color)
        axes[1, col].axhline(0, color="gray", lw=.8)
        axes[1, col].set_ylabel("Conditional residual (Hz)")
        axes[1, col].set_xlabel("Time in scan (s)")
    for ax in axes.flat:
        ax.legend(fontsize=8)
        ax.grid(alpha=.2)
    fig.suptitle("Long curves fit visually, but structured residuals remain\n"
                 "Fitted-c diagnostic proposals — neither qualifies in both c arms")
    fig.tight_layout()
    fig.savefig(output / "tracks_and_residuals.png", dpi=160)
    plt.close(fig)
    for folder, filename in (("high-channels-v2", "residual_context.png"),
                             ("shared-corrections-v1", "recovery_residuals.png")):
        (output / filename).write_bytes((study / folder / filename).read_bytes())
    print(json.dumps({"trials": len(trials), "qualified": sum(r["paired_valid"] for r in trials.values()),
                      "compressed_receipt_bytes": len(compressed)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    main(args.study, args.output)
