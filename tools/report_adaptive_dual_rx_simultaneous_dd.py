#!/usr/bin/env python3
"""Bootstrap simultaneous two-source dual-RX phase differences from saved IQ.

The phase-blind source and 20 ms overlap gates are frozen in the prior raw-IQ
evidence.  This tool revisits only those qualified blocks.  It forms the two
source transfer products at the same samples, differences them before time
averaging, and resamples paired time atoms so common receiver fluctuations keep
their covariance.
"""

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
import numpy.typing as npt

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.contracts.digests import canonical_json_bytes, sha256_digest  # noqa: E402
from leo.storage.adaptive_hop import AdaptiveHopIqStore  # noqa: E402
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore  # noqa: E402

VISITS = (1065, 1109, 1136)
ATOM_SAMPLES = 8192
HALF_WIDTH_HZ = 6_000.0


@dataclass(frozen=True, slots=True)
class MatchedAtom:
    numerator: complex
    denominator: float
    center_sample: float
    low_effective_sample: float
    high_effective_sample: float


def _raw_module() -> Any:
    path = Path(__file__).with_name("report_adaptive_dual_rx_raw_coherence.py")
    spec = importlib.util.spec_from_file_location("_adaptive_dual_rx_raw", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _band_transfer(
    rx0: npt.NDArray[np.complexfloating],
    rx1: npt.NDArray[np.complexfloating],
    sample_rate_hz: float,
    center_hz: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return the time-local transfer product and its amplitude support."""
    size = len(rx0)
    if size != len(rx1) or size < 256:
        raise ValueError("invalid matched source atom")
    window = np.hanning(size)
    frequency = np.fft.fftfreq(size, 1 / sample_rate_hz)
    # Circular distance keeps the gate valid if a future center approaches the
    # sampled spectrum edge.
    distance = abs(
        (frequency - center_hz + sample_rate_hz / 2) % sample_rate_hz - sample_rate_hz / 2
    )
    mask = distance <= HALF_WIDTH_HZ
    if np.count_nonzero(mask) < 4:
        raise ValueError("source band has insufficient frequency support")
    spectrum0 = np.fft.fft(np.asarray(rx0, np.complex128) * window)
    spectrum1 = np.fft.fft(np.asarray(rx1, np.complex128) * window)
    filtered0 = np.fft.ifft(np.where(mask, spectrum0, 0))
    filtered1 = np.fft.ifft(np.where(mask, spectrum1, 0))
    product = filtered1 * np.conj(filtered0)
    return product, abs(filtered1) * abs(filtered0)


def simultaneous_atom(
    values: npt.NDArray[np.complexfloating],
    sample_rate_hz: float,
    receiver_offset_hz: float,
    centers_hz: tuple[float, float],
    *,
    global_start_sample: int,
) -> MatchedAtom:
    """Difference two source transfers sample by sample at one shared epoch."""
    if values.shape != (ATOM_SAMPLES, 2):
        raise ValueError("simultaneous atom must have the frozen FFT length")
    absolute = np.arange(ATOM_SAMPLES, dtype=float) + global_start_sample
    rx0 = np.asarray(values[:, 0], np.complex128)
    rx1 = np.asarray(values[:, 1], np.complex128) * np.exp(
        -2j * np.pi * receiver_offset_hz * absolute / sample_rate_hz
    )
    low, low_support = _band_transfer(rx0, rx1, sample_rate_hz, centers_hz[0])
    high, high_support = _band_transfer(rx0, rx1, sample_rate_hz, centers_hz[1])
    joint = low_support * high_support
    denominator = float(np.sum(joint))
    if not math.isfinite(denominator) or denominator <= np.finfo(float).tiny:
        raise ValueError("matched sources have no joint support")
    numerator = complex(np.sum(high * np.conj(low)))
    indexes = np.arange(ATOM_SAMPLES, dtype=float) + global_start_sample
    low_total = float(np.sum(low_support))
    high_total = float(np.sum(high_support))
    return MatchedAtom(
        numerator=numerator,
        denominator=denominator,
        center_sample=global_start_sample + (ATOM_SAMPLES - 1) / 2,
        low_effective_sample=float(np.sum(indexes * low_support) / low_total),
        high_effective_sample=float(np.sum(indexes * high_support) / high_total),
    )


def phase_deg(atoms: list[MatchedAtom]) -> float:
    if not atoms:
        raise ValueError("phase requires matched atoms")
    return math.degrees(float(np.angle(sum(atom.numerator for atom in atoms))))


def _paired_moving_block_errors(
    block_atoms: list[list[MatchedAtom]],
    *,
    replicates: int = 10_000,
    seed: int = 20260921,
) -> np.ndarray:
    """Draw phase errors from adjacent paired-source atoms."""
    if replicates < 100 or not block_atoms or any(len(block) < 3 for block in block_atoms):
        raise ValueError("insufficient paired blocks for bootstrap")
    nominal = math.radians(phase_deg([atom for block in block_atoms for atom in block]))
    adjacent = [
        (block[index], block[index + 1])
        for block in block_atoms
        for index in range(len(block) - 1)
    ]
    count = sum(len(block) for block in block_atoms)
    draws = math.ceil(count / 2)
    rng = np.random.default_rng(seed)
    errors = np.empty(replicates)
    for replicate in range(replicates):
        selected = rng.integers(0, len(adjacent), size=draws)
        total = sum(
            (adjacent[index][0].numerator + adjacent[index][1].numerator for index in selected),
            start=0j,
        )
        estimate = float(np.angle(total))
        errors[replicate] = math.degrees(float(np.angle(np.exp(1j * (estimate - nominal)))))
    return errors


def paired_moving_block_bootstrap(
    block_atoms: list[list[MatchedAtom]],
    *,
    replicates: int = 10_000,
    seed: int = 20260921,
) -> dict[str, Any]:
    """Resample adjacent paired-source atoms without crossing 20 ms gaps."""
    errors = _paired_moving_block_errors(block_atoms, replicates=replicates, seed=seed)
    low, high = np.quantile(errors, (0.025, 0.975))
    return {
        "method": "paired adjacent-atom moving-block bootstrap within qualified 20ms blocks",
        "atom_samples": ATOM_SAMPLES,
        "moving_block_atoms": 2,
        "replicates": replicates,
        "conditional_standard_error_deg": float(np.std(errors, ddof=1)),
        "conditional_95_error_interval_low_deg": float(low),
        "conditional_95_error_interval_high_deg": float(high),
    }


def _wrapped_difference_deg(left: float, right: float) -> float:
    return math.degrees(float(np.angle(np.exp(1j * math.radians(left - right)))))


def summarize_atoms(
    block_atoms: list[list[MatchedAtom]],
    sample_rate_hz: float,
    *,
    bootstrap_seed: int = 20260921,
) -> dict[str, Any]:
    flattened = [atom for block in block_atoms for atom in block]
    ordered = sorted(flattened, key=lambda atom: atom.center_sample)
    midpoint = len(ordered) // 2
    first = phase_deg(ordered[:midpoint])
    second = phase_deg(ordered[midpoint:])
    even = phase_deg(ordered[::2])
    odd = phase_deg(ordered[1::2])
    numerator = sum(atom.numerator for atom in flattened)
    denominator = sum(atom.denominator for atom in flattened)
    mismatches = [
        1_000 * abs(atom.high_effective_sample - atom.low_effective_sample) / sample_rate_hz
        for atom in flattened
    ]
    return {
        "wrapped_high_minus_low_deg": phase_deg(flattened),
        "joint_resultant": float(abs(numerator) / denominator),
        "qualified_20ms_block_count": len(block_atoms),
        "matched_time_atom_count": len(flattened),
        "first_time_half_deg": first,
        "second_time_half_deg": second,
        "second_minus_first_deg": _wrapped_difference_deg(second, first),
        "even_time_atoms_deg": even,
        "odd_time_atoms_deg": odd,
        "odd_minus_even_deg": _wrapped_difference_deg(odd, even),
        "source_effective_time_mismatch_ms_median": float(np.median(mismatches)),
        "source_effective_time_mismatch_ms_maximum": float(np.max(mismatches)),
        "matched_20ms_blocks": [
            {
                "first_atom_center_sample": block[0].center_sample,
                "atom_count": len(block),
                "wrapped_high_minus_low_deg": phase_deg(block),
                "joint_resultant": float(
                    abs(sum(atom.numerator for atom in block))
                    / sum(atom.denominator for atom in block)
                ),
            }
            for block in block_atoms
        ],
        "matched_time_atoms": [
            {
                "center_sample": atom.center_sample,
                "numerator_real": atom.numerator.real,
                "numerator_imag": atom.numerator.imag,
                "amplitude_denominator": atom.denominator,
                "low_effective_sample": atom.low_effective_sample,
                "high_effective_sample": atom.high_effective_sample,
            }
            for atom in ordered
        ],
        "bootstrap": paired_moving_block_bootstrap(block_atoms, seed=bootstrap_seed),
    }


def _qualified_starts(prior_visit: dict[str, Any], sample_rate_hz: float) -> tuple[int, ...]:
    evidence = prior_visit["source_overlap_evidence"]
    return tuple(
        round(float(block["start_ms"]) * sample_rate_hz / 1_000)
        for block in evidence["blocks"]
        if block["both_sources_qualified"] is True
    )


def _atoms_for_starts(
    values: np.ndarray,
    sample_rate_hz: float,
    receiver_offset_hz: float,
    centers_hz: tuple[float, float],
    starts: tuple[int, ...],
) -> list[list[MatchedAtom]]:
    block_samples = round(sample_rate_hz * 0.020)
    output: list[list[MatchedAtom]] = []
    for start in starts:
        atoms = []
        for local in range(0, block_samples - ATOM_SAMPLES + 1, ATOM_SAMPLES):
            atom_start = start + local
            atoms.append(
                simultaneous_atom(
                    values[atom_start : atom_start + ATOM_SAMPLES],
                    sample_rate_hz,
                    receiver_offset_hz,
                    centers_hz,
                    global_start_sample=atom_start,
                )
            )
        output.append(atoms)
    return output


def run(bulk_root: Path, prior_evidence: Path) -> dict[str, Any]:
    prior = json.loads(prior_evidence.read_text(encoding="utf-8"))
    prior_by_visit = {row["visit_index"]: row for row in prior["visits"]}
    if tuple(index for index in VISITS if index in prior_by_visit) != VISITS:
        raise ValueError("prior evidence lacks the frozen three-visit cohort")
    raw = _raw_module()
    store = AdaptiveHopIqStore(bulk_root, read_only=True)
    rows = []
    bootstrap_errors: dict[int, np.ndarray] = {}
    try:
        inspected = store.inspect(prior["session_id"])
        with AdaptiveHopAnalysisInputStore(store).source(prior["session_id"]) as source:
            sample_rate_hz = float(source.receipt.plan.geometry.sample_rate_hz)
            for visit_index in VISITS:
                prior_visit = prior_by_visit[visit_index]
                overlap = prior_visit["source_overlap_evidence"]
                centers_hz = tuple(
                    sorted(float(row["center_hz"]) for row in overlap["blocks"][0]["sources"])
                )
                if len(centers_hz) != 2:
                    raise ValueError("frozen source pair must contain exactly two sources")
                receiver_offset_hz = float(prior_visit["train_peak"]["frequency_hz"])
                if int(prior_visit["train_peak"]["delay_samples"]) != 0:
                    raise ValueError("nonzero delay is outside this bounded replay")
                starts = _qualified_starts(prior_visit, sample_rate_hz)
                values = source.read_visit(visit_index)
                raw_atoms = _atoms_for_starts(
                    values, sample_rate_hz, receiver_offset_hz, centers_hz, starts
                )
                corrected, nuisance = raw.remove_common_phase_nuisance(
                    values, sample_rate_hz, receiver_offset_hz, centers_hz
                )
                corrected_atoms = _atoms_for_starts(
                    corrected, sample_rate_hz, receiver_offset_hz, centers_hz, starts
                )
                raw_seed = 20260921 + visit_index
                raw_summary = summarize_atoms(
                    raw_atoms, sample_rate_hz, bootstrap_seed=raw_seed
                )
                bootstrap_errors[visit_index] = _paired_moving_block_errors(
                    raw_atoms, seed=raw_seed
                )
                corrected_summary = summarize_atoms(
                    corrected_atoms,
                    sample_rate_hz,
                    bootstrap_seed=20270921 + visit_index,
                )
                rows.append(
                    {
                        "visit_index": visit_index,
                        "centers_hz": list(centers_hz),
                        "source_separation_hz": centers_hz[1] - centers_hz[0],
                        "receiver_offset_hz": receiver_offset_hz,
                        "qualified_20ms_starts": [
                            1_000 * start / sample_rate_hz for start in starts
                        ],
                        "raw_exact_time_double_difference": raw_summary,
                        "off_target_nuisance_corrected_double_difference": corrected_summary,
                        "corrected_minus_raw_deg": _wrapped_difference_deg(
                            corrected_summary["wrapped_high_minus_low_deg"],
                            raw_summary["wrapped_high_minus_low_deg"],
                        ),
                        "off_target_nuisance": nuisance,
                    }
                )
    finally:
        store.close()
    comparisons = []
    for left_index in range(len(rows)):
        for right_index in range(left_index + 1, len(rows)):
            left = rows[left_index]
            right = rows[right_index]
            left_summary = left["raw_exact_time_double_difference"]
            right_summary = right["raw_exact_time_double_difference"]
            difference = _wrapped_difference_deg(
                right_summary["wrapped_high_minus_low_deg"],
                left_summary["wrapped_high_minus_low_deg"],
            )
            errors = (
                bootstrap_errors[right["visit_index"]]
                - bootstrap_errors[left["visit_index"]]
            )
            simulated = np.degrees(
                np.angle(np.exp(1j * np.radians(difference + errors)))
            )
            interval = np.quantile(simulated, (0.025, 0.975))
            comparisons.append(
                {
                    "from_visit_index": left["visit_index"],
                    "to_visit_index": right["visit_index"],
                    "wrapped_change_deg": difference,
                    "conditional_bootstrap_standard_error_deg": float(
                        np.std(errors, ddof=1)
                    ),
                    "conditional_bootstrap_95_interval_deg": [
                        float(interval[0]),
                        float(interval[1]),
                    ],
                    "conditionally_resolved_from_zero_at_95_percent": bool(
                        interval[0] > 0 or interval[1] < 0
                    ),
                }
            )
    body = {
        "schema_version": 1,
        "kind": "adaptive_dual_rx_simultaneous_double_difference_bootstrap_research",
        "session_id": prior["session_id"],
        "input_manifest_sha256": inspected.manifest_sha256,
        "prior_source_overlap_evidence_sha256": prior["evidence_sha256"],
        "selection_uses_phase": False,
        "source_identity_claimed": False,
        "stable_lnb_channel_assumption_applied": True,
        "absolute_single_source_phase_claimed": False,
        "rows": rows,
        "temporal_comparisons": comparisons,
    }
    body["evidence_sha256"] = sha256_digest(canonical_json_bytes(body))
    return body


def render(document: dict[str, Any], path: Path) -> None:
    rows = document["rows"]
    indexes = np.asarray([row["visit_index"] for row in rows])
    positions = np.arange(len(rows), dtype=float)
    raw = [row["raw_exact_time_double_difference"] for row in rows]
    corrected = [row["off_target_nuisance_corrected_double_difference"] for row in rows]
    figure, axes = plt.subplots(2, 1, figsize=(9, 8), layout="constrained")
    axes[0].errorbar(
        positions,
        [row["wrapped_high_minus_low_deg"] for row in raw],
        yerr=[row["bootstrap"]["conditional_standard_error_deg"] for row in raw],
        fmt="o-",
        capsize=4,
        label="raw exact-time DD (error bar: conditional SE)",
    )
    axes[0].plot(
        positions,
        [row["wrapped_high_minus_low_deg"] for row in corrected],
        "s--",
        label="off-target nuisance corrected",
    )
    axes[0].set_ylabel("high-minus-low RX phase DD (deg)\nwrapped 360 degrees")
    axes[0].legend()
    axes[0].grid(alpha=0.25)
    width = 0.35
    axes[1].bar(
        positions - width / 2,
        [abs(row["second_minus_first_deg"]) for row in raw],
        width,
        label="first/second time half",
    )
    axes[1].bar(
        positions + width / 2,
        [abs(row["odd_minus_even_deg"]) for row in raw],
        width,
        label="odd/even time atoms",
    )
    axes[1].set_xlabel("visit index")
    axes[1].set_ylabel("absolute independent-subset difference (deg)")
    axes[1].legend()
    axes[1].grid(axis="y", alpha=0.25)
    for axis in axes:
        axis.set_xticks(positions, [str(index) for index in indexes])
    figure.suptitle("28d simultaneous two-source phase, paired-IQ bootstrap")
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--prior-evidence", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    args = parser.parse_args()
    document = run(args.bulk_root, args.prior_evidence)
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
