"""Later recording extensions cannot enter a sealed-corpus evaluation."""

from copy import deepcopy

import pytest

from leo.analysis.research.fast_capture_projection import project_fast_capture


def test_projection_uses_exact_raw_visits_and_checks_device_support():
    doc = dict(
        source=dict(
            sample_rate_hz=1000,
            probe_ms=20,
            probes=[
                dict(visit_index=i, receiver_id=rx, valid_start_counter=i * 100)
                for i in range(4)
                for rx in (0, 1)
            ],
        ),
        last_sample_counter=400,
    )
    before = deepcopy(doc)
    windows = [dict(visit=i, sample_start=i * 100, sample_end=i * 100 + 20) for i in (0, 2)]
    projected = project_fast_capture(doc, windows)
    assert [p["visit_index"] for p in projected["source"]["probes"]] == [0, 0, 2, 2]
    assert projected["last_sample_counter"] == 220
    assert doc == before
    windows[1]["sample_start"] += 1
    with pytest.raises(ValueError, match="counter differs"):
        project_fast_capture(doc, windows)
