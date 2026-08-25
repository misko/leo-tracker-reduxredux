from __future__ import annotations

import math

import numpy as np
import pytest

import leo.analysis.starlink.seeded_acquisition as seeded
from leo.analysis.starlink.acquisition import (
    DEFAULT_ACQUIRE_SYMBOLS,
    NumericalStatus,
)
from leo.analysis.starlink.seeded_acquisition import (
    KnownPilotModeSeed,
    ResearchEvidenceDecision,
    SeededPilotAcquisitionConfig,
    acquire_seeded_known_pilot_modes,
)
from leo.analysis.starlink.templates import (
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    qin_edge_pilot_frame,
)
from leo.contracts.states import StarlinkEdge

SAMPLE_RATE_HZ = 2_500_000.0
WINDOW_SAMPLE_COUNT = round(0.075 * SAMPLE_RATE_HZ)
PROVENANCE_SHA256 = "d" * 64


def _config(**overrides: object) -> SeededPilotAcquisitionConfig:
    return SeededPilotAcquisitionConfig(global_fallback_enabled=False, **overrides)


def _seed(
    epoch_sample: int,
    absolute_cfo_hz: float = 0.0,
    doppler_rate_hz_s: float = 0.0,
) -> KnownPilotModeSeed:
    return KnownPilotModeSeed(
        nominal_epoch_sample=epoch_sample,
        nominal_absolute_cfo_hz=absolute_cfo_hz,
        nominal_doppler_rate_hz_s=doppler_rate_hz_s,
        branch_id="adversarial-trajectory",
        provenance_sha256=PROVENANCE_SHA256,
    )


def _symbol_sample_indexes(symbols: tuple[int, ...]) -> np.ndarray:
    return np.concatenate(
        tuple(
            np.arange(
                round(symbol * SAMPLE_RATE_HZ * OFDM_SYMBOL_DURATION_S),
                round((symbol + 1) * SAMPLE_RATE_HZ * OFDM_SYMBOL_DURATION_S),
            )
            for symbol in symbols
        )
    )


def _pilot_capture(
    *,
    epoch_sample: int,
    absolute_cfo_hz: float = 0.0,
    doppler_rate_hz_s: float = 0.0,
    edge: StarlinkEdge = StarlinkEdge.LOWER,
    symbol_roll: int = 0,
    additional_symbol_roll: int | None = None,
    active_symbols: tuple[int, ...] | None = None,
    noise_standard_deviation: float = 0.0,
) -> np.ndarray:
    template = np.asarray(
        qin_edge_pilot_frame(SAMPLE_RATE_HZ, edge, symbol_roll=symbol_roll),
        dtype=np.complex128,
    )
    if additional_symbol_roll is not None:
        template = template + qin_edge_pilot_frame(
            SAMPLE_RATE_HZ,
            edge,
            symbol_roll=additional_symbol_roll,
        )
    if active_symbols is not None:
        masked = np.zeros_like(template)
        indexes = _symbol_sample_indexes(active_symbols)
        masked[indexes] = template[indexes]
        template = masked

    result = np.zeros(WINDOW_SAMPLE_COUNT, dtype=np.complex128)
    local_samples = np.arange(template.size, dtype=np.float64)
    frame_index = 0
    while True:
        frame_start = epoch_sample + round(frame_index * SAMPLE_RATE_HZ / FRAME_RATE_HZ)
        if frame_start + template.size > result.size:
            break
        local_time_s = local_samples / SAMPLE_RATE_HZ
        frame_time_s = frame_start / SAMPLE_RATE_HZ
        phase_cycles = (
            absolute_cfo_hz + doppler_rate_hz_s * frame_time_s
        ) * local_time_s + 0.5 * doppler_rate_hz_s * local_time_s**2
        result[frame_start : frame_start + template.size] += template * np.exp(
            2j * np.pi * phase_cycles
        )
        frame_index += 1

    if noise_standard_deviation:
        generator = np.random.default_rng(20260825)
        noise = generator.standard_normal(result.size) + 1j * generator.standard_normal(result.size)
        result += noise_standard_deviation * noise / math.sqrt(2.0)
    return result


