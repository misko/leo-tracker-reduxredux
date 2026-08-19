from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from leo.analysis.starlink import (
    NumericalStatus,
    ReceiverFrequencyCalibration,
    acquire_symbolwise,
    qin_edge_pilot_frame,
)

RATE = 2_500_000.0


def _injected(*, epoch: int, residual_cfo_hz: float, receiver_center_hz: float) -> np.ndarray:
    rng = np.random.default_rng(20260819)
    values = (
        rng.normal(0, 0.1 / np.sqrt(2), 14_000) + 1j * rng.normal(0, 0.1 / np.sqrt(2), 14_000)
    ).astype(np.complex128)
    template = qin_edge_pilot_frame(RATE)
    indexes = np.arange(template.size)
    absolute_cfo_hz = receiver_center_hz + residual_cfo_hz
    for frame in range(4):
        start = epoch + round(frame * RATE / 750.0)
        values[start + indexes] += (
            2 * np.exp(2j * np.pi * absolute_cfo_hz * (start + indexes) / RATE) * template
        )
    return values


def test_receiver_center_is_immutable_and_absolute_is_center_plus_residual() -> None:
    calibration = ReceiverFrequencyCalibration("rx-a", 1_170.0, "1" * 64)
    result = acquire_symbolwise(
        _injected(epoch=37, residual_cfo_hz=200_000.0, receiver_center_hz=1_170.0),
        RATE,
        calibration,
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.winner is not None
    assert result.winner.refined_epoch_sample == 37
    assert result.winner.residual_cfo_hz == pytest.approx(200_000.0, abs=1.0)
    assert result.winner.absolute_cfo_hz == pytest.approx(201_170.0, abs=1.0)
    assert result.winner.absolute_cfo_hz == pytest.approx(
        calibration.center_hz + result.winner.residual_cfo_hz,
        abs=1e-12,
    )
    assert result.winner.verify_minus_control_margin == pytest.approx(
        0.9832180261583393,
        abs=1e-10,
    )
    with pytest.raises(FrozenInstanceError):
        calibration.center_hz = 0.0  # type: ignore[misc]


def test_acquisition_retains_alias_basin_until_held_out_adjudication() -> None:
    rng = np.random.default_rng(18)
    values = (
        rng.normal(0, 0.05 / np.sqrt(2), 18_000) + 1j * rng.normal(0, 0.05 / np.sqrt(2), 18_000)
    ).astype(np.complex128)
    template = qin_edge_pilot_frame(RATE)

    def inject(epoch: int, cfo_hz: float, amplitude: float, *, acquire_only: bool) -> None:
        for frame in range(5):
            start = epoch + round(frame * RATE / 750.0)
            symbols = range(2, 302, 2) if acquire_only else (None,)
            for symbol in symbols:
                indexes = (
                    np.arange(template.size)
                    if symbol is None
                    else np.arange(
                        round(symbol * RATE * 4.4e-6),
                        round((symbol + 1) * RATE * 4.4e-6),
                    )
                )
                if start + indexes[-1] >= values.size:
                    continue
                values[start + indexes] += (
                    amplitude
                    * np.exp(2j * np.pi * cfo_hz * (start + indexes) / RATE)
                    * template[indexes]
                )

    inject(811, -160_000.0, 5.0, acquire_only=True)
    inject(127, 200_000.0, 1.5, acquire_only=False)
    result = acquire_symbolwise(
        values,
        RATE,
        ReceiverFrequencyCalibration("rx-alias", 0.0, "2" * 64),
    )

    assert result.winner is not None
    assert len(result.candidates) == 8
    assert result.winner.refined_epoch_sample == 127
    assert result.winner.residual_cfo_hz == pytest.approx(200_000.0, abs=35.0)
    alias = next(
        item
        for item in result.candidates
        if item.refined_epoch_sample == 811 and abs(item.residual_cfo_hz + 160_000.0) < 35.0
    )
    assert alias.acquire_score > result.winner.acquire_score
    assert alias.verify_minus_control_margin < result.winner.verify_minus_control_margin


def test_null_and_short_windows_have_explicit_outcomes() -> None:
    calibration = ReceiverFrequencyCalibration("rx-null", 0.0, "3" * 64)
    short = acquire_symbolwise(np.zeros(4_000, dtype=np.complex64), RATE, calibration)
    null = acquire_symbolwise(np.zeros(14_000, dtype=np.complex64), RATE, calibration)

    assert short.status is NumericalStatus.INSUFFICIENT
    assert short.candidates == ()
    assert "two supported frames" in short.reason
    assert null.status is NumericalStatus.NO_RESULT
    assert null.winner is None
