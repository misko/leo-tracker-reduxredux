from pathlib import Path
import sys

import numpy as np
import pytest


RESEARCH = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(RESEARCH))
try:
    from continuation_quality import (
        bracket_forecast,
        forecasting_noise,
        full_slot_brackets,
        transfer,
        variance_evidence,
    )
finally:
    sys.path.remove(str(RESEARCH))


def test_forecast_uses_only_bracketing_donors_and_includes_leverage():
    times = np.array([-4., -2., -1., 1., 2., 4.])
    track = dict(times=times, values=119000.+800.*times+40.*times**2,
                 observation_ids=[str(i) for i in range(len(times))])
    fit = bracket_forecast(track, 0.)
    assert fit["frequency_hz"] == pytest.approx(119000.)
    assert fit["slope_hz_s"] == pytest.approx(800.)
    assert fit["leverage"] > 0
    assert fit["donor_ids"] == track["observation_ids"]
    assert bracket_forecast(track, 1.) is None
    assert bracket_forecast(dict(track, values=9000.*times), 0.) is None


def test_use_original_margin_law_only_when_its_bic_test_selects_it():
    model = dict(constant_radio_sigma_hz=150., extra_parameter_BIC_gain=-1.,
                 floor_sigma_hz=80., strength_hz2=1600.)
    assert forecasting_noise(model, .25) == 150.
    model["extra_parameter_BIC_gain"] = 1.
    assert forecasting_noise(model, .25) == pytest.approx(np.sqrt(12800.))
    assert forecasting_noise(model, 1e-6) == 600.


def test_anchor_availability_uses_exact_lane_and_time_without_accessing_cfo():
    rows = [dict(observation_id=oid, receiver=rx, channel=1, actual_rf_hz=11e9, time_s=time)
            for oid, rx, time in (("a", 0, 0.), ("b", 0, 2.), ("c", 0, 5.), ("d", 1, 6.))]
    marks = {row["observation_id"]: dict(short=row["observation_id"] in ("b", "d"), supported=False)
             for row in rows}
    assert full_slot_brackets(rows, marks)["short_unsupported"] == dict(total=2, before=1, after=1, both=1)


def sample(size, supported, squared):
    return [dict(category="short_supported" if supported else "short_unsupported", visit=i,
                 lane=(1+i%2, 1, 11e9), block=i//2, periodic_innovation_hz=100.,
                 leverage_corrected_error_hz=100., standardized_squared_error=squared)
            for i in range(size)]


def test_calibration_refuses_unsupported_groups_below_frozen_minimum():
    missing = dict(held=sample(24, True, 1.)+sample(11, False, 4.))
    adequate = dict(held=sample(24, True, 1.)+sample(12, False, 4.))
    low, high = map(variance_evidence, (missing, adequate))
    assert low["descriptive_short_ratio"] == 4.
    assert low["calibrated_ratio"] is None
    assert not transfer(high, missing, low)["scored"]
    assert high["calibrated_ratio"] == 4.
    target = dict(held=sample(24, True, .4549364231)+sample(12, False, 4.))
    assert transfer(high, target, variance_evidence(target))["improves"]