def _null_input(kind: str) -> tuple[np.ndarray, StarlinkEdge, KnownPilotModeSeed]:
    generator = np.random.default_rng(0x150802)
    if kind == "zero":
        values = np.zeros(WINDOW_SAMPLE_COUNT, dtype=np.complex128)
    elif kind == "gaussian":
        values = (
            generator.standard_normal(WINDOW_SAMPLE_COUNT)
            + 1j * generator.standard_normal(WINDOW_SAMPLE_COUNT)
        ) / math.sqrt(2.0)
    elif kind == "colored":
        white = (
            generator.standard_normal(WINDOW_SAMPLE_COUNT)
            + 1j * generator.standard_normal(WINDOW_SAMPLE_COUNT)
        ) / math.sqrt(2.0)
        kernel = 0.96 ** np.arange(48)
        values = np.convolve(white, kernel, mode="full")[:WINDOW_SAMPLE_COUNT]
        values /= math.sqrt(float(np.vdot(values, values).real) / values.size)
    elif kind == "impulsive":
        values = np.zeros(WINDOW_SAMPLE_COUNT, dtype=np.complex128)
        indexes = generator.choice(WINDOW_SAMPLE_COUNT, size=127, replace=False)
        phases = generator.uniform(-np.pi, np.pi, size=indexes.size)
        values[indexes] = 100.0 * np.exp(1j * phases)
    elif kind == "tone":
        indexes = np.arange(WINDOW_SAMPLE_COUNT)
        values = np.exp(2j * np.pi * 137_123.0 * indexes / SAMPLE_RATE_HZ)
    elif kind == "wrong_edge":
        values = _pilot_capture(
            epoch_sample=123,
            absolute_cfo_hz=800.0,
            edge=StarlinkEdge.LOWER,
        )
        return values, StarlinkEdge.UPPER, _seed(123, 800.0)
    else:  # pragma: no cover - the parametrization is closed
        raise AssertionError(kind)
    return values, StarlinkEdge.LOWER, _seed(127)


def test_exact_2p5_msps_frame_lattice_repeats_3333_3334_3333() -> None:
    epoch = 211
    period = SAMPLE_RATE_HZ / FRAME_RATE_HZ
    starts = tuple(epoch + round(index * period) for index in range(13))

    assert tuple(np.diff(starts)) == (3333, 3334, 3333) * 4
    for index, start in enumerate(starts):
        projected, first = seeded._project_epoch(epoch, start, period)
        assert first == start
        assert projected == start - start
        if index:
            _, next_frame = seeded._project_epoch(epoch, starts[index - 1] + 1, period)
            assert next_frame == start


def test_joint_sample_and_epoch_shift_preserves_candidate_evidence() -> None:
    epoch = 211
    shift = 37
    cfo_hz = 1_700.0
    config = _config(
        local_epoch_radius_samples=0,
        local_cfo_radius_hz=0.0,
        retained_candidate_count=1,
    )
    baseline = acquire_seeded_known_pilot_modes(
        _pilot_capture(epoch_sample=epoch, absolute_cfo_hz=cfo_hz),
        SAMPLE_RATE_HZ,
        seed=_seed(epoch, cfo_hz),
        edge=StarlinkEdge.LOWER,
        config=config,
    )
    shifted = acquire_seeded_known_pilot_modes(
        _pilot_capture(epoch_sample=epoch + shift, absolute_cfo_hz=cfo_hz),
        SAMPLE_RATE_HZ,
        seed=_seed(epoch + shift, cfo_hz),
        edge=StarlinkEdge.LOWER,
        config=config,
    )

    assert baseline.status is shifted.status is NumericalStatus.COMPLETE
    assert baseline.winner is not None and shifted.winner is not None
    assert shifted.winner.epoch_sample - baseline.winner.epoch_sample == shift
    assert shifted.winner.absolute_cfo_hz == baseline.winner.absolute_cfo_hz
    assert shifted.winner.acquire_score == pytest.approx(
        baseline.winner.acquire_score,
        abs=1e-12,
    )
    assert shifted.winner.median_verify_score == pytest.approx(
        baseline.winner.median_verify_score,
        abs=1e-12,
    )
    assert shifted.winner.median_exact_minus_control_margin == pytest.approx(
        baseline.winner.median_exact_minus_control_margin,
        abs=1e-12,
    )
    for original, moved in zip(
        baseline.winner.blocks,
        shifted.winner.blocks,
        strict=True,
    ):
        assert moved.first_frame_start_sample - original.first_frame_start_sample == shift
        assert moved.projected_epoch_sample - original.projected_epoch_sample == shift
        assert moved.frame_support == original.frame_support


