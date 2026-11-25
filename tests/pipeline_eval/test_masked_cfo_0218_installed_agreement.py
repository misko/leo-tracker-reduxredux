from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def study(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("masked_cfo_0218_installed_agreement")


def test_physical_arrival_wrap_keeps_signed_cfo_unwrapped(study):
    from reports.ALGO08.v3 import held_short_cfo_shrink as held

    def lane(hz, integer, fractional):
        return dict(counter=30_391_194_741_537, short=True, factor=dict(fractional_tracking_cfo_hz=hz,
                    integer_epoch_sample=integer, fractional_epoch_offset_samples=fractional))

    mixed = lane(252., 13_332, .9)
    stock = lane(0., 0, .2)
    edit = dict(original_hz=252., updated_hz=248., forecast_hz=244.,
                arrival=held.arrival_phase(mixed["counter"], mixed["factor"]))
    result = study.matched_rows({"row": edit}, {"row": mixed}, {"row": stock}, held.aligned_errors)["row"]
    assert result[:2] == (252., 248.)
    assert 0 < result[2] < 2
    summary = study.summarize([result], held.evaluate, held.odd.WINDOWS, study.residual.PERIOD)
    assert summary["windows"]["250Hz_2samples"]["joint_restored"] == 1


def test_alias_diagnostic_never_replaces_signed_agreement_or_fills_empty(study):
    from reports.ALGO08.v3 import held_short_cfo_shrink as held

    period = study.residual.PERIOD
    rows = {"wrapped": (period+12., period+20., 1.), "near": (252., 248., .2), "empty": None}
    owners = {"c0": {"wrapped": None}, "fitted_c": {"empty": None, "near": None}}
    result = study.view(rows, owners, held.evaluate, held.odd.WINDOWS, period)
    all_edits = result["all_edits"]
    assert all_edits["scored"] == 2 and all_edits["installed_empty"] == 1
    assert all_edits["matched_coverage"] == pytest.approx(2/3)
    strict = all_edits["windows"]["250Hz_2samples"]
    assert strict["alias_only_before"] == strict["alias_only_after"] == 1
    assert strict["joint_before"] == 0 and strict["joint_after"] == 1
    assert result["by_ordinary_arm"]["c0"]["owned"]["scored"] == 1
    assert result["by_ordinary_arm"]["fitted_c"]["owned"]["installed_empty"] == 1


def test_opportunity_identity_failure_cannot_be_counted_as_detector_empty(study):
    lane = dict(counter=8, short=True, factor={"signed": True})
    original = {"edited": lane}
    with pytest.raises(ValueError, match="matching authenticated installed opportunity"):
        study.matched_rows({"edited": {}}, original, {}, lambda *_: None)
    with pytest.raises(ValueError, match="same signed short opportunity"):
        study.matched_rows({"edited": {}}, original, {"edited": dict(lane, counter=9)}, lambda *_: None)
