import pytest

from reports.ALGO08.v3.eight_ms_primary import checked_shape
from reports.ALGO08.v3.four_frame_primary import ORDERS, scientific_gate, shape
from reports.ALGO08.v3.short_signed_trial import short_source


def test_four_independent_origins_require_66444_samples():
    admitted = shape()
    assert admitted["last_origin"] == 40_000
    assert admitted["first_unused_latest_confirmation_sample"] == admitted["short_samples"] == 66_444
    for samples, frames in ((60_000, 4), (60_000, 3), (66_440, 4), (66_444, 5)):
        with pytest.raises(ValueError, match="lacks complete"):
            checked_shape(samples, frames)
    source = "points = 200000; count = 14; early ? 7 : 2"
    assert short_source("timing_first_receiver", source, 66_444, 4) == (
        "points = 66444; count = 4; early ? count / 2 : 2"
    )
    assert ORDERS[0] == ORDERS[1][::-1]


def factor(epoch, hz, margin=0.2, rank=0):
    return dict(integer_epoch_sample=epoch, fractional_epoch_offset_samples=0.0,
                fractional_tracking_cfo_hz=hz, fractional_margin=margin, candidate_rank=rank,
                passed_fractional_margin_gate=True)


def probes(measurement):
    return [dict(edge="lower", channel=0, actual_rf_hz=10.7e9, visit_index=visit, receiver_id=antenna,
                 candidates=[factor(0, -1000)] if visit == 0 else measurement(antenna))
            for visit in range(5) for antenna in (0, 1)]


def test_science_uses_paired_antenna_epochs_signed_cfo_and_full_support():
    baseline = probes(lambda _: [factor(0, -1100)])
    candidate = probes(lambda _: [factor(13_332, -1100)])
    full = probes(lambda _: [factor(0, -1000, rank=1)])
    gate = scientific_gate(baseline, candidate, full)
    assert gate["passed"]
    assert gate["residuals"]["eight_four"]["epoch_samples"]["maximum"] == 1
    assert gate["residuals"]["full_four_common"]["cfo_hz"]["rms"] == 100

    candidate = probes(lambda antenna: [factor(0, 1100)] if antenna else [factor(0, -1270)])
    gate = scientific_gate(baseline, candidate, full)
    assert not gate["passed"]
    assert not gate["gates"]["eight_support"]
    assert not gate["gates"]["eight_strong"]
    assert not gate["gates"]["full_support"]
    assert not gate["gates"]["common_support"]
    assert gate["differences"][1]["eight_to_four"][1] == 2200


def test_science_rejects_anchors_and_incomplete_opportunities():
    rows = probes(lambda _: [])
    changed = probes(lambda _: [])
    changed[0]["candidates"] = []
    with pytest.raises(ValueError, match="anchor"):
        scientific_gate(rows, changed, rows)
    with pytest.raises(ValueError, match="argument"):
        scientific_gate(rows, rows, rows[:-1])
