import json
from struct import pack

import pytest

from leo.analysis.localization_v3 import phase_prior
from reports.ALGO08.v3 import exact_phase_forecast as variant


@pytest.mark.parametrize(
    ("alignment", "age", "gap"), [
        (0., 0., 1.), (-0., 3.1, 1.), (-.827386, 86001.19, 7240.1), (19., 1000., 1.),
    ],
)
def test_scalar_sigma_has_identical_binary64(alignment, age, gap):
    result = variant.causal_sigma(alignment, age, gap)
    assert pack("d", result) == pack("d", phase_prior.causal_phase_sigma(alignment, age, gap))


def test_many_triples_share_time_only_and_keep_every_fresh_propagation(monkeypatch):
    constructed = []

    class Tle:
        @classmethod
        def twoline2rv(cls, value, _unused):
            obj = cls()
            constructed.append(obj)
            obj.offset = value
            return obj

        def sgp4(self, day, fraction):
            return 0, (day * .00001, self.offset + fraction, 10.), (0., 4.132, 1.)

    monkeypatch.setattr(phase_prior, "Satrec", Tle)
    date = 1_794_568_912_154_038_024
    rows = [{"collected_utc_ns": date,
             "epoch": date - (10 - n) * 1_400_000_000, "lines": (n + .3, "")}
            for n in range(5)]
    history = {"case": "SCAN", "cutoff_utc_ns": date,
               "past_versions": {"1": rows, "2": rows[::-1], "3": rows[1:]}}

    stock = phase_prior.forecast(history)
    candidate, audit = variant.forecast(phase_prior.forecast, history)
    from leo.application.localization_v3_engine import _json_value

    assert json.dumps(stock, default=_json_value) == json.dumps(candidate, default=_json_value)
    assert audit["julian_cache_misses"] == 1 and audit["julian_cache_hits"] == 4
    assert len({id(obj) for obj in constructed}) == 30
