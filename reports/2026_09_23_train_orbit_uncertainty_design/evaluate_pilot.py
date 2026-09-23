"""Post-seal geographic evaluation; never imported by inference code."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REFERENCE = (37.84903264307456, -122.4856541910174)
MODES = ("tau_zero_uncorrected", "point_mean_zero_rate", "all_identity_rate")
LABELS = ("Causal baseline", "Causal point mean", "Shared NORAD rate")


def distance_m(point):
    lat, lon, ref_lat, ref_lon = np.deg2rad([*point, *REFERENCE])
    a = (
        np.sin((lat - ref_lat) / 2) ** 2
        + np.cos(lat) * np.cos(ref_lat) * np.sin((lon - ref_lon) / 2) ** 2
    )
    return float(2 * 6371008.8 * np.arcsin(np.sqrt(np.clip(a, 0, 1))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    content = args.inference.read_bytes()
    actual = hashlib.sha256(content).hexdigest()
    if actual != args.sha256:
        raise ValueError("inference does not match the required seal")
    data = json.loads(content)
    expected = {
        (group, prior) for group in ("first6", "second6") for prior in ("sacramento", "reno")
    }
    arms = data["results"]
    if len(arms) != 4 or {(a["view"], a["prior"]) for a in arms} != expected:
        raise ValueError("four complete unique arms required")
    for arm in arms:
        for mode in MODES:
            result = arm[mode]
            if not result["converged"] or not result["held_1mhz_parameter_invariance"]:
                raise ValueError("convergence and held isolation must pass before evaluation")
        exact = arm[MODES[-1]]["exact_final_state_verification"]
        if exact["profiled_residual_difference_per_track_rms_hz"]["maximum"] > 0.1:
            raise ValueError("quadratic approximation requires further numerical review")
    rows = []
    for arm in arms:
        for mode, label in zip(MODES, LABELS, strict=True):
            result = arm[mode]
            rows.append(
                {
                    "group": arm["view"],
                    "prior": arm["prior"],
                    "mode": mode,
                    "label": label,
                    "track_count": arm["track_count"],
                    "latitude_deg": result["latitude_deg"],
                    "longitude_deg": result["longitude_deg"],
                    "position_error_m": distance_m(
                        (result["latitude_deg"], result["longitude_deg"])
                    ),
                    "training_rms_hz": result["training_rms_hz"],
                    "held_rms_hz": result["evaluation_rms_hz"],
                    "rate_at_bound_count": result["rate_at_bound_count"],
                }
            )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = {
        "inference_sha256": actual,
        "reference_used_only_after_seal": True,
        "reference_lat_lon": REFERENCE,
        "independent_validation": False,
        "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "rows": rows,
    }
    (args.output_dir / "evaluation.json").write_text(json.dumps(output, indent=2) + "\n")
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    groups = [(a["view"], a["prior"]) for a in arms]
    for index, (mode, label) in enumerate(zip(MODES, LABELS, strict=True)):
        selected = [
            next(r for r in rows if (r["group"], r["prior"]) == group and r["mode"] == mode)
            for group in groups
        ]
        x = np.arange(4) + (index - 1) * 0.24
        axes[0].bar(x, [r["position_error_m"] / 1000 for r in selected], 0.24, label=label)
        axes[1].bar(x, [r["held_rms_hz"] for r in selected], 0.24, label=label)
    for axis in axes:
        axis.set_xticks(range(4), [f"{group}\n{prior}" for group, prior in groups])
        axis.grid(axis="y", alpha=0.25)
    axes[0].axhline(0.3, color="black", linestyle="--", label="300 m target")
    axes[0].set_ylabel("Post-seal geographic error (km)")
    axes[1].set_ylabel("Randomized held-out frequency RMS (Hz)")
    axes[0].legend(fontsize=8)
    figure.suptitle("Fixed blind associations · six-scan TRAIN views · not independent validation")
    figure.savefig(args.output_dir / "pilot_comparison.png", dpi=170)
    plt.close(figure)


if __name__ == "__main__":
    main()
