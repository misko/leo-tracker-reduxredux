"""Synthetic falsifiers for the report's nuisance controls and compensation."""

from dataclasses import dataclass

import numpy as np
from offset_controls import design, fit_nuisance
from replay_compensation import compensate


def test_opposite_steps_require_receiver_specific_offsets():
    rng = np.random.default_rng(7193)
    n = 4000
    rx = np.arange(n) % 2
    channel = rng.integers(1, 9, n)
    times = rng.uniform(0, 300, n)
    rf = 10459687500 + 250000000 * channel
    group = channel >= 5
    y = np.where(rx == 0, -80000 + 2 * (times - 150), -54000 + 1.5 * (times - 150))
    y += np.where(rx == 0, -24000, 38000) * group - 600 * (rf - 11584687500) / 1e9
    y += rng.normal(0, 70, n)
    train = (np.floor(times / 5).astype(int) % 5) != 0
    test = ~train
    for model in ("shared-rf", "shared-step", "receiver-step"):
        x, names = design(times, rf, rx, channel, model, True)
        beta = fit_nuisance(x, y, np.ones(n), train, names)
        rms = np.sqrt(np.mean((y[test] - x[test] @ beta) ** 2))
        if model == "receiver-step":
            assert rms < 80
            result = dict(zip(names, beta, strict=True))
            assert abs(result["step0"] + 24000) < 20
            assert abs(result["step1"] - 38000) < 20
            assert abs(result["c"] + 600) < 20
        else:
            assert rms > 10000


def test_heldout_responses_do_not_change_fitted_offsets():
    rng = np.random.default_rng(3)
    times = np.linspace(0, 300, 500)
    rx = np.arange(500) % 2
    channel = rng.integers(1, 9, 500)
    rf = 10459687500 + 250000000 * channel
    x, names = design(times, rf, rx, channel, "receiver-step", True)
    beta = np.array([-80000, 300, -54000, 225, -600, -24000, 38000])
    y = x @ beta
    train = np.arange(500) % 5 != 0
    first = fit_nuisance(x, y, np.ones(500), train, names)
    altered = y.copy()
    altered[~train] += 50000
    second = fit_nuisance(x, altered, np.ones(500), train, names)
    np.testing.assert_array_equal(first, second)


def test_zero_c_control_keeps_identical_other_design_columns():
    times = np.array([0, 20, 50, 70, 100, 130, 200, 300])
    rx = np.arange(8) % 2
    ch = np.arange(1, 9)
    rf = 10459687500 + 250000000 * ch
    fitted, names = design(times, rf, rx, ch, "receiver-step", True)
    zero, zero_names = design(times, rf, rx, ch, "receiver-step", False)
    keep = [i for i, name in enumerate(names) if name != "c"]
    assert [names[i] for i in keep] == zero_names
    np.testing.assert_array_equal(fitted[:, keep], zero)


@dataclass(frozen=True)
class Candidate:
    fractional_tracking_cfo_hz: float
    passed_fractional_margin_gate: bool
    candidate_rank: int


@dataclass(frozen=True)
class Probe:
    receiver_id: int
    channel: int
    candidates: tuple


@dataclass(frozen=True)
class Source:
    probes: tuple
    timing: object


def test_compensation_translates_all_high_candidates_and_preserves_evidence():
    probes = tuple(
        Probe(rx, ch, (Candidate(100, True, 0), Candidate(-200, False, 1)))
        for rx in (0, 1)
        for ch in range(1, 9)
    )
    source = Source(probes, object())
    corrected = compensate(source, {0: -24000, 1: 38000})
    assert corrected.timing is source.timing
    assert source.probes[0].candidates[0].fractional_tracking_cfo_hz == 100
    for before, after in zip(source.probes, corrected.probes, strict=True):
        assert (before.channel, before.receiver_id) == (after.channel, after.receiver_id)
        for a, b in zip(before.candidates, after.candidates, strict=True):
            step = {0: -24000, 1: 38000}[before.receiver_id] if before.channel >= 5 else 0
            assert b.fractional_tracking_cfo_hz == a.fractional_tracking_cfo_hz - step
            assert (a.passed_fractional_margin_gate, a.candidate_rank) == (
                b.passed_fractional_margin_gate,
                b.candidate_rank,
            )
