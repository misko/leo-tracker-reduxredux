"""Full-data residual diagnostics and reproducible bounded tracklet tuning.

All observations participate in discovery and fitting. Selection uses residual
structure on adequately supported pieces; no withheld prediction metric enters
the ranking. Noise scale, final residual gate and support floors stay fixed.
"""

from __future__ import annotations

import argparse
import importlib
import json
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
from compare_tracklet_methods import METHODS, assert_integrity
from evaluate_polynomial_tracklets import (
    DEFAULT_INPUT,
    REPO,
    digest,
    evaluate_lanes,
    json_default,
    load_observations,
    save_results,
)

from leo.analysis.polynomial_tracklets import TrackConfig

OUTPUT = REPO / "reports/2026_10_17_dsx01_full_data_tuning"


def full_residual_diagnostics(time_s, residual_hz, noise_sigma_hz=150.0):
    """Descriptive effect-size checks; their thresholds do not certify whiteness."""
    order = np.argsort(time_s, kind="stable")
    t, r = np.asarray(time_s)[order], np.asarray(residual_hz)[order]
    n = len(r)
    if n < 1:
        raise ValueError("Residual diagnostics require observations")
    bins = np.array_split(np.arange(n), min(5, max(1, n // 5)))
    local_z = [float(np.mean(r[b]) / noise_sigma_hz * np.sqrt(len(b))) for b in bins]
    bridge = float(np.max(np.abs(np.cumsum(r - r.mean()))) / (noise_sigma_hz * np.sqrt(n)))
    corr = (
        float(np.corrcoef(r[:-1], r[1:])[0, 1])
        if (n > 3 and np.std(r[:-1]) > 1e-8 and np.std(r[1:]) > 1e-8)
        else 0.0
    )
    signs = r > 0
    plus, minus = int(signs.sum()), int((~signs).sum())
    runs = int(1 + np.count_nonzero(signs[1:] != signs[:-1]))
    runs_z = 0.0
    if plus and minus and n > 2 and np.std(r) > 1e-8:
        expected = 1 + 2 * plus * minus / n
        variance = 2 * plus * minus * (2 * plus * minus - n) / (n * n * (n - 1))
        runs_z = float((runs - expected) / np.sqrt(variance)) if variance > 0 else 0.0
    candidates = np.arange(max(5, n // 10), n - max(5, n // 10) + 1)
    step_z = 0.0
    if len(candidates):
        cumulative = np.cumsum(r)
        differences = cumulative[candidates - 1] / candidates - (
            cumulative[-1] - cumulative[candidates - 1]
        ) / (n - candidates)
        step_z = float(
            np.max(
                np.abs(differences)
                / (noise_sigma_hz * np.sqrt(1 / candidates + 1 / (n - candidates)))
            )
        )
    flags = []
    if abs(r.mean()) * np.sqrt(n) / noise_sigma_hz > 3.5:
        flags.append("nonzero_mean")
    if max(np.abs(local_z)) > 3.5:
        flags.append("local_mean_structure")
    if bridge > 1.6:
        flags.append("cumulative_residual_structure")
    if abs(corr) > max(0.35, 2.5 / np.sqrt(n)):
        flags.append("adjacent_residual_correlation")
    if abs(runs_z) > 3.5:
        flags.append("residual_sign_runs")
    if step_z > 4:
        flags.append("residual_mean_step")
    status = (
        "structure_flagged"
        if flags
        else ("insufficient_support" if n < 20 else "no_structure_detected")
    )
    return {
        "observations": n,
        "mean_hz": float(r.mean()),
        "rms_hz": float(np.sqrt(np.mean(r * r))),
        "flags": flags,
        "status": status,
        "local_mean_z": local_z,
        "cumulative_bridge": bridge,
        "adjacent_correlation": corr,
        "sign_runs": runs,
        "sign_runs_z": runs_z,
        "maximum_mean_step_z": step_z,
        "bin_std_hz": [float(np.std(r[b])) for b in bins],
        "median_elapsed_s": float(np.median(np.diff(t))) if n > 1 else None,
    }


def annotate_full_data_quality(summary, exports):
    """Replace report quality categories with the same full-data-only policy."""
    lookup = {(r["receiver"], r["channel"], r["observation_id"]): r for r in exports}
    totals = {
        s: {"tracks": 0, "associated_points": 0}
        for s in ("no_structure_detected", "structure_flagged", "insufficient_support")
    }
    for lane in summary["lanes"]:
        for track in lane["tracks"]:
            piece_diagnostics = []
            for piece in track["pieces"]:
                rows = [
                    lookup[lane["receiver"], lane["channel"], oid]
                    for oid in piece["observation_ids"]
                ]
                diagnostic = full_residual_diagnostics(
                    [r["time_s"] for r in rows],
                    [r["residual_hz"] for r in rows],
                    summary["config"]["noise_sigma_hz"],
                )
                piece["full_data_residual_diagnostics"] = diagnostic
                piece_diagnostics.append(diagnostic)
            flags = sorted({f for d in piece_diagnostics for f in d["flags"]})
            status = (
                "structure_flagged"
                if flags
                else (
                    "insufficient_support"
                    if any(d["status"] == "insufficient_support" for d in piece_diagnostics)
                    else "no_structure_detected"
                )
            )
            track["previous_quality_status"] = track["quality_status"]
            track["quality_status"] = status
            track["full_data_quality_flags"] = flags
            totals[status]["tracks"] += 1
            totals[status]["associated_points"] += len(track["indices"])
            for piece in track["pieces"]:
                for oid in piece["observation_ids"]:
                    lookup[lane["receiver"], lane["channel"], oid]["quality_status"] = status
    summary["residual_quality"] = totals
    summary["quality_policy"] = (
        "Full-data mean, local means, cumulative residuals, sign runs, adjacent correlation "
        "and residual steps; >=20 observations per piece for adequate diagnostic support. "
        "No withheld prediction metric used. No-structure-detected remains descriptive."
    )
    return summary, exports


def rank_candidate(summary):
    quality = summary["residual_quality"]
    return (
        quality["no_structure_detected"]["associated_points"],
        summary["assigned"],
        -quality["structure_flagged"]["associated_points"],
        -summary["track_count"],
        -summary["residual_diagnostics"]["rms_hz"],
    )


def candidate_record(name, summary):
    return {
        "name": name,
        "config": summary["config"],
        "track_count": summary["track_count"],
        "assigned": summary["assigned"],
        "unresolved": summary["unresolved"],
        "residual_quality": summary["residual_quality"],
        "runtime_s": summary["runtime_s"],
        "rank": rank_candidate(summary),
    }


def audit_real_result(rows, summary, exports, cfg):
    assert len(rows) == len(exports) == 4797
    assert {r["observation_id"] for r in rows} == {r["observation_id"] for r in exports}
    for lane in summary["lanes"]:
        selected = [
            r
            for r in exports
            if (r["receiver"], r["channel"]) == (lane["receiver"], lane["channel"])
        ]
        assert_integrity(
            {
                "tracks": lane["tracks"],
                "assignment": np.array([r["track_id"] for r in selected]),
                "alias_lifts": np.array([r["alias_lift"] for r in selected]),
            },
            np.array([r["time_s"] for r in selected]),
            np.array([r["measured_cfo_hz"] for r in selected]),
            cfg,
        )


def run_search(method, configs, output=OUTPUT):
    """Save every trial, including failures, then choose by fixed residual-quality rules."""
    rows, provenance = load_observations(DEFAULT_INPUT)
    module = importlib.import_module(METHODS[method])
    hashes = {
        str(p.relative_to(REPO)): digest(p)
        for p in [
            Path(module.__file__),
            Path(__file__),
            REPO / "src/leo/analysis/tracklet_fitting.py",
            REPO / "src/leo/analysis/polynomial_tracklets.py",
        ]
    }
    records = []
    for name, cfg in configs:
        if (
            cfg.noise_sigma_hz != 150
            or cfg.association_sigma != 3
            or cfg.max_degree > 4
            or cfg.min_points < 8
            or cfg.points_per_coefficient < 4
            or cfg.min_span_s < 6
            or cfg.max_gap_s > 10
            or cfg.track_penalty <= 0
            or cfg.breakpoint_penalty <= 0
        ):
            raise ValueError(
                "Tuning must preserve the fixed noise/gate and scientific support floors"
            )
        folder = output / method / "trials" / name
        try:
            summary, exports = evaluate_lanes(rows, cfg, module.fit_lane)
            summary, exports = annotate_full_data_quality(summary, exports)
            audit_real_result(rows, summary, exports, cfg)
            summary["provenance"] = {**provenance, "source_hashes": hashes}
            summary["method"] = method
            save_results(folder, summary, exports)
            record = candidate_record(name, summary)
        except Exception as error:
            record = {"name": name, "config": asdict(cfg), "failure": repr(error)}
        records.append(record)
        (output / method).mkdir(parents=True, exist_ok=True)
        (output / method / "search.json").write_text(
            json.dumps(records, indent=2, default=json_default, allow_nan=False) + "\n"
        )
        print("TUNING", method, json.dumps(record, default=json_default), flush=True)
    assert all(digest(REPO / path) == value for path, value in hashes.items())
    successful = [r for r in records if "rank" in r]
    if not successful:
        raise RuntimeError(f"Every {method} trial failed")
    winner = max(successful, key=lambda r: tuple(r["rank"]))
    (output / method / "selected.json").write_text(
        json.dumps(winner, indent=2, default=json_default, allow_nan=False) + "\n"
    )
    return winner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=METHODS, required=True)
    args = parser.parse_args()
    base = TrackConfig(max_slope_hz_s=8000.0)
    configs = [
        ("base", base),
        ("slope12000", replace(base, max_slope_hz_s=12000.0)),
        ("slope16000", replace(base, max_slope_hz_s=16000.0)),
        ("penalty10", replace(base, track_penalty=10.0, breakpoint_penalty=5.0)),
        (
            "slope12000-penalty10",
            replace(base, max_slope_hz_s=12000.0, track_penalty=10.0, breakpoint_penalty=5.0),
        ),
        (
            "slope16000-penalty6",
            replace(base, max_slope_hz_s=16000.0, track_penalty=6.0, breakpoint_penalty=5.0),
        ),
        ("degree3", replace(base, max_degree=3)),
        ("seed1702", replace(base, random_seed=1702)),
    ]
    print(json.dumps(run_search(args.method, configs), default=json_default, indent=2))


if __name__ == "__main__":
    main()
