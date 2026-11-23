import numpy as np
import pytest

from reports.ALGO08.v3.anchor_sky import (
    ADC,
    ALIAS,
    PERIOD,
    Factor,
    Lane,
    anchor_factors,
    cluster,
    diagnostic_packet,
    match,
    ranked,
    stereo_offset,
    timing_proposal,
)


def lane(index, time, channel, rx=0):
    return Lane(index, index, rx, channel, 10_709_687_500. + (channel-1)*250e6,
                "lower", round(time*ADC), time)


def test_provisional_orbit_links_different_rfs_and_keeps_signed_alias():
    anchors = [lane(i, float(i), 1+i%2) for i in range(4)]
    target = lane(4, 1.5, 3)
    geometry = np.array([[15000. + p.time*1000 + p.channel*175 for p in [*anchors, target]],
                         [10000., -55083., 6338., -2350., -20000.]])
    delay = np.array([[95500 + 220*p.time for p in [*anchors, target]], [0., 0., 0., 0., 0.]])
    factors = [Factor(p, float(geometry[0, p.index]+3280.0-ALIAS),
                      (10500.+16.*p.time+delay[0, p.index]) % PERIOD) for p in anchors]
    fits, matches = cluster(factors, geometry, 0, None)
    assert matches == 1
    assert fits[0].alias == -1
    assert fits[0].offset == pytest.approx(3280.)
    assert timing_proposal(fits[0], target, delay, False) is None
    assert timing_proposal(fits[0], target, delay, True) == pytest.approx(
        (10500. + 16*target.time + delay[0, target.index]) % PERIOD)


def test_stereo_offset_counts_visits_and_never_claims_phase_alignment():
    pairs = [Factor(lane(i, float(i), 1+i%2, rx), -10000.+i*50.+rx*1000., rx*1200.)
             for i in range(3) for rx in (0, 1)]
    assert stereo_offset(pairs)[0] == pytest.approx(1000.)
    assert stereo_offset(pairs[:2] * 8)[0] is None


def test_held_factors_are_inaccessible_to_anchor_selection():
    points = [lane(i, i*.25, 1) for i in range(2)]
    raw = dict(fractional_tracking_cfo_hz=-5000., integer_epoch_sample=100,
               fractional_epoch_offset_samples=.25)
    rows = [{"candidates": [raw]}, {}]
    used = anchor_factors(rows, points, {0})
    assert len(used) == 1
    assert used[0].cfo == -5000.


def test_signed_credit_and_frame_wrap_require_distinct_proposals():
    raw = dict(integer_epoch_sample=0, fractional_epoch_offset_samples=.25,
               fractional_tracking_cfo_hz=-55000.)
    offers = [dict(frequencies=[55000.], phase_same=PERIOD-1),
              dict(frequencies=[-55000.], phase_same=PERIOD-1),
              dict(frequencies=[-55001.], phase_same=0.)]
    attempts = ranked(offers)
    assert len(attempts) == 2
    assert match(0, [raw, raw], attempts, "phase_same") == [raw]
    assert match(0, [raw], attempts[:1], None) == []


def test_diagnostic_packet_excludes_held_factors_and_model_identities():
    rows = [dict(visit_index=i, receiver_id=rx, channel=1, actual_rf_hz=10_709_687_500.,
                 edge="lower", valid_start_counter=i, candidates=[object()])
            for i in range(49) if i != 4 for rx in (0, 1)]
    offered = {3: [dict(norad=12345, frequencies=[-12345.], phase_same=0.25, phase_shared=None)]}
    packet = diagnostic_packet(rows, {0}, offered, dict(raw_authority="raw", session_id="session"), "locked",
                               rejected_visits=[dict(visit=4, reason="invalid sample support")])
    assert packet["first_visit"] == 0
    assert len(packet["receiver_rows"]) == 94
    assert packet["rejected_visits"] == [dict(visit_index=4, reason="invalid sample support")]
    assert packet["receiver_rows"][0]["full_anchor"]
    result = packet["receiver_rows"][3]
    assert result["local_time"][0]["epoch_sample"] == pytest.approx(PERIOD-.75)
    assert not result["shared_time"]
    assert "candidates" not in result and "norad" not in result
