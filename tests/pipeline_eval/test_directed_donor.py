from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def donor(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("directed_donor")


def measured(donor, counter, hz, phase):
    epoch = (phase - (3 * counter % 40_000) / 3) % donor.PERIOD
    return dict(integer_epoch_sample=int(epoch), fractional_epoch_offset_samples=epoch % 1,
                fractional_tracking_cfo_hz=hz, fractional_margin=1., candidate_rank=0)


def test_secant_wraps_phase_without_folding_signed_frequency(donor):
    origin = 30_348_433_000_000
    counters = (origin, origin + donor.ADC, origin + 3*donor.ADC)
    anchors = [measured(donor, counters[0], -226_500., donor.PERIOD - 2.),
               measured(donor, counters[1], -224_500., 3.)]
    query = donor.extrapolate(counters, anchors, ((0., 0.),) * 3)
    assert query["phase_sample"] == pytest.approx(13.)
    assert query["cfo_hz"] == -220_500.
    corrected = donor.extrapolate(counters, anchors, ((0., 0.), (500., 5.), (3000., 30.)))
    assert corrected["cfo_hz"] == -218_500.
    assert corrected["phase_sample"] == pytest.approx(28.)


def test_matching_uses_each_factor_and_query_once_and_minimizes_error(donor):
    factors = [measured(donor, 0, 10., 0.), measured(donor, 0, 40., .9)]
    queries = [dict(cfo_hz=10., phase_sample=0.), dict(cfo_hz=25., phase_sample=1.1)]
    assert donor.matching(0, factors, queries, donor.TIGHT) == ((0, 0), (1, 1))
    assert donor.matching(0, factors[:1], queries[:1]*2, donor.LOOSE) == ((0, 0),)
    alias = [dict(cfo_hz=10. + 1/4.4e-6, phase_sample=0.)]
    assert donor.matching(0, factors, alias, donor.LOOSE) == ()
