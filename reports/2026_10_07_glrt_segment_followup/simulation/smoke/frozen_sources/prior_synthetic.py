"""Seeded, bounded conditional pilot-correlator comparison; no RF acquisition."""

# Thread limits must precede NumPy/BLAS imports.
# ruff: noqa: E402

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
from pathlib import Path

for _thread_variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_thread_variable] = "1"

import numpy as np
from methods import fit_whitener, score_individual_bank, score_trials_bank

from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    OFDM_SYMBOL_DURATION_S,
    qin_edge_pilot_frame,
)

CONFIG = {
    "seed": 2026100701,
    "calibration_null_count": 3000,
    "heldout_null_count": 5000,
    "signal_count_per_snr": 600,
    "covariance_training_count": 512,
    "target_false_alarm": 0.01,
    "snr_db": [-18, -15, -12, -9, -6, -3, 0],
    "environments": ["white", "correlated_ar", "coherent_tone", "phase_decoherence"],
    "ar_coefficient": 0.85,
    "tone_frequency_hz": 117187.5,
    "tone_inr_db": 10.0,
    "phase_increment_std_rad": 0.35,
    "covariance_shrinkage": 0.25,
    "symbol_count": 64,
    "frames_per_trial": 14,
    "sample_rate_hz": 20_000_000,
    "symbol_step_s": OFDM_SYMBOL_DURATION_S,
    "fft_size": 512,
    "true_cfo_uniform_hz": [-70_000, 70_000],
    "batch_size": 64,
    "candidate_epoch_count": 1,
    "decision": "score > independently calibrated higher empirical 99th percentile",
    "scope": "conditional fixed correct acquired epoch, complete 512-bin residual CFO search",
    "signal_model": (
        "14 frames, common CFO, independent frame phases, unit-energy symbol pilots; "
        "CFO constant within symbol"
    ),
    "noise_model": "joint exact/control Gaussian using actual Qin normalized template Gram",
    "seed_derivation": {
        "white_covariance": "SeedSequence([seed,0,0])",
        "environment_covariance": "SeedSequence([seed,environment_index+1,1])",
        "calibration_null": "SeedSequence([seed,environment_index+1,2])",
        "heldout_null": "SeedSequence([seed,environment_index+1,3])",
        "heldout_signal": "SeedSequence([seed,environment_index+1,4,snr_index])",
    },
}


def complex_normal(rng: np.random.Generator, shape: tuple[int, ...]) -> np.ndarray:
    return (rng.standard_normal(shape) + 1j * rng.standard_normal(shape)) / np.sqrt(2)


def pilot_geometry() -> dict[str, np.ndarray]:
    """Actual template projections: control shares the exact symbol's received IQ."""
    rate = CONFIG["sample_rate_hz"]
    exact_frame = qin_edge_pilot_frame(rate, "upper")
    control_frame = qin_edge_pilot_frame(rate, "upper", symbol_roll=CONTROL_SYMBOL_ROLL)
    step = round(rate * OFDM_SYMBOL_DURATION_S)
    starts = np.arange(2, 66) * step
    indexes = starts[:, None] + np.arange(step)[None, :]
    exact = exact_frame[indexes].astype(np.complex128)
    control = control_frame[indexes].astype(np.complex128)
    raw_exact_energy = np.sum(np.abs(exact) ** 2, axis=1)
    raw_control_energy = np.sum(np.abs(control) ** 2, axis=1)
    exact /= np.linalg.norm(exact, axis=1)[:, None]
    control /= np.linalg.norm(control, axis=1)[:, None]
    overlap = np.sum(np.conj(control) * exact, axis=1)
    tone = np.exp(2j * np.pi * CONFIG["tone_frequency_hz"] * indexes / rate)
    exact_tone = np.sum(np.conj(exact) * tone, axis=1)
    control_tone = np.sum(np.conj(control) * tone, axis=1)
    scale = np.sqrt(np.mean(np.abs(exact_tone) ** 2))
    return {
        "exact": exact,
        "control": control,
        "overlap": overlap,
        "exact_tone": exact_tone / scale,
        "control_tone": control_tone / scale,
        "raw_exact_energy": raw_exact_energy,
        "raw_control_energy": raw_control_energy,
    }