@pytest.mark.parametrize(
    "kind",
    ("zero", "gaussian", "colored", "impulsive", "tone", "wrong_edge"),
)
def test_adversarial_null_classes_do_not_produce_a_candidate(kind: str) -> None:
    values, edge, seed = _null_input(kind)
    result = acquire_seeded_known_pilot_modes(
        values,
        SAMPLE_RATE_HZ,
        seed=seed,
        edge=edge,
        config=_config(
            local_epoch_radius_samples=0,
            local_cfo_radius_hz=0.0,
            retained_candidate_count=1,
        ),
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.winner is None
    assert result.accepted_modes == ()
    assert len(result.retained_modes) == 1
    assert result.retained_modes[0].decision is ResearchEvidenceDecision.REJECTED
    assert result.retained_modes[0].passing_block_count < 3
    assert not result.specificity_claimed


def test_even_only_proposal_decoy_is_rejected_by_odd_verification() -> None:
    epoch = 123
    cfo_hz = 800.0
    result = acquire_seeded_known_pilot_modes(
        _pilot_capture(
            epoch_sample=epoch,
            absolute_cfo_hz=cfo_hz,
            active_symbols=DEFAULT_ACQUIRE_SYMBOLS,
        ),
        SAMPLE_RATE_HZ,
        seed=_seed(epoch, cfo_hz),
        edge=StarlinkEdge.LOWER,
        config=_config(
            local_epoch_radius_samples=0,
            local_cfo_radius_hz=0.0,
            retained_candidate_count=1,
        ),
    )

    assert result.winner is None
    assert len(result.retained_modes) == 1
    decoy = result.retained_modes[0]
    assert decoy.acquire_score == pytest.approx(1.0)
    assert decoy.median_verify_score == 0.0
    assert decoy.passing_block_count == 0
    assert decoy.decision is ResearchEvidenceDecision.REJECTED


def test_moderate_noise_cfo_and_rate_recover_the_injected_local_mode() -> None:
    actual_epoch = 321
    actual_cfo_hz = 1_250.0
    doppler_rate_hz_s = -3_200.0
    result = acquire_seeded_known_pilot_modes(
        _pilot_capture(
            epoch_sample=actual_epoch,
            absolute_cfo_hz=actual_cfo_hz,
            doppler_rate_hz_s=doppler_rate_hz_s,
            noise_standard_deviation=0.35,
        ),
        SAMPLE_RATE_HZ,
        seed=_seed(319, 1_150.0, doppler_rate_hz_s),
        edge=StarlinkEdge.LOWER,
        config=_config(
            local_epoch_radius_samples=2,
            local_cfo_radius_hz=100.0,
            local_cfo_step_hz=50.0,
            retained_candidate_count=4,
        ),
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.winner is not None
    assert result.winner.epoch_sample == actual_epoch
    assert result.winner.absolute_cfo_hz == actual_cfo_hz
    assert result.winner.doppler_rate_hz_s == doppler_rate_hz_s
    assert result.winner.passing_block_count == 4
    assert result.winner.median_verify_score > 0.9
    assert result.winner.median_exact_minus_control_margin > 0.5


def test_conditional_roll_accepts_exact_rejects_wrong_and_rejects_ambiguity() -> None:
    epoch = 123
    cfo_hz = 800.0
    exact_config = _config(
        local_epoch_radius_samples=0,
        local_cfo_radius_hz=0.0,
        retained_candidate_count=1,
        control_symbol_rolls=(29, 53, 101),
    )
    exact = acquire_seeded_known_pilot_modes(
        _pilot_capture(
            epoch_sample=epoch,
            absolute_cfo_hz=cfo_hz,
            symbol_roll=17,
        ),
        SAMPLE_RATE_HZ,
        seed=_seed(epoch, cfo_hz),
        edge=StarlinkEdge.LOWER,
        expected_symbol_roll=17,
        config=exact_config,
    )
    wrong = acquire_seeded_known_pilot_modes(
        _pilot_capture(
            epoch_sample=epoch,
            absolute_cfo_hz=cfo_hz,
            symbol_roll=17,
        ),
        SAMPLE_RATE_HZ,
        seed=_seed(epoch, cfo_hz),
        edge=StarlinkEdge.LOWER,
        expected_symbol_roll=0,
        config=_config(
            local_epoch_radius_samples=0,
            local_cfo_radius_hz=0.0,
            retained_candidate_count=1,
        ),
    )
    ambiguous = acquire_seeded_known_pilot_modes(
        _pilot_capture(
            epoch_sample=epoch,
            absolute_cfo_hz=cfo_hz,
            symbol_roll=0,
            additional_symbol_roll=17,
        ),
        SAMPLE_RATE_HZ,
        seed=_seed(epoch, cfo_hz),
        edge=StarlinkEdge.LOWER,
        expected_symbol_roll=0,
        config=_config(
            local_epoch_radius_samples=0,
            local_cfo_radius_hz=0.0,
            retained_candidate_count=1,
        ),
    )

    assert exact.winner is not None
    assert exact.winner.median_verify_score == pytest.approx(1.0)
    assert wrong.winner is None
    assert (
        wrong.retained_modes[0].median_control_score > wrong.retained_modes[0].median_verify_score
    )
    assert ambiguous.winner is None
    assert ambiguous.retained_modes[0].median_verify_score > 0.5
    assert ambiguous.retained_modes[0].median_exact_minus_control_margin < 0.02
