import math

import numpy as np
import pytest

from tools.pipeline_eval.variants.epoch_carry import ALIAS_HZ, Holdover, wrap
from tools.pipeline_eval.variants.epoch_carry_power import FRAME, PilotEnvelope, distance

RATE = 10_000_000
START = 12_345_678_901_234
LANE = (0, 4, "lower")


def positive(epoch, cfo=31_000, margin=0.1, rank=0):
    base = math.floor(epoch)
    return dict(
        integer_epoch_sample=base,
        fractional_epoch_offset_samples=epoch - base,
        fractional_tracking_cfo_hz=cfo,
        candidate_rank=rank,
        fractional_margin=margin,
        passed_fractional_margin_gate=True,
    )


def test_rational_counter_holdover_recovers_signed_sample_drift():
    model = Holdover(RATE)
    slope = -87.5
    for i in range(3):
        sample = START + i * RATE // 50
        phase = (2.0 + slope * i / 50) % model.period
        e = model.global_phase(-sample, phase)
        assert model.forecast(LANE, sample) is None
        model.advance(LANE, sample, [positive(e, cfo=31_000 - ALIAS_HZ * (i % 2))])
    target = START + 3 * RATE // 50
    result = model.forecast(LANE, target)
    e = model.global_phase(-target, 2.0 + slope * 3 / 50)
    assert result["drift_samples_s"] == pytest.approx(slope)
    assert wrap(result["epoch"] - e, model.period) == pytest.approx(0, abs=1e-7)
    assert all(prior < target for prior in result["prior_samples"])
    assert model.forecast(LANE, target + RATE) is None


def test_replacing_unrelated_emitter_clears_measured_holdover():
    model = Holdover(RATE)
    for i in range(3):
        sample = START + i * RATE // 50
        e = model.global_phase(-sample, 284)
        model.advance(LANE, sample, [positive(e)])
    next_sample = START + 3 * RATE // 50
    assert model.forecast(LANE, next_sample) is not None
    assert model.forecast((1, *LANE[1:]), next_sample) is None
    assert model.null_channel(LANE, next_sample) is None
    assert model.null_channel((0, 5, "upper"), next_sample) is not None
    model.advance(LANE, next_sample, [positive(8_500, cfo=251_111)])
    assert model.forecast(LANE, next_sample + RATE // 50) is None
    with pytest.raises(ValueError, match="sample counter did not advance"):
        model.advance(LANE, next_sample, [])


def test_energy_proposal_is_cfo_invariant_and_keeps_three_original_slots():
    rng = np.random.default_rng(162)
    source = rng.uniform(500, 7000, FRAME)
    env = PilotEnvelope(source)
    stock = [4000, 6000, 8000, 10_000]
    iq = np.zeros(RATE // 50, dtype=complex)
    for frame in range(15):
        start = round(frame * RATE / 750) + 735
        count = min(FRAME, len(iq) - start)
        iq[start : start + count] = source[:count]
    centers = []
    for cfo in (-750_000, 790_000):
        v = iq * np.exp(2j * np.pi * cfo * np.arange(len(iq)) / RATE)
        result, detail = env.select(np.column_stack((v.real, v.imag)), stock)
        assert result[:3] == stock[:3] and distance(result[-1], 735) <= 1
        assert detail is not None and detail["correlation"] >= 0.08
        centers.append(result[-1])
    assert centers[0] == centers[1]
    assert env.select(np.zeros((len(iq), 2)), stock) == (stock, None)