def draw_observations(
    rng: np.random.Generator,
    count: int,
    environment: str,
    geometry: dict[str, np.ndarray],
    snr_db: float | None = None,
    frames: int = 1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """Construct sufficient correlations from shared underlying two-direction IQ noise.

    Colored stress imposes AR correlation on each orthogonal IQ direction across
    symbols. It is a correlator-domain covariance stress, not a measured RF PSD.
    White stress exactly matches iid complex Gaussian IQ projected on both pilots.
    """
    if environment not in CONFIG["environments"]:
        raise ValueError(f"unknown environment: {environment}")
    row_count = count * frames
    exact_noise = complex_normal(rng, (row_count, 64))
    orthogonal_noise = complex_normal(rng, (row_count, 64))
    if environment == "correlated_ar":
        rho = CONFIG["ar_coefficient"]
        innovation_scale = np.sqrt(1 - rho**2)
        for symbol in range(1, 64):
            exact_noise[:, symbol] = (
                rho * exact_noise[:, symbol - 1] + innovation_scale * exact_noise[:, symbol]
            )
            orthogonal_noise[:, symbol] = (
                rho * orthogonal_noise[:, symbol - 1]
                + innovation_scale * orthogonal_noise[:, symbol]
            )
    overlap = geometry["overlap"]
    exact = exact_noise
    control = overlap * exact_noise + np.sqrt(1 - np.abs(overlap) ** 2) * orthogonal_noise
    if environment == "coherent_tone":
        # One physical coherent tone per trial. Frame phases track its frequency;
        # pooled spectra discard these phases, but covariance training does not
        # falsely create independent tone amplitudes inside one observation.
        phase_angle = np.repeat(rng.uniform(-np.pi, np.pi, count), frames)
        phase_angle += (
            np.tile(np.arange(frames), count) * 2 * np.pi * CONFIG["tone_frequency_hz"] / 750
        )
        phase = np.exp(1j * phase_angle)[:, None]
        amplitude = 10 ** (CONFIG["tone_inr_db"] / 20)
        exact = exact + amplitude * phase * geometry["exact_tone"]
        control = control + amplitude * phase * geometry["control_tone"]
    if snr_db is None:
        if frames == 1:
            return exact, control, None
        return exact.reshape(count, frames, 64), control.reshape(count, frames, 64), None
    cfo = rng.uniform(*CONFIG["true_cfo_uniform_hz"], count)
    phase = rng.uniform(-np.pi, np.pi, row_count)[:, None]
    phase = phase + (
        2 * np.pi * np.repeat(cfo, frames)[:, None] * np.arange(64) * OFDM_SYMBOL_DURATION_S
    )
    if environment == "phase_decoherence":
        increments = rng.normal(0, CONFIG["phase_increment_std_rad"], (row_count, 63))
        phase[:, 1:] += np.cumsum(increments, axis=1)
    signal = 10 ** (snr_db / 20) * np.exp(1j * phase)
    exact, control = exact + signal, control + overlap * signal
    if frames == 1:
        return exact, control, cfo
    return exact.reshape(count, frames, 64), control.reshape(count, frames, 64), cfo


def wilson_interval(successes: int, count: int) -> list[float]:
    """Two-sided 95% Wilson binomial interval."""
    z = 1.959963984540054
    proportion = successes / count
    denominator = 1 + z**2 / count
    center = (proportion + z**2 / (2 * count)) / denominator
    half = z * np.sqrt(proportion * (1 - proportion) / count + z**2 / (4 * count**2))
    half /= denominator
    return [float(max(0, center - half)), float(min(1, center + half))]


def cfo_error(estimate: np.ndarray, truth: np.ndarray) -> np.ndarray:
    period = 1 / OFDM_SYMBOL_DURATION_S
    return np.abs((estimate - truth + period / 2) % period - period / 2)


def summarize_cfo(errors: np.ndarray) -> dict[str, float | int | None]:
    if not errors.size:
        return {"count": 0, "median_hz": None, "p90_hz": None, "rmse_hz": None}
    return {
        "count": int(errors.size),
        "median_hz": float(np.median(errors)),
        "p90_hz": float(np.quantile(errors, 0.9)),
        "rmse_hz": float(np.sqrt(np.mean(errors**2))),
    }


def score_cases(exact, control, whitener, white_whitener):
    batches = []
    scorer = score_individual_bank if exact.ndim == 2 else score_trials_bank
    for start in range(0, len(exact), CONFIG["batch_size"]):
        stop = start + CONFIG["batch_size"]
        result = scorer(exact[start:stop], control[start:stop], whitener=whitener)
        # The control covariance differs under color/tone. A common exact-trained
        # covariance is sufficient for the natural exact statistic, not this margin.
        result.pop("adaptive_nmf64_margin", None)
        white_result = scorer(
            exact[start:stop], control[start:stop], whitener=white_whitener
        )
        result["adaptive_nmf64_white_training"] = white_result["adaptive_nmf64"]
        batches.append(result)
    return {
        method: {key: np.concatenate([batch[method][key] for batch in batches])
                 for key in values}
        for method, values in batches[0].items()
    }


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output: Path, *, quick: bool = False) -> dict:
    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)
    config = dict(CONFIG)
    if quick:
        config.update(calibration_null_count=200, heldout_null_count=200,
                      signal_count_per_snr=40, covariance_training_count=128)
    geometry = pilot_geometry()
    config["template_overlap_abs_mean"] = float(np.mean(np.abs(geometry["overlap"])))
    config["template_overlap_abs_max"] = float(np.max(np.abs(geometry["overlap"])))
    config["raw_exact_template_energy_max_min_ratio"] = float(
        np.max(geometry["raw_exact_energy"]) / np.min(geometry["raw_exact_energy"])
    )
    config["raw_control_template_energy_max_min_ratio"] = float(
        np.max(geometry["raw_control_energy"]) / np.min(geometry["raw_control_energy"])
    )
    config["synthetic_source_sha256"] = file_hash(Path(__file__))
    config["methods_source_sha256"] = file_hash(Path(__file__).with_name("methods.py"))
    config["numpy_version"] = np.__version__
    config["quick_smoke_only"] = quick
    # Persist the design before covariance/threshold training and held-out generation.
    protocol = json.dumps(config, indent=2, sort_keys=True) + "\n"
    (output / "frozen_protocol.json").write_text(protocol)
    protocol_hash = hashlib.sha256(protocol.encode()).hexdigest()
    white_rng = np.random.default_rng(np.random.SeedSequence([config["seed"], 0, 0]))
    white_training = draw_observations(
        white_rng, config["covariance_training_count"], "white", geometry
    )[0]
    white_whitener = fit_whitener(white_training, shrinkage=config["covariance_shrinkage"])
    thresholds, whiteners = {}, {}
    training_artifacts = {"white_training": white_training}
    calibration_artifacts = {}
    # No held-out RNG is used anywhere in this calibration stage.
    for environment_index, environment in enumerate(config["environments"]):
        train_rng = np.random.default_rng(
            np.random.SeedSequence([config["seed"], environment_index + 1, 1])
        )
        train = draw_observations(
            train_rng, config["covariance_training_count"], environment, geometry
        )[0]
        whitener = fit_whitener(train, shrinkage=config["covariance_shrinkage"])
        whiteners[environment] = whitener
        training_artifacts[f"{environment}__training"] = train
        calibration_rng = np.random.default_rng(
            np.random.SeedSequence([config["seed"], environment_index + 1, 2])
        )
        exact, control, _ = draw_observations(
            calibration_rng, config["calibration_null_count"], environment, geometry,
            frames=config["frames_per_trial"],
        )
        scores = score_cases(exact, control, whitener, white_whitener)
        for method, values in scores.items():
            calibration_artifacts[f"{environment}__{method}"] = values["score"]
        thresholds[environment] = {
            method: float(np.quantile(values["score"], 1 - config["target_false_alarm"],
                                      method="higher"))
            for method, values in scores.items()
        }
        print(f"calibrated {environment}", flush=True)
    # Thresholds and training are frozen before any held-out sample is generated.
    (output / "frozen_thresholds.json").write_text(json.dumps({
        "protocol_sha256": protocol_hash, "thresholds": thresholds,
    }, indent=2, sort_keys=True) + "\n")
    np.savez_compressed(output / "covariance_training.npz", **training_artifacts)
    np.savez_compressed(output / "calibration_null_scores.npz", **calibration_artifacts)
    summary = {"protocol_sha256": protocol_hash, "config": config, "environments": {}}
    csv_rows = []
    null_score_artifacts = {}
    signal_score_artifacts = {}
    for environment_index, environment in enumerate(config["environments"]):
        heldout_rng = np.random.default_rng(
            np.random.SeedSequence([config["seed"], environment_index + 1, 3])
        )
        exact, control, _ = draw_observations(
            heldout_rng, config["heldout_null_count"], environment, geometry,
            frames=config["frames_per_trial"],
        )
        scored_null = score_cases(exact, control, whiteners[environment], white_whitener)
        environment_summary = {"null": {}, "signals": {}}
        for method, values in scored_null.items():
            threshold = thresholds[environment][method]
            count = config["heldout_null_count"]
            false_alarms = int(np.count_nonzero(values["score"] > threshold))
            interval = wilson_interval(false_alarms, count)
            environment_summary["null"][method] = {
                "threshold": threshold, "false_alarms": false_alarms, "count": count,
                "rate": false_alarms / count, "wilson_95": interval,
            }
            null_score_artifacts[f"{environment}__{method}"] = values["score"]
            csv_rows.append({"environment": environment, "method": method, "snr_db": "H0",
                             "count": count, "detected": false_alarms,
                             "rate": false_alarms / count, "ci_low": interval[0],
                             "ci_high": interval[1]})
        for snr_index, snr in enumerate(config["snr_db"]):
            signal_rng = np.random.default_rng(
                np.random.SeedSequence([config["seed"], environment_index + 1, 4, snr_index])
            )
            exact, control, truth = draw_observations(
                signal_rng, config["signal_count_per_snr"], environment, geometry, snr,
                frames=config["frames_per_trial"],
            )
            scored_signal = score_cases(exact, control, whiteners[environment], white_whitener)
            artifact_prefix = f"{environment}__snr_{snr}"
            signal_score_artifacts[f"{artifact_prefix}__truth_cfo_hz"] = truth
            signal_summary = {}
            for method, values in scored_signal.items():
                for key, array in values.items():
                    signal_score_artifacts[f"{artifact_prefix}__{method}__{key}"] = array
                detected = values["score"] > thresholds[environment][method]
                errors = cfo_error(values["cfo_hz"], truth)
                successes = int(np.count_nonzero(detected))
                count = len(detected)
                interval = wilson_interval(successes, count)
                unconditional = summarize_cfo(errors)
                conditional = summarize_cfo(errors[detected])
                correct_detections = detected & (errors <= 1000)
                correct_detection_rate = float(np.mean(correct_detections))
                signal_summary[method] = {
                    "detected": successes, "count": count, "rate": successes / count,
                    "wilson_95": interval, "cfo_unconditional": unconditional,
                    "cfo_detection_conditional": conditional,
                    "detected_and_cfo_within_1khz": int(np.count_nonzero(correct_detections)),
                    "detected_and_cfo_within_1khz_rate": correct_detection_rate,
                }
                csv_rows.append({
                    "environment": environment, "method": method, "snr_db": snr,
                    "count": count, "detected": successes, "rate": successes / count,
                    "ci_low": interval[0], "ci_high": interval[1],
                    "cfo_all_median_hz": unconditional["median_hz"],
                    "cfo_all_p90_hz": unconditional["p90_hz"],
                    "cfo_detected_median_hz": conditional["median_hz"],
                    "cfo_detected_p90_hz": conditional["p90_hz"],
                    "detected_and_cfo_within_1khz_rate": correct_detection_rate,
                })
            environment_summary["signals"][str(snr)] = signal_summary
        summary["environments"][environment] = environment_summary
        print(f"completed held-out {environment}", flush=True)
    summary["elapsed_seconds"] = time.monotonic() - started
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    np.savez_compressed(output / "heldout_null_scores.npz", **null_score_artifacts)
    np.savez_compressed(output / "heldout_signal_scores.npz", **signal_score_artifacts)
    fields = list(dict.fromkeys(key for row in csv_rows for key in row))
    with (output / "metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(csv_rows)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).with_name("synthetic") / "pooled14"
    )
    parser.add_argument("--quick", action="store_true", help="small smoke run, not report evidence")
    args = parser.parse_args()
    result = run(args.output, quick=args.quick)
    print(f"Finished in {result['elapsed_seconds']:.1f}s", flush=True)
