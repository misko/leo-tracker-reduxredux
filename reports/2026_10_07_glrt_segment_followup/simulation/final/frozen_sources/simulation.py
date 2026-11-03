"""Independent development, calibration, and held-out segment comparison."""

# Set thread limits before numerical imports.
# ruff: noqa: E402
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

for _thread_variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_thread_variable] = "1"

import numpy as np
from segment_methods import score_trials

from leo.analysis.starlink import templates

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / "2026_10_07_glrt_detector_comparison"
_spec = importlib.util.spec_from_file_location(
    "segment_comparison_prior_utilities", PRIOR / "synthetic.py"
)
prior = importlib.util.module_from_spec(_spec)
# Its uniquely named utility module imports the prior scorer, whereas this
# experiment imports segment_methods. No prior source or config is changed.
sys.path.insert(0, str(PRIOR))
try:
    _spec.loader.exec_module(prior)
finally:
    sys.path.pop(0)

SCENARIOS = {
    "coherent": {"environment": "white", "sigma": 0.0, "jump_probability": 0.0},
    "sigma_0p15": {"environment": "white", "sigma": 0.15, "jump_probability": 0.0},
    "sigma_0p35": {"environment": "white", "sigma": 0.35, "jump_probability": 0.0},
    "sigma_0p60": {"environment": "white", "sigma": 0.60, "jump_probability": 0.0},
    "rare_pi_jump": {"environment": "white", "sigma": 0.0, "jump_probability": 0.25},
    "colored_ar": {"environment": "correlated_ar", "sigma": 0.0, "jump_probability": 0.0},
    "coherent_tone": {"environment": "coherent_tone", "sigma": 0.0, "jump_probability": 0.0},
}
BASELINES = ("gaussian_coherent", "current_coherent_margin")
SEGMENTS = ("segment8", "segment16", "segment32", "segment64")
UNION_MEMBERS = ("segment16", "segment32", "segment64")
NATURAL_CANDIDATES = (
    "segment8", "segment16", "segment32",
    "phase_kernel8", "phase_kernel16", "phase_kernel32",
    "multiscale_union", "multiscale_union_cfo64",
)
PRIMARY_PHASE_SCENARIOS = ("sigma_0p15", "sigma_0p35", "sigma_0p60", "rare_pi_jump")
CONFIG = {
    "seed": 2026100702,
    "frames_per_trial": 14,
    "symbols_per_frame": 64,
    "symbol_step_s": 4.4e-6,
    "fft_size": 512,
    "batch_size": 64,
    "snr_db": [-18, -15, -12, -9],
    "normalization_null_count": 2000,
    "development_null_count": 3000,
    "development_signal_count": 400,
    "calibration_null_count": 3000,
    "heldout_null_count": 5000,
    "heldout_signal_count": 600,
    "target_false_alarm": 0.01,
    "correct_cfo_tolerance_hz": 1000,
    "bootstrap_replicates": 2000,
    "scenarios": SCENARIOS,
    "natural_candidates": list(NATURAL_CANDIDATES),
    "selection_rule": {
        "criterion": "maximum equal-weight mean joint detection and CFO error <=1 kHz",
        "primary_phase_scenarios": list(PRIMARY_PHASE_SCENARIOS),
        "snr_db": [-18, -15, -12, -9],
        "coherent_constraint_snr_db": -15,
        "maximum_detection_regression": 0.05,
        "coherent_constraint_baselines": list(BASELINES),
        "eligibility_uses": "development point estimates; uncertainty reported",
        "ties": "lexicographic candidate name",
        "if_no_candidate_qualifies": "no short-method recommendation",
        "margin_diagnostics": "evaluated but excluded from selection",
        "oracle_segment": "held-out diagnostic only, never selected",
    },
    "union": {
        "members": list(UNION_MEMBERS),
        "normalization": "per-environment independent null mean and population std",
        "statistic": "max of standardized member whole-CFO-bank scores",
        "cfo": "CFO of maximizing member; hybrid replaces with coherent64 CFO",
        "calibration": "own independent null threshold including multiscale search",
    },
    "seed_namespaces": {
        "normalization_null": "[seed,10,environment_index]",
        "development_null": "[seed,20,0]",
        "development_signal": "[seed,21,scenario_index,snr_index]",
        "final_calibration_null": "[seed,30,environment_index]",
        "final_heldout_null": "[seed,40,environment_index]",
        "final_heldout_signal": "[seed,41,scenario_index,snr_index]",
        "paired_bootstrap": "[seed,50,baseline_index,scenario_index,snr_index]",
        "aggregate_bootstrap": "[seed,51,baseline_index]",
    },
    "scope": "conditioned on one correct epoch; fourteen frames; entire 512 CFO-bin search",
    "noise_model": "prior actual Qin normalized template Gram; shared exact/control IQ projection",
    "signal_model": "constant unit-energy pilot response; common CFO; independent frame phases",
    "ar_coefficient": 0.85,
    "tone_inr_db": 10.0,
    "tone_frequency_hz": 117187.5,
    "true_cfo_uniform_hz": [-70000, 70000],
}


