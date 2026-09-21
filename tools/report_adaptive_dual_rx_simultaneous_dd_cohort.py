#!/usr/bin/env python3
"""Extend exact-time dual-source phase to the frozen 20-visit 28d cohort."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.starlink.adaptive_dual_rx_phase import circular_frequency_delta  # noqa: E402
from leo.application.adaptive_dual_rx_phase_v2 import _phase_blind_pairs  # noqa: E402
from leo.contracts.digests import canonical_json_bytes, sha256_digest  # noqa: E402
from leo.scanner.adaptive_hop_analysis import (  # noqa: E402
    AdaptiveHopAnalysisConfigurationV1,
    analyze_adaptive_hop_visit,
)
from leo.storage.adaptive_hop import AdaptiveHopIqStore  # noqa: E402
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore  # noqa: E402

SLOPE_MINIMUM_DEG_S = -360.0
SLOPE_MAXIMUM_DEG_S = 360.0
SLOPE_STEP_DEG_S = 0.25
MINIMUM_QUALIFIED_BLOCKS = 2
BOOTSTRAP_REPLICATES = 2_000


@dataclass(frozen=True, slots=True)
class CohortMatchedAtom:
    numerator: complex
    denominator: float
    center_sample: float
    low_effective_sample: float
    high_effective_sample: float
    joint_effective_sample: float


def _load_sibling(filename: str, name: str) -> Any:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def circular_profile(
    times_s: np.ndarray,
    phases_deg: np.ndarray,
    standard_errors_deg: np.ndarray,
) -> dict[str, Any]:
    """Profile a wrapped full-circle line over a fixed, bounded slope domain."""
    if len(times_s) < 4 or not (len(times_s) == len(phases_deg) == len(standard_errors_deg)):
        raise ValueError("circular profile requires four matched observations")
    reference = float(np.mean(times_s))
    delta = times_s - reference
    slopes = np.arange(
        SLOPE_MINIMUM_DEG_S,
        SLOPE_MAXIMUM_DEG_S + SLOPE_STEP_DEG_S / 2,
        SLOPE_STEP_DEG_S,
    )
    weights = 1.0 / np.maximum(standard_errors_deg, 5.0) ** 2
    residual_phase = np.radians(
        phases_deg[None, :] - slopes[:, None] * delta[None, :]
    )
    profile = abs(np.sum(weights[None, :] * np.exp(1j * residual_phase), axis=1)) / np.sum(
        weights
    )
    local = np.flatnonzero(
        (profile >= np.roll(profile, 1)) & (profile > np.roll(profile, -1))
    )
    local = local[(local > 0) & (local < len(profile) - 1)]
    ranked = sorted(local, key=lambda index: profile[index], reverse=True)
    retained: list[int] = []
    for index in ranked:
        if all(abs(slopes[index] - slopes[other]) >= 5.0 for other in retained):
            retained.append(int(index))
        if len(retained) == 8:
            break
    best = int(np.argmax(profile))
    intercept = math.degrees(
        float(
            np.angle(
                np.sum(
                    weights
                    * np.exp(1j * np.radians(phases_deg - slopes[best] * delta))
                )
            )
        )
    )
    zero_index = int(np.argmin(abs(slopes)))
    return {
        "slope_domain_deg_s": [SLOPE_MINIMUM_DEG_S, SLOPE_MAXIMUM_DEG_S],
        "slope_step_deg_s": SLOPE_STEP_DEG_S,
        "reference_time_s": reference,
        "best_slope_deg_s": float(slopes[best]),
        "best_intercept_deg": intercept,
        "best_profile_resultant": float(profile[best]),
        "best_at_slope_domain_boundary": bool(best in (0, len(slopes) - 1)),
        "zero_slope_profile_resultant": float(profile[zero_index]),
        "competing_local_maxima": [
            {
                "slope_deg_s": float(slopes[index]),
                "profile_resultant": float(profile[index]),
                "score_below_best": float(profile[best] - profile[index]),
            }
            for index in retained
        ],
    }


def _cohort_simultaneous_atom(
    base: Any,
    values: np.ndarray,
    sample_rate_hz: float,
    receiver_offset_hz: float,
    centers_hz: tuple[float, float],
    *,
    global_start_sample: int,
) -> CohortMatchedAtom:
    if values.shape != (base.ATOM_SAMPLES, 2):
        raise ValueError("cohort atom must have the frozen FFT length")
    absolute = np.arange(base.ATOM_SAMPLES, dtype=float) + global_start_sample
    rx0 = np.asarray(values[:, 0], np.complex128)
    rx1 = np.asarray(values[:, 1], np.complex128) * np.exp(
        -2j * np.pi * receiver_offset_hz * absolute / sample_rate_hz
    )
    low, low_support = base._band_transfer(rx0, rx1, sample_rate_hz, centers_hz[0])
    high, high_support = base._band_transfer(rx0, rx1, sample_rate_hz, centers_hz[1])
    joint = low_support * high_support
    denominator = float(np.sum(joint))
    if denominator <= np.finfo(float).tiny:
        raise ValueError("matched cohort sources have no joint support")
    indexes = np.arange(base.ATOM_SAMPLES, dtype=float) + global_start_sample
    return CohortMatchedAtom(
        numerator=complex(np.sum(high * np.conj(low))),
        denominator=denominator,
        center_sample=global_start_sample + (base.ATOM_SAMPLES - 1) / 2,
        low_effective_sample=float(np.sum(indexes * low_support) / np.sum(low_support)),
        high_effective_sample=float(np.sum(indexes * high_support) / np.sum(high_support)),
        joint_effective_sample=float(np.sum(indexes * joint) / denominator),
    )


def _cohort_atoms_for_starts(
    base: Any,
    values: np.ndarray,
    sample_rate_hz: float,
    receiver_offset_hz: float,
    centers_hz: tuple[float, float],
    starts: tuple[int, ...],
) -> list[list[CohortMatchedAtom]]:
    block_samples = round(sample_rate_hz * 0.020)
    output = []
    for start in starts:
        atoms = []
        for local in range(0, block_samples - base.ATOM_SAMPLES + 1, base.ATOM_SAMPLES):
            atom_start = start + local
            atoms.append(
                _cohort_simultaneous_atom(
                    base,
                    values[atom_start : atom_start + base.ATOM_SAMPLES],
                    sample_rate_hz,
                    receiver_offset_hz,
                    centers_hz,
                    global_start_sample=atom_start,
                )
            )
        output.append(atoms)
    return output


def _add_effective_samples(summary: dict[str, Any], blocks: list[list[CohortMatchedAtom]]) -> None:
    ordered = sorted(
        (atom for block in blocks for atom in block), key=lambda atom: atom.center_sample
    )

    def effective(atoms: list[CohortMatchedAtom]) -> float:
        return float(
            np.average(
                [atom.joint_effective_sample for atom in atoms],
                weights=[atom.denominator for atom in atoms],
            )
        )

    midpoint = len(ordered) // 2
    for record, atom in zip(summary["matched_time_atoms"], ordered, strict=True):
        record["joint_effective_sample"] = atom.joint_effective_sample
    summary.update(
        {
            "joint_effective_sample": effective(ordered),
            "first_time_half_effective_sample": effective(ordered[:midpoint]),
            "second_time_half_effective_sample": effective(ordered[midpoint:]),
            "even_time_atoms_effective_sample": effective(ordered[::2]),
            "odd_time_atoms_effective_sample": effective(ordered[1::2]),
        }
    )


def _profile_best_slope(
    times_s: np.ndarray,
    phases_deg: np.ndarray,
    standard_errors_deg: np.ndarray,
) -> float:
    return float(circular_profile(times_s, phases_deg, standard_errors_deg)["best_slope_deg_s"])


def _association_audit(
    rows_by_visit: dict[int, dict[str, Any]], fixed_path: list[int]
) -> dict[str, Any]:
    transitions = []
    for left_index, right_index in zip(fixed_path, fixed_path[1:], strict=False):
        left = rows_by_visit[left_index]
        right = rows_by_visit[right_index]
        signal_steps = [
            abs(circular_frequency_delta(left["centers_hz"][index], right["centers_hz"][index]))
            for index in (0, 1)
        ]
        transition = {
            "from_visit_index": left_index,
            "to_visit_index": right_index,
            "visit_gap": right_index - left_index,
            "time_gap_s": right["exact_time_s"] - left["exact_time_s"],
            "signal_steps_hz": signal_steps,
            "separation_step_hz": abs(
                right["source_separation_hz"] - left["source_separation_hz"]
            ),
            "receiver_offset_step_hz": abs(
                right["receiver_offset_hz"] - left["receiver_offset_hz"]
            ),
        }
        transition["passes_fixed_rf_gates"] = bool(
            1 <= transition["visit_gap"] <= 32
            and 0 < transition["time_gap_s"] <= 3.5
            and max(signal_steps) <= 15_000.0
            and transition["separation_step_hz"] <= 3_000.0
            and transition["receiver_offset_step_hz"] <= 10_000.0
        )
        transitions.append(transition)
    return {
        "fixed_path_visit_indexes": fixed_path,
        "phase_used": False,
        "catalog_identity_claimed": False,
        "all_transitions_pass_corrected_rf_and_time_gates": all(
            row["passes_fixed_rf_gates"] for row in transitions
        ),
        "transitions": transitions,
    }


def run(
    bulk_root: Path,
    raw_evidence_path: Path,
    dense_summary_path: Path,
) -> dict[str, Any]:
    base = _load_sibling(
        "report_adaptive_dual_rx_simultaneous_dd.py", "_adaptive_dual_rx_simultaneous_dd"
    )
    raw = _load_sibling("report_adaptive_dual_rx_raw_coherence.py", "_adaptive_raw_coherence")
    raw_evidence = json.loads(raw_evidence_path.read_text(encoding="utf-8"))
    dense_summary = json.loads(dense_summary_path.read_text(encoding="utf-8"))
    cohort = [int(row["visit_index"]) for row in raw_evidence["visits"]]
    if len(cohort) != 20 or len(set(cohort)) != 20:
        raise ValueError("extension requires the frozen unique 20-visit cohort")
    fixed_states = dense_summary["tracks"][0]["states"]
    if any(int(row["orientation"]) != 0 for row in fixed_states):
        raise ValueError("fixed path orientation no longer matches high-minus-low")
    fixed_path = [int(row["visit_index"]) for row in fixed_states]
    prior_by_visit = {int(row["visit_index"]): row for row in raw_evidence["visits"]}
    store = AdaptiveHopIqStore(bulk_root, read_only=True)
    rows: list[dict[str, Any]] = []
    bootstrap_errors: dict[int, np.ndarray] = {}
    try:
        inspected = store.inspect(raw_evidence["session_id"])
        with AdaptiveHopAnalysisInputStore(store).source(raw_evidence["session_id"]) as source:
            sample_rate_hz = int(source.receipt.plan.geometry.sample_rate_hz)
            configuration = AdaptiveHopAnalysisConfigurationV1(
                sample_rate_hz=sample_rate_hz,
                probe_stride_ms=10,
            )
            for visit_index in cohort:
                prior = prior_by_visit[visit_index]
                base_row: dict[str, Any] = {
                    "visit_index": visit_index,
                    "in_fixed_phase_blind_path": visit_index in fixed_path,
                    "prior_phase_blind_pair_count": int(prior["phase_blind_pair_count"]),
                }
                if prior["phase_blind_pair_count"] != 2:
                    base_row.update(
                        {
                            "state": "unmatched_not_two_sources",
                            "reason": "phase_blind_pair_count_is_not_two",
                        }
                    )
                    rows.append(base_row)
                    continue
                analysis = analyze_adaptive_hop_visit(
                    source, visit_index, configuration=configuration
                )
                pairs = _phase_blind_pairs(analysis)
                if len(pairs) != 2:
                    raise ValueError("current phase-blind pairs differ from frozen evidence")
                centers_hz = tuple(
                    sorted(float(pair[0].fractional_tracking_cfo_hz) for pair in pairs)
                )
                prior_centers = tuple(
                    sorted(float(pair["rx0_tracking_cfo_hz"]) for pair in prior["corrected_pairs"])
                )
                if not np.allclose(centers_hz, prior_centers, atol=1e-6, rtol=0):
                    raise ValueError("current source centers differ from frozen evidence")
                receiver_offset_hz = float(prior["train_peak"]["frequency_hz"])
                if int(prior["train_peak"]["delay_samples"]) != 0:
                    raise ValueError("frozen cohort contains unsupported nonzero delay")
                values = source.read_visit(visit_index)
                corrected, nuisance = raw.remove_common_phase_nuisance(
                    values, sample_rate_hz, receiver_offset_hz, centers_hz
                )
                overlap = raw.source_overlap_evidence(
                    corrected, sample_rate_hz, receiver_offset_hz, centers_hz
                )
                starts = tuple(
                    round(float(block["start_ms"]) * sample_rate_hz / 1_000)
                    for block in overlap["blocks"]
                    if block["both_sources_qualified"] is True
                )
                origin_s = (
                    float(analysis.valid_start_counter - analysis.source_origin_counter)
                    / sample_rate_hz
                )
                base_row.update(
                    {
                        "centers_hz": list(centers_hz),
                        "source_separation_hz": centers_hz[1] - centers_hz[0],
                        "receiver_offset_hz": receiver_offset_hz,
                        "valid_visit_origin_s": origin_s,
                        "exact_time_s": origin_s + 0.060,
                        "overlap_gate": overlap,
                        "off_target_nuisance": nuisance,
                    }
                )
                if len(starts) < MINIMUM_QUALIFIED_BLOCKS:
                    base_row.update(
                        {
                            "state": "insufficient_phase_blind_overlap",
                            "reason": "fewer_than_two_qualified_20ms_blocks",
                            "qualified_20ms_block_count": len(starts),
                        }
                    )
                    rows.append(base_row)
                    continue
                raw_atoms = _cohort_atoms_for_starts(
                    base, values, sample_rate_hz, receiver_offset_hz, centers_hz, starts
                )
                corrected_atoms = _cohort_atoms_for_starts(
                    base, corrected, sample_rate_hz, receiver_offset_hz, centers_hz, starts
                )
                seed = 20260921 + visit_index
                raw_summary = base.summarize_atoms(
                    raw_atoms, sample_rate_hz, bootstrap_seed=seed
                )
                corrected_summary = base.summarize_atoms(
                    corrected_atoms,
                    sample_rate_hz,
                    bootstrap_seed=20270921 + visit_index,
                )
                _add_effective_samples(raw_summary, raw_atoms)
                _add_effective_samples(corrected_summary, corrected_atoms)
                bootstrap_errors[visit_index] = base._paired_moving_block_errors(
                    raw_atoms, replicates=BOOTSTRAP_REPLICATES, seed=seed
                )
                exact_time_s = (
                    origin_s + raw_summary["joint_effective_sample"] / sample_rate_hz
                )
                base_row.update(
                    {
                        "state": "accepted_exact_time_double_difference",
                        "qualified_20ms_block_count": len(starts),
                        "exact_time_s": exact_time_s,
                        "raw_exact_time_double_difference": raw_summary,
                        "off_target_nuisance_corrected_double_difference": corrected_summary,
                        "corrected_minus_raw_deg": base._wrapped_difference_deg(
                            corrected_summary["wrapped_high_minus_low_deg"],
                            raw_summary["wrapped_high_minus_low_deg"],
                        ),
                    }
                )
                rows.append(base_row)
    finally:
        store.close()
    rf_rows_by_visit = {
        int(row["visit_index"]): row for row in rows if "centers_hz" in row
    }
    rows_by_visit = {
        int(row["visit_index"]): row
        for row in rows
        if row["state"] == "accepted_exact_time_double_difference"
    }
    association = _association_audit(rf_rows_by_visit, fixed_path)
    accepted_path = [index for index in fixed_path if index in rows_by_visit]
    fit_rows = [rows_by_visit[index] for index in accepted_path]
    if not association["all_transitions_pass_corrected_rf_and_time_gates"]:
        trend = {
            "state": "unavailable_fixed_rf_path_failed_corrected_audit",
            "accepted_path_visit_indexes": accepted_path,
        }
    elif len(fit_rows) < 4:
        trend: dict[str, Any] = {
            "state": "unavailable_insufficient_accepted_fixed_path",
            "accepted_path_visit_indexes": accepted_path,
        }
    else:
        times = np.asarray([row["exact_time_s"] for row in fit_rows])
        phases = np.asarray(
            [
                row["raw_exact_time_double_difference"]["wrapped_high_minus_low_deg"]
                for row in fit_rows
            ]
        )
        sigmas = np.asarray(
            [
                row["raw_exact_time_double_difference"]["bootstrap"][
                    "conditional_standard_error_deg"
                ]
                for row in fit_rows
            ]
        )
        full = circular_profile(times, phases, sigmas)
        first_half = circular_profile(
            np.asarray(
                [
                    row["valid_visit_origin_s"]
                    + row["raw_exact_time_double_difference"][
                        "first_time_half_effective_sample"
                    ]
                    / sample_rate_hz
                    for row in fit_rows
                ]
            ),
            np.asarray(
                [row["raw_exact_time_double_difference"]["first_time_half_deg"] for row in fit_rows]
            ),
            sigmas,
        )
        second_half = circular_profile(
            np.asarray(
                [
                    row["valid_visit_origin_s"]
                    + row["raw_exact_time_double_difference"][
                        "second_time_half_effective_sample"
                    ]
                    / sample_rate_hz
                    for row in fit_rows
                ]
            ),
            np.asarray(
                [
                    row["raw_exact_time_double_difference"]["second_time_half_deg"]
                    for row in fit_rows
                ]
            ),
            sigmas,
        )
        even_atoms = circular_profile(
            np.asarray(
                [
                    row["valid_visit_origin_s"]
                    + row["raw_exact_time_double_difference"][
                        "even_time_atoms_effective_sample"
                    ]
                    / sample_rate_hz
                    for row in fit_rows
                ]
            ),
            np.asarray(
                [row["raw_exact_time_double_difference"]["even_time_atoms_deg"] for row in fit_rows]
            ),
            sigmas,
        )
        odd_atoms = circular_profile(
            np.asarray(
                [
                    row["valid_visit_origin_s"]
                    + row["raw_exact_time_double_difference"][
                        "odd_time_atoms_effective_sample"
                    ]
                    / sample_rate_hz
                    for row in fit_rows
                ]
            ),
            np.asarray(
                [row["raw_exact_time_double_difference"]["odd_time_atoms_deg"] for row in fit_rows]
            ),
            sigmas,
        )
        rng = np.random.default_rng(20260921)
        bootstrap_slopes = np.empty(BOOTSTRAP_REPLICATES)
        for replicate in range(BOOTSTRAP_REPLICATES):
            perturbed = np.asarray(
                [
                    phase
                    + bootstrap_errors[row["visit_index"]][
                        rng.integers(0, len(bootstrap_errors[row["visit_index"]]))
                    ]
                    for phase, row in zip(phases, fit_rows, strict=True)
                ]
            )
            bootstrap_slopes[replicate] = _profile_best_slope(times, perturbed, sigmas)
        unique, counts = np.unique(bootstrap_slopes, return_counts=True)
        ranked = np.argsort(counts)[::-1][:12]
        profile_modes = np.asarray(
            [row["slope_deg_s"] for row in full["competing_local_maxima"]]
        )
        basin_indexes = np.argmin(
            abs(bootstrap_slopes[:, None] - profile_modes[None, :]), axis=1
        )
        basin_fractions = [
            float(np.mean(basin_indexes == index)) for index in range(len(profile_modes))
        ]
        subset_slopes = [
            first_half["best_slope_deg_s"],
            second_half["best_slope_deg_s"],
            even_atoms["best_slope_deg_s"],
            odd_atoms["best_slope_deg_s"],
        ]
        quantiles = np.quantile(bootstrap_slopes, (0.025, 0.5, 0.975))
        primary_basin_fraction = basin_fractions[0]
        subsets_agree = max(
            abs(slope - full["best_slope_deg_s"]) for slope in subset_slopes
        ) <= 5.0
        bootstrap_excludes_zero = bool(quantiles[0] > 0 or quantiles[2] < 0)
        detection_claimed = bool(
            not full["best_at_slope_domain_boundary"]
            and primary_basin_fraction >= 0.95
            and bootstrap_excludes_zero
            and subsets_agree
        )
        trend = {
            "state": "measured_conditional_circular_profile",
            "accepted_path_visit_indexes": accepted_path,
            "phase_model": "wrapped_full_circle_intercept_plus_linear_rate",
            "full": full,
            "first_time_half": first_half,
            "second_time_half": second_half,
            "even_time_atoms": even_atoms,
            "odd_time_atoms": odd_atoms,
            "bootstrap_global_best_slope_quantiles_deg_s": list(map(float, quantiles)),
            "bootstrap_fraction_nonpositive_slope": float(np.mean(bootstrap_slopes <= 0)),
            "bootstrap_global_best_slope_modes": [
                {
                    "slope_deg_s": float(unique[index]),
                    "fraction": float(counts[index] / len(bootstrap_slopes)),
                }
                for index in ranked
            ],
            "bootstrap_profile_mode_basin_fractions": [
                {
                    "profile_mode_slope_deg_s": float(profile_modes[index]),
                    "bootstrap_fraction": basin_fractions[index],
                }
                for index in range(len(profile_modes))
            ],
            "independent_subset_best_slope_range_deg_s": [
                float(min(subset_slopes)),
                float(max(subset_slopes)),
            ],
            "primary_mode_bootstrap_fraction": primary_basin_fraction,
            "bootstrap_excludes_zero": bootstrap_excludes_zero,
            "independent_subsets_agree_within_5_deg_s": subsets_agree,
            "detection_claimed": detection_claimed,
            "detection_rule": (
                "requires a unique global circular maximum, bootstrap support away from zero, "
                "and agreement of first/second and odd/even time subsets"
            ),
        }
    body = {
        "schema_version": 1,
        "kind": "adaptive_dual_rx_simultaneous_double_difference_cohort_research",
        "session_id": raw_evidence["session_id"],
        "input_manifest_sha256": inspected.manifest_sha256,
        "raw_authority_evidence_sha256": raw_evidence["evidence_sha256"],
        "dense_phase_blind_association_sha256": sha256_digest(
            canonical_json_bytes(dense_summary)
        ),
        "cohort_visit_indexes": cohort,
        "selection_uses_phase": False,
        "catalog_identity_claimed": False,
        "stable_lnb_channel_assumption_applied": True,
        "minimum_qualified_20ms_blocks": MINIMUM_QUALIFIED_BLOCKS,
        "association_audit": association,
        "rows": rows,
        "trend": trend,
    }
    body["evidence_sha256"] = sha256_digest(canonical_json_bytes(body))
    return body


def render(document: dict[str, Any], path: Path) -> None:
    rows = [
        row for row in document["rows"] if row["state"] == "accepted_exact_time_double_difference"
    ]
    path_set = set(document["trend"].get("accepted_path_visit_indexes", []))
    figure, axes = plt.subplots(2, 1, figsize=(11, 9), layout="constrained")
    for in_path, marker, label in (
        (True, "o", "accepted fixed RF path"),
        (False, "x", "accepted outside fixed path"),
    ):
        selected = [row for row in rows if (row["visit_index"] in path_set) is in_path]
        if selected:
            axes[0].errorbar(
                [row["exact_time_s"] for row in selected],
                [
                    row["raw_exact_time_double_difference"]["wrapped_high_minus_low_deg"]
                    for row in selected
                ],
                yerr=[
                    row["raw_exact_time_double_difference"]["bootstrap"][
                        "conditional_standard_error_deg"
                    ]
                    for row in selected
                ],
                fmt=marker,
                capsize=3,
                label=label,
            )
    axes[0].set_ylabel("exact-time high-minus-low DD (deg)\nwrapped 360 degrees")
    axes[0].set_xlabel("session time since capture origin (s)")
    axes[0].grid(alpha=0.25)
    axes[0].legend()
    states = {
        "accepted_exact_time_double_difference": 0,
        "insufficient_phase_blind_overlap": 1,
        "unmatched_not_two_sources": 2,
    }
    colors = {0: "#2ca02c", 1: "#ff7f0e", 2: "#d62728"}
    for row in document["rows"]:
        level = states[row["state"]]
        axes[1].scatter(row["visit_index"], level, color=colors[level])
    axes[1].set_yticks(
        [0, 1, 2], ["accepted", "<2 overlap blocks", "not two sources"]
    )
    axes[1].set_xlabel("visit index")
    axes[1].set_ylabel("phase-blind disposition")
    axes[1].grid(axis="x", alpha=0.25)
    figure.suptitle("28d frozen 20-visit simultaneous DD extension")
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--raw-evidence", type=Path, required=True)
    parser.add_argument("--dense-summary", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    args = parser.parse_args()
    document = run(args.bulk_root, args.raw_evidence, args.dense_summary)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    render(document, args.png)
    print(
        json.dumps(
            {
                "evidence_sha256": document["evidence_sha256"],
                "json": str(args.json),
                "png": str(args.png),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
