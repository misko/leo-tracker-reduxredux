from __future__ import annotations

import math

import numpy as np
import pytest

import leo.analysis.starlink.seeded_acquisition as seeded
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.seeded_acquisition import (
    KnownPilotModeSeed,
    PilotModeProposalOrigin,
    ResearchDisposition,
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
EPOCH_SAMPLE = 211
ABSOLUTE_CFO_HZ = 1_350.0


def _seed(
    epoch_sample: int = EPOCH_SAMPLE,
    absolute_cfo_hz: float = ABSOLUTE_CFO_HZ,
    rate_hz_s: float = 0.0,
    *,
    branch_id: str = "remaining-properties",
    digest_character: str = "e",
) -> KnownPilotModeSeed:
    return KnownPilotModeSeed(
        nominal_epoch_sample=epoch_sample,
        nominal_absolute_cfo_hz=absolute_cfo_hz,
        nominal_doppler_rate_hz_s=rate_hz_s,
        branch_id=branch_id,
        provenance_sha256=digest_character * 64,
    )


def _single_mode_config(*, global_fallback_enabled: bool = False) -> SeededPilotAcquisitionConfig:
    return SeededPilotAcquisitionConfig(
        local_epoch_radius_samples=0,
        local_cfo_radius_hz=0.0,
        retained_candidate_count=1,
        global_fallback_enabled=global_fallback_enabled,
        global_cfo_radius_hz=0.0,
        global_retained_candidate_count=4,
    )


def _frame_starts(epoch_sample: int, frame_period_ppm: float) -> tuple[int, ...]:
    period_samples = SAMPLE_RATE_HZ / FRAME_RATE_HZ * (1.0 + frame_period_ppm * 1e-6)
    template_size = round(SAMPLE_RATE_HZ / FRAME_RATE_HZ)
    starts = []
    frame_index = 0
    while True:
        start = epoch_sample + round(frame_index * period_samples)
        if start + template_size > WINDOW_SAMPLE_COUNT:
            return tuple(starts)
        starts.append(start)
        frame_index += 1


def _capture(
    *,
    epoch_sample: int = EPOCH_SAMPLE,
    absolute_cfo_hz: float = ABSOLUTE_CFO_HZ,
    rate_hz_s: float = 0.0,
    symbol_roll: int = 0,
    frame_period_ppm: float = 0.0,
    initial_phase_rad: float = 0.0,
    modulo_pi_flips: bool = True,
    snr_db: float | None = None,
    frame_payload: np.ndarray | None = None,
) -> np.ndarray:
    template = np.asarray(
        frame_payload
        if frame_payload is not None
        else qin_edge_pilot_frame(
            SAMPLE_RATE_HZ,
            StarlinkEdge.LOWER,
            symbol_roll=symbol_roll,
        ),
        dtype=np.complex128,
    )
    result = np.zeros(WINDOW_SAMPLE_COUNT, dtype=np.complex128)
    local_samples = np.arange(template.size, dtype=np.float64)
    local_time_s = local_samples / SAMPLE_RATE_HZ
    for frame_index, frame_start in enumerate(_frame_starts(epoch_sample, frame_period_ppm)):
        frame_time_s = frame_start / SAMPLE_RATE_HZ
        arbitrary_frame_phase = initial_phase_rad + 0.71 * math.sin(0.43 * frame_index)
        if modulo_pi_flips:
            arbitrary_frame_phase += math.pi * ((3 * frame_index + 1) % 2)
        phase_cycles = (
            absolute_cfo_hz + rate_hz_s * frame_time_s
        ) * local_time_s + 0.5 * rate_hz_s * local_time_s**2
        result[frame_start : frame_start + template.size] += template * np.exp(
            1j * arbitrary_frame_phase + 2j * np.pi * phase_cycles
        )

    if snr_db is not None:
        generator = np.random.default_rng(0x20260825)
        noise = generator.standard_normal(result.size) + 1j * generator.standard_normal(result.size)
        noise /= math.sqrt(float(np.vdot(noise, noise).real) / noise.size)
        signal_rms = math.sqrt(float(np.vdot(result, result).real) / result.size)
        result += signal_rms * 10.0 ** (-snr_db / 20.0) * noise
    return result


@pytest.mark.parametrize(
    ("snr_db", "rate_hz_s", "initial_phase_rad"),
    (
        pytest.param(18.0, -5_000.0, -2.3, id="snr18-rate-minus5000"),
        pytest.param(12.0, -2_500.0, 0.1, id="snr12-rate-minus2500"),
        pytest.param(6.0, 0.0, 1.7, id="snr6-zero-rate"),
        pytest.param(3.0, 2_500.0, -0.7, id="snr3-rate-plus2500"),
        pytest.param(0.0, 5_000.0, 2.8, id="snr0-rate-plus5000"),
    ),
)
def test_bounded_snr_rate_frame_phase_and_modulo_pi_sweep_recovers_mode(
    snr_db: float,
    rate_hz_s: float,
    initial_phase_rad: float,
) -> None:
    result = acquire_seeded_known_pilot_modes(
        _capture(
            rate_hz_s=rate_hz_s,
            initial_phase_rad=initial_phase_rad,
            modulo_pi_flips=True,
            snr_db=snr_db,
        ),
        SAMPLE_RATE_HZ,
        seed=_seed(rate_hz_s=rate_hz_s),
        edge=StarlinkEdge.LOWER,
        config=_single_mode_config(),
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.winner is not None
    assert result.winner.epoch_sample == EPOCH_SAMPLE
    assert result.winner.absolute_cfo_hz == ABSOLUTE_CFO_HZ
    assert result.winner.doppler_rate_hz_s == rate_hz_s
    assert result.winner.passing_block_count == 4
    assert result.winner.median_verify_score > 0.6
    assert result.winner.whole_window_verify_score is not None
    assert result.winner.whole_window_verify_score > 0.6
    assert result.winner.whole_window_consistent_with_blocks
    assert result.presence_disposition is ResearchDisposition.UNCALIBRATED_CANDIDATE
    assert result.code_specificity_disposition is ResearchDisposition.AMBIGUOUS
    assert not result.specificity_claimed


@pytest.mark.parametrize("frame_period_ppm", (-10.0, 10.0))
def test_small_deterministic_frame_lattice_drift_is_accepted_without_specificity_claim(
    frame_period_ppm: float,
) -> None:
    nominal_starts = _frame_starts(EPOCH_SAMPLE, 0.0)
    drifted_starts = _frame_starts(EPOCH_SAMPLE, frame_period_ppm)
    assert len(drifted_starts) == len(nominal_starts)
    assert 1 <= abs(drifted_starts[-1] - nominal_starts[-1]) <= 2

    result = acquire_seeded_known_pilot_modes(
        _capture(
            frame_period_ppm=frame_period_ppm,
            initial_phase_rad=0.37,
            modulo_pi_flips=True,
        ),
        SAMPLE_RATE_HZ,
        seed=_seed(),
        edge=StarlinkEdge.LOWER,
        config=_single_mode_config(),
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.winner is not None
    assert result.winner.passing_block_count >= 3
    assert result.winner.whole_window_consistent_with_blocks
    assert result.presence_disposition is ResearchDisposition.UNCALIBRATED_CANDIDATE
    assert result.code_specificity_disposition is ResearchDisposition.AMBIGUOUS
    assert not result.specificity_claimed


@pytest.mark.parametrize(
    "nonfinite",
    (
        pytest.param(complex(math.nan, 0.0), id="nan-real"),
        pytest.param(complex(math.inf, 0.0), id="inf-real"),
        pytest.param(complex(0.0, math.inf), id="inf-imaginary"),
    ),
)
def test_nonfinite_samples_fail_closed(nonfinite: complex) -> None:
    samples = np.zeros(8, dtype=np.complex128)
    samples[3] = nonfinite

    with pytest.raises(ValueError, match="samples must be finite"):
        acquire_seeded_known_pilot_modes(
            samples,
            SAMPLE_RATE_HZ,
            seed=_seed(),
            edge=StarlinkEdge.LOWER,
            config=_single_mode_config(),
        )


def test_per_subcarrier_deranged_code_is_rejected_even_with_global_fallback() -> None:
    deranged_frame, _ = seeded._orbit_breaking_control_payloads(
        SAMPLE_RATE_HZ,
        StarlinkEdge.LOWER,
    )
    seed = _seed(
        epoch_sample=123,
        absolute_cfo_hz=0.0,
        branch_id="deranged-code",
        digest_character="d",
    )
    result = acquire_seeded_known_pilot_modes(
        _capture(
            epoch_sample=123,
            absolute_cfo_hz=0.0,
            initial_phase_rad=-0.43,
            frame_payload=deranged_frame,
        ),
        SAMPLE_RATE_HZ,
        seed=seed,
        edge=StarlinkEdge.LOWER,
        config=_single_mode_config(global_fallback_enabled=True),
    )

    protected = next(
        mode
        for mode in result.retained_modes
        if mode.proposal_origin is PilotModeProposalOrigin.PROTECTED_SEED
    )
    assert result.status is NumericalStatus.COMPLETE
    assert result.global_fallback_attempted
    assert result.accepted_modes == ()
    assert result.winner is None
    assert protected.decision is ResearchEvidenceDecision.REJECTED
    assert protected.median_diagnostic_control_scores[0] == pytest.approx(1.0)
    assert result.presence_disposition is ResearchDisposition.NO_RESEARCH_CANDIDATE
    assert result.code_specificity_disposition is ResearchDisposition.UNASSESSED
    assert not result.specificity_claimed


def test_compensating_roll_and_epoch_shift_reports_code_specificity_ambiguity() -> None:
    actual_epoch = 123
    symbol_roll = 17
    compensating_shift = round(symbol_roll * SAMPLE_RATE_HZ * OFDM_SYMBOL_DURATION_S)
    compensated_epoch = actual_epoch + compensating_shift
    result = acquire_seeded_known_pilot_modes(
        _capture(
            epoch_sample=actual_epoch,
            absolute_cfo_hz=0.0,
            symbol_roll=symbol_roll,
            initial_phase_rad=1.13,
            modulo_pi_flips=True,
        ),
        SAMPLE_RATE_HZ,
        seed=_seed(
            epoch_sample=compensated_epoch,
            absolute_cfo_hz=0.0,
            branch_id="roll-epoch-equivalent",
            digest_character="f",
        ),
        edge=StarlinkEdge.LOWER,
        expected_symbol_roll=0,
        config=_single_mode_config(global_fallback_enabled=True),
    )

    assert compensating_shift == 187
    assert result.status is NumericalStatus.COMPLETE
    assert result.winner is not None
    assert result.winner.epoch_sample == compensated_epoch
    assert result.winner.median_verify_score > 0.8
    assert result.winner.whole_window_consistent_with_blocks
    assert not result.global_fallback_attempted
    assert result.presence_disposition is ResearchDisposition.UNCALIBRATED_CANDIDATE
    assert result.code_specificity_disposition is ResearchDisposition.AMBIGUOUS
    assert not result.specificity_claimed