def draw_case(rng, count, scenario, geometry, snr_db=None):
    """Use unchanged prior shared-IQ noise and a new prespecified phase signal."""
    environment = scenario["environment"]
    exact, control, _ = prior.draw_observations(
        rng, count, environment, geometry, frames=CONFIG["frames_per_trial"]
    )
    if snr_db is None:
        return exact, control, None
    frames = CONFIG["frames_per_trial"]
    truth = rng.uniform(*CONFIG["true_cfo_uniform_hz"], count)
    phase = rng.uniform(-np.pi, np.pi, (count, frames, 1))
    phase = phase + (
        2 * np.pi * truth[:, None, None] * np.arange(64) * CONFIG["symbol_step_s"]
    )
    increments = rng.normal(0, scenario["sigma"], (count, frames, 63))
    phase[:, :, 1:] += np.cumsum(increments, axis=2)
    if scenario["jump_probability"]:
        has_jump = rng.uniform(0, 1, (count, frames)) < scenario["jump_probability"]
        boundary = rng.integers(1, 64, (count, frames))
        phase += np.pi * has_jump[:, :, None] * (np.arange(64) >= boundary[:, :, None])
    signal = 10 ** (snr_db / 20) * np.exp(1j * phase)
    return exact + signal, control + geometry["overlap"] * signal, truth


def score_cases(exact, control):
    batches = []
    for start in range(0, len(exact), CONFIG["batch_size"]):
        stop = start + CONFIG["batch_size"]
        batches.append(score_trials(exact[start:stop], control[start:stop]))
    return {
        method: {key: np.concatenate([batch[method][key] for batch in batches])
                 for key in values}
        for method, values in batches[0].items()
    }


def fit_normalization(scores):
    return {
        member: {"mean": float(np.mean(scores[member]["score"])),
                 "std": float(np.std(scores[member]["score"]))}
        for member in UNION_MEMBERS
    }


def add_union(scores, normalization):
    standardized = np.stack([
        (scores[member]["score"] - normalization[member]["mean"])
        / normalization[member]["std"] for member in UNION_MEMBERS
    ], axis=1)
    winner = np.argmax(standardized, axis=1)
    rows = np.arange(len(winner))
    member_cfo = np.stack([scores[member]["cfo_hz"] for member in UNION_MEMBERS], axis=1)
    member_control_cfo = np.stack([
        scores[member]["control_cfo_hz"] for member in UNION_MEMBERS
    ], axis=1)
    # The union's score is the calibrated standardized maximum, not a margin.
    scores["multiscale_union"] = {
        "score": standardized[rows, winner], "cfo_hz": member_cfo[rows, winner],
        "exact_score": standardized[rows, winner],
        "control_score": np.full(len(winner), np.nan),
        "control_cfo_hz": member_control_cfo[rows, winner],
        "selected_member_index": winner,
    }
    scores["multiscale_union_cfo64"] = dict(scores["multiscale_union"])
    scores["multiscale_union_cfo64"]["cfo_hz"] = scores["gaussian_coherent"]["cfo_hz"]
    return scores


def calibrated_thresholds(scores, false_alarm):
    return {method: float(np.quantile(values["score"], 1 - false_alarm, method="higher"))
            for method, values in scores.items()}


def method_events(values, truth, threshold):
    detected = values["score"] > threshold
    error = prior.cfo_error(values["cfo_hz"], truth)
    joint = detected & (error <= CONFIG["correct_cfo_tolerance_hz"])
    return detected, joint, error


