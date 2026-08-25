#!/usr/bin/env python3
"""Bounded cross-fit fractional-grid timing prototype for Aug-25 anchor 016.

This is a research microprobe, not a persisted product.  The integer 750 Hz
frame lattice is frozen before looking at the timing surface.  A trajectory
model may center the within-frame CFO search, but it cannot move any integer
frame tooth.  Contiguous early and late Pluto-refill blocks cross-fit one
constant fractional delay and CFO correction in both directions.  Interleaved
even/odd frame results are retained only as a secondary diagnostic.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.qam import estimate_edge_pilot_frame_complex_split  # noqa: E402
from leo.analysis.qam.pilot import _KnownPilotDemodulator  # noqa: E402
from leo.analysis.starlink.templates import (  # noqa: E402
    CONTROL_SYMBOL_ROLL,
    CYCLIC_PREFIX_DURATION_S,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    StarlinkEdge,
    edge_frequencies_hz,
    qin_edge_pilot_frame,
    qin_edge_pilot_symbols,
)
from leo.storage import PinnedLocalRoot, RecordingStore  # noqa: E402

BULK_ROOT = Path("/srv/bulk/leo")
OUTPUT_ROOT = Path("/tmp/fine-grid-anchor016-prototype")
SESSION_ID = "cap-20260825T150802-473cb5bbcbd6"
STREAM_ID = "stream-1"
RECEIVER_ID = 1
EDGE = StarlinkEdge.UPPER
RATE = 2_500_000
EXPECTED_MANIFEST = "sha256:ab55917851a9cd37af94b6145cc719f7b8d9d0809f2202a2dcd1ac38c3e7a31e"

ANCHOR_ID = "persisted-branch-anchor-016"
ACQUISITION_START = 113_687_500
ACQUISITION_STOP = 113_737_500
ABSOLUTE_EPOCH = 113_688_708
ANCHOR_CFO_HZ = -121_901.40927889547
ANCHOR_EXACT_SCORE = 0.6110410215473684
ANCHOR_CONTROL_SCORE = 0.03487542620330337
INTERVAL_START = 113_737_500
INTERVAL_STOP = 115_050_000

MODEL_REFERENCE_TIME_S = 37.575
MODEL_RATE_HZ_S = -3_568.45195795211
MODEL_INTERCEPT_HZ = -93_809.55647388805

COARSE_DELAY = np.linspace(-0.75, 0.75, 301)
# The first bounded ±250 Hz control search hit both edges.  Expand exact and
# rolled-17 symmetrically once, predeclared here, and fail if either hits ±500.
COARSE_CFO_OFFSET = np.linspace(-500.0, 500.0, 41)
PILOT_TIMES_S = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
PILOT_TIMES_S -= np.mean(PILOT_TIMES_S)
TONE_FREQUENCIES_HZ = edge_frequencies_hz(EDGE)


@dataclass(frozen=True, slots=True)
class Frame:
    lattice_index: int
    start_sample: int
    time_s: float
    model_absolute_cfo_hz: float
    model_residual_cfo_hz: float
    refill_index: int
    public_training_supported: bool
    public_even_search_boundary: bool
    public_odd_search_boundary: bool


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.shape[1:] != (1, 2):
        raise ValueError("expected one selected CI16 receiver")
    return np.asarray(
        (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / 2**15,
        dtype=np.complex128,
    )


def _lattice_start(index: int) -> int:
    return ABSOLUTE_EPOCH + round(index * RATE / FRAME_RATE_HZ)


def _model_cfo(time_s: float) -> float:
    return MODEL_INTERCEPT_HZ + MODEL_RATE_HZ_S * (time_s - MODEL_REFERENCE_TIME_S)


def _surface_one(
    matched: np.ndarray,
    residual_cfo_hz: np.ndarray,
    delays: np.ndarray,
) -> np.ndarray:
    """Profile one frame over CFO/delay with one complex scalar nuisance."""

    rotations = np.exp(-2j * np.pi * residual_cfo_hz[:, None] * PILOT_TIMES_S[None, :])
    channels = np.einsum("cs,sk->ck", rotations, matched, optimize=True)
    ramps = np.exp(-2j * np.pi * delays[:, None] * TONE_FREQUENCIES_HZ[None, :] / RATE)
    projections = np.einsum("dk,ck->dc", ramps, channels, optimize=True)
    # One scalar complex nuisance spans all 300x8 pilot values.  Cauchy's
    # ceiling therefore contains the full element count, not only symbols.
    ceiling = matched.size * float(np.sum(np.abs(matched) ** 2))
    return np.abs(projections) ** 2 / max(ceiling, np.finfo(float).tiny)


def _analytic_time_template(delay_samples: float, *, symbol_roll: int = 0) -> np.ndarray:
    """Evaluate the published eight-tone waveform at a fractional sample shift."""

    count = round(RATE / FRAME_RATE_HZ)
    time_s = (np.arange(count, dtype=float) - delay_samples) / RATE
    symbol_index = np.floor(time_s / OFDM_SYMBOL_DURATION_S).astype(int)
    output = np.zeros(count, dtype=np.complex128)
    symbols = qin_edge_pilot_symbols(EDGE, symbol_roll=symbol_roll)
    for index in range(2, 302):
        selected = np.flatnonzero(symbol_index == index)
        if not selected.size:
            continue
        local_time_s = time_s[selected] - index * OFDM_SYMBOL_DURATION_S
        output[selected] = np.sum(
            symbols[index - 2][None, :]
            * np.exp(
                2j
                * np.pi
                * TONE_FREQUENCIES_HZ[None, :]
                * (local_time_s[:, None] - CYCLIC_PREFIX_DURATION_S)
            ),
            axis=1,
        ) / math.sqrt(8)
    return output


def _windowed_sinc_shift(
    base: np.ndarray, delay_samples: float, *, half_width: int = 16
) -> np.ndarray:
    """Shift one padded integer template with a finite symmetric Lanczos kernel."""

    count = len(base)
    target = np.arange(count, dtype=float) - delay_samples
    center = np.floor(target).astype(int)
    offsets = np.arange(-half_width, half_width + 1)
    indexes = center[:, None] + offsets[None, :]
    difference = target[:, None] - indexes
    weights = np.sinc(difference) * np.sinc(difference / (half_width + 1))
    valid = (indexes >= 0) & (indexes < count)
    clipped = np.clip(indexes, 0, count - 1)
    weights *= valid
    normalizer = np.sum(weights, axis=1)
    weights = np.divide(
        weights,
        normalizer[:, None],
        out=np.zeros_like(weights),
        where=np.abs(normalizer[:, None]) > 1e-12,
    )
    return np.sum(base[clipped] * weights, axis=1)


def _time_template_bank(
    delays: np.ndarray,
    *,
    symbol_roll: int,
    implementation: str,
) -> np.ndarray:
    if implementation == "analytic":
        return np.asarray(
            [_analytic_time_template(float(value), symbol_roll=symbol_roll) for value in delays]
        )
    if implementation == "windowed_sinc":
        base = np.asarray(
            qin_edge_pilot_frame(RATE, EDGE, symbol_roll=symbol_roll),
            dtype=np.complex128,
        )
        return np.asarray([_windowed_sinc_shift(base, float(value)) for value in delays])
    raise ValueError(f"unknown time-template implementation {implementation!r}")


def _time_template_banks(
    delays: np.ndarray,
    *,
    symbol_roll: int,
    implementation: str,
) -> dict[int, np.ndarray]:
    """Build replicas for all fixed-lattice rounding classes.

    A frame starts at ``round(epoch + k Fs/750)``.  If that tooth differs
    from the rational lattice by ``r`` samples, a global delay hypothesis
    delta must use the local replica delay ``delta-r``.  At 2.5 MHz the only
    rounding values are -1/3, 0, and +1/3 sample.
    """

    return {
        thirds: _time_template_bank(
            delays - thirds / 3.0,
            symbol_roll=symbol_roll,
            implementation=implementation,
        )
        for thirds in (-1, 0, 1)
    }


def _time_profile(
    template_banks: dict[int, np.ndarray],
    raw_frames: np.ndarray,
    frame_indexes: np.ndarray,
    absolute_cfo_hz: np.ndarray,
    rounding_thirds: np.ndarray,
) -> np.ndarray:
    if frame_indexes.size == 0:
        raise ValueError("direct-time fold contains no frames")
    sample_time_s = np.arange(raw_frames.shape[1], dtype=float) / RATE
    output = np.zeros(next(iter(template_banks.values())).shape[0], dtype=float)
    for thirds, templates in template_banks.items():
        selected_indexes = frame_indexes[rounding_thirds[frame_indexes] == thirds]
        if selected_indexes.size == 0:
            continue
        selected = raw_frames[selected_indexes]
        rotations = np.exp(
            -2j * np.pi * absolute_cfo_hz[selected_indexes, None] * sample_time_s[None, :]
        )
        corrected = selected * rotations
        correlations = np.conj(templates) @ corrected.T
        template_energy = np.sum(np.abs(templates) ** 2, axis=1)
        received_energy = np.sum(np.abs(selected) ** 2, axis=1)
        denominator = template_energy[:, None] * received_energy[None, :]
        scores = np.divide(
            np.abs(correlations) ** 2,
            denominator,
            out=np.zeros_like(correlations.real),
            where=denominator > 0,
        )
        output += np.sum(scores, axis=1)
    return output / len(frame_indexes)


def _time_score(
    template_banks: dict[int, np.ndarray],
    raw_frames: np.ndarray,
    frame_indexes: np.ndarray,
    absolute_cfo_hz: np.ndarray,
    rounding_thirds: np.ndarray,
) -> float:
    return float(
        _time_profile(
            template_banks,
            raw_frames,
            frame_indexes,
            absolute_cfo_hz,
            rounding_thirds,
        )[0]
    )


def _time_surface(
    template_banks: dict[int, np.ndarray],
    raw_frames: np.ndarray,
    frame_indexes: np.ndarray,
    model_absolute_cfo_hz: np.ndarray,
    cfo_offsets_hz: np.ndarray,
    rounding_thirds: np.ndarray,
) -> np.ndarray:
    delay_count = next(iter(template_banks.values())).shape[0]
    output = np.empty((delay_count, len(cfo_offsets_hz)), dtype=float)
    for column, offset in enumerate(cfo_offsets_hz):
        output[:, column] = _time_profile(
            template_banks,
            raw_frames,
            frame_indexes,
            model_absolute_cfo_hz + float(offset),
            rounding_thirds,
        )
    return output


def _select_direct_time_model(
    *,
    symbol_roll: int,
    implementation: str,
    coarse_template_banks: dict[int, np.ndarray],
    raw_frames: np.ndarray,
    indexes: np.ndarray,
    model_absolute_cfo_hz: np.ndarray,
    rounding_thirds: np.ndarray,
) -> tuple[dict[str, float | bool], np.ndarray]:
    coarse = _time_surface(
        coarse_template_banks,
        raw_frames,
        indexes,
        model_absolute_cfo_hz,
        COARSE_CFO_OFFSET,
        rounding_thirds,
    )
    row, column = _winner(coarse, COARSE_DELAY, COARSE_CFO_OFFSET)
    coarse_interior = bool(
        0 < row < len(COARSE_DELAY) - 1 and 0 < column < len(COARSE_CFO_OFFSET) - 1
    )
    delay = float(COARSE_DELAY[row])
    cfo = float(COARSE_CFO_OFFSET[column])
    score = float(coarse[row, column])
    refined = False
    refinement_interior = False
    if coarse_interior:
        fine_delay = delay + np.linspace(-0.025, 0.025, 51)
        fine_cfo = cfo + np.linspace(-25.0, 25.0, 21)
        fine_template_banks = _time_template_banks(
            fine_delay,
            symbol_roll=symbol_roll,
            implementation=implementation,
        )
        fine = _time_surface(
            fine_template_banks,
            raw_frames,
            indexes,
            model_absolute_cfo_hz,
            fine_cfo,
            rounding_thirds,
        )
        fine_row, fine_column = _winner(fine, fine_delay, fine_cfo)
        delay = float(fine_delay[fine_row])
        cfo = float(fine_cfo[fine_column])
        score = float(fine[fine_row, fine_column])
        refined = True
        refinement_interior = bool(
            0 < fine_row < len(fine_delay) - 1 and 0 < fine_column < len(fine_cfo) - 1
        )
    return (
        {
            "delay_samples": delay,
            "cfo_offset_hz": cfo,
            "training_score": score,
            "coarse_maximum_interior": coarse_interior,
            "numerically_refined": refined,
            "refinement_maximum_interior": refinement_interior,
        },
        coarse,
    )


def _aggregate_surface(
    matched: np.ndarray,
    frame_indexes: np.ndarray,
    model_residual_hz: np.ndarray,
    delays: np.ndarray,
    cfo_offsets_hz: np.ndarray,
) -> np.ndarray:
    if frame_indexes.size == 0:
        raise ValueError("surface fold contains no frames")
    total = np.zeros((len(delays), len(cfo_offsets_hz)), dtype=float)
    for index in frame_indexes:
        total += _surface_one(
            matched[index],
            model_residual_hz[index] + cfo_offsets_hz,
            delays,
        )
    return total / len(frame_indexes)


def _winner(
    surface: np.ndarray,
    delays: np.ndarray,
    cfo_offsets_hz: np.ndarray,
) -> tuple[int, int]:
    maximum = float(np.max(surface))
    candidates = np.argwhere(np.isclose(surface, maximum, rtol=0.0, atol=1e-15))
    row, column = min(
        ((int(value[0]), int(value[1])) for value in candidates),
        key=lambda value: (
            abs(float(delays[value[0]])),
            abs(float(cfo_offsets_hz[value[1]])),
            float(delays[value[0]]),
            float(cfo_offsets_hz[value[1]]),
        ),
    )
    return row, column


def _score_point(
    matched: np.ndarray,
    frame_indexes: np.ndarray,
    model_residual_hz: np.ndarray,
    delay: float,
    cfo_offset_hz: float,
) -> float:
    return float(
        _aggregate_surface(
            matched,
            frame_indexes,
            model_residual_hz,
            np.asarray([delay]),
            np.asarray([cfo_offset_hz]),
        )[0, 0]
    )


def _select_model(
    matched: np.ndarray,
    indexes: np.ndarray,
    model_residual_hz: np.ndarray,
) -> tuple[dict[str, float | bool], np.ndarray]:
    coarse = _aggregate_surface(
        matched,
        indexes,
        model_residual_hz,
        COARSE_DELAY,
        COARSE_CFO_OFFSET,
    )
    coarse_row, coarse_column = _winner(coarse, COARSE_DELAY, COARSE_CFO_OFFSET)
    coarse_interior = bool(
        0 < coarse_row < len(COARSE_DELAY) - 1 and 0 < coarse_column < len(COARSE_CFO_OFFSET) - 1
    )
    selected_delay = float(COARSE_DELAY[coarse_row])
    selected_cfo = float(COARSE_CFO_OFFSET[coarse_column])
    selected_score = float(coarse[coarse_row, coarse_column])
    refined = False
    refinement_interior = False
    if coarse_interior:
        fine_delay = selected_delay + np.linspace(-0.025, 0.025, 51)
        fine_cfo = selected_cfo + np.linspace(-25.0, 25.0, 21)
        fine = _aggregate_surface(
            matched,
            indexes,
            model_residual_hz,
            fine_delay,
            fine_cfo,
        )
        fine_row, fine_column = _winner(fine, fine_delay, fine_cfo)
        selected_delay = float(fine_delay[fine_row])
        selected_cfo = float(fine_cfo[fine_column])
        selected_score = float(fine[fine_row, fine_column])
        refined = True
        refinement_interior = bool(
            0 < fine_row < len(fine_delay) - 1 and 0 < fine_column < len(fine_cfo) - 1
        )
    return (
        {
            "delay_samples": selected_delay,
            "cfo_offset_hz": selected_cfo,
            "training_score": selected_score,
            "coarse_maximum_interior": coarse_interior,
            "numerically_refined": refined,
            "refinement_maximum_interior": refinement_interior,
        },
        coarse,
    )


def _crossfit_direction(
    name: str,
    train: np.ndarray,
    holdout: np.ndarray,
    exact_matched: np.ndarray,
    control_matched: np.ndarray,
    model_residual_hz: np.ndarray,
) -> tuple[dict[str, object], np.ndarray]:
    exact, surface = _select_model(exact_matched, train, model_residual_hz)
    control, _ = _select_model(control_matched, train, model_residual_hz)

    zero_surface = _aggregate_surface(
        exact_matched,
        train,
        model_residual_hz,
        np.asarray([0.0]),
        COARSE_CFO_OFFSET,
    )[0]
    zero_column = int(np.argmax(zero_surface))
    zero_cfo = float(COARSE_CFO_OFFSET[zero_column])
    heldout_exact = _score_point(
        exact_matched,
        holdout,
        model_residual_hz,
        float(exact["delay_samples"]),
        float(exact["cfo_offset_hz"]),
    )
    heldout_integer = _score_point(
        exact_matched,
        holdout,
        model_residual_hz,
        0.0,
        zero_cfo,
    )
    heldout_control = _score_point(
        control_matched,
        holdout,
        model_residual_hz,
        float(control["delay_samples"]),
        float(control["cfo_offset_hz"]),
    )
    gain = heldout_exact - heldout_integer
    margin = heldout_exact - heldout_control
    result: dict[str, object] = {
        "direction": name,
        "training_frame_count": int(len(train)),
        "heldout_frame_count": int(len(holdout)),
        "exact_model": exact,
        "independently_selected_rolled17_model": control,
        "integer_baseline": {
            "delay_samples": 0.0,
            "training_selected_cfo_offset_hz": zero_cfo,
            "heldout_score": heldout_integer,
        },
        "heldout_exact_score": heldout_exact,
        "heldout_rolled17_score": heldout_control,
        "heldout_gain_over_integer": gain,
        "heldout_exact_minus_rolled17": margin,
        "gain_positive": bool(gain > 0.0),
        "rolled_margin_positive": bool(margin > 0.0),
        "maximum_interior": bool(
            exact["coarse_maximum_interior"] and exact["refinement_maximum_interior"]
        ),
    }
    return result, surface


def _direct_time_crossfit_direction(
    name: str,
    train: np.ndarray,
    holdout: np.ndarray,
    raw_frames: np.ndarray,
    model_absolute_cfo_hz: np.ndarray,
    rounding_thirds: np.ndarray,
    sinc_exact: dict[int, np.ndarray],
    analytic_exact: dict[int, np.ndarray],
    sinc_control: dict[int, np.ndarray],
) -> tuple[dict[str, object], np.ndarray]:
    """Select a direct-time delay/CFO cell and score unchanged heldout blocks."""

    exact, exact_surface = _select_direct_time_model(
        symbol_roll=0,
        implementation="windowed_sinc",
        coarse_template_banks=sinc_exact,
        raw_frames=raw_frames,
        indexes=train,
        model_absolute_cfo_hz=model_absolute_cfo_hz,
        rounding_thirds=rounding_thirds,
    )
    control, _ = _select_direct_time_model(
        symbol_roll=CONTROL_SYMBOL_ROLL,
        implementation="windowed_sinc",
        coarse_template_banks=sinc_control,
        raw_frames=raw_frames,
        indexes=train,
        model_absolute_cfo_hz=model_absolute_cfo_hz,
        rounding_thirds=rounding_thirds,
    )
    exact_absolute = model_absolute_cfo_hz + float(exact["cfo_offset_hz"])
    control_absolute = model_absolute_cfo_hz + float(control["cfo_offset_hz"])
    analytic_profile = _time_profile(
        analytic_exact,
        raw_frames,
        train,
        exact_absolute,
        rounding_thirds,
    )
    analytic_index = int(np.argmax(analytic_profile))

    # Give the delta=0 baseline the same local 2.5-Hz refinement as a candidate.
    zero_index = int(np.argmin(np.abs(COARSE_DELAY)))
    zero_column = int(np.argmax(exact_surface[zero_index]))
    zero_cfo_coarse = float(COARSE_CFO_OFFSET[zero_column])
    zero_fine_cfo = zero_cfo_coarse + np.linspace(-25.0, 25.0, 21)
    zero_banks = _time_template_banks(
        np.asarray([0.0]), symbol_roll=0, implementation="windowed_sinc"
    )
    zero_fine_surface = _time_surface(
        zero_banks,
        raw_frames,
        train,
        model_absolute_cfo_hz,
        zero_fine_cfo,
        rounding_thirds,
    )[0]
    zero_cfo = float(zero_fine_cfo[int(np.argmax(zero_fine_surface))])

    exact_delay = float(exact["delay_samples"])
    control_delay = float(control["delay_samples"])
    exact_banks = _time_template_banks(
        np.asarray([exact_delay]), symbol_roll=0, implementation="windowed_sinc"
    )
    control_banks = _time_template_banks(
        np.asarray([control_delay]),
        symbol_roll=CONTROL_SYMBOL_ROLL,
        implementation="windowed_sinc",
    )
    heldout_exact = _time_score(
        exact_banks,
        raw_frames,
        holdout,
        exact_absolute,
        rounding_thirds,
    )
    heldout_integer = _time_score(
        zero_banks,
        raw_frames,
        holdout,
        model_absolute_cfo_hz + zero_cfo,
        rounding_thirds,
    )
    heldout_control = _time_score(
        control_banks,
        raw_frames,
        holdout,
        control_absolute,
        rounding_thirds,
    )
    analytic_delay = float(COARSE_DELAY[analytic_index])
    exact_all_interior = bool(
        exact["coarse_maximum_interior"] and exact["refinement_maximum_interior"]
    )
    control_all_interior = bool(
        control["coarse_maximum_interior"] and control["refinement_maximum_interior"]
    )
    return (
        {
            "direction": name,
            "selection_note": (
                "padded windowed-sinc direct-time delay/CFO surface selects on "
                "training refill blocks; heldout refill blocks score unchanged cells"
            ),
            "training_frame_count": int(len(train)),
            "heldout_frame_count": int(len(holdout)),
            "exact_model": exact,
            "independently_selected_rolled17_model": control,
            "integer_baseline": {
                "delay_samples": 0.0,
                "coarse_selected_cfo_offset_hz": zero_cfo_coarse,
                "training_selected_cfo_offset_hz": zero_cfo,
                "cfo_refinement_step_hz": 2.5,
                "heldout_score": heldout_integer,
            },
            "primary_windowed_sinc_delay_samples": exact_delay,
            "analytic_delay_samples_at_exact_selected_cfo": analytic_delay,
            "analytic_vs_windowed_sinc_difference_samples": abs(exact_delay - analytic_delay),
            "heldout_exact_score": heldout_exact,
            "heldout_rolled17_score": heldout_control,
            "heldout_gain_over_integer": heldout_exact - heldout_integer,
            "heldout_exact_minus_rolled17": heldout_exact - heldout_control,
            "gain_positive": bool(heldout_exact > heldout_integer),
            "rolled_margin_positive": bool(heldout_exact > heldout_control),
            "exact_maximum_interior": exact_all_interior,
            "rolled17_maximum_interior": control_all_interior,
            "all_nuisance_maxima_interior": bool(exact_all_interior and control_all_interior),
            "analytic_maximum_interior": bool(0 < analytic_index < len(COARSE_DELAY) - 1),
            "analytic_vs_sinc_stable_lt_0p02": bool(abs(exact_delay - analytic_delay) < 0.02),
        },
        exact_surface,
    )


def _synthetic_qualification(
    exact_matched: np.ndarray,
    model_residual_hz: np.ndarray,
) -> dict[str, object]:
    """Run a bounded tone-cube numerical smoke test, not waveform qualification."""

    corrected = exact_matched * np.exp(
        -2j * np.pi * model_residual_hz[:, None, None] * PILOT_TIMES_S[None, :, None]
    )
    preliminary = np.mean(corrected, axis=1)
    reference = preliminary[0]
    phases = np.angle(preliminary @ np.conj(reference))
    aligned = preliminary * np.exp(-1j * phases)[:, None]
    channel = np.median(aligned.real, axis=0) + 1j * np.median(aligned.imag, axis=0)
    channel /= max(np.linalg.norm(channel), np.finfo(float).tiny)
    coefficients = np.einsum("fsk,k->f", corrected, np.conj(channel)) / (
        len(PILOT_TIMES_S) * max(float(np.vdot(channel, channel).real), 1e-20)
    )
    residuals = corrected - coefficients[:, None, None] * channel[None, None, :]
    amplitudes = np.abs(coefficients)

    noiseless = channel[None, :] * np.ones((len(PILOT_TIMES_S), 1), dtype=np.complex128)
    gauge_surface = _surface_one(noiseless, COARSE_CFO_OFFSET, COARSE_DELAY)
    gauge_row, _ = _winner(gauge_surface, COARSE_DELAY, COARSE_CFO_OFFSET)
    gauge_delay = float(COARSE_DELAY[gauge_row])

    generator = np.random.default_rng(0xA016)
    errors: list[float] = []
    discrepancies: list[float] = []
    branch_errors = 0
    trial_count = 96
    # Match one parity fold's information scale in the real 388-frame interval.
    # This is still independently generated; only the bounded frame count is reused.
    synthetic_frame_count = 384
    sim_indexes = np.arange(synthetic_frame_count)
    even = sim_indexes[sim_indexes % 2 == 0]
    odd = sim_indexes[sim_indexes % 2 == 1]
    zero_model = np.zeros(synthetic_frame_count, dtype=float)
    for _ in range(trial_count):
        allowable = max(0.05, 0.60 - abs(gauge_delay))
        true_delay = float(generator.uniform(-allowable, allowable))
        true_cfo = float(generator.uniform(-175.0, 175.0))
        cubes = np.empty((synthetic_frame_count, 300, 8), dtype=np.complex128)
        for frame_index in range(synthetic_frame_count):
            phase = generator.uniform(-math.pi, math.pi)
            amplitude = float(generator.choice(amplitudes))
            signal = (
                amplitude
                * np.exp(1j * phase)
                * channel[None, :]
                * np.exp(2j * np.pi * true_delay * TONE_FREQUENCIES_HZ[None, :] / RATE)
                * np.exp(2j * np.pi * true_cfo * PILOT_TIMES_S[:, None])
            )
            residual = residuals[int(generator.integers(len(residuals)))]
            residual_phase = np.exp(1j * generator.uniform(-math.pi, math.pi))
            cubes[frame_index] = signal + residual_phase * residual
        even_model, _ = _select_model(cubes, even, zero_model)
        odd_model, _ = _select_model(cubes, odd, zero_model)
        estimates = (
            float(even_model["delay_samples"]) - gauge_delay,
            float(odd_model["delay_samples"]) - gauge_delay,
        )
        estimate = float(np.mean(estimates))
        error = estimate - true_delay
        errors.append(error)
        discrepancies.append(abs(estimates[0] - estimates[1]))
        branch_errors += abs(error) > 0.5

    values = np.asarray(errors)
    discrepancy_values = np.asarray(discrepancies)
    bias = float(np.mean(values))
    rmse = float(np.sqrt(np.mean(values**2)))
    p95 = float(np.percentile(discrepancy_values, 95))
    branch_fraction = branch_errors / trial_count
    return {
        "status": "numerical_smoke_only_not_continuous_waveform_qualification",
        "generator": (
            "phase-randomized synthetic pilot cubes using a measured eight-tone channel, "
            "bootstrap amplitudes, and independently phase-randomized real-IQ residual cubes"
        ),
        "trial_count": trial_count,
        "frame_count_per_trial": synthetic_frame_count,
        "injected_delay_scope_samples": [
            -float(max(0.05, 0.60 - abs(gauge_delay))),
            float(max(0.05, 0.60 - abs(gauge_delay))),
        ],
        "injected_cfo_scope_hz": [-175.0, 175.0],
        "measured_channel_gauge_delay_samples": gauge_delay,
        "bias_samples": bias,
        "rmse_samples": rmse,
        "branch_error_fraction": branch_fraction,
        "parity_discrepancy_p95_samples": p95,
        "acceptance": {
            "absolute_bias_le_0p02": bool(abs(bias) <= 0.02),
            "rmse_le_0p05": bool(rmse <= 0.05),
            "branch_error_lt_0p01": bool(branch_fraction < 0.01),
        },
        "accepted": bool(abs(bias) <= 0.02 and rmse <= 0.05 and branch_fraction < 0.01),
    }


def _plot(
    path: Path,
    even_surface: np.ndarray,
    odd_surface: np.ndarray,
    directions: list[dict[str, object]],
    synthetic: dict[str, object],
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(12.5, 8.2), constrained_layout=True)
    for axis, surface, title in (
        (
            axes[0, 0],
            even_surface,
            "Early time blocks select; late time blocks held out",
        ),
        (
            axes[0, 1],
            odd_surface,
            "Late time blocks select; early time blocks held out",
        ),
    ):
        image = axis.imshow(
            surface,
            origin="lower",
            aspect="auto",
            extent=(COARSE_CFO_OFFSET[0], COARSE_CFO_OFFSET[-1], COARSE_DELAY[0], COARSE_DELAY[-1]),
            cmap="viridis",
        )
        axis.axhline(0.0, color="white", linewidth=1.0, linestyle="--", alpha=0.8)
        axis.set_title(title)
        axis.set_xlabel("CFO correction around frozen trajectory model (Hz)")
        axis.set_ylabel("Template-relative delay δ (samples)")
        figure.colorbar(image, ax=axis, label="training exact score")
    for axis, result in zip(axes[0], directions, strict=True):
        model = result["exact_model"]
        axis.scatter(
            [float(model["cfo_offset_hz"])],
            [float(model["delay_samples"])],
            marker="x",
            s=85,
            linewidths=2.0,
            color="#d62728",
            label="training-selected refined cell",
        )
        axis.legend(loc="upper right", fontsize=8)

    axes[1, 0].plot(
        COARSE_DELAY,
        np.max(even_surface, axis=1),
        label="early-time training profile",
        color="#2b6cb0",
    )
    axes[1, 0].plot(
        COARSE_DELAY,
        np.max(odd_surface, axis=1),
        label="late-time training profile",
        color="#c05621",
    )
    axes[1, 0].axvline(0.0, color="black", linestyle="--", linewidth=1.0, label="integer δ=0")
    axes[1, 0].set_xlabel("Template-relative delay δ (samples)")
    axes[1, 0].set_ylabel("Profile score (max over CFO)")
    axes[1, 0].set_title("No integer frame tooth was refit")
    axes[1, 0].grid(alpha=0.25)
    axes[1, 0].legend(fontsize=8)
    axes[1, 0].text(
        0.02,
        0.97,
        "Two-block implied rate +1.412 sample/s\n"
        "epoch-model derivative +1.338 sample/s\n"
        "diagnostic only; not refill causality",
        transform=axes[1, 0].transAxes,
        va="top",
        fontsize=8,
        bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "0.7"},
    )

    labels = ["early time→late", "late time→early"]
    gains = [float(item["heldout_gain_over_integer"]) for item in directions]
    margins = [float(item["heldout_exact_minus_rolled17"]) for item in directions]
    x = np.arange(2)
    width = 0.36
    axes[1, 1].bar(x - width / 2, gains, width, label="held-out gain vs integer δ=0")
    axes[1, 1].bar(x + width / 2, margins, width, label="held-out exact − rolled-17")
    axes[1, 1].axhline(0.0, color="black", linewidth=1.0)
    axes[1, 1].set_xticks(x, labels)
    axes[1, 1].set_ylabel("Normalized score difference")
    axes[1, 1].set_title(
        f"Blocked cross-fit; tone-cube smoke RMSE {float(synthetic['rmse_samples']):.3f} sample"
    )
    axes[1, 1].grid(axis="y", alpha=0.25)
    axes[1, 1].legend(fontsize=8)

    figure.suptitle(
        "Anchor 016 · fixed 750 Hz integer lattice · template-relative delay prototype\n"
        "δ is channel/template-relative, not absolute TOA or pseudorange",
        fontsize=13,
    )
    figure.savefig(path, dpi=180)
    plt.close(figure)


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    timings: dict[str, float] = {}
    capability = PinnedLocalRoot(BULK_ROOT)
    store: RecordingStore | None = None
    try:
        started = time.perf_counter()
        store = RecordingStore.open_pinned(capability)
        bundle = store.inspect(SESSION_ID)
        reader = store.reader(bundle, STREAM_ID, verify=True)
        if reader.manifest_digest != EXPECTED_MANIFEST:
            raise ValueError("recording manifest digest changed")
        if reader.sample_rate_hz != RATE or reader.sample_count != 150_000_000:
            raise ValueError("recording geometry changed")
        gap_map = reader.gap_map()
        if gap_map.boundaries or gap_map.segment_count != 1:
            raise ValueError("prototype requires one lossless device-coordinate segment")
        timeline = tuple(reader.iter_timeline_metadata())
        refill_boundaries = tuple(
            item.session_sample_start
            for item in timeline[1:]
            if INTERVAL_START < item.session_sample_start < INTERVAL_STOP
        )
        read_start = INTERVAL_START - 1
        span = reader.read_device_span(
            read_start,
            INTERVAL_STOP - INTERVAL_START + 2,
            receiver_ids=(RECEIVER_ID,),
        )
        if not np.all(span.valid_samples):
            raise ValueError("requested device span is not wholly observed")
        raw = span.samples
        timings["verified_read_and_inspection_s"] = time.perf_counter() - started
    finally:
        if store is not None:
            store.close()
        capability.close()

    iq = _complex_receiver(raw)
    frame_content = round(302 * RATE * OFDM_SYMBOL_DURATION_S)
    full_frame_samples = round(RATE / FRAME_RATE_HZ)
    reference_offset_samples = float(
        np.mean((np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S) * RATE
    )
    first_index = math.floor((INTERVAL_START - ABSOLUTE_EPOCH) * FRAME_RATE_HZ / RATE) - 1
    while _lattice_start(first_index) < INTERVAL_START:
        first_index += 1

    starts: list[tuple[int, int, int]] = []
    index = first_index
    while True:
        start = _lattice_start(index)
        if start + max(frame_content, full_frame_samples) > INTERVAL_STOP:
            break
        crossings = [
            value
            for value in refill_boundaries
            if start - 1 < value < start + max(frame_content + 1, full_frame_samples)
        ]
        if not crossings:
            refill_index = sum(value <= start for value in refill_boundaries)
            starts.append((index, start, refill_index))
        index += 1
    if len(starts) < 40:
        raise ValueError("too few refill-safe complete frames")

    exact = qin_edge_pilot_symbols(EDGE)
    control = qin_edge_pilot_symbols(EDGE, symbol_roll=CONTROL_SYMBOL_ROLL)
    demodulator = _KnownPilotDemodulator(iq, RATE, EDGE, ANCHOR_CFO_HZ)
    pilots: list[np.ndarray] = []
    raw_frames: list[np.ndarray] = []
    frames: list[Frame] = []
    started = time.perf_counter()
    for lattice_index, start, refill_index in starts:
        local_start = start - read_start
        pilot = demodulator.frame(local_start)
        pilots.append(pilot)
        raw_frames.append(iq[local_start : local_start + full_frame_samples])
        frame_time_s = (start + reference_offset_samples) / RATE
        model_absolute = _model_cfo(frame_time_s)
        guarded = iq[local_start - 1 : local_start + frame_content + 1]
        public = estimate_edge_pilot_frame_complex_split(
            guarded,
            RATE,
            frame_start_sample=start,
            acquisition_absolute_cfo_hz=model_absolute,
            edge=EDGE,
        )
        frames.append(
            Frame(
                lattice_index=lattice_index,
                start_sample=start,
                time_s=frame_time_s,
                model_absolute_cfo_hz=model_absolute,
                model_residual_cfo_hz=model_absolute - ANCHOR_CFO_HZ,
                refill_index=refill_index,
                public_training_supported=public.training_supported,
                public_even_search_boundary=bool(public.even and public.even.search_boundary),
                public_odd_search_boundary=bool(public.odd and public.odd.search_boundary),
            )
        )
    timings["demodulation_and_public_diagnostics_s"] = time.perf_counter() - started

    pilot_values = np.asarray(pilots, dtype=np.complex128)
    raw_frame_values = np.asarray(raw_frames, dtype=np.complex128)
    exact_matched = pilot_values * np.conj(exact)[None, :, :]
    control_matched = pilot_values * np.conj(control)[None, :, :]
    model_residual = np.asarray([value.model_residual_cfo_hz for value in frames])
    model_absolute = np.asarray([value.model_absolute_cfo_hz for value in frames])
    refill_ids = np.asarray([value.refill_index for value in frames])
    rounding_thirds = np.asarray(
        [
            int(
                round(
                    3
                    * (
                        value.start_sample
                        - (ABSOLUTE_EPOCH + value.lattice_index * RATE / FRAME_RATE_HZ)
                    )
                )
            )
            for value in frames
        ]
    )
    if not set(rounding_thirds).issubset({-1, 0, 1}):
        raise ValueError("unexpected rational-lattice rounding class")
    even_indexes = np.flatnonzero(np.asarray([value.lattice_index % 2 == 0 for value in frames]))
    odd_indexes = np.flatnonzero(np.asarray([value.lattice_index % 2 == 1 for value in frames]))
    unique_refills = np.unique(refill_ids)
    split_at = len(unique_refills) // 2
    early_refills = unique_refills[:split_at]
    late_refills = unique_refills[split_at:]
    early_indexes = np.flatnonzero(np.isin(refill_ids, early_refills))
    late_indexes = np.flatnonzero(np.isin(refill_ids, late_refills))

    # Interleaved parity is retained only as a secondary reproducibility check.
    started = time.perf_counter()
    even_to_odd, even_surface = _crossfit_direction(
        "even_frames_train__odd_frames_heldout",
        even_indexes,
        odd_indexes,
        exact_matched,
        control_matched,
        model_residual,
    )
    odd_to_even, odd_surface = _crossfit_direction(
        "odd_frames_train__even_frames_heldout",
        odd_indexes,
        even_indexes,
        exact_matched,
        control_matched,
        model_residual,
    )
    parity_directions = [even_to_odd, odd_to_even]
    leave_one_refill_out: list[dict[str, object]] = []
    per_refill_models: list[dict[str, object]] = []
    for refill in unique_refills:
        heldout = np.flatnonzero(refill_ids == refill)
        train = np.flatnonzero(refill_ids != refill)
        direction, _ = _crossfit_direction(
            f"all_other_refills_train__refill_{int(refill)}_heldout",
            train,
            heldout,
            exact_matched,
            control_matched,
            model_residual,
        )
        leave_one_refill_out.append(direction)
        local_model, _ = _select_model(exact_matched, heldout, model_residual)
        per_refill_models.append(
            {
                "refill_index": int(refill),
                "frame_count": int(len(heldout)),
                "delay_samples": float(local_model["delay_samples"]),
                "cfo_offset_hz": float(local_model["cfo_offset_hz"]),
            }
        )
    timings["secondary_tone_domain_diagnostics_s"] = time.perf_counter() - started

    started = time.perf_counter()
    analytic_exact = _time_template_banks(COARSE_DELAY, symbol_roll=0, implementation="analytic")
    sinc_exact = _time_template_banks(COARSE_DELAY, symbol_roll=0, implementation="windowed_sinc")
    sinc_control = _time_template_banks(
        COARSE_DELAY,
        symbol_roll=CONTROL_SYMBOL_ROLL,
        implementation="windowed_sinc",
    )
    direct_early_to_late, early_surface = _direct_time_crossfit_direction(
        "early_counter_continuous_time_blocks_train__late_blocks_heldout",
        early_indexes,
        late_indexes,
        raw_frame_values,
        model_absolute,
        rounding_thirds,
        sinc_exact,
        analytic_exact,
        sinc_control,
    )
    direct_late_to_early, late_surface = _direct_time_crossfit_direction(
        "late_counter_continuous_time_blocks_train__early_blocks_heldout",
        late_indexes,
        early_indexes,
        raw_frame_values,
        model_absolute,
        rounding_thirds,
        sinc_exact,
        analytic_exact,
        sinc_control,
    )
    direct_directions = [direct_early_to_late, direct_late_to_early]
    timings["primary_direct_time_blocked_crossfit_s"] = time.perf_counter() - started

    started = time.perf_counter()
    synthetic_smoke = _synthetic_qualification(exact_matched, model_residual)
    timings["synthetic_tone_cube_smoke_s"] = time.perf_counter() - started
    parity_discrepancy = abs(
        float(even_to_odd["exact_model"]["delay_samples"])
        - float(odd_to_even["exact_model"]["delay_samples"])
    )
    direct_block_discrepancy = abs(
        float(direct_early_to_late["exact_model"]["delay_samples"])
        - float(direct_late_to_early["exact_model"]["delay_samples"])
    )
    real_acceptance = {
        "primary_cohort": (
            "early versus late counter-continuous time blocks, bounded at Pluto refill handoffs"
        ),
        "blocked_gain_positive_both_directions": all(
            bool(value["gain_positive"]) for value in direct_directions
        ),
        "blocked_exact_minus_rolled17_positive_both_directions": all(
            bool(value["rolled_margin_positive"]) for value in direct_directions
        ),
        "blocked_all_exact_and_control_maxima_interior": all(
            bool(value["all_nuisance_maxima_interior"]) for value in direct_directions
        ),
        "analytic_vs_sinc_stable_both_directions": all(
            bool(value["analytic_vs_sinc_stable_lt_0p02"]) for value in direct_directions
        ),
        "direct_block_training_delay_discrepancy_samples": direct_block_discrepancy,
        "secondary_interleaved_parity_delay_discrepancy_samples": parity_discrepancy,
        "continuous_waveform_synthetic_qualification_passed": False,
    }
    real_acceptance["bounded_direct_blocked_criteria_passed"] = bool(
        real_acceptance["blocked_gain_positive_both_directions"]
        and real_acceptance["blocked_exact_minus_rolled17_positive_both_directions"]
        and real_acceptance["blocked_all_exact_and_control_maxima_interior"]
        and real_acceptance["analytic_vs_sinc_stable_both_directions"]
    )
    # Fail closed: the channel-relative gauge is not absolute timing, and the
    # separate continuous-waveform synthetic qualification was not completed.
    real_acceptance["promotion_gate_complete"] = False
    real_acceptance["accepted"] = False

    rows_path = OUTPUT_ROOT / "anchor016-frame-rows.json"
    rows = [
        {
            "lattice_index": value.lattice_index,
            "frame_start_sample": value.start_sample,
            "time_s": value.time_s,
            "fixed_integer_lattice_rounding_samples": float(
                value.start_sample - (ABSOLUTE_EPOCH + value.lattice_index * RATE / FRAME_RATE_HZ)
            ),
            "model_absolute_cfo_hz": value.model_absolute_cfo_hz,
            "model_residual_cfo_hz": value.model_residual_cfo_hz,
            "refill_index": value.refill_index,
            "public_training_supported": value.public_training_supported,
            "public_even_search_boundary": value.public_even_search_boundary,
            "public_odd_search_boundary": value.public_odd_search_boundary,
        }
        for value in frames
    ]
    rows_path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    plot_path = OUTPUT_ROOT / "anchor016-fine-grid-crossfit.png"
    _plot(
        plot_path,
        early_surface,
        late_surface,
        direct_directions,
        synthetic_smoke,
    )
    early_mean_time = float(np.mean([frames[value].time_s for value in early_indexes]))
    late_mean_time = float(np.mean([frames[value].time_s for value in late_indexes]))
    raw_block_rate = (
        float(direct_late_to_early["exact_model"]["delay_samples"])
        - float(direct_early_to_late["exact_model"]["delay_samples"])
    ) / (late_mean_time - early_mean_time)
    cubic_reference_rate = 1.33793
    evidence = {
        "schema": "org.leo.research.anchor016-fractional-grid-prototype/v1",
        "input": {
            "session_id": SESSION_ID,
            "stream_id": STREAM_ID,
            "receiver_id": RECEIVER_ID,
            "edge": EDGE.value,
            "sample_rate_hz": RATE,
            "manifest_sha256": EXPECTED_MANIFEST,
            "anchor_id": ANCHOR_ID,
            "acquisition_interval_samples": [ACQUISITION_START, ACQUISITION_STOP],
            "analysis_interval_samples": [INTERVAL_START, INTERVAL_STOP],
            "analysis_interval_s": [INTERVAL_START / RATE, INTERVAL_STOP / RATE],
            "absolute_integer_epoch_sample": ABSOLUTE_EPOCH,
            "anchor_cfo_hz": ANCHOR_CFO_HZ,
            "anchor_exact_score": ANCHOR_EXACT_SCORE,
            "anchor_control_score": ANCHOR_CONTROL_SCORE,
        },
        "frozen_geometry": {
            "integer_lattice": "epoch + round(k * Fs / 750); never fit from this surface",
            "positive_delay_convention": "delta > 0 means later waveform s[n-delta]",
            "rational_tooth_replica": (
                "each frame uses delta-r where r is its fixed rounded-tooth residual"
            ),
            "coarse_delay_samples": [-0.75, 0.75, 0.005],
            "coarse_cfo_correction_hz": [-500.0, 500.0, 25.0],
            "cfo_volume_note": (
                "exact and rolled-17 symmetrically expanded once after ±250-Hz controls hit bounds"
            ),
            "local_numeric_refinement": (
                "±0.025 sample at 0.001 and ±25 Hz at 2.5 Hz; interior coarse maxima only"
            ),
            "trajectory_cfo_center": {
                "reference_time_s": MODEL_REFERENCE_TIME_S,
                "rate_hz_s": MODEL_RATE_HZ_S,
                "intercept_hz": MODEL_INTERCEPT_HZ,
            },
            "complete_refill_safe_frame_count": len(frames),
            "even_frame_count": len(even_indexes),
            "odd_frame_count": len(odd_indexes),
            "early_refill_ids": [int(value) for value in early_refills],
            "late_refill_ids": [int(value) for value in late_refills],
            "early_block_frame_count": len(early_indexes),
            "late_block_frame_count": len(late_indexes),
            "refill_boundary_samples": list(refill_boundaries),
            "crossing_frames_excluded": (index - first_index) - len(frames),
        },
        "public_split_diagnostics": {
            "training_supported_count": sum(value.public_training_supported for value in frames),
            "even_search_boundary_count": sum(
                value.public_even_search_boundary for value in frames
            ),
            "odd_search_boundary_count": sum(value.public_odd_search_boundary for value in frames),
            "membership_note": (
                "diagnostic only; primary folds are contiguous groups of complete "
                "refill-safe frames"
            ),
        },
        "synthetic_evidence": {
            "tone_domain_numerical_smoke": synthetic_smoke,
            "continuous_waveform_qualification": {
                "completed": False,
                "passed": False,
                "reason": (
                    "the bounded run did not implement a generator independent of "
                    "the recovery replica with continuous bandlimited transitions"
                ),
            },
        },
        "real_crossfit": {
            "primary_direct_time_blocked_directions": direct_directions,
            "secondary_interleaved_tone_domain_directions": parity_directions,
            "secondary_leave_one_refill_out_tone_domain": leave_one_refill_out,
            "secondary_per_refill_tone_domain_models": per_refill_models,
            "conditional_differential_rate_comparison": {
                "status": "diagnostic_not_a_blocked_rate_model_fit",
                "raw_direct_two_block_rate_samples_s": raw_block_rate,
                "independent_cubic_epoch_derivative_samples_s": cubic_reference_rate,
                "absolute_difference_samples_s": abs(raw_block_rate - cubic_reference_rate),
                "note": (
                    "The two direct-time constant block estimates imply a sign-consistent "
                    "rate under the s[n-delta] convention, but this is not a heldout "
                    "delay-rate/curvature model test and is not refill causality."
                ),
            },
            "acceptance": real_acceptance,
        },
        "interpretation_limits": [
            (
                "The fractional delay is relative to the assumed Qin scalar template/channel "
                "gauge; it is not absolute propagation time, code phase, TOA, "
                "pseudorange, or range."
            ),
            (
                "With one eight-tone edge, a delay ramp is exchangeable with linear "
                "phase in unknown channel H_k; receiver/channel group delay can bias delta."
            ),
            (
                "The trajectory model centers only CFO. It never selects, bends, deletes, "
                "or refits the fixed 3333/3334-sample integer frame teeth."
            ),
            (
                "Each frame has an independent complex scalar phase/amplitude nuisance; "
                "no phase continuity is claimed across frames or Pluto refills."
            ),
            (
                "The rolled-17 control independently selects over the same delay/CFO "
                "volume before held-out scoring."
            ),
            (
                "The primary direct-time score searches a full two-dimensional delay/CFO "
                "surface on training blocks only; padded windowed-sinc replicas are "
                "primary and the discontinuous analytic replica is a stability check."
            ),
            (
                "A constant delay can average a time-varying residual. Interleaved parity "
                "is not temporal validation; early/late refill-block directions are primary."
            ),
            (
                "The conditional two-block slope comparison does not validate a delay-rate "
                "model; rate and curvature need their own blocked cross-fit before promotion."
            ),
        ],
        "artifacts": {
            "script": {"path": str(Path(__file__)), "sha256": _sha256(Path(__file__))},
            "rows": {"path": str(rows_path), "sha256": _sha256(rows_path)},
            "plot": {"path": str(plot_path), "sha256": _sha256(plot_path)},
        },
        "timings_s": timings,
    }
    evidence_path = OUTPUT_ROOT / "anchor016-fine-grid-evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(evidence_path)


if __name__ == "__main__":
    main()
