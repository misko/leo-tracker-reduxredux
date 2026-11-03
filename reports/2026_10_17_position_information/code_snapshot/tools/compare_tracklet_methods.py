"""Compare independent CFO discovery methods on frozen DSX01 S01 observations."""

from __future__ import annotations

import argparse
import importlib
import json
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np
from evaluate_polynomial_tracklets import (
    DEFAULT_INPUT,
    REPO,
    digest,
    evaluate_lanes,
    json_default,
    load_observations,
    plot_results,
    save_results,
)
from numpy.polynomial import legendre as leg
from validate_polynomial_tracklet_predictions import cross_validate

from leo.analysis.polynomial_tracklets import TrackConfig

METHODS = {
    "baseline": "leo.analysis.polynomial_tracklets",
    "em": "leo.analysis.em_tracklets",
    "graph": "leo.analysis.graph_tracklets",
    "hough": "leo.analysis.hough_tracklets",
    "mht": "leo.analysis.mht_tracklets",
}
DEFAULT_OUTPUT = REPO / "reports/2026_10_17_dsx01_four_methods"


def synthetic_examples():
    rng = np.random.default_rng(20261017)
    t = np.linspace(0, 60, 181)
    z, x = t - 30, (t - 30) / 30
    identity = np.zeros(len(t), int)
    yield "wrap_line", t, 125_000 - 1500 * t, identity, 35.0
    yield "quadratic", t, 70_000 - 900 * z + 12 * z**2, identity, 35.0
    yield (
        "quartic",
        t,
        50_000 + 20_000 * x - 10_000 * x**2 + 4000 * x**3 + 8000 * x**4,
        identity,
        35.0,
    )
    yield (
        "continuous_curvature_change",
        t,
        50_000 - 1000 * z + np.where(z < 0, 25 * z**2, -25 * z**2),
        identity,
        35.0,
    )
    yield "frequency_step", t, 50_000 - 700 * t + 20_000 * (t >= 30), (t >= 30).astype(int), 35.0
    crossing_t = np.r_[t, t + 0.01, rng.uniform(0, 60, 100)]
    crossing_y = np.r_[90_000 - 1200 * t, 18_000 + 1200 * t, rng.uniform(-110_000, 110_000, 100)]
    crossing_id = np.r_[identity, identity + 1, np.full(100, -1)]
    yield "crossing_and_clutter", crossing_t, crossing_y, crossing_id, 35.0
    gap_t = np.r_[np.linspace(0, 20, 61), np.linspace(80, 100, 61)]
    yield (
        "unobserved_gap",
        gap_t,
        110_000 - 1600 * gap_t,
        np.r_[np.zeros(61, int), np.ones(61, int)],
        35.0,
    )
    yield "realistic_noise", t, 125_000 - 1400 * t, identity, 150.0
    yield (
        "parallel_close_tracks",
        np.r_[t, t + 0.01],
        np.r_[70_000 - 900 * t, 72_000 - 900 * t],
        np.r_[identity, identity + 1],
        100.0,
    )
    yield "pure_clutter", t, rng.uniform(-110_000, 110_000, len(t)), np.full(len(t), -1), 0.0


def assert_integrity(result, t, y, cfg):
    """Independently check ownership, aliases, analytic slope extrema and C1 joins."""
    assignment, lifts = np.asarray(result["assignment"]), np.asarray(result["alias_lifts"])
    assert assignment.shape == lifts.shape == t.shape
    assert np.issubdtype(assignment.dtype, np.integer)
    assert np.issubdtype(lifts.dtype, np.integer)
    assert np.all((assignment >= -1) & (assignment < len(result["tracks"])))
    owners = []
    for number, track in enumerate(result["tracks"]):
        members, residuals = [], []
        for piece in track["pieces"]:
            ix = np.asarray(piece["indices"], int)
            assert len(ix) == len(set(ix.tolist()))
            assert len(ix) >= max(
                cfg.min_points, cfg.points_per_coefficient * (piece["degree"] + 1)
            )
            assert 0 <= piece["degree"] <= cfg.max_degree
            assert np.ptp(t[ix]) >= cfg.min_span_s - 1e-9
            assert np.max(np.diff(np.sort(t[ix]))) <= cfg.max_gap_s + 1e-9
            assert np.all(assignment[ix] == number)
            x = (t[ix] - piece["reference_time_s"]) / piece["time_scale_s"]
            coeff = piece["coefficients_hz"]
            prediction = leg.legval(x, coeff)
            residual = y[ix] + cfg.alias_spacing_hz * lifts[ix] - prediction
            assert np.max(abs(residual)) <= cfg.noise_sigma_hz * cfg.association_sigma + 1e-7
            derivative = leg.legder(coeff)
            roots = leg.legroots(leg.legder(derivative))
            candidates = [x.min(), x.max()] + [
                r.real for r in roots if abs(r.imag) < 1e-9 and x.min() <= r.real <= x.max()
            ]
            slopes = leg.legval(candidates, derivative) / piece["time_scale_s"]
            assert np.max(abs(slopes)) <= cfg.max_slope_hz_s + 1e-7
            members.extend(ix.tolist())
            residuals.extend(residual.tolist())
        assert Counter(members) == Counter(track["indices"])
        assert np.isclose(
            np.sqrt(np.mean(np.square(residuals))), track["residual_rms_hz"], atol=1e-7
        )
        for left, right in zip(track["pieces"][:-1], track["pieces"][1:], strict=True):
            knot = left["join_time_s"]
            assert right["join_time_s"] == knot
            values, slopes = [], []
            for piece in (left, right):
                x = (knot - piece["reference_time_s"]) / piece["time_scale_s"]
                values.append(leg.legval(x, piece["coefficients_hz"]))
                slopes.append(
                    leg.legval(x, leg.legder(piece["coefficients_hz"])) / piece["time_scale_s"]
                )
            assert abs(values[0] - values[1]) < 1e-6
            assert abs(slopes[0] - slopes[1]) < 1e-7
        owners.extend(members)
    assert len(owners) == len(set(owners))
    assert sorted(owners) == np.flatnonzero(assignment >= 0).tolist()


