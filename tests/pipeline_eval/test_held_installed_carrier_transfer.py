from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def study(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("held_installed_carrier_transfer")


def test_receiver_strata_preserve_full_denominators_and_paired_transitions(study):
    from reports.ALGO08.v3 import held_short_cfo_shrink as held

    rows = {"gain": (251., 244., .1), "empty": None, "spoiled": (243., 260., .1),
            "never-matched": (study.method.residual.PERIOD+12., study.method.residual.PERIOD+10., .1)}
    opportunities = {key: dict(radio=rx) for key, rx in (("gain", 0), ("empty", 0), ("spoiled", 1), ("never-matched", 1))}
    result = study.receiver_view(rows, opportunities, held.evaluate, held.odd.WINDOWS, study.method.residual.PERIOD)
    assert [result[rx]["eligible"] for rx in ("0", "1")] == [2, 2]
    assert [result[rx]["installed_empty"] for rx in ("0", "1")] == [1, 0]
    assert result["0"]["windows"]["250Hz_2samples"]["joint_restored"] == 1
    strict = result["1"]["windows"]["250Hz_2samples"]
    assert strict["joint_spoiled"] == 1 and strict["joint_after"] == 0
    assert strict["alias_only_before"] == strict["alias_only_after"] == 1

    opportunities["empty"]["radio"] = 2
    with pytest.raises(ValueError, match="native receivers"):
        study.receiver_view(rows, opportunities, held.evaluate, held.odd.WINDOWS, study.method.residual.PERIOD)
