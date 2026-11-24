from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def study(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
    return import_module("stereo_doppler_buy")


def history(second_offset):
    return [(int(t*1e7), i, -100_000+1000*t+second_offset*(i%2))
            for i,t in enumerate((1.,1.5,2.,2.5,3.,3.5))]


def test_separated_signed_bands_require_two_independent_triples(study):
    prediction = study.forecast(history(410_000), 40_000_000)
    low, high = prediction["bands"]
    assert low["lower_hz"] < -96_000 < low["upper_hz"]
    assert high["lower_hz"] < 314_000 < high["upper_hz"]
    assert low["support_visits"] == (0,2,4) and high["support_visits"] == (1,3,5)
    assert study.forecast(history(410_000)[:-1], 40_000_000) is None
    assert study.forecast(history(410_000), 60_000_000) is None
    assert study.forecast(history(0), 40_000_000) is None


def test_never_use_current_or_future_paid_rows(study):
    with pytest.raises(ValueError, match="precede"):
        study.forecast(history(410_000), 35_000_000)


def test_exact_quartet_controls_never_open_omitted_outcomes(study, monkeypatch):
    class Omitted(dict):
        def __getitem__(self, key):
            if key == "candidates":
                raise AssertionError("The planner inspected an unmeasured lane")
            return super().__getitem__(key)

    monkeypatch.setattr(study, "QUARTETS", 1)
    monkeypatch.setattr(study, "schedule", lambda packet: [(i, "short_primary", False) for i in range(4)])
    rows = [Omitted(visit_index=i, receiver_id=r, edge="lower", channel=1,
                    actual_rf_hz=10.7e9, valid_start_counter=int(i*1e7)) for i in range(4) for r in (0,1)]
    plan = study.plan_rows({"source":{"probes":rows}})
    assert [row["buys"] for row in plan["targets"]] == [
        {"earliest":"fixed"}, {}, {"uniform":"fixed"}, {"doppler":"forced"},
    ]
