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


def test_ineligible_installed_source_runs_the_original_once(monkeypatch):
    from leo.application import localization_v3

    seen = []

    def original(history):
        seen.append(history)
        return history

    monkeypatch.setattr(localization_v3, "forecast", original)
    monkeypatch.setattr(phase_prior, "forecast", original)
    monkeypatch.setattr(variant, "PHASE_SHA", "wrong source")
    history, audit = {"orig": True}, {"executions": []}
    with variant.active_forecast(audit):
        assert localization_v3.forecast(history) is history
    assert localization_v3.forecast is original and seen == [history]
    (execution,) = audit["executions"]
    assert not execution["used"]
    assert execution["fallback"].startswith("unreviewed installed phase source ")


def test_original_data_validation_failure_still_propagates_once(monkeypatch):
    from leo.application import localization_v3

    seen = []

    def fail(history):
        seen.append(history)
        raise ValueError("malformed original causal data")

    monkeypatch.setattr(localization_v3, "forecast", fail)
    monkeypatch.setattr(phase_prior, "forecast", fail)
    audit = {"executions": []}
    with pytest.raises(ValueError, match="malformed original causal data"), variant.active_forecast(audit):
        localization_v3.forecast("bad input")
    assert localization_v3.forecast is fail and seen == ["bad input"]
    assert phase_prior.transition.__name__ == "transition" and audit["executions"] == []


def test_installed_table_wrapper_still_clocks_the_exact_forecast(monkeypatch):
    from leo.application import localization_v3
    from leo.application.localization_v3_engine import _json_value
    from tools.pipeline_eval.variants import algo08_causal_table

    history = {"case": "SCAN", "cutoff_utc_ns": 1_794_568_912_154_038_024, "past_versions": {}}
    expected = phase_prior.forecast(history)
    with algo08_causal_table.causal_table() as table:
        original = localization_v3.forecast
        audit = {"executions": []}
        with variant.active_forecast(audit):
            actual = localization_v3.forecast(history)
            assert json.dumps(actual, default=_json_value) == json.dumps(expected, default=_json_value)
        assert localization_v3.forecast is original
        assert table["forecast_calls"] == 1
    (run,) = audit["executions"]
    assert run["used"] and audit["source_sha256"]["installed/algo08_causal_table.py"] == variant.TABLE_SHA

    def different(history):
        return None

    substituted = algo08_causal_table.timed(different, {}, "forecast")
    monkeypatch.setattr(substituted, "__wrapped__", phase_prior.forecast)
    assert not variant.checked_table_wrapper(substituted, phase_prior.forecast)
