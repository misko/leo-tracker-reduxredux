from copy import deepcopy

import numpy as np
import pytest

from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    CYCLIC_PREFIX_DURATION_S,
    OFDM_SYMBOL_DURATION_S,
    edge_frequencies_hz,
    qin_edge_pilot_symbols,
)
from tools.pipeline_eval.variants.pilot_confirmation import PilotConfirmation

RATE = 10_000_000
EPOCH = 4201
OFFSET = -1.125
CFO = -126_200.0


def _candidate(epoch=EPOCH, offset=OFFSET, cfo=CFO, margin=0.1):
    return dict(
        epoch=epoch,
        fractional_epoch=dict(
            status="complete", offset_samples=offset, tracking_cfo_hz=cfo, margin=margin
        ),
    )


def _rows(candidate, *more, second=()):
    return [
        dict(receiver_id=0, probe_start_ms=0, candidates=[candidate, *more]),
        dict(receiver_id=1, probe_start_ms=0, candidates=list(second)),
    ]


def _synthetic(edge, *, areas=(0, 1), seed=173):
    rng = np.random.default_rng(seed)
    samples = rng.normal(0, 100, size=(RATE // 50, 2, 2))
    frequencies = edge_frequencies_hz(edge)
    for frame in range(15):
        actual_epoch = EPOCH + OFFSET + frame * RATE / 750
        start = max(0, int(np.floor(actual_epoch)))
        time = np.arange(start, min(start + 13_334, len(samples))) / RATE
        symbol_phase, symbol = np.modf((time - actual_epoch / RATE) / OFDM_SYMBOL_DURATION_S)
        keep = np.full(symbol.size, False)
        for area in areas:
            first, last = ((79, 141), (199, 261))[area]
            keep |= (symbol >= first) & (symbol <= last) & (symbol % 2 == 1)
        targets = start + np.flatnonzero(keep)
        tone = np.exp(
            2j
            * np.pi
            * np.outer(
                symbol_phase[keep] * OFDM_SYMBOL_DURATION_S - CYCLIC_PREFIX_DURATION_S,
                frequencies,
            )
        )
        gain = 35 * np.exp(1j * (rng.uniform(-np.pi, np.pi) + 2 * np.pi * CFO * time[keep]))
        for receiver, roll in enumerate((0, CONTROL_SYMBOL_ROLL)):
            states = qin_edge_pilot_symbols(edge, symbol_roll=roll)[symbol[keep].astype(int) - 2]
            signal = np.sum(tone * states, axis=1) * gain / np.sqrt(8)
            samples[targets, receiver, 0] += signal.real
            samples[targets, receiver, 1] += signal.imag
    return np.rint(samples).astype("<i2")


@pytest.mark.parametrize("edge", ("lower", "upper"))
def test_exact_and_same_iq_control_have_opposite_sign(edge):
    confirm = PilotConfirmation(RATE, edge)
    candidates = _rows(_candidate(), second=(_candidate(),))
    original = deepcopy(candidates)
    samples = _synthetic(edge)
    samples.setflags(write=False)

    evidence = confirm(samples, candidates)

    assert evidence[0, 0].passed
    assert evidence[0, 0].frames == 14
    assert min(evidence[0, 0].block_z) > 10
    assert not evidence[1, 0].passed
    assert max(evidence[1, 0].block_z) < -10
    assert candidates == original


def test_fixed_coordinates_and_existing_gate_are_preserved():
    confirm = PilotConfirmation(RATE, "lower")
    good = _candidate()
    candidate_rows = _rows(
        good,
        _candidate(epoch=EPOCH + 230),
        _candidate(cfo=CFO + 47_000),
        _candidate(margin=0.0249),
        {"fractional_epoch": {"status": "unbracketed"}},
        good,
    )
    evidence = confirm(_synthetic("lower"), candidate_rows)

    assert set(evidence) == {(0, 0), (0, 1), (0, 2), (0, 5)}
    assert evidence[0, 0] is evidence[0, 5]
    assert evidence[0, 0].passed
    assert not evidence[0, 1].passed
    assert not evidence[0, 2].passed


def test_noise_floor_and_absent_capture_energy():
    confirm = PilotConfirmation(RATE, "upper")
    rows = _rows(_candidate())
    rng = np.random.default_rng(191)
    outcomes = []
    for _ in range(32):
        noise = np.rint(rng.normal(0, 100, size=(RATE // 50, 2, 2))).astype("<i2")
        outcomes.append(confirm(noise, rows)[0, 0])

    assert sum(evidence.passed for evidence in outcomes) <= 2
    assert abs(np.mean([evidence.pooled_z for evidence in outcomes])) < 0.5
    zero = confirm(np.zeros((RATE // 50, 2, 2), dtype="<i2"), rows)[0, 0]
    assert not zero.passed
    assert zero.frames == 0


def test_signal_present_in_only_one_region_can_be_rejected():
    confirm = PilotConfirmation(RATE, "lower")
    evidence = confirm(_synthetic("lower", areas=(0,)), _rows(_candidate()))[0, 0]

    assert evidence.block_z[0] > 10
    assert evidence.block_z[1] < 0
    assert not evidence.passed


def test_rejects_unbound_layout_and_native_metadata():
    with pytest.raises(ValueError, match="10 MS/s"):
        PilotConfirmation(2_500_000, "lower")
    confirm = PilotConfirmation(RATE, "lower")
    samples = np.zeros((RATE // 50, 2, 2), dtype="<i2")
    with pytest.raises(ValueError, match="dual-CI16"):
        confirm(samples[:-1], _rows(_candidate()))
    with pytest.raises(ValueError, match="two native short-window rows"):
        confirm(samples, _rows(_candidate())[::-1])
    with pytest.raises(ValueError, match="fractional coordinates"):
        confirm(samples, _rows(_candidate(epoch=13_333)))
