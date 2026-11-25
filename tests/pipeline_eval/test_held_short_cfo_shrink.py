from math import inf

import pytest

from reports.ALGO08.v3 import held_short_cfo_shrink as trial


def row(oid, counter, hz, arrival, *, lift=1):
    integer = int(arrival)
    return dict(id=oid, counter=counter, lift=lift, short=True,
                row=dict(edge="falling", channel=2, actual_rf_hz=11_900_000_000., receiver_id=0),
                factor={trial.odd.HERTZ: hz, "integer_epoch_sample": integer,
                        "fractional_epoch_offset_samples": arrival-integer})


def test_half_bin_cap_and_direct_sign_forbid_an_alias_hop():
    assert trial.BIN_HZ == pytest.approx(443.8920454545)
    assert trial.shrink(0, trial.BIN_HZ) == trial.BIN_HZ/2
    assert trial.shrink(0, -trial.BIN_HZ) == -trial.BIN_HZ/2
    assert trial.shrink(-101_000, -101_200) == -101_100
    assert trial.shrink(0, trial.BIN_HZ+0.001) is None
    assert trial.shrink(30, 30+trial.odd.signed.ALIAS) is None
    assert trial.shrink(30, inf) is None


def test_forecast_must_straddle_with_bought_donors_and_arrival_never_changes():
    l, m, r = (row("l", 0, 100., 3), row("m", trial.odd.ADC//2, 350., 10.75),
               row("r", trial.odd.ADC, 300., 3))
    middle = {"m": {"lane": tuple(m["row"][k] for k in trial.odd.LANE)}}
    forecast, status = trial.odd.interpolate(l, m["counter"], r)
    assert status == "proposed"
    proposals, coverage = trial.nominate_changes(middle, {"l": l, "m": m, "r": r}, {"m": forecast})
    assert coverage == {"eligible": 1}
    assert proposals["m"]["updated_hz"] == pytest.approx(275.)
    actual = row("m", m["counter"], 50., 10.75)
    assert trial.aligned_errors(m, actual, proposals["m"]) == pytest.approx((300., 225., 0.))
    with pytest.raises(ValueError, match="unmeasured visit"):
        trial.nominate_changes(middle, {"l": l, "m": m, "r": r}, {"m": forecast | {"donors": ["m", "r"]}})
    with pytest.raises(ValueError, match="same-lift straddlers"):
        trial.nominate_changes(middle, {"l": l, "m": m, "r": r}, {"m": forecast | {"cfo_hz": 1.}})
    assert trial.nominate_changes(middle, {"l": l, "m": m | {"factor": None}, "r": r}, {"m": forecast}) == (
        {}, {"target_empty": 1})


def test_same_denominator_for_both_windows_and_missing_reference():
    measured = [(300., 225., 1.9), (-240., -251., 2.), (0., 10., 2.01), (2300., 2200., 6.)]
    scored = trial.evaluate(measured, 1)
    assert (scored["eligible"], scored["scored"], scored["installed_empty"]) == (5, 4, 1)
    strict, loose = (scored["windows"][key] for key in ("250Hz_2samples", "2250Hz_6samples"))
    assert (strict["joint_before"], strict["joint_after"], strict["joint_restored"], strict["joint_spoiled"]) == (1, 1, 1, 1)
    assert strict["original_arrival_only_miss"] == 1
    assert strict["original_cfo_miss_closer"] == 2
    assert (loose["joint_before"], loose["joint_after"]) == (3, 4)
    assert scored["original"]["bias_hz"] == pytest.approx(590.)
    assert scored["shrunk"]["p95_absolute_hz"] == 2200.
