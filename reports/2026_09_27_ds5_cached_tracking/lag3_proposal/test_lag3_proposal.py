from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from lag3_proposal import Lag3Proposal, build_library, sha256  # noqa: E402


def _ideal_visit(rate: int, proposal: Lag3Proposal, specifications: list[tuple[int, int, int, float]],
                 fractional: float = 0.0) -> np.ndarray:
    """Construct a bounded repeated-template convention check, not a channel model."""
    count = rate * 120 // 1000
    window_samples = rate // 50
    n = proposal.template.size
    positions = np.arange(count, dtype=np.float64)
    raw = np.zeros((count, 2, 2), dtype="<i2")
    for receiver, window, epoch, cfo in specifications:
        values = np.zeros(count, dtype=np.complex128)
        selected = (positions >= window * window_samples) & (positions < (window + 1) * window_samples)
        phase = (positions[selected] - window * window_samples - epoch - fractional) % n
        left = np.floor(phase).astype(np.int64)
        right = (left + 1) % n
        alpha = phase - left
        signal = (1.0 - alpha) * proposal.template[left] + alpha * proposal.template[right]
        signal *= np.exp(2j * np.pi * cfo * positions[selected] / rate)
        values[selected] = signal
        scale = 1800.0 / max(float(np.max(np.abs(values))), 1.0)
        raw[:, receiver, 0] = np.rint(values.real * scale).astype("<i2")
        raw[:, receiver, 1] = np.rint(values.imag * scale).astype("<i2")
    return raw


def _coordinate(candidate: dict) -> tuple:
    return tuple(candidate[key] for key in (
        "window", "epoch_samples", "projected_bin", "cfo_hz", "score",
        "phase_support_score", "correlation_re", "correlation_im", "phase_valid", "supported",
    ))


def test_build_receipt_pins_sources_and_binary():
    binary = build_library()
    receipt = json.loads(binary.with_name(binary.name + ".build.json").read_text())
    assert sha256(binary) == receipt["binary_sha256"]
    assert all(sha256(Path(path)) == digest for path, digest in receipt["sources_sha256"].items())


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
def test_deterministic_dual_receiver_bounds_and_no_mutation(rate: int):
    with Lag3Proposal(rate, "lower") as proposal:
        raw = _ideal_visit(rate, proposal, [(0, 1, 173, 200_000.0), (1, 4, 421, -200_000.0)])
        before = hashlib.sha256(raw.view(np.uint8)).digest()
        first = proposal.run(raw, 0)
        second = proposal.run(raw, 0)
        other = proposal.run(raw, 1)
        assert hashlib.sha256(raw.view(np.uint8)).digest() == before
        assert [_coordinate(row) for row in first["candidates"]] == [
            _coordinate(row) for row in second["candidates"]
        ]
        n = first["epoch_period_samples"]
        for result in (first, other):
            assert len(result["candidates"]) <= 3
            for row in result["candidates"]:
                assert 0 <= row["window"] < 6
                assert 0 <= row["projected_bin"] < 512
                assert 0 <= row["epoch_samples"] < n
                assert 0.0 <= row["phase_support_score"] <= 1.000001
                assert abs(row["cfo_hz"]) <= rate / 6 + 1e-6
        assert first["candidates"][0]["window"] == 1
        assert other["candidates"][0]["window"] == 4


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("cfo", [-399_000.0, -200_000.0, 0.0, 200_000.0, 399_000.0])
def test_direct_lag3_phase_sign_and_integer_ideal(rate: int, cfo: float):
    with Lag3Proposal(rate, "lower") as proposal:
        raw = _ideal_visit(rate, proposal, [(0, 2, 123, cfo)])
        row = proposal.run(raw, 0)["candidates"][0]
    assert row["window"] == 2
    assert row["phase_valid"]
    assert abs(row["epoch_samples"] - 123) <= 3
    assert abs(row["cfo_hz"] - cfo) <= 8_000.0
    assert row["supported"] == (abs(row["cfo_hz"]) <= 400_000.0)
    if abs(cfo) > 1.0:
        assert np.sign(row["cfo_hz"]) == np.sign(cfo)


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("fractional", [-0.49, 0.49])
def test_fractional_timing_preserves_phase_convention_without_unbiased_claim(rate: int,
                                                                            fractional: float):
    with Lag3Proposal(rate, "lower") as proposal:
        raw = _ideal_visit(rate, proposal, [(0, 3, 211, 200_000.0)], fractional=fractional)
        row = proposal.run(raw, 0)["candidates"][0]
    assert row["window"] == 3
    assert row["supported"]
    assert abs(row["epoch_samples"] - 211) <= 4
    assert row["cfo_hz"] > 0.0
    # Fractional timing can impart waveform-dependent phase. This deliberately
    # checks convention and bounded principal phase, not an unbiased estimate.
    assert abs(row["cfo_hz"]) <= 400_000.0


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("epoch_selector", [0, 1, -2, -1])
def test_circular_native_timing_seam(rate: int, epoch_selector: int):
    with Lag3Proposal(rate, "lower") as proposal:
        n = proposal.template.size
        epoch = epoch_selector % n
        raw = _ideal_visit(rate, proposal, [(0, 1, epoch, 123_456.7)])
        candidates = proposal.run(raw, 0)["candidates"]
    distance = lambda row: abs(((row["epoch_samples"] - epoch + n / 2) % n) - n / 2)
    row = min(candidates, key=distance)
    # A seam proposal must either meet the coordinate/CFO checks or explicitly
    # remain unsupported. This does not relabel unsupported evidence as absent.
    assert not row["phase_valid"] or (
        distance(row) <= rate * 2e-6 and abs(row["cfo_hz"] - 123_456.7) <= 8_000.0
    )


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
def test_zero_and_tone_do_not_claim_supported_phase(rate: int):
    count = rate * 120 // 1000
    zero = np.zeros((count, 2, 2), dtype="<i2")
    positions = np.arange(count)
    tone = 1200.0 * np.exp(2j * np.pi * 71_000.0 * positions / rate)
    tone_raw = zero.copy()
    tone_raw[:, 0, 0] = np.rint(tone.real).astype("<i2")
    tone_raw[:, 0, 1] = np.rint(tone.imag).astype("<i2")
    with Lag3Proposal(rate, "lower") as proposal:
        assert proposal.run(zero, 0)["candidates"] == []
        result = proposal.run(tone_raw, 0)
    assert all(not row["supported"] for row in result["candidates"])


def test_ci16_extrema_both_receivers_are_safe_and_bounded():
    rate = 2_500_000
    count = rate * 120 // 1000
    raw = np.empty((count, 2, 2), dtype="<i2")
    pattern = np.array([-32768, 32767], dtype="<i2")
    raw[:, 0, :] = pattern
    raw[:, 1, :] = pattern[::-1]
    before = raw.tobytes()
    with Lag3Proposal(rate, "lower") as proposal:
        for receiver in (0, 1):
            result = proposal.run(raw, receiver)
            assert len(result["candidates"]) <= 3
            assert all(0 <= row["epoch_samples"] < result["epoch_period_samples"]
                       for row in result["candidates"])
    assert raw.tobytes() == before


def test_shape_receiver_and_contiguity_contracts():
    rate = 2_500_000
    raw = np.zeros((rate * 120 // 1000, 2, 2), dtype="<i2")
    with Lag3Proposal(rate, "lower") as proposal:
        with pytest.raises(ValueError):
            proposal.run(raw, 2)
        with pytest.raises(ValueError):
            proposal.run(raw[::2], 0)
        with pytest.raises(TypeError):
            proposal.run(raw.astype(np.float32), 0)
