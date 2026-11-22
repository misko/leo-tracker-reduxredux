from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from tools.pipeline_eval.variants.experimental.receiver_cadence import BurstCadence


def test_interleaved_rf_visits_keep_real_time_and_both_lanes_in_selected_bursts():
    cadence = BurstCadence()
    seen = []
    def detector():
        def detect(w):
            seen.append(w.acquisition["global_visit"])
            return list(w.receiver_ids)
        return nullcontext(detect)
    with cadence.wrap(detector)() as receiver:
        for visit in range(49):
            channel = visit % 3
            window = SimpleNamespace(acquisition=dict(actual_if_center_hz=100 + channel, global_visit=visit),
                                     target=dict(lnb_lo_hz=1000, channel=channel), receiver_ids=(0, 1))
            assert receiver(window) == ([0, 1] if visit < 24 or visit == 48 else [])
    assert seen == [*range(24), 48]
    counts = dict(processed=25, invalid_capture=2)
    assert cadence.receipt(dict(window_count=51, counts=counts))["skipped_by_channel"] == {0: 8, 1: 8, 2: 8}
    with pytest.raises(ValueError, match="reconcile"):
        cadence.receipt(dict(window_count=50, counts=counts))
