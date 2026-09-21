#!/usr/bin/env python3
"""Covariance-corrected matched-pilot simultaneous DD on three saved visits."""

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

from leo.analysis.starlink.adaptive_dual_rx_phase import SYMBOL_ALIAS_HZ  # noqa: E402
from leo.analysis.starlink.templates import (  # noqa: E402
    CONTROL_SYMBOL_ROLL,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    qin_edge_pilot_frame,
)
from leo.application.adaptive_dual_rx_phase_v2 import _phase_blind_pairs  # noqa: E402
from leo.contracts.digests import canonical_json_bytes, sha256_digest  # noqa: E402
from leo.scanner.adaptive_hop_analysis import (  # noqa: E402
    AdaptiveHopAnalysisConfigurationV1,
    analyze_adaptive_hop_visit,
)
from leo.storage.adaptive_hop import AdaptiveHopIqStore  # noqa: E402
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore  # noqa: E402

VISITS = (1065, 1109, 1136)
MINIMUM_COEFFICIENT_SNR = 4.0
MAXIMUM_GRAM_CONDITION = 10.0
MINIMUM_EXACT_TO_CONTROL_EXPLAINED_RATIO = 2.0
MINIMUM_ALIAS_WINNER_RUNNER_RATIO = 1.05
MAXIMUM_NOISE_BIAS_FRACTION = 0.25
MAXIMUM_CROSS_RECEIVER_RESIDUAL_COHERENCE = 0.20
MINIMUM_QUALIFIED_FRAMES_PER_BLOCK = 6


@dataclass(frozen=True, slots=True)
class ComplexFit:
    coefficients: tuple[complex, complex]
    coefficient_covariance: npt.NDArray[np.complex128]
    residual: npt.NDArray[np.complex128]
    residual_variance: float
    explained_power: float
    residual_power: float
    coefficient_snr: tuple[float, float]


def _load_sibling(filename: str, name: str) -> Any:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def joint_complex_fit(
    values: npt.NDArray[np.complexfloating],
    design: npt.NDArray[np.complexfloating],
) -> ComplexFit:
    """Fit two simultaneous complex templates and retain coefficient covariance."""
    y = np.asarray(values, np.complex128)
    x = np.asarray(design, np.complex128)
    if y.ndim != 1 or x.shape != (len(y), 2) or len(y) < 16:
        raise ValueError("joint complex fit requires two templates on common support")
    gram = x.conj().T @ x
    inverse = np.linalg.inv(gram)
    beta = inverse @ x.conj().T @ y
    fitted = x @ beta
    residual = y - fitted
    residual_power = float(np.vdot(residual, residual).real)
    variance = residual_power / max(len(y) - 2, 1)
    covariance = variance * inverse
    snr = tuple(
        float(abs(beta[index]) ** 2 / max(covariance[index, index].real, 1e-30))
        for index in range(2)
    )
    return ComplexFit(
        coefficients=(complex(beta[0]), complex(beta[1])),
        coefficient_covariance=np.asarray(covariance, np.complex128),
        residual=np.asarray(residual, np.complex128),
        residual_variance=variance,
        explained_power=float(np.vdot(fitted, fitted).real),
        residual_power=residual_power,
        coefficient_snr=snr,
    )


def covariance_corrected_dd(
    receiver0: ComplexFit,
    receiver1: ComplexFit,
) -> dict[str, complex | float]:
    """Subtract within-receiver LS source covariance before forming DD."""
    naive_cross0 = receiver0.coefficients[1] * np.conj(receiver0.coefficients[0])
    naive_cross1 = receiver1.coefficients[1] * np.conj(receiver1.coefficients[0])
    covariance0 = receiver0.coefficient_covariance[1, 0]
    covariance1 = receiver1.coefficient_covariance[1, 0]
    corrected_cross0 = naive_cross0 - covariance0
    corrected_cross1 = naive_cross1 - covariance1
    naive = naive_cross1 * np.conj(naive_cross0)
    corrected = corrected_cross1 * np.conj(corrected_cross0)
    covariance_product = covariance1 * np.conj(covariance0)
    return {
        "naive_phasor": complex(naive),
        "corrected_phasor": complex(corrected),
        "receiver0_source_cross_covariance": complex(covariance0),
        "receiver1_source_cross_covariance": complex(covariance1),
        "covariance_product": complex(covariance_product),
        "noise_bias_fraction": float(
            abs(covariance_product) / max(abs(naive), np.finfo(float).tiny)
        ),
    }


