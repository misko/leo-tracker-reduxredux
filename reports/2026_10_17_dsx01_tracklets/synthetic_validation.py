"""Bounded, identity-aware synthetic audit of the polynomial tracklet fitter."""

import argparse
import json
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.analysis.polynomial_tracklets import TrackConfig, fit_lane

PERIOD = 1 / 4.4e-6


def examples():
    rng = np.random.default_rng(20261017)
    t = np.linspace(0, 60, 181)
    x = (t - 30) / 30
    zeros = np.zeros(len(t), dtype=int)
    yield "wrap_line", t, 125_000 - 1_500 * t, zeros
    yield "quadratic", t, 70_000 - 900 * (t - 30) + 12 * (t - 30) ** 2, zeros
    yield "quartic", t, 50_000 + 20_000 * x - 10_000 * x**2 + 4_000 * x**3 + 8_000 * x**4, zeros
    z = t - 30
    yield "continuous_curvature_change", t, (
        50_000 - 1_000 * z + np.where(z < 0, 25 * z**2, -25 * z**2)
    ), zeros
    yield "frequency_step", t, 50_000 - 700 * t + 20_000 * (t >= 30), (t >= 30).astype(int)
    crossing_t = np.concatenate([t, t + 0.01, rng.uniform(0, 60, 100)])
    yield "crossing_and_clutter", crossing_t, np.concatenate(
        [90_000 - 1_200 * t, 18_000 + 1_200 * t, rng.uniform(-PERIOD / 2, PERIOD / 2, 100)]
    ), np.concatenate([zeros, zeros + 1, np.full(100, -1)])
    gap_t = np.concatenate([np.linspace(0, 20, 61), np.linspace(80, 100, 61)])
    yield "unobserved_gap", gap_t, 110_000 - 1_600 * gap_t, np.concatenate(
        [np.zeros(61, int), np.ones(61, int)]
    )


def audit(name, t, frequency, identity, config):
    started = time.perf_counter()
    result = fit_lane(t, frequency, config)
    assignment = np.asarray(result["assignment"])
    signal = identity >= 0
    clutter = ~signal
    dominant_count = 0
    track_details = []
    for track in result["tracks"]:
        indices = np.asarray(track["indices"], int)
        counts = Counter(identity[indices][identity[indices] >= 0].tolist())
        dominant = max(counts.values(), default=0)
        dominant_count += dominant
        track_details.append(
            {
                "points": len(indices),
                "signal_identity_counts": dict(sorted(counts.items())),
                "signal_purity": dominant / sum(counts.values()) if counts else None,
                "clutter_points": int(np.sum(identity[indices] < 0)),
                "degrees": [piece["degree"] for piece in track["pieces"]],
                "start_s": track["start_s"],
                "end_s": track["end_s"],
                "residual_rms_hz": track["residual_rms_hz"],
                "quality_flags": track["diagnostics"]["quality_flags"],
            }
        )
    assigned_signal = int(np.sum((assignment >= 0) & signal))
    return {
        "case": name,
        "points": len(t),
        "tracks": len(result["tracks"]),
        "associated_points": int(np.sum(assignment >= 0)),
        "signal_coverage": assigned_signal / int(signal.sum()),
        "assigned_signal_purity": dominant_count / assigned_signal if assigned_signal else None,
        "clutter_association_fraction": (
            float(np.mean(assignment[clutter] >= 0)) if clutter.any() else None
        ),
        "fragments_per_truth_identity": {
            str(label): len(set(assignment[identity == label].tolist()) - {-1})
            for label in np.unique(identity[signal])
        },
        "runtime_s": time.perf_counter() - started,
        "track_details": track_details,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = TrackConfig()
    rng = np.random.default_rng(4000)
    results = []
    for name, t, truth, identity in examples():
        observed = (truth + rng.normal(0, 35, len(t)) + PERIOD / 2) % PERIOD - PERIOD / 2
        report = audit(name, t, observed, identity, config)
        results.append(report)
        print(
            f"{name}: {report['tracks']} tracks, "
            f"{report['associated_points']}/{report['points']} points, "
            f"signal coverage {report['signal_coverage']:.1%}, "
            f"identity purity {report['assigned_signal_purity'] or 0:.1%}",
            flush=True,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "seed": 4000,
        "noise_sigma_hz": 35,
        "config": asdict(config),
        "interpretation": (
            "Synthetic identities measure clustering coherence, not astronomical identity. "
            "The gap case treats both observed sides separately to reveal unsupported joins."
        ),
        "cases": results,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