def summarize_method(values, truth, threshold):
    detected, joint, errors = method_events(values, truth, threshold)
    return {
        "count": len(detected), "detected": int(detected.sum()),
        "detection_rate": float(np.mean(detected)),
        "detection_wilson_95": prior.wilson_interval(int(detected.sum()), len(detected)),
        "correct_detections": int(joint.sum()), "joint_rate": float(np.mean(joint)),
        "joint_wilson_95": prior.wilson_interval(int(joint.sum()), len(joint)),
        "cfo_unconditional": prior.summarize_cfo(errors),
        "cfo_detection_conditional": prior.summarize_cfo(errors[detected]),
    }


def paired_interval(selected, baseline, rng, replicates=2000):
    """Paired percentile bootstrap conditional on fixed trained decisions."""
    difference = np.asarray(selected, dtype=float) - np.asarray(baseline, dtype=float)
    boot = difference[rng.integers(0, len(difference), (replicates, len(difference)))].mean(axis=1)
    return {
        "difference": float(difference.mean()),
        "bootstrap_95": [float(x) for x in np.quantile(boot, [0.025, 0.975])],
        "selected_only": int(np.count_nonzero(difference == 1)),
        "baseline_only": int(np.count_nonzero(difference == -1)),
        "count": len(difference),
    }


def choose_recommendation(development):
    coherent = development["coherent"]["-15"]
    candidates = {}
    for candidate in NATURAL_CANDIDATES:
        regression = {
            baseline: coherent[candidate]["detection_rate"] - coherent[baseline]["detection_rate"]
            for baseline in BASELINES
        }
        eligible = all(value >= -0.05 for value in regression.values())
        objective = float(np.mean([
            development[scenario][str(snr)][candidate]["joint_rate"]
            for scenario in PRIMARY_PHASE_SCENARIOS for snr in CONFIG["snr_db"]
        ]))
        candidates[candidate] = {
            "eligible": eligible, "development_joint_objective": objective,
            "coherent_detection_difference": regression,
        }
    qualifying = [
        candidate for candidate in NATURAL_CANDIDATES if candidates[candidate]["eligible"]
    ]
    selected = (
        min(qualifying, key=lambda name: (-candidates[name]["development_joint_objective"], name))
        if qualifying else None
    )
    return {"selected": selected, "candidates": candidates}


