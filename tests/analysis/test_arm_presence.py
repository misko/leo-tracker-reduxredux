"""Component-owned synthetic tests; no archive, hardware, or database required."""

from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.research import arm_presence as presence


def candidate(cfo=12_000.0, margin=0.1, epoch=130, offset=0.25):
    return presence.PresenceCandidate(epoch, offset, cfo, cfo, margin, margin + 0.05)


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
def test_fractional_lag_repetition_and_tone_control(rate):
    time_s = np.arange(round(rate * 0.020)) / rate
    values = sum(np.exp(2j * np.pi * 750 * k * time_s + 1j * k * k) for k in range(1, 20))
    score = presence.periodicity_scout(values, rate)
    assert score["lag_margin"] > 0.5
    tone = np.exp(2j * np.pi * 123_456 * time_s)
    assert abs(presence.periodicity_scout(tone, rate)["lag_margin"]) < 1e-5


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
def test_seed_uses_fractional_physical_period_not_repeated_rounded_period(rate):
    counter = 10**16
    seed = presence.TimingSeed(counter, rate, candidate())
    elapsed = round(rate * 1.004567)
    expected = (130.25 - elapsed) % (rate / 750)
    assert seed.predict_epoch(counter + elapsed) == pytest.approx(expected, abs=1e-8)
    assert abs(seed.predict_epoch(counter + elapsed) - (130.25 - elapsed) % round(rate / 750)) > 1
    with pytest.raises(ValueError, match="later"):
        seed.predict_epoch(counter)


def test_reference_never_calls_missing_detection_negative():
    assert presence.reference_label([(), ()]) == "unresolved"
    assert presence.reference_label([(candidate(),), ()]) == "single_window_reference_positive"
    assert (
        presence.reference_label([(candidate(), candidate(80_000.0)), ()])
        != "repeated_reference_positive"
    )
    assert (
        presence.reference_label([(candidate(),), (candidate(14_000.0),)])
        == "repeated_reference_positive"
    )
    assert (
        presence.reference_label([(candidate(),), (candidate(90_000.0),)])
        == "single_window_reference_positive"
    )


def test_reference_considers_nonwinning_basins():
    assert (
        presence.reference_label(
            [
                (candidate(120_000.0, 0.2), candidate(12_000.0, 0.1)),
                (candidate(240_000.0, 0.2), candidate(13_000.0, 0.1)),
            ]
        )
        == "repeated_reference_positive"
    )


def test_budget_reaches_acquisition_not_posthoc_truncation(monkeypatch):
    observed = []

    def acquire(*args, config, **kwargs):
        observed.append(config.retained_candidate_count)
        return SimpleNamespace(candidates=())

    monkeypatch.setattr(presence, "acquire_symbolwise", acquire)
    for budget in (1, 2, 8):
        assert (
            presence.fresh_glrt(np.ones(50_000), 2_500_000, edge="lower", candidate_count=budget)
            == ()
        )
    assert observed == [1, 2, 8]


def test_pss_bank_performs_blind_search_at_each_cfo(monkeypatch):
    frequencies = []

    def search(*args, nominal_frequency_offset_hz, config, **kwargs):
        frequencies.append(nominal_frequency_offset_hz)
        assert config.minimum_epoch_robust_z == 1e12
        return SimpleNamespace(candidates=())

    monkeypatch.setattr(presence, "search_pss_frame_timing", search)
    presence.pss_scout(np.ones(50_000), 2_500_000, slice_center_offset_hz=-115_312_500.0)
    assert frequencies == [-400_000.0, -200_000.0, 0.0, 200_000.0, 400_000.0]


def test_cache_rate_change_rejected_before_scoring():
    with pytest.raises(ValueError, match="rate"):
        presence.cached_glrt(
            np.ones(100_000),
            5_000_000,
            edge="lower",
            device_counter=1000,
            seed=presence.TimingSeed(0, 2_500_000, candidate()),
        )


def test_controls_reproducible_and_labeled():
    first = presence.noise_control(50_000, 2_500_000, seed=7, kind="gaussian")
    second = presence.noise_control(50_000, 2_500_000, seed=7, kind="gaussian")
    np.testing.assert_array_equal(first, second)
    with pytest.raises(ValueError):
        presence.noise_control(10, 1000, seed=7, kind="quiet_rf")


@pytest.mark.parametrize(
    "values,rate",
    [(np.ones(2), 2_500_000), (np.ones(100), 0), (np.full(50_000, np.nan), 2_500_000)],
)
def test_invalid_iq_rejected(values, rate):
    with pytest.raises(ValueError):
        presence.periodicity_scout(values, rate)
