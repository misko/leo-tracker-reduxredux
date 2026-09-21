#!/usr/bin/env python3
"""Replay matched-pilot DD on the frozen 28d cohort and profile its rate."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.contracts.digests import canonical_json_bytes, sha256_digest  # noqa: E402

BOOTSTRAP_REPLICATES = 2_000
MINIMUM_QUALIFIED_BLOCKS = 2


def _load_sibling(filename: str, name: str) -> Any:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _phasor(row: dict[str, Any], prefix: str = "corrected_phasor") -> complex:
    return complex(row[f"{prefix}_real"], row[f"{prefix}_imag"])


def _moving_block_errors(contiguous_runs: list[np.ndarray], *, seed: int) -> np.ndarray:
    nominal = float(np.angle(sum(np.sum(run) for run in contiguous_runs)))
    rng = np.random.default_rng(seed)
    errors = np.empty(BOOTSTRAP_REPLICATES)
    for replicate in range(BOOTSTRAP_REPLICATES):
        total = 0j
        for run in contiguous_runs:
            if len(run) == 1:
                total += run[0]
                continue
            pair_count = math.ceil(len(run) / 2)
            starts = rng.integers(0, len(run) - 1, size=pair_count)
            resampled = np.concatenate([run[start : start + 2] for start in starts])[: len(run)]
            total += np.sum(resampled)
        errors[replicate] = float(np.angle(np.exp(1j * (np.angle(total) - nominal))))
    return errors


def _aggregate_visit(
    row: dict[str, Any], sample_rate_hz: float
) -> tuple[dict[str, Any], np.ndarray] | None:
    qualified_blocks = []
    contiguous_runs = []
    for block in row["blocks"]:
        if block["state"] != "qualified":
            continue
        frames = [frame for frame in block["frames"] if frame["qualified"]]
        if len(frames) < 6:
            raise ValueError("qualified block violates frozen six-frame gate")
        qualified_blocks.append(frames)
        current = []
        for frame in block["frames"]:
            if frame["qualified"]:
                current.append(frame)
            elif current:
                contiguous_runs.append(current)
                current = []
        if current:
            contiguous_runs.append(current)
    if len(qualified_blocks) < MINIMUM_QUALIFIED_BLOCKS:
        return None
    frames = sorted(
        (frame for block in qualified_blocks for frame in block),
        key=lambda frame: frame["exact_time_s"],
    )
    phasors = np.asarray([_phasor(frame) for frame in frames])
    weights = abs(phasors)
    exact_time = float(np.average([frame["exact_time_s"] for frame in frames], weights=weights))
    bootstrap_errors = _moving_block_errors(
        [np.asarray([_phasor(frame) for frame in run]) for run in contiguous_runs],
        seed=20260921 + row["visit_index"],
    )

    half_frames = [
        frame
        for frame in frames
        if all(part["qualified"] for part in frame["contiguous_sample_halves"])
    ]
    half_summaries = []
    for half in (0, 1):
        if not half_frames:
            break
        half_values = np.asarray(
            [
                complex(
                    frame["contiguous_sample_halves"][half]["corrected_phasor_real"],
                    frame["contiguous_sample_halves"][half]["corrected_phasor_imag"],
                )
                for frame in half_frames
            ]
        )
        half_times = np.asarray(
            [
                frame["exact_time_s"]
                + (-1 if half == 0 else 1)
                * (frame["sample_end"] - frame["sample_start"])
                / (4 * sample_rate_hz)
                for frame in half_frames
            ]
        )
        half_summaries.append(
            {
                "phase_deg": math.degrees(float(np.angle(np.sum(half_values)))),
                "exact_time_s": float(np.average(half_times, weights=abs(half_values))),
                "frame_count": len(half_values),
            }
        )

    sample_parity = []
    for parity in (0, 1):
        values = np.asarray(
            [complex(*frame["sample_parity_crossfit_phasors"][parity]) for frame in frames]
        )
        sample_parity.append(
            {
                "phase_deg": math.degrees(float(np.angle(np.sum(values)))),
                "exact_time_s": float(
                    np.average([frame["exact_time_s"] for frame in frames], weights=abs(values))
                ),
            }
        )

    frame_parity = []
    for parity in (0, 1):
        selected = frames[parity::2]
        values = np.asarray([_phasor(frame) for frame in selected])
        frame_parity.append(
            {
                "phase_deg": math.degrees(float(np.angle(np.sum(values)))),
                "exact_time_s": float(
                    np.average([frame["exact_time_s"] for frame in selected], weights=abs(values))
                ),
            }
        )

    return (
        {
            "visit_index": row["visit_index"],
            "state": "accepted_matched_pilot_double_difference",
            "centers_hz": row["source_tracking_frequencies_hz"],
            "source_separation_hz": (
                row["source_tracking_frequencies_hz"][1] - row["source_tracking_frequencies_hz"][0]
            ),
            "receiver_offset_hz": row["receiver_offset_authority_hz"],
            "exact_time_s": exact_time,
            "qualified_20ms_block_count": len(qualified_blocks),
            "qualified_frame_count": len(frames),
            "effective_weighted_frame_count": float(np.sum(weights) ** 2 / np.sum(weights**2)),
            "wrapped_high_minus_low_deg": math.degrees(float(np.angle(np.sum(phasors)))),
            "resultant": float(abs(np.sum(phasors)) / np.sum(abs(phasors))),
            "conditional_adjacent_pair_standard_error_deg": math.degrees(
                float(np.std(bootstrap_errors))
            ),
            "conditional_adjacent_pair_95_error_interval_deg": [
                math.degrees(float(value))
                for value in np.quantile(bootstrap_errors, (0.025, 0.975))
            ],
            "contiguous_sample_halves": half_summaries,
            "sample_parities": sample_parity,
            "frame_parities": frame_parity,
        },
        bootstrap_errors,
    )


def _profiles(
    profile_tool: Any,
    rows: list[dict[str, Any]],
    bootstrap_errors: dict[int, np.ndarray],
) -> dict[str, Any]:
    times = np.asarray([row["exact_time_s"] for row in rows])
    phases = np.asarray([row["wrapped_high_minus_low_deg"] for row in rows])
    sigmas = np.asarray([row["conditional_adjacent_pair_standard_error_deg"] for row in rows])

    def profile(component: str | None = None, index: int = 0) -> dict[str, Any]:
        if component is None:
            component_times = times
            component_phases = phases
            component_sigmas = sigmas
        else:
            retained = [row for row in rows if len(row[component]) > index]
            if len(retained) < 4:
                return {"state": "unavailable_insufficient_subset_support"}
            component_times = np.asarray(
                [row[component][index]["exact_time_s"] for row in retained]
            )
            component_phases = np.asarray([row[component][index]["phase_deg"] for row in retained])
            component_sigmas = np.asarray(
                [row["conditional_adjacent_pair_standard_error_deg"] for row in retained]
            )
        return profile_tool.circular_profile(component_times, component_phases, component_sigmas)

    full = profile()

    def residuals(profile_result: dict[str, Any], values: np.ndarray) -> np.ndarray:
        prediction = profile_result["best_intercept_deg"] + profile_result["best_slope_deg_s"] * (
            times - profile_result["reference_time_s"]
        )
        return np.degrees(np.angle(np.exp(1j * np.radians(values - prediction))))

    observed_residuals = residuals(full, phases)
    observed_rms = float(np.sqrt(np.mean(observed_residuals**2)))
    rng = np.random.default_rng(20260921)
    slopes = np.empty(BOOTSTRAP_REPLICATES)
    null_residual_rms = np.empty(BOOTSTRAP_REPLICATES)
    for replicate in range(BOOTSTRAP_REPLICATES):
        sampled_errors = np.asarray(
            [
                math.degrees(
                    float(
                        bootstrap_errors[row["visit_index"]][rng.integers(0, BOOTSTRAP_REPLICATES)]
                    )
                )
                for row in rows
            ]
        )
        perturbed = phases + sampled_errors
        slopes[replicate] = profile_tool.circular_profile(times, perturbed, sigmas)[
            "best_slope_deg_s"
        ]
        null_values = (
            full["best_intercept_deg"]
            + full["best_slope_deg_s"] * (times - full["reference_time_s"])
            + sampled_errors
        )
        null_profile = profile_tool.circular_profile(times, null_values, sigmas)
        null_residual_rms[replicate] = float(
            np.sqrt(np.mean(residuals(null_profile, null_values) ** 2))
        )
    modes = np.asarray([item["slope_deg_s"] for item in full["competing_local_maxima"]])
    nearest = np.argmin(abs(slopes[:, None] - modes[None, :]), axis=1)
    return {
        "state": "measured_conditional_circular_profile",
        "phase_model": "wrapped_full_circle_intercept_plus_linear_rate",
        "full": full,
        "first_contiguous_half": profile("contiguous_sample_halves", 0),
        "second_contiguous_half": profile("contiguous_sample_halves", 1),
        "sample_parity_0": profile("sample_parities", 0),
        "sample_parity_1": profile("sample_parities", 1),
        "frame_parity_0": profile("frame_parities", 0),
        "frame_parity_1": profile("frame_parities", 1),
        "bootstrap_global_best_slope_quantiles_deg_s": [
            float(value) for value in np.quantile(slopes, (0.025, 0.5, 0.975))
        ],
        "linear_model_residuals_deg": list(map(float, observed_residuals)),
        "linear_model_residual_rms_deg": observed_rms,
        "linear_model_residual_max_abs_deg": float(np.max(abs(observed_residuals))),
        "conditional_within_visit_null_residual_rms_quantiles_deg": [
            float(value) for value in np.quantile(null_residual_rms, (0.025, 0.5, 0.975))
        ],
        "conditional_within_visit_null_fraction_at_least_observed": float(
            np.mean(null_residual_rms >= observed_rms)
        ),
        "linear_model_adequate_under_within_visit_bootstrap": bool(
            np.mean(null_residual_rms >= observed_rms) >= 0.05
        ),
        "bootstrap_profile_mode_basin_fractions": [
            {
                "profile_mode_slope_deg_s": float(modes[index]),
                "bootstrap_fraction": float(np.mean(nearest == index)),
            }
            for index in range(len(modes))
        ],
        "detection_claimed": False,
        "detection_rule": (
            "no linear-rate detection unless the model passes lack-of-fit, the global "
            "mode dominates bootstrap aliases, and independent subsets agree"
        ),
    }


def run(
    bulk_root: Path,
    overlap_evidence_path: Path,
    raw_evidence_path: Path,
    dense_summary_path: Path,
) -> dict[str, Any]:
    matched = _load_sibling("report_adaptive_dual_rx_matched_pilot_dd.py", "_matched_pilot_dd")
    profile_tool = _load_sibling(
        "report_adaptive_dual_rx_simultaneous_dd_cohort.py", "_simultaneous_dd_cohort"
    )
    raw = json.loads(raw_evidence_path.read_text(encoding="utf-8"))
    frozen_overlap = json.loads(overlap_evidence_path.read_text(encoding="utf-8"))
    dense = json.loads(dense_summary_path.read_text(encoding="utf-8"))
    eligible = tuple(
        int(row["visit_index"]) for row in raw["visits"] if int(row["phase_blind_pair_count"]) == 2
    )
    fixed_path = [int(row["visit_index"]) for row in dense["tracks"][0]["states"]]
    replay = matched.run(
        bulk_root,
        overlap_evidence_path,
        raw_evidence_path,
        visit_indexes=eligible,
        include_timing=True,
        derive_missing_overlap=True,
    )
    aggregated = []
    errors = {}
    for row in replay["rows"]:
        result = _aggregate_visit(row, replay["sample_rate_hz"])
        if result is None:
            aggregated.append(
                {
                    "visit_index": row["visit_index"],
                    "state": "insufficient_matched_pilot_overlap",
                }
            )
        else:
            summary, bootstrap = result
            aggregated.append(summary)
            errors[row["visit_index"]] = bootstrap
    for row in raw["visits"]:
        if int(row["phase_blind_pair_count"]) != 2:
            aggregated.append(
                {
                    "visit_index": int(row["visit_index"]),
                    "state": "unmatched_not_two_sources",
                }
            )
    aggregated.sort(key=lambda row: row["visit_index"])
    accepted_by_visit = {
        row["visit_index"]: row
        for row in aggregated
        if row["state"] == "accepted_matched_pilot_double_difference"
    }
    accepted_path = [index for index in fixed_path if index in accepted_by_visit]
    path_rows = [accepted_by_visit[index] for index in accepted_path]
    rf_by_visit = {}
    for row in replay["rows"]:
        centers = row["source_tracking_frequencies_hz"]
        rf_by_visit[row["visit_index"]] = {
            "centers_hz": centers,
            "source_separation_hz": centers[1] - centers[0],
            "receiver_offset_hz": row["receiver_offset_authority_hz"],
            "exact_time_s": row["valid_visit_origin_s"] + 0.060,
        }
    association = profile_tool._association_audit(rf_by_visit, fixed_path)
    if not association["all_transitions_pass_corrected_rf_and_time_gates"]:
        trend = {"state": "unavailable_fixed_rf_path_failed_corrected_audit"}
    elif len(path_rows) < 4:
        trend = {"state": "unavailable_insufficient_fixed_path_support"}
    else:
        trend = _profiles(profile_tool, path_rows, errors)
    trend["accepted_path_visit_indexes"] = accepted_path
    body = {
        "schema_version": 1,
        "kind": "adaptive_dual_rx_matched_pilot_double_difference_cohort_research",
        "session_id": raw["session_id"],
        "input_manifest_sha256": replay["input_manifest_sha256"],
        "raw_authority_evidence_sha256": raw["evidence_sha256"],
        "source_overlap_evidence_sha256": replay["source_overlap_evidence_sha256"],
        "frozen_overlap_visit_indexes": [
            int(row["visit_index"]) for row in frozen_overlap["visits"]
        ],
        "saved_iq_derived_overlap_visit_indexes": [
            index
            for index in eligible
            if index not in {int(row["visit_index"]) for row in frozen_overlap["visits"]}
        ],
        "saved_iq_overlap_derivation_uses_phase": False,
        "dense_phase_blind_association_sha256": sha256_digest(canonical_json_bytes(dense)),
        "selection_uses_phase": False,
        "catalog_identity_claimed": False,
        "minimum_qualified_20ms_blocks": MINIMUM_QUALIFIED_BLOCKS,
        "eligible_visit_indexes": list(eligible),
        "fixed_phase_blind_path_visit_indexes": fixed_path,
        "association_audit": association,
        "rows": aggregated,
        "trend": trend,
        "per_frame_replay": replay,
    }
    body["evidence_sha256"] = sha256_digest(canonical_json_bytes(body))
    return body


def render(document: dict[str, Any], path: Path) -> None:
    accepted = [
        row
        for row in document["rows"]
        if row["state"] == "accepted_matched_pilot_double_difference"
    ]
    fixed = set(document["fixed_phase_blind_path_visit_indexes"])
    figure, axes = plt.subplots(2, 1, figsize=(11, 9), layout="constrained")
    for on_path, marker, label in (
        (True, "o", "fixed phase-blind RF path"),
        (False, "x", "eligible outside fixed path"),
    ):
        rows = [row for row in accepted if (row["visit_index"] in fixed) is on_path]
        if rows:
            axes[0].errorbar(
                [row["exact_time_s"] for row in rows],
                [row["wrapped_high_minus_low_deg"] for row in rows],
                yerr=[row["conditional_adjacent_pair_standard_error_deg"] for row in rows],
                fmt=marker,
                capsize=3,
                label=label,
            )
    axes[0].set_ylabel("matched-pilot high-minus-low DD (deg)\nwrapped 360 degrees")
    axes[0].set_xlabel("session time since capture origin (s)")
    axes[0].grid(alpha=0.25)
    axes[0].legend()
    state_level = {
        "accepted_matched_pilot_double_difference": 0,
        "insufficient_matched_pilot_overlap": 1,
        "unmatched_not_two_sources": 2,
    }
    colors = {0: "#2ca02c", 1: "#ff7f0e", 2: "#d62728"}
    for row in document["rows"]:
        level = state_level[row["state"]]
        axes[1].scatter(row["visit_index"], level, color=colors[level])
    axes[1].set_yticks([0, 1, 2], ["accepted", "insufficient overlap", "not two sources"])
    axes[1].set_xlabel("visit index")
    axes[1].grid(axis="x", alpha=0.25)
    figure.suptitle("28d frozen cohort matched-pilot simultaneous DD")
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--overlap-evidence", type=Path, required=True)
    parser.add_argument("--raw-evidence", type=Path, required=True)
    parser.add_argument("--dense-summary", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    args = parser.parse_args()
    document = run(
        args.bulk_root,
        args.overlap_evidence,
        args.raw_evidence,
        args.dense_summary,
    )
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    render(document, args.png)
    print(json.dumps({"evidence_sha256": document["evidence_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
