from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from algo02_scan import paired_policy, pair_passes, validate_history, validate_prior_receipt


def record(valid=True, phase=.001):
    return dict(gates=dict(tracks=[dict(compatible=valid)]), linear_gates=[dict(compatible=True)],
                final_phase_change_s=phase, endpoint_east_north_km=[1., -2.])


def test_one_failed_c_arm_falls_back_both_arms_without_selecting_by_score():
    curved = {arm: record() for arm in ("c0", "fitted_c")}
    linear = deepcopy(curved)
    linear["fitted_c"]["linear_gates"][0]["compatible"] = False
    linear["c0"]["negative_twice_elbo"] = -1e20
    policy, accepted = paired_policy(curved, linear)
    assert not accepted
    assert policy is curved


def test_phase_refresh_and_region_are_required_even_with_passing_residuals():
    pair = {arm: record() for arm in ("c0", "fitted_c")}
    assert pair_passes(pair, include_linear=True)
    pair["c0"]["final_phase_change_s"] = .011
    assert not pair_passes(pair, include_linear=True)
    pair["c0"]["final_phase_change_s"] = .001
    pair["fitted_c"]["endpoint_east_north_km"] = [12.5001, 0.]
    assert not pair_passes(pair, include_linear=True)


def history_fixture():
    scan = SimpleNamespace(case="DS23-9999", receipt=dict(origin_utc_ns=1000, cutoff_utc_ns=1000))
    raw = dict(case=scan.case, **scan.receipt,
               past_versions={"1": [dict(epoch=500, collected_utc_ns=600)],
                              "unselected": [dict(epoch=700, collected_utc_ns=800)]})
    forecast = dict(case=scan.case, history_sha256="digest", strictly_pre_RF=True,
                    GPS_or_radio_used=False, all_past_distribution=dict(shrinkage=.5, multiplier=2., nu=4),
                    distribution_validation=dict(count=40, negative_twice_log_density=50.),
                    original_distribution_validation=dict(negative_twice_log_density=60.))
    return raw, forecast, scan


def test_causal_forecast_rejects_future_collection_even_for_unselected_candidate():
    raw, forecast, scan = history_fixture()
    raw["past_versions"]["unselected"][0]["collected_utc_ns"] = 1001
    with pytest.raises(ValueError, match="post-scan"):
        validate_history(raw, forecast, scan, "digest")


def test_insufficient_pre_RF_validation_falls_back_to_original_phase_prior():
    raw, forecast, scan = history_fixture()
    model, valid = validate_history(raw, forecast, scan, "digest")
    assert valid and model["shrinkage"] == .5
    forecast["distribution_validation"]["count"] = 29
    model, valid = validate_history(raw, forecast, scan, "digest")
    assert not valid
    assert model == dict(shrinkage=0., multiplier=1., nu=None, fallback=True)


def test_history_digest_and_recording_identity_are_mandatory():
    raw, forecast, scan = history_fixture()
    with pytest.raises(ValueError, match="digest"):
        validate_history(raw, forecast, scan, "changed")
    raw["case"] = "another"
    with pytest.raises(ValueError, match="another recording"):
        validate_history(raw, forecast, scan, "digest")


def test_prior_rejects_pre_scan_epoch_collected_after_scan():
    receipt = dict(cutoff_utc_ns=1000, origin_utc_ns=1000, reference_position_used=False,
                   search_center=[37.906, -122.545], search_box_width_km=25.)
    previous = dict(catalogue_sha256="digest",
                    sources={"1": dict(epoch_utc_ns=500, collected_utc_ns=1001)})
    with pytest.raises(ValueError, match="post-scan"):
        validate_prior_receipt(receipt, previous, "digest")


def test_prior_search_center_cannot_be_replaced_by_evaluation_coordinate():
    receipt = dict(cutoff_utc_ns=1000, origin_utc_ns=1000, reference_position_used=False,
                   search_center=[0., 0.], search_box_width_km=25.)
    with pytest.raises(ValueError, match="regional search"):
        validate_prior_receipt(receipt, dict(catalogue_sha256="digest", sources={}), "digest")
