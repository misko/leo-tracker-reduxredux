from unittest.mock import patch

import pytest

from reports.ALGO08.v3 import balanced_stereo as common, complete_rf_streams as keep


def original():
    probes = []
    for visit in range(16*8):
        channel = visit % 8 + 1
        for radio in (0, 1):
            probes.append(dict(visit_index=visit, receiver_id=radio, edge="lower", channel=channel,
                               actual_rf_hz=channel*250_000_000, payload_start_sample=visit*2_500_000,
                               valid_start_counter=(visit+1)*2_500_000,
                               candidates=[dict(fractional_tracking_cfo_hz=200., fractional_margin=.5,
                                                candidate_rank=0, passed_fractional_margin_gate=True)]))
    return dict(source=dict(probes=probes), provenance=dict(excluded_windows=[], processed_windows=len(probes)//2,
                window_count=len(probes)//2, invalid_capture=0), delivery_clocks=[{} for _ in probes[::2]])


def test_four_whole_streams_preserve_full_anchors_and_rf_basis():
    with patch.object(common, "schedule", keep.schedule):
        rows = common.schedule(original())
    assert sum(row["paid"] for row in rows if row["slot"] == 0) == 16
    assert sum(row["paid"] for row in rows if row["slot"] != 0) == 56
    assert {n for n in common.donor_budget(rows).values()} == {0, 7}
    spectrum = keep.freq_support(rows)["lower"]
    assert spectrum["all"]["mean_hz"] == spectrum["continuous"]["mean_hz"]
    assert spectrum["all"]["min_hz"] == spectrum["continuous"]["min_hz"]
    assert spectrum["all"]["max_hz"] == spectrum["continuous"]["max_hz"]
    assert spectrum["all"]["variance_hz2"] / 250_000_000**2 == 5.25
    assert spectrum["continuous"]["variance_hz2"] / 250_000_000**2 == 6.25


def test_history_on_continuous_streams_requires_no_hidden_factors():
    packet = original()
    events = [dict(row, states=["measured_positive" if row["paid"] else "unmeasured"]*2)
              for row in keep.schedule(packet)]
    evidence = keep.original_history_support(packet, events)
    assert evidence["continuous"]["positive_paid"] == evidence["continuous"]["positive_original"] > 0
    assert evidence["anchors_only"]["positive_paid"] == 0
    events[8]["states"] = ["unmeasured"]*2
    with pytest.raises(ValueError, match="continuously measured"):
        keep.original_history_support(packet, events)