def source_manifest():
    sources = {
        "simulation.py": Path(__file__),
        "segment_methods.py": HERE / "segment_methods.py",
        "prior_synthetic.py": PRIOR / "synthetic.py",
        "prior_methods.py": PRIOR / "methods.py",
        "templates.py": Path(templates.__file__),
    }
    return {name: {"path": str(path.resolve()),
                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for name, path in sources.items()}


def assert_sources_unchanged(manifest):
    current = source_manifest()
    if current != manifest:
        raise RuntimeError("Experiment source changed after protocol freeze")


def save_scores(destination, scores):
    np.savez_compressed(destination, **{
        f"{method}__{key}": value
        for method, values in scores.items() for key, value in values.items()
    })


def run(output, quick=False):
    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)
    config = dict(CONFIG)
    if quick:
        config.update(normalization_null_count=100, development_null_count=100,
                      development_signal_count=30, calibration_null_count=100,
                      heldout_null_count=100, heldout_signal_count=30,
                      bootstrap_replicates=100)
    config["quick_smoke_only"] = quick
    config["numpy_version"] = np.__version__
    config["sources"] = source_manifest()
    geometry = prior.pilot_geometry()
    config["template_overlap_real"] = geometry["overlap"].real.tolist()
    config["template_overlap_imag"] = geometry["overlap"].imag.tolist()
    protocol = json.dumps(config, indent=2, sort_keys=True) + "\n"
    protocol_hash = hashlib.sha256(protocol.encode()).hexdigest()
    (output / "frozen_protocol.json").write_text(protocol)
    snapshots = output / "frozen_sources"
    snapshots.mkdir(exist_ok=True)
    for name, source in config["sources"].items():
        (snapshots / name).write_bytes(Path(source["path"]).read_bytes())
    environments = ["white", "correlated_ar", "coherent_tone"]
    normalizers = {}
    for index, environment in enumerate(environments):
        rng = np.random.default_rng(np.random.SeedSequence([config["seed"], 10, index]))
        null_scenario = {"environment": environment}
        exact, control, _ = draw_case(
            rng, config["normalization_null_count"], null_scenario, geometry
        )
        scores = score_cases(exact, control)
        normalizers[environment] = fit_normalization(scores)
        save_scores(output / f"normalization_{environment}.npz", scores)
    (output / "frozen_normalizers.json").write_text(json.dumps(normalizers, indent=2) + "\n")
    development_null_rng = np.random.default_rng(np.random.SeedSequence([config["seed"], 20, 0]))
    exact, control, _ = draw_case(
        development_null_rng, config["development_null_count"], SCENARIOS["coherent"], geometry
    )
    development_null = add_union(score_cases(exact, control), normalizers["white"])
    save_scores(output / "development_null.npz", development_null)
    development_thresholds = calibrated_thresholds(development_null, config["target_false_alarm"])
    development = {}
    for scenario_index, (scenario_name, scenario) in enumerate(SCENARIOS.items()):
        if scenario_name in ("colored_ar", "coherent_tone"):
            continue
        development[scenario_name] = {}
        for snr_index, snr in enumerate(config["snr_db"]):
            rng = np.random.default_rng(np.random.SeedSequence([
                config["seed"], 21, scenario_index, snr_index
            ]))
            exact, control, truth = draw_case(
                rng, config["development_signal_count"], scenario, geometry, snr
            )
            scores = add_union(score_cases(exact, control), normalizers["white"])
            save_scores(output / f"development_{scenario_name}_{snr}.npz", scores)
            np.save(output / f"development_{scenario_name}_{snr}_truth.npy", truth)
            development[scenario_name][str(snr)] = {
                method: summarize_method(values, truth, development_thresholds[method])
                for method, values in scores.items()
            }
        print(f"development {scenario_name}", flush=True)
    recommendation = choose_recommendation(development)
    (output / "frozen_recommendation.json").write_text(json.dumps({
        "protocol_sha256": protocol_hash, "recommendation": recommendation,
        "development_thresholds": development_thresholds, "development": development,
    }, indent=2, sort_keys=True) + "\n")
    print(f"Selected on development: {recommendation['selected']}", flush=True)
    # Final calibration is independent of normalization and all development.
    thresholds = {}
    for index, environment in enumerate(environments):
        rng = np.random.default_rng(np.random.SeedSequence([config["seed"], 30, index]))
        exact, control, _ = draw_case(
            rng, config["calibration_null_count"], {"environment": environment}, geometry
        )
        scores = add_union(score_cases(exact, control), normalizers[environment])
        save_scores(output / f"calibration_{environment}.npz", scores)
        thresholds[environment] = calibrated_thresholds(scores, config["target_false_alarm"])
    (output / "frozen_thresholds.json").write_text(json.dumps({
        "protocol_sha256": protocol_hash, "thresholds": thresholds,
        "recommended_method": recommendation["selected"],
    }, indent=2, sort_keys=True) + "\n")
    assert_sources_unchanged(config["sources"])
    summary = {"config": config, "protocol_sha256": protocol_hash,
               "recommendation": recommendation, "null": {}, "signals": {}}
    descriptive_thresholds = {}
    for index, environment in enumerate(environments):
        rng = np.random.default_rng(np.random.SeedSequence([config["seed"], 40, index]))
        exact, control, _ = draw_case(
            rng, config["heldout_null_count"], {"environment": environment}, geometry
        )
        scores = add_union(score_cases(exact, control), normalizers[environment])
        save_scores(output / f"heldout_null_{environment}.npz", scores)
        descriptive_thresholds[environment] = calibrated_thresholds(
            scores, config["target_false_alarm"]
        )
        summary["null"][environment] = {}
        for method, values in scores.items():
            count = len(values["score"])
            alarms = int(np.count_nonzero(values["score"] > thresholds[environment][method]))
            summary["null"][environment][method] = {
                "threshold": thresholds[environment][method], "false_alarms": alarms,
                "count": count, "rate": alarms / count,
                "wilson_95": prior.wilson_interval(alarms, count),
                "descriptive_heldout_1pct_threshold": descriptive_thresholds[environment][method],
            }
    rows = []
    aggregate_events = {baseline: [] for baseline in BASELINES}
    selected = recommendation["selected"]
    for scenario_index, (scenario_name, scenario) in enumerate(SCENARIOS.items()):
        environment = scenario["environment"]
        summary["signals"][scenario_name] = {}
        for snr_index, snr in enumerate(config["snr_db"]):
            rng = np.random.default_rng(np.random.SeedSequence([
                config["seed"], 41, scenario_index, snr_index
            ]))
            exact, control, truth = draw_case(
                rng, config["heldout_signal_count"], scenario, geometry, snr
            )
            scores = add_union(score_cases(exact, control), normalizers[environment])
            save_scores(output / f"heldout_{scenario_name}_{snr}.npz", scores)
            np.save(output / f"heldout_{scenario_name}_{snr}_truth.npy", truth)
            cell = {"methods": {}, "selected_paired_vs_baselines": {}}
            decisions = {}
            for method, values in scores.items():
                trained = summarize_method(values, truth, thresholds[environment][method])
                descriptive = summarize_method(
                    values, truth, descriptive_thresholds[environment][method]
                )
                cell["methods"][method] = {
                    "trained_threshold": trained,
                    "descriptive_heldout_1pct": descriptive,
                }
                detected, joint, _ = method_events(values, truth, thresholds[environment][method])
                decisions[f"{method}__detected"] = detected
                decisions[f"{method}__joint"] = joint
                row = {"scenario": scenario_name, "environment": environment, "snr_db": snr,
                       "method": method, "count": trained["count"],
                       "detection_rate": trained["detection_rate"],
                       "joint_rate": trained["joint_rate"],
                       "joint_ci_low": trained["joint_wilson_95"][0],
                       "joint_ci_high": trained["joint_wilson_95"][1],
                       "false_alarm_rate": summary["null"][environment][method]["rate"],
                       "descriptive_1pct_detection_rate": descriptive["detection_rate"],
                       "descriptive_1pct_joint_rate": descriptive["joint_rate"],
                       "cfo_unconditional_median_hz": trained["cfo_unconditional"]["median_hz"],
                       "cfo_detected_median_hz": trained["cfo_detection_conditional"]["median_hz"]}
                rows.append(row)
            # These are descriptive oracles, not selectable detector methods.
            segment_joint = [decisions[f"{method}__joint"] for method in SEGMENTS]
            cell["oracle_cell_best_segment_joint_rate"] = float(
                max(x.mean() for x in segment_joint)
            )
            cell["oracle_truth_any_segment_joint_rate"] = float(
                np.logical_or.reduce(segment_joint).mean()
            )
            np.savez_compressed(output / f"decisions_{scenario_name}_{snr}.npz", **decisions)
            if selected is not None:
                for baseline_index, baseline in enumerate(BASELINES):
                    pair_rng = np.random.default_rng(np.random.SeedSequence([
                        config["seed"], 50, baseline_index, scenario_index, snr_index
                    ]))
                    paired = {
                        endpoint: paired_interval(decisions[f"{selected}__{endpoint}"],
                                                  decisions[f"{baseline}__{endpoint}"], pair_rng,
                                                  config["bootstrap_replicates"])
                        for endpoint in ("detected", "joint")
                    }
                    cell["selected_paired_vs_baselines"][baseline] = paired
                    if scenario_name in PRIMARY_PHASE_SCENARIOS:
                        difference = (decisions[f"{selected}__joint"].astype(float)
                                      - decisions[f"{baseline}__joint"].astype(float))
                        aggregate_events[baseline].append(difference)
            summary["signals"][scenario_name][str(snr)] = cell
        print(f"held-out {scenario_name}", flush=True)
    summary["selected_equal_weight_phase_joint_difference"] = {}
    if selected is not None:
        for baseline_index, baseline in enumerate(BASELINES):
            pair_rng = np.random.default_rng(np.random.SeedSequence([
                config["seed"], 51, baseline_index
            ]))
            differences = aggregate_events[baseline]
            bootstrap_means = np.zeros(config["bootstrap_replicates"])
            for difference in differences:
                resampled = difference[pair_rng.integers(
                    0, len(difference), (config["bootstrap_replicates"], len(difference))
                )].mean(axis=1)
                bootstrap_means += resampled / len(differences)
            summary["selected_equal_weight_phase_joint_difference"][baseline] = {
                "difference": float(np.mean([x.mean() for x in differences])),
                "stratified_paired_bootstrap_95": [
                    float(x) for x in np.quantile(bootstrap_means, [0.025, 0.975])
                ],
                "independent_scenario_snr_cells": len(differences),
                "signals_per_cell": config["heldout_signal_count"],
            }
    assert_sources_unchanged(config["sources"])
    summary["source_guard_passed"] = True
    summary["elapsed_seconds"] = time.monotonic() - started
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    with (output / "metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "simulation" / "final")
    parser.add_argument(
        "--quick", action="store_true", help="small preflight; no scientific inference"
    )
    args = parser.parse_args()
    result = run(args.output, args.quick)
    print(f"Finished in {result['elapsed_seconds']:.1f}s", flush=True)
