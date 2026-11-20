import numpy as np

from tools.pipeline_eval.qualification import seeded_acquisition_results as results
from tools.pipeline_eval.qualification import seeded_acquisition_trial as trial
from tools.pipeline_eval.variants import seeded_acquisition as seeded


def candidate(epoch, cfo, hit=True):
    return dict(
        integer_epoch_sample=epoch,
        fractional_epoch_offset_samples=0.0,
        fractional_tracking_cfo_hz=cfo,
        fractional_margin=0.1 if hit else 0.01,
        passed_fractional_margin_gate=hit,
        candidate_rank=0,
    )


def test_hardware_rational_phase_and_live_signed_update():
    key = (0, "clock", 11e9, "upper")
    before = 2**54 + 31
    t = seeded.Tracker(220)
    t.anchor(key, before, [candidate(400, 22_000)])
    after = before + 3_600_071
    forecast = t.forecast(key, after)
    assert abs(seeded.wrapped(forecast.epoch - (400 - 71))) < 1e-9
    assert t.forecast((1, *key[1:]), after) is None
    assert t.forecast(key, before + 2 * seeded.RATE) is None
    assert not t.observe(key, after, forecast, [candidate(329, 22_000 + seeded.ALIAS)])
    assert t.observe(key, after, forecast, [candidate(329, 22_500)])
    assert t.lanes[key].sample == after
    t.anchor(key, after + 1, [candidate(330, 22_500, False)])
    assert t.forecast(key, after + 2) is None


def test_known_symbol_search_uses_the_actual_offset_in_raw_iq():
    rng = np.random.default_rng(921)
    exact = (rng.normal(size=seeded.EPOCHS) + 1j * rng.normal(size=seeded.EPOCHS)).astype("c8")
    raw = (rng.normal(size=200_000) + 1j * rng.normal(size=200_000)).astype("c8")
    actual, cfo = 411, -45_000
    picker = seeded.LocalSearch(exact)
    signal = exact[picker.relative] * np.exp(2j * np.pi * cfo * picker.relative / seeded.RATE)
    for start in picker.starts:
        raw[start + actual + picker.relative] = signal
    assert picker.rank(raw, seeded.Search(403, cfo, 24, 0.35))[0] == actual


def test_budget_follows_rf_ordinals_and_signed_matching_keeps_aliases_separate():
    assert [i for i in range(10) if trial.native_selected(0.4, i)] == [2, 4, 7, 9]
    p, q = candidate(400, 22_000), candidate(400, 22_000 + seeded.ALIAS)
    assert not results.compatible(p, q)
    assert results.compatible(p, q, alias=True)
