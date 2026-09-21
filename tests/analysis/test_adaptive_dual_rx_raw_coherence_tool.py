from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

PATH = Path(__file__).parents[2] / "tools" / "report_adaptive_dual_rx_raw_coherence.py"
SPEC = importlib.util.spec_from_file_location("raw_coherence_tool", PATH)
assert SPEC is not None and SPEC.loader is not None
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)


def test_cross_ambiguity_recovers_frequency_delay_and_rejects_controls() -> None:
    rate = 200_000.0
    count = 24_000
    offset_hz = -31_257.4
    delay = 3
    rng = np.random.default_rng(20260921)
    common = rng.normal(size=count) + 1j * rng.normal(size=count)
    left = common + 0.4 * (rng.normal(size=count) + 1j * rng.normal(size=count))
    right = np.zeros(count, dtype=np.complex128)
    sample = np.arange(count - delay)
    right[delay:] = common[:-delay] * np.exp(2j * np.pi * offset_hz * sample / rate + 0.7j)
    right += 0.4 * (rng.normal(size=count) + 1j * rng.normal(size=count))
    values = np.column_stack((left, right))

    peak = tool.cross_ambiguity_peak(
        values,
        rate,
        minimum_frequency_hz=-40_000,
        maximum_frequency_hz=-20_000,
        maximum_delay_samples=6,
    )

    assert peak.frequency_hz == pytest.approx(offset_hz, abs=2.0)
    assert peak.delay_samples == delay
    assert peak.coherence > 0.7
    assert tool.coherence_at(values, rate, offset_hz + 8_000, delay) < 0.03
    assert (
        tool.coherence_at(
            np.column_stack((values[:, 0], np.roll(values[:, 1], 1000))),
            rate,
            offset_hz,
            delay,
        )
        < 0.03
    )


def test_subband_transfer_matches_same_waveform_and_rejects_wrong_source() -> None:
    rate = 200_000.0
    count = 32_768
    offset_hz = -30_000.0
    receiver_phase = 0.63
    rng = np.random.default_rng(4)
    time = np.arange(count) / rate

    def source(center_hz: float) -> np.ndarray:
        symbols = rng.normal(size=count // 32 + 1) + 1j * rng.normal(size=count // 32 + 1)
        envelope = np.repeat(symbols, 32)[:count]
        return envelope * np.exp(2j * np.pi * center_hz * time)

    rx0 = source(20_000.0) + source(55_000.0)
    rx1 = rx0 * np.exp(2j * np.pi * offset_hz * time + 1j * receiver_phase)
    values = np.column_stack((rx0, rx1))

    matched = tool.subband_transfer(values, rate, offset_hz, 20_000.0)
    wrong = tool.subband_transfer(
        values,
        rate,
        offset_hz,
        20_000.0,
        rx1_aligned_center_hz=55_000.0,
    )

    assert matched.coherence > 0.99
    assert matched.phase_deg == pytest.approx(np.degrees(receiver_phase), abs=0.1)
    assert wrong.coherence < 0.1
    overlap = tool.source_overlap_evidence(values, rate, offset_hz, (20_000.0, 55_000.0))
    assert overlap["gate_uses_phase"] is False
    assert overlap["qualified_overlap_block_count"] == overlap["total_block_count"]
    assert all(
        row["wrapped_high_minus_low_phase_deg"] == pytest.approx(0.0, abs=0.2)
        for row in overlap["blocks"]
    )


def test_common_phase_nuisance_uses_bins_outside_target_and_stabilizes_transfer() -> None:
    rate = 200_000.0
    count = 60_000
    offset_hz = -30_000.0
    rng = np.random.default_rng(19)
    time = np.arange(count) / rate
    common = rng.normal(size=count) + 1j * rng.normal(size=count)
    target = np.repeat(
        rng.normal(size=count // 20 + 1) + 1j * rng.normal(size=count // 20 + 1), 20
    )[:count] * np.exp(2j * np.pi * 20_000 * time)
    rx0 = common + 2 * target
    nuisance = 1.2 * np.sin(2 * np.pi * np.arange(count) / count) + 0.4 * time
    rx1 = rx0 * np.exp(2j * np.pi * offset_hz * time + 0.3j + 1j * nuisance)
    values = np.column_stack((rx0, rx1))
    before_first = tool.subband_transfer(values[: count // 2], rate, offset_hz, 20_000)
    before_second = tool.subband_transfer(
        values[count // 2 :],
        rate,
        offset_hz,
        20_000,
        global_start_sample=count // 2,
    )

    corrected, evidence = tool.remove_common_phase_nuisance(
        values, rate, offset_hz, (20_000.0,), block_samples=1_000
    )
    after_first = tool.subband_transfer(corrected[: count // 2], rate, offset_hz, 20_000)
    after_second = tool.subband_transfer(
        corrected[count // 2 :],
        rate,
        offset_hz,
        20_000,
        global_start_sample=count // 2,
    )

    before_error = abs(
        np.angle(np.exp(1j * np.radians(before_second.phase_deg - before_first.phase_deg)))
    )
    after_error = abs(
        np.angle(np.exp(1j * np.radians(after_second.phase_deg - after_first.phase_deg)))
    )
    assert evidence["target_bands_used_for_nuisance"] is False
    assert evidence["coherence_median"] > 0.8
    assert after_error < before_error / 4


@pytest.mark.parametrize("bad_delay", [-1, 33])
def test_cross_ambiguity_rejects_invalid_delay_bound(bad_delay: int) -> None:
    with pytest.raises(ValueError, match="invalid cross-ambiguity input"):
        tool.cross_ambiguity_peak(
            np.ones((100, 2), dtype=np.complex128),
            100_000,
            maximum_delay_samples=bad_delay,
        )
