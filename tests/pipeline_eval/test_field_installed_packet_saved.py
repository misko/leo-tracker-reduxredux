import pytest

from reports.ALGO08.v3.field_installed_packet_saved import deny_backing, quality, timer_model


def terminal(decision, c0, fitted):
    return dict(decision=decision, arms={arm: dict(latlon=None if value is None else [value, 0], rf_rms_hz=4.)
                                     for arm, value in (("c0", c0), ("fitted_c", fitted))})


def test_both_arms_must_pass_and_withhold_must_match():
    distance = lambda site, endpoint: endpoint[0]
    baseline = terminal("complete", 1., 2.)
    assert quality(baseline, terminal("complete", 1.25, 1.9), distance, None)["qualified"]
    assert not quality(baseline, terminal("complete", .8, 2.251), distance, None)["qualified"]
    withheld = terminal("withheld", None, None)
    assert not quality(baseline, withheld, distance, None)["qualified"]
    assert quality(withheld, withheld, distance, None)["qualified"]


def test_budget_charges_full_publication_and_input_once():
    answer = timer_model(100., 15., 8., 35.)
    assert answer["required_native_before_2x_s"] == 27.
    assert answer["required_native_reduction_s"] == 8.
    assert answer["required_native_reduction_fraction"] == pytest.approx(8./35.)


def test_no_iq_or_backing_archive_allowed():
    with pytest.raises(ValueError, match="Saved-only"):
        deny_backing("open", ("/dev/shm/original.ci16.zst", "r", 0))
    with pytest.raises(ValueError, match="Saved-only"):
        deny_backing("open", ("/srv/bulk/metadata", "r", 0))
    deny_backing("open", ("/dev/shm/causal", "r", 0))
