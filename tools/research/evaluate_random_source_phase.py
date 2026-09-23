"""Evaluate train-even frequency models on held-odd source-seeded phase.

This bounded research tool compares constant-CFO and linear-CFO descriptions
of one frozen GLRT source hypothesis.  Model fitting and phase-bias profiling
use even pilot folds in random training 20 ms groups.  Odd folds in held groups
are responses only: they do not select frames, branches, gates, or models.
The result is a local source-tracking check, not orbit or satellite identity.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

from leo.analysis.research.candidate_phase_validation import (
    CandidatePhaseEvidence,
    score_candidate_integrated_phase,
)

DEFAULT_INPUT = Path("reports/figures/2026_09_23_source_phase_random/frames.json.gz")
TRAINING_GROUPS = (0, 3, 5)
SEED = 20260923


def _complex_vector(values) -> np.ndarray:
    vector = np.asarray([complex(real, imag) for real, imag in values], dtype=complex)
    norm = float(np.linalg.norm(vector))
    if vector.shape != (8,) or not np.all(np.isfinite(vector)) or norm <= 0:
        raise ValueError("pilot channel vector must contain eight finite nonzero tones")
    return vector / norm


def _wrap_pi(value):
    return (np.asarray(value) + np.pi / 2) % np.pi - np.pi / 2


def _frequency_models(rows: list[dict], rate: float) -> tuple[np.ndarray, np.ndarray, float]:
    selected = [
        row
        for row in rows
        if row["group_id"] in TRAINING_GROUPS and row["frame"]["training_supported"]
    ]
    if len(selected) < 4:
        raise ValueError("fewer than four training-even supported frames")
    time_s = np.asarray([row["frame"]["reference_sample"] / rate for row in selected])
    frequency_hz = np.asarray([row["frame"]["even"]["absolute_cfo_hz"] for row in selected])
    reference_s = float(np.mean(time_s))
    centered = time_s - reference_s
    linear = np.linalg.lstsq(
        np.column_stack([np.ones(len(centered)), centered]), frequency_hz, rcond=None
    )[0]
    constant = np.asarray([float(np.mean(frequency_hz)), 0.0])
    return constant, linear, reference_s


def _pairs(
    rows: list[dict], fold: str, selected_groups: tuple[int, ...], rate: float
) -> list[dict]:
    output = []
    for group in selected_groups:
        # Eligibility depends only on the even-fold training support, including
        # in held groups. Odd response values never influence this inventory.
        opportunities = sorted(
            (row for row in rows if row["group_id"] == group),
            key=lambda row: row["frame"]["reference_sample"],
        )
        for index in range(0, len(opportunities) - 1, 2):
            left, right = opportunities[index : index + 2]
            left_frame, right_frame = left["frame"], right["frame"]
            if not (left_frame["training_supported"] and right_frame["training_supported"]):
                continue
            left_sample = float(left_frame["reference_sample"])
            right_sample = float(right_frame["reference_sample"])
            if right_sample <= left_sample:
                raise ValueError("frame references are not increasing")
            if right_sample - left_sample > 1.5 * rate / 750:
                raise ValueError("adjacent frame pair crosses a frame opportunity gap")
            left_vector = _complex_vector(left_frame[fold]["channel_vector"])
            right_vector = _complex_vector(right_frame[fold]["channel_vector"])
            inner = complex(np.vdot(left_vector, right_vector))
            output.append(
                {
                    "group_id": group,
                    "left_frame_start_sample": int(left_frame["frame_start_sample"]),
                    "right_frame_start_sample": int(right_frame["frame_start_sample"]),
                    "left_reference_sample": left_sample,
                    "right_reference_sample": right_sample,
                    "phase_advance_rad": float(_wrap_pi(np.angle(inner))),
                    "channel_similarity": float(abs(inner)),
                }
            )
    return output


def _integrated_phase(pair: dict, coefficients: np.ndarray, reference_s: float, rate: float):
    left = pair["left_reference_sample"] / rate - reference_s
    right = pair["right_reference_sample"] / rate - reference_s
    intercept, slope = coefficients
    return float(2 * np.pi * (intercept * (right - left) + 0.5 * slope * (right**2 - left**2)))


def _circular_metrics(values: np.ndarray) -> dict[str, float]:
    return {
        "rms_rad": float(np.sqrt(np.mean(np.square(values)))),
        "resultant": float(abs(np.mean(np.exp(2j * values)))),
    }


def _odd_summary(held: list[dict]) -> dict:
    exact = np.asarray([row["frame"]["odd"]["exact_coherence"] for row in held])
    control = np.asarray([row["frame"]["odd"]["control_coherence"] for row in held])
    return {
        "frame_count": len(held),
        "median_odd_exact_coherence": float(np.median(exact)),
        "median_odd_control_coherence": float(np.median(control)),
        "median_odd_exact_minus_control": float(np.median(exact - control)),
        "held_odd_used_for_conditioning": False,
    }


def _held_odd_evidence(rows: list[dict], held_groups: tuple[int, ...]) -> dict:
    all_held = [row for row in rows if row["group_id"] in held_groups]
    conditioned = [row for row in all_held if row["frame"]["training_supported"]]
    return {
        "all_held_opportunities": _odd_summary(all_held),
        "even_conditioned_subset": _odd_summary(conditioned),
    }


def _branch_evidence(rows: list[dict], held_groups: tuple[int, ...]) -> dict:
    return {
        "total_frame_count": len(rows),
        "training_even_supported_frame_count": sum(
            row["frame"]["training_supported"] and row["group_id"] in TRAINING_GROUPS
            for row in rows
        ),
        "held_odd_exact_control": _held_odd_evidence(rows, held_groups),
    }


def _evaluate_receiver(rows: list[dict], rate: float, receiver_id: int) -> dict:
    receiver = [row for row in rows if row["receiver_id"] == receiver_id]
    observed_groups = tuple(sorted({int(row["group_id"]) for row in receiver}))
    held_groups = tuple(group for group in observed_groups if group not in TRAINING_GROUPS)
    constant, linear, reference_s = _frequency_models(receiver, rate)
    training_pairs = _pairs(receiver, "even", TRAINING_GROUPS, rate)
    held_pairs = _pairs(receiver, "odd", held_groups, rate)
    if min(len(training_pairs), len(held_pairs)) < 4:
        raise ValueError("insufficient disjoint adjacent frame pairs")
    combined = training_pairs + held_pairs
    measured = np.asarray([pair["phase_advance_rad"] for pair in combined])
    durations = np.asarray(
        [
            (pair["right_reference_sample"] - pair["left_reference_sample"]) / rate
            for pair in combined
        ]
    )
    groups = np.asarray([pair["group_id"] for pair in combined])
    endpoints = np.asarray(
        [
            (
                f"{receiver_id}:{pair['left_frame_start_sample']}",
                f"{receiver_id}:{pair['right_frame_start_sample']}",
            )
            for pair in combined
        ]
    )
    predictions = np.asarray(
        [
            [_integrated_phase(pair, model, reference_s, rate) for pair in combined]
            for model in (constant, linear)
        ]
    )
    validation = score_candidate_integrated_phase(
        CandidatePhaseEvidence(
            measured_phase_advance_rad=measured,
            interval_duration_s=durations,
            group_id=groups,
            training_group_ids=TRAINING_GROUPS,
            candidate_integrated_phase_rad=predictions,
            candidate_ids=("constant_train_even_cfo", "linear_train_even_cfo"),
            split_seed=SEED,
            endpoint_frame_ids=endpoints,
        )
    )
    rate_grid_hz_s = linear[1] + np.linspace(-5000.0, 5000.0, 41)
    rate_models = np.column_stack([np.full(len(rate_grid_hz_s), linear[0]), rate_grid_hz_s])
    rate_predictions = np.asarray(
        [
            [_integrated_phase(pair, model, reference_s, rate) for pair in combined]
            for model in rate_models
        ]
    )
    rate_validation = score_candidate_integrated_phase(
        CandidatePhaseEvidence(
            measured_phase_advance_rad=measured,
            interval_duration_s=durations,
            group_id=groups,
            training_group_ids=TRAINING_GROUPS,
            candidate_integrated_phase_rad=rate_predictions,
            candidate_ids=tuple(f"rate-grid-{index}" for index in range(len(rate_grid_hz_s))),
            split_seed=SEED,
            endpoint_frame_ids=endpoints,
        )
    )
    rate_choice = int(np.argmax(rate_validation.training_composite_score))
    phase_selected_rate_hz_s = float(rate_grid_hz_s[rate_choice])
    held_frames = [
        row
        for row in receiver
        if row["group_id"] in held_groups and row["frame"]["training_supported"]
    ]
    held_time = np.asarray([row["frame"]["reference_sample"] / rate for row in held_frames])
    held_odd_cfo = np.asarray([row["frame"]["odd"]["absolute_cfo_hz"] for row in held_frames])
    centered = held_time - reference_s
    frequency_rms = {
        name: float(np.sqrt(np.mean(np.square(held_odd_cfo - (model[0] + model[1] * centered)))))
        for name, model in zip(("constant", "linear"), (constant, linear), strict=True)
    }
    phase_rate_frequency_rms = float(
        np.sqrt(
            np.mean(np.square(held_odd_cfo - (linear[0] + phase_selected_rate_hz_s * centered)))
        )
    )
    held_mask = ~np.isin(groups, TRAINING_GROUPS)
    phase_metrics = {}
    for index, name in enumerate(("constant", "linear")):
        residual = validation.heldout_residual_rad[index, held_mask]
        phase_metrics[name] = _circular_metrics(residual)
    phase_rate_residual = rate_validation.heldout_residual_rad[rate_choice, held_mask]
    per_group = []
    for group in held_groups:
        selected = held_mask & (groups == group)
        per_group.append(
            {
                "group_id": group,
                "pair_count": int(np.sum(selected)),
                "median_channel_similarity": float(
                    np.median(
                        [
                            pair["channel_similarity"]
                            for pair in held_pairs
                            if pair["group_id"] == group
                        ]
                    )
                ),
                "constant": _circular_metrics(validation.heldout_residual_rad[0, selected]),
                "linear": _circular_metrics(validation.heldout_residual_rad[1, selected]),
            }
        )
    return {
        "receiver_id": receiver_id,
        "training_groups": list(TRAINING_GROUPS),
        "held_groups": list(held_groups),
        "training_supported_frame_count": sum(
            row["frame"]["training_supported"] and row["group_id"] in TRAINING_GROUPS
            for row in receiver
        ),
        "held_even_supported_frame_count": len(held_frames),
        "held_odd_exact_control": _held_odd_evidence(receiver, held_groups),
        "total_frame_count": len(receiver),
        "training_pair_count": len(training_pairs),
        "held_pair_count": len(held_pairs),
        "frequency_model_reference_s": reference_s,
        "constant_cfo_hz": float(constant[0]),
        "linear_cfo_at_reference_hz": float(linear[0]),
        "linear_cfo_rate_hz_s": float(linear[1]),
        "held_odd_cfo_rms_hz": frequency_rms,
        "phase_informed_rate": {
            "grid_half_width_hz_s": 5000.0,
            "grid_point_count": 41,
            "cfo_intercept_frozen_to_train_even_line_hz": float(linear[0]),
            "baseline_rate_hz_s": float(linear[1]),
            "selected_rate_hz_s": phase_selected_rate_hz_s,
            "selected_delta_hz_s": float(phase_selected_rate_hz_s - linear[1]),
            "selected_on_training_phase_only": True,
            "selected_at_grid_boundary": rate_choice in (0, len(rate_grid_hz_s) - 1),
            "fitted_phase_bias_hz": float(rate_validation.fitted_bias_hz[rate_choice]),
            "training_composite_score": float(
                rate_validation.training_composite_score[rate_choice]
            ),
            "held_composite_score": float(rate_validation.heldout_composite_score[rate_choice]),
            "held_phase_metrics": _circular_metrics(phase_rate_residual),
            "held_odd_cfo_rms_hz": phase_rate_frequency_rms,
            "held_data_used_for_selection": False,
        },
        "phase_bias_scope": "finite-principal-branch-minus187.5-to187.5Hz-conditional",
        "exact_375hz_periodicity_claimed": False,
        "fitted_phase_bias_hz": dict(
            zip(validation.candidate_ids, validation.fitted_bias_hz.tolist(), strict=True)
        ),
        "training_composite_score": dict(
            zip(validation.candidate_ids, validation.training_composite_score.tolist(), strict=True)
        ),
        "held_composite_score": dict(
            zip(validation.candidate_ids, validation.heldout_composite_score.tolist(), strict=True)
        ),
        "held_phase_metrics": phase_metrics,
        "candidate_contrast_rms_rad": validation.candidate_contrast_rms_rad.tolist(),
        "maximum_candidate_contrast_rad": validation.maximum_candidate_contrast_rad,
        "identifiable_after_nuisance": validation.identifiable_after_nuisance,
        "per_held_group": per_group,
        "held_odd_used_for_selection_or_gating": False,
        "held_frame_coverage_conditioned_on_even_support": True,
    }


def run(input_path: Path, output_path: Path) -> None:
    with gzip.open(input_path, "rt") as source:
        evidence = json.load(source)
    results = []
    for item in evidence["results"]:
        selection = item["selection"]
        row = {
            "session_id": selection["session_id"],
            "visit": selection["visit"],
            "sample_rate_hz": selection["sample_rate_hz"],
            "state": "abstained",
        }
        try:
            alternatives = {int(value["receiver_id"]): value for value in item["seed_alternatives"]}
            row["receivers"] = []
            for receiver in (0, 1):
                alternative = alternatives[receiver]
                selected = _evaluate_receiver(item["frames"], selection["sample_rate_hz"], receiver)
                refined_branch_index = min(1, len(alternative["frames_by_branch"]) - 1)
                refined = _branch_evidence(
                    alternative["frames_by_branch"][refined_branch_index],
                    tuple(group for group in range(6) if group not in TRAINING_GROUPS),
                )
                refined["train_even_branch_state"] = (
                    "selected"
                    if alternative["selected_branch_index"] == refined_branch_index
                    else "rejected"
                )
                refined["phase_model_scored"] = False
                row["receivers"].append(
                    {
                        "receiver_id": receiver,
                        "seed_choice": {
                            "seed_cfo_hz": alternative["seed_cfo_hz"],
                            "selected_branch_index": alternative["selected_branch_index"],
                            "refined_baseline_branch_index": refined_branch_index,
                            "training_even_margin": alternative["training_even_margin"],
                            "selection_used_held_odd": False,
                        },
                        "selected_train_even_branch": selected,
                        "refined_seed_only_baseline": refined,
                    }
                )
            row["state"] = "evaluated"
        except ValueError as error:
            row["reason"] = f"{type(error).__name__}: {error}"
        results.append(row)
    document = {
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "source_sha256": {
            "evaluator": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "candidate_phase_validation": hashlib.sha256(
                (
                    Path(__file__).resolve().parents[2]
                    / "src/leo/analysis/research/candidate_phase_validation.py"
                ).read_bytes()
            ).hexdigest(),
        },
        "seed": SEED,
        "training_groups": list(TRAINING_GROUPS),
        "comparison": "constant versus linear CFO fit to train-even frames",
        "source_scope": "one training-only GLRT-seeded waveform hypothesis",
        "source_binding_claimed": False,
        "held_response": "odd-fold CFO and channel-vector phase advances",
        "held_odd_used_for_selection_or_gating": False,
        "satellite_identity_claimed": False,
        "orbit_improvement_claimed": False,
        "results": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.input, args.output)


if __name__ == "__main__":
    main()