def synthetic_benchmark(fitter, cfg):
    rng = np.random.default_rng(4000)
    cases = []
    for name, t, truth, identity, noise in synthetic_examples():
        y = (truth + rng.normal(0, noise, len(t)) + cfg.alias_spacing_hz / 2) % (
            cfg.alias_spacing_hz
        ) - cfg.alias_spacing_hz / 2
        started = time.perf_counter()
        result = fitter(t, y, cfg)
        assert_integrity(result, t, y, cfg)
        assigned = result["assignment"] >= 0
        signal, clutter = identity >= 0, identity < 0
        correct = 0
        for track in result["tracks"]:
            labels = identity[track["indices"]]
            counts = Counter(labels[labels >= 0].tolist())
            correct += max(counts.values(), default=0)
        signal_assigned = int(np.sum(assigned & signal))
        cases.append(
            {
                "case": name,
                "observations": len(t),
                "tracks": len(result["tracks"]),
                "assigned": int(assigned.sum()),
                "signal_coverage": signal_assigned / int(signal.sum()) if signal.any() else None,
                "assigned_signal_purity": correct / signal_assigned if signal_assigned else None,
                "clutter_assigned": int(np.sum(assigned & clutter)),
                "clutter_observations": int(clutter.sum()),
                "runtime_s": time.perf_counter() - started,
            }
        )
        print("synthetic", json.dumps(cases[-1]), flush=True)
    return cases


def source_hashes(module):
    paths = [
        Path(module.__file__),
        Path(__file__),
        REPO / "tools/evaluate_polynomial_tracklets.py",
        REPO / "tools/validate_polynomial_tracklet_predictions.py",
        REPO / "src/leo/analysis/polynomial_tracklets.py",
        REPO / "src/leo/analysis/tracklet_fitting.py",
    ]
    return {str(p.relative_to(REPO)): digest(p) for p in paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=METHODS, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument("--skip-crossfit", action="store_true")
    args = parser.parse_args()
    module = importlib.import_module(METHODS[args.method])
    hashes = source_hashes(module)
    cfg = TrackConfig(max_slope_hz_s=8000.0)
    rows, provenance = load_observations(DEFAULT_INPUT)
    summary, exports = evaluate_lanes(rows, cfg, fitter=module.fit_lane)
    # Reconstruct and check the complete real corpus independently of the runner.
    for lane in summary["lanes"]:
        subset = [
            r for r in rows if (r["receiver"], r["channel"]) == (lane["receiver"], lane["channel"])
        ]
        lane_exports = [
            r
            for r in exports
            if (r["receiver"], r["channel"]) == (lane["receiver"], lane["channel"])
        ]
        reconstructed = {
            "tracks": lane["tracks"],
            "assignment": np.array([r["track_id"] for r in lane_exports]),
            "alias_lifts": np.array([r["alias_lift"] for r in lane_exports]),
        }
        assert_integrity(
            reconstructed,
            np.array([r["time_s"] for r in subset]),
            np.array([r["measured_cfo_hz"] for r in subset]),
            cfg,
        )
    summary["method"] = args.method
    summary["provenance"] = {**provenance, "source_hashes": hashes}
    directory = args.output_dir / args.method
    save_results(directory, summary, exports)
    cases = synthetic_benchmark(module.fit_lane, cfg)
    prediction = None if args.skip_crossfit else cross_validate(rows, cfg, module.fit_lane)
    if source_hashes(module) != hashes:
        raise RuntimeError("Source changed during evaluation; rerun frozen implementation")
    if not args.no_plots:
        plot_results(directory, summary, exports)
    report = {
        "method": args.method,
        "config": asdict(cfg),
        "provenance": summary["provenance"],
        "real_data": {k: v for k, v in summary.items() if k not in ("lanes", "provenance")},
        "synthetic_cases": cases,
        "heldout_prediction": prediction,
        "validation": "complete real/synthetic ownership, aliases, support, gap, degree, "
        "analytic slope and C1 continuity checks passed",
        "limitations": "S01 development evidence; no true satellite identities. Residual "
        "quality remains conditional. Full-discovery crossfit excludes "
        "5-second time blocks before every fit and scores every point.",
    }
    (directory / "comparison.json").write_text(
        json.dumps(report, indent=2, default=json_default, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            {
                "method": args.method,
                "tracks": summary["track_count"],
                "assigned": summary["assigned"],
                "quality": summary["residual_quality"],
                "heldout": prediction,
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