def normalized_gram(design: np.ndarray) -> tuple[float, float]:
    norms = np.sqrt(np.sum(abs(design) ** 2, axis=0))
    normalized = design / norms[None, :]
    coherence = float(abs(np.vdot(normalized[:, 0], normalized[:, 1])))
    condition = float(np.linalg.cond(normalized.conj().T @ normalized))
    return coherence, condition


def frame_lattice_pairs(
    sample_count: int,
    sample_rate_hz: float,
    epochs: tuple[int, int],
    frame_length: int,
) -> list[tuple[int, int]]:
    period = sample_rate_hz / FRAME_RATE_HZ
    lattices = []
    for epoch in epochs:
        lattice = {
            offset: epoch + round(offset * period)
            for offset in range(-200, 201)
            if epoch + round(offset * period) >= 0
            and epoch + round(offset * period) + frame_length <= sample_count
        }
        lattices.append(lattice)
    shift = round((epochs[0] - epochs[1]) / period)
    return [
        (start, lattices[1][offset + shift])
        for offset, start in lattices[0].items()
        if offset + shift in lattices[1]
    ]


def common_designs(
    templates: tuple[np.ndarray, np.ndarray],
    starts: tuple[int, int],
    frequencies_hz: tuple[float, float],
    receiver_offset_hz: float,
    sample_rate_hz: float,
    common_reference_sample: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build both receiver designs on exactly the same known-pilot samples."""
    first_known = round(2 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    last_known = min(round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S), len(templates[0]))
    begin = max(starts[0] + first_known, starts[1] + first_known)
    end = min(starts[0] + last_known, starts[1] + last_known)
    if end - begin < 256:
        raise ValueError("source pilot windows lack common sample support")
    samples = np.arange(begin, end, dtype=int)
    relative = samples.astype(float) - common_reference_sample
    designs = []
    for receiver_offset in (0.0, receiver_offset_hz):
        columns = []
        for template, start, frequency in zip(templates, starts, frequencies_hz, strict=True):
            waveform = template[samples - start]
            columns.append(
                waveform
                * np.exp(2j * np.pi * (frequency + receiver_offset) * relative / sample_rate_hz)
            )
        designs.append(np.column_stack(columns))
    return samples, designs[0], designs[1]


def _residual_cross_receiver_coherence(
    fit0: ComplexFit,
    fit1: ComplexFit,
    samples: np.ndarray,
    receiver_offset_hz: float,
    sample_rate_hz: float,
    reference_sample: float,
) -> float:
    aligned1 = fit1.residual * np.exp(
        -2j * np.pi * receiver_offset_hz * (samples - reference_sample) / sample_rate_hz
    )
    numerator = abs(np.vdot(fit0.residual, aligned1))
    denominator = math.sqrt(
        float(np.vdot(fit0.residual, fit0.residual).real) * float(np.vdot(aligned1, aligned1).real)
    )
    return float(numerator / max(denominator, np.finfo(float).tiny))


def _subset_dd(
    iq: np.ndarray,
    samples: np.ndarray,
    designs: tuple[np.ndarray, np.ndarray],
    control_designs: tuple[np.ndarray, np.ndarray],
    receiver_offset_hz: float,
    sample_rate_hz: float,
    common_reference_sample: float,
) -> dict[str, Any]:
    fits = tuple(joint_complex_fit(iq[samples, receiver], designs[receiver]) for receiver in (0, 1))
    controls = tuple(
        joint_complex_fit(iq[samples, receiver], control_designs[receiver]) for receiver in (0, 1)
    )
    dd = covariance_corrected_dd(fits[0], fits[1])
    _, gram_condition = normalized_gram(designs[0])
    exact_explained = sum(fit.explained_power for fit in fits)
    control_explained = sum(fit.explained_power for fit in controls)
    exact_control_ratio = exact_explained / max(control_explained, np.finfo(float).tiny)
    residual_coherence = _residual_cross_receiver_coherence(
        fits[0],
        fits[1],
        samples,
        receiver_offset_hz,
        sample_rate_hz,
        common_reference_sample,
    )
    minimum_snr = min(value for fit in fits for value in fit.coefficient_snr)
    qualified = bool(
        gram_condition <= MAXIMUM_GRAM_CONDITION
        and minimum_snr >= MINIMUM_COEFFICIENT_SNR
        and exact_control_ratio >= MINIMUM_EXACT_TO_CONTROL_EXPLAINED_RATIO
        and dd["noise_bias_fraction"] <= MAXIMUM_NOISE_BIAS_FRACTION
        and residual_coherence <= MAXIMUM_CROSS_RECEIVER_RESIDUAL_COHERENCE
    )
    return {
        "qualified": qualified,
        "fits": fits,
        "dd": dd,
        "gram_condition": gram_condition,
        "exact_control_ratio": exact_control_ratio,
        "residual_coherence": residual_coherence,
        "minimum_snr": minimum_snr,
    }


def analyze_frame(
    iq: np.ndarray,
    samples: np.ndarray,
    designs: tuple[np.ndarray, np.ndarray],
    control_designs: tuple[np.ndarray, np.ndarray],
    receiver_offset_hz: float,
    sample_rate_hz: float,
    common_reference_sample: float,
) -> dict[str, Any]:
    full = _subset_dd(
        iq,
        samples,
        designs,
        control_designs,
        receiver_offset_hz,
        sample_rate_hz,
        common_reference_sample,
    )
    fits = full["fits"]
    dd = full["dd"]
    gram_coherence, gram_condition = normalized_gram(designs[0])
    exact_control_ratio = full["exact_control_ratio"]
    residual_coherence = full["residual_coherence"]
    minimum_snr = full["minimum_snr"]
    qualified = full["qualified"]
    split_phasors: list[complex] = []
    for split in (slice(None, None, 2), slice(1, None, 2)):
        split_fits = tuple(
            joint_complex_fit(iq[samples[split], receiver], designs[receiver][split])
            for receiver in (0, 1)
        )
        split_phasors.append(
            complex(covariance_corrected_dd(split_fits[0], split_fits[1])["corrected_phasor"])
        )
    half_rows = []
    midpoint = len(samples) // 2
    for indices in (slice(0, midpoint), slice(midpoint, None)):
        subset = _subset_dd(
            iq,
            samples[indices],
            (designs[0][indices], designs[1][indices]),
            (control_designs[0][indices], control_designs[1][indices]),
            receiver_offset_hz,
            sample_rate_hz,
            common_reference_sample,
        )
        half_rows.append(
            {
                "qualified": subset["qualified"],
                "corrected_phase_deg": math.degrees(
                    float(np.angle(subset["dd"]["corrected_phasor"]))
                ),
                "corrected_phasor_real": complex(subset["dd"]["corrected_phasor"]).real,
                "corrected_phasor_imag": complex(subset["dd"]["corrected_phasor"]).imag,
                "minimum_coefficient_snr": subset["minimum_snr"],
                "exact_to_control_explained_ratio": subset["exact_control_ratio"],
                "cross_receiver_residual_coherence": subset["residual_coherence"],
            }
        )
    half_disagreement = None
    if all(row["qualified"] for row in half_rows):
        half_disagreement = math.degrees(
            abs(
                float(
                    np.angle(
                        np.exp(1j * math.radians(half_rows[1]["corrected_phase_deg"]))
                        * np.exp(-1j * math.radians(half_rows[0]["corrected_phase_deg"]))
                    )
                )
            )
        )
    return {
        "qualified": qualified,
        "sample_start": int(samples[0]),
        "sample_end": int(samples[-1] + 1),
        "sample_count": len(samples),
        "gram_coherence": gram_coherence,
        "gram_condition": gram_condition,
        "minimum_coefficient_snr": minimum_snr,
        "exact_to_control_explained_ratio": exact_control_ratio,
        "cross_receiver_residual_coherence": residual_coherence,
        "corrected_phase_deg": math.degrees(float(np.angle(dd["corrected_phasor"]))),
        "naive_phase_deg": math.degrees(float(np.angle(dd["naive_phasor"]))),
        "corrected_phasor_real": complex(dd["corrected_phasor"]).real,
        "corrected_phasor_imag": complex(dd["corrected_phasor"]).imag,
        "naive_phasor_real": complex(dd["naive_phasor"]).real,
        "naive_phasor_imag": complex(dd["naive_phasor"]).imag,
        "noise_bias_fraction": dd["noise_bias_fraction"],
        "receiver0_source_cross_covariance": [
            complex(dd["receiver0_source_cross_covariance"]).real,
            complex(dd["receiver0_source_cross_covariance"]).imag,
        ],
        "receiver1_source_cross_covariance": [
            complex(dd["receiver1_source_cross_covariance"]).real,
            complex(dd["receiver1_source_cross_covariance"]).imag,
        ],
        "receiver_coefficient_snr": [list(fit.coefficient_snr) for fit in fits],
        "sample_parity_crossfit_phase_disagreement_deg": math.degrees(
            abs(float(np.angle(split_phasors[1] * np.conj(split_phasors[0]))))
        ),
        "sample_parity_crossfit_phasors": [[value.real, value.imag] for value in split_phasors],
        "sample_parity_crossfit_is_independence_claim": False,
        "contiguous_sample_halves": half_rows,
        "contiguous_half_phase_disagreement_deg": half_disagreement,
    }


def _paired_frame_bootstrap(
    phasors: np.ndarray,
    *,
    seed: int,
    draws: int = 2_000,
) -> dict[str, float | list[float]]:
    """Conditional circular uncertainty with IID and adjacent-pair resampling."""
    values = np.asarray(phasors, np.complex128)
    nominal = float(np.angle(np.sum(values)))
    rng = np.random.default_rng(seed)
    iid_phases = np.empty(draws, dtype=float)
    adjacent_phases = np.empty(draws, dtype=float)
    adjacent_count = math.ceil(len(values) / 2)
    for index in range(draws):
        resampled = values[rng.integers(0, len(values), size=len(values))]
        iid_phases[index] = float(np.angle(np.sum(resampled)))
        starts = rng.integers(0, len(values), size=adjacent_count)
        adjacent = np.concatenate([values[[start, (start + 1) % len(values)]] for start in starts])[
            : len(values)
        ]
        adjacent_phases[index] = float(np.angle(np.sum(adjacent)))
    iid_errors = np.angle(np.exp(1j * (iid_phases - nominal)))
    adjacent_errors = np.angle(np.exp(1j * (adjacent_phases - nominal)))
    return {
        "conditional_iid_frame_phase_standard_error_deg": math.degrees(float(np.std(iid_errors))),
        "conditional_iid_frame_95_error_interval_deg": [
            math.degrees(float(value)) for value in np.quantile(iid_errors, (0.025, 0.975))
        ],
        "conditional_adjacent_pair_phase_standard_error_deg": math.degrees(
            float(np.std(adjacent_errors))
        ),
        "conditional_adjacent_pair_95_error_interval_deg": [
            math.degrees(float(value)) for value in np.quantile(adjacent_errors, (0.025, 0.975))
        ],
    }


def _alias_score(
    iq: np.ndarray,
    frame_pairs: list[tuple[int, int]],
    templates: tuple[np.ndarray, np.ndarray],
    frequencies_hz: tuple[float, float],
    aliases: tuple[int, int],
    receiver_offset_hz: float,
    sample_rate_hz: float,
    reference_sample: float,
) -> float:
    score = 0.0
    for starts in frame_pairs[: min(8, len(frame_pairs))]:
        shifted = tuple(
            frequency + alias * SYMBOL_ALIAS_HZ
            for frequency, alias in zip(frequencies_hz, aliases, strict=True)
        )
        samples, design0, design1 = common_designs(
            templates,
            starts,
            shifted,
            receiver_offset_hz,
            sample_rate_hz,
            reference_sample,
        )
        for receiver, design in enumerate((design0, design1)):
            fit = joint_complex_fit(iq[samples, receiver], design)
            score += fit.explained_power / max(fit.residual_power, 1e-30)
    return score


def run(bulk_root: Path, overlap_evidence_path: Path, raw_evidence_path: Path) -> dict[str, Any]:
    overlap_document = json.loads(overlap_evidence_path.read_text(encoding="utf-8"))
    raw_document = json.loads(raw_evidence_path.read_text(encoding="utf-8"))
    overlap_by_visit = {row["visit_index"]: row for row in overlap_document["visits"]}
    raw_by_visit = {row["visit_index"]: row for row in raw_document["visits"]}
    store = AdaptiveHopIqStore(bulk_root, read_only=True)
    rows = []
    try:
        inspected = store.inspect(raw_document["session_id"])
        with AdaptiveHopAnalysisInputStore(store).source(raw_document["session_id"]) as source:
            rate = int(source.receipt.plan.geometry.sample_rate_hz)
            configuration = AdaptiveHopAnalysisConfigurationV1(
                sample_rate_hz=rate, probe_stride_ms=10
            )
            exact_template = np.asarray(qin_edge_pilot_frame(rate, "lower"), np.complex128)
            control_template = np.asarray(
                qin_edge_pilot_frame(rate, "lower", symbol_roll=CONTROL_SYMBOL_ROLL),
                np.complex128,
            )
            for visit_index in VISITS:
                analysis = analyze_adaptive_hop_visit(
                    source, visit_index, configuration=configuration
                )
                pairs = sorted(
                    _phase_blind_pairs(analysis),
                    key=lambda pair: pair[0].fractional_tracking_cfo_hz,
                )
                if len(pairs) != 2:
                    raise ValueError("frozen pilot visit no longer has two source pairs")
                epochs = tuple(pair[3] + pair[0].integer_epoch_sample for pair in pairs)
                frequencies = tuple(float(pair[0].fractional_tracking_cfo_hz) for pair in pairs)
                receiver_offset = float(raw_by_visit[visit_index]["train_peak"]["frequency_hz"])
                iq = source.read_visit(visit_index)
                lattices = frame_lattice_pairs(len(iq), rate, epochs, len(exact_template))
                qualified_blocks = [
                    block
                    for block in overlap_by_visit[visit_index]["source_overlap_evidence"]["blocks"]
                    if block["both_sources_qualified"] is True
                ]
                reference = len(iq) / 2
                eligible_frames = []
                for block in qualified_blocks:
                    begin = round(float(block["start_ms"]) * rate / 1_000)
                    end = begin + round(0.020 * rate)
                    for starts in lattices:
                        common_begin = max(starts) + round(2 * rate * OFDM_SYMBOL_DURATION_S)
                        common_end = min(starts) + min(
                            round(302 * rate * OFDM_SYMBOL_DURATION_S), len(exact_template)
                        )
                        if begin <= common_begin and common_end <= end:
                            eligible_frames.append((begin, starts))
                alias_rows = []
                for low_alias in (-1, 0, 1):
                    for high_alias in (-1, 0, 1):
                        alias_rows.append(
                            {
                                "aliases": [low_alias, high_alias],
                                "score": _alias_score(
                                    iq,
                                    [row[1] for row in eligible_frames],
                                    (exact_template, exact_template),
                                    frequencies,
                                    (low_alias, high_alias),
                                    receiver_offset,
                                    rate,
                                    reference,
                                ),
                            }
                        )
                alias_rows.sort(key=lambda row: row["score"], reverse=True)
                selected_aliases = tuple(alias_rows[0]["aliases"])
                alias_ratio = alias_rows[0]["score"] / max(alias_rows[1]["score"], 1e-30)
                shifted_frequencies = tuple(
                    frequency + alias * SYMBOL_ALIAS_HZ
                    for frequency, alias in zip(frequencies, selected_aliases, strict=True)
                )
                frame_rows = []
                for block_start, starts in eligible_frames:
                    samples, design0, design1 = common_designs(
                        (exact_template, exact_template),
                        starts,
                        shifted_frequencies,
                        receiver_offset,
                        rate,
                        reference,
                    )
                    _, control0, control1 = common_designs(
                        (control_template, control_template),
                        starts,
                        shifted_frequencies,
                        receiver_offset,
                        rate,
                        reference,
                    )
                    row = analyze_frame(
                        iq,
                        samples,
                        (design0, design1),
                        (control0, control1),
                        receiver_offset,
                        rate,
                        reference,
                    )
                    row["block_start_ms"] = 1_000 * block_start / rate
                    frame_rows.append(row)
                for row in frame_rows:
                    row["qualified"] = bool(
                        row["qualified"] and alias_ratio >= MINIMUM_ALIAS_WINNER_RUNNER_RATIO
                    )
                blocks = []
                for block in qualified_blocks:
                    start_ms = float(block["start_ms"])
                    selected = [row for row in frame_rows if row["block_start_ms"] == start_ms]
                    qualified = [row for row in selected if row["qualified"]]
                    phasors = np.asarray(
                        [
                            row["corrected_phasor_real"] + 1j * row["corrected_phasor_imag"]
                            for row in qualified
                        ]
                    )
                    naive_phasors = np.asarray(
                        [
                            row["naive_phasor_real"] + 1j * row["naive_phasor_imag"]
                            for row in qualified
                        ]
                    )
                    parity_phasors = [
                        np.asarray(
                            [
                                complex(*row["sample_parity_crossfit_phasors"][parity])
                                for row in qualified
                            ]
                        )
                        for parity in (0, 1)
                    ]
                    half_qualified = [
                        row
                        for row in qualified
                        if all(part["qualified"] for part in row["contiguous_sample_halves"])
                    ]
                    half_phasors = [
                        np.asarray(
                            [
                                complex(
                                    row["contiguous_sample_halves"][half]["corrected_phasor_real"],
                                    row["contiguous_sample_halves"][half]["corrected_phasor_imag"],
                                )
                                for row in half_qualified
                            ]
                        )
                        for half in (0, 1)
                    ]
                    state = (
                        "qualified"
                        if len(qualified) >= MINIMUM_QUALIFIED_FRAMES_PER_BLOCK
                        else "insufficient_qualified_frames"
                    )
                    block_result = {
                        "start_ms": start_ms,
                        "state": state,
                        "eligible_frame_count": len(selected),
                        "qualified_frame_count": len(qualified),
                        "wrapped_phase_deg": (
                            None
                            if not len(qualified)
                            else math.degrees(float(np.angle(np.sum(phasors))))
                        ),
                        "resultant": (
                            None
                            if not len(qualified)
                            else float(abs(np.sum(phasors)) / np.sum(abs(phasors)))
                        ),
                        "effective_weighted_frame_count": (
                            None
                            if not len(qualified)
                            else float(np.sum(abs(phasors)) ** 2 / np.sum(abs(phasors) ** 2))
                        ),
                        "covariance_correction_phase_shift_deg": (
                            None
                            if not len(qualified)
                            else math.degrees(
                                float(np.angle(np.sum(phasors) * np.conj(np.sum(naive_phasors))))
                            )
                        ),
                        "odd_even_frame_phase_disagreement_deg": (
                            None
                            if len(qualified) < 2
                            else math.degrees(
                                abs(
                                    float(
                                        np.angle(
                                            np.sum(phasors[1::2]) * np.conj(np.sum(phasors[0::2]))
                                        )
                                    )
                                )
                            )
                        ),
                        "sample_parity_aggregate_phase_disagreement_deg": (
                            None
                            if not len(qualified)
                            else math.degrees(
                                abs(
                                    float(
                                        np.angle(
                                            np.sum(parity_phasors[1])
                                            * np.conj(np.sum(parity_phasors[0]))
                                        )
                                    )
                                )
                            )
                        ),
                        "contiguous_half_qualified_frame_count": len(half_qualified),
                        "contiguous_half_aggregate_phase_disagreement_deg": (
                            None
                            if not len(half_qualified)
                            else math.degrees(
                                abs(
                                    float(
                                        np.angle(
                                            np.sum(half_phasors[1])
                                            * np.conj(np.sum(half_phasors[0]))
                                        )
                                    )
                                )
                            )
                        ),
                        "frames": selected,
                    }
                    if state == "qualified":
                        block_result.update(
                            _paired_frame_bootstrap(
                                phasors,
                                seed=visit_index * 1_000 + round(start_ms),
                            )
                        )
                    blocks.append(block_result)
                rows.append(
                    {
                        "visit_index": visit_index,
                        "source_epochs": list(epochs),
                        "source_tracking_frequencies_hz": list(frequencies),
                        "receiver_offset_authority_hz": receiver_offset,
                        "global_reference_sample": reference,
                        "paired_frame_count": len(lattices),
                        "eligible_frame_count": len(eligible_frames),
                        "selected_symbol_aliases": list(selected_aliases),
                        "alias_winner_runner_ratio": alias_ratio,
                        "alias_scores": alias_rows,
                        "qualified_block_count": sum(
                            block["state"] == "qualified" for block in blocks
                        ),
                        "blocks": blocks,
                    }
                )
    finally:
        store.close()
    body = {
        "schema_version": 1,
        "kind": "adaptive_dual_rx_covariance_corrected_matched_pilot_dd_research",
        "session_id": raw_document["session_id"],
        "input_manifest_sha256": inspected.manifest_sha256,
        "raw_authority_evidence_sha256": raw_document["evidence_sha256"],
        "source_overlap_evidence_sha256": overlap_document["evidence_sha256"],
        "selection_uses_phase": False,
        "catalog_identity_claimed": False,
        "noise_bias_correction": (
            "subtract sigma_squared_times_inverse_gram_source_cross_covariance_"
            "within_each_receiver_before_receiver_product"
        ),
        "qualification": {
            "minimum_coefficient_snr": MINIMUM_COEFFICIENT_SNR,
            "maximum_gram_condition": MAXIMUM_GRAM_CONDITION,
            "minimum_exact_to_control_explained_ratio": MINIMUM_EXACT_TO_CONTROL_EXPLAINED_RATIO,
            "minimum_alias_winner_runner_ratio": MINIMUM_ALIAS_WINNER_RUNNER_RATIO,
            "maximum_noise_bias_fraction": MAXIMUM_NOISE_BIAS_FRACTION,
            "maximum_cross_receiver_residual_coherence": MAXIMUM_CROSS_RECEIVER_RESIDUAL_COHERENCE,
            "minimum_qualified_frames_per_block": MINIMUM_QUALIFIED_FRAMES_PER_BLOCK,
        },
        "rows": rows,
    }
    body["evidence_sha256"] = sha256_digest(canonical_json_bytes(body))
    return body


def render(document: dict[str, Any], path: Path) -> None:
    figure, axes = plt.subplots(2, 1, figsize=(10, 8), layout="constrained")
    for row in document["rows"]:
        blocks = [block for block in row["blocks"] if block["state"] == "qualified"]
        axes[0].errorbar(
            [block["start_ms"] for block in blocks],
            [block["wrapped_phase_deg"] for block in blocks],
            yerr=[
                block["conditional_adjacent_pair_phase_standard_error_deg"]
                for block in blocks
            ],
            fmt="o-",
            capsize=3,
            label=f"visit {row['visit_index']}",
        )
        axes[1].plot(
            [block["start_ms"] for block in row["blocks"]],
            [block["qualified_frame_count"] for block in row["blocks"]],
            "o-",
            label=f"visit {row['visit_index']}",
        )
    axes[0].set_ylabel("covariance-corrected pilot DD (deg)")
    axes[0].set_xlabel("visit-local block start (ms)")
    axes[0].grid(alpha=0.25)
    axes[0].legend()
    axes[1].axhline(MINIMUM_QUALIFIED_FRAMES_PER_BLOCK, color="black", linestyle="--")
    axes[1].set_ylabel("qualified matched frames")
    axes[1].set_xlabel("visit-local block start (ms)")
    axes[1].grid(alpha=0.25)
    figure.suptitle("28d covariance-corrected matched-pilot simultaneous DD")
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--overlap-evidence", type=Path, required=True)
    parser.add_argument("--raw-evidence", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    args = parser.parse_args()
    document = run(args.bulk_root, args.overlap_evidence, args.raw_evidence)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    render(document, args.png)
    print(json.dumps({"evidence_sha256": document["evidence_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
