import importlib
from pathlib import Path

import pytest


@pytest.fixture
def occupancy(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return importlib.import_module("selector_occupancy")


def packet(site):
    rows = []
    for visit in range(128):
        channel = visit % 2 + 1
        for radio in (0, 1):
            rows.append(dict(
                visit_index=visit, receiver_id=radio, channel=channel, edge="lower",
                actual_rf_hz=10_000_000_000. + channel * 250_000_000., valid_start_counter=visit * 2_500_000,
                candidates=[dict(fractional_tracking_cfo_hz=500. + visit, candidate_rank=0,
                                 fractional_margin=.09, passed_fractional_margin_gate=True)],
            ))
    return dict(source=dict(probes=rows, raw_recording_authority_digest=site, qualified=True), provenance=dict(
        detector_sha256="native", processed_windows=128, invalid_capture=0, window_count=128))


def test_blackout_is_one_schedule_for_stereo_and_sites(occupancy):
    assert [i for i in range(16) if occupancy.blackout(i * 16)] == [2, 5]
    pre_a, pre_b = packet("a"), packet("b")
    a, count_a = occupancy.erased(pre_a)
    b, count_b = occupancy.erased(pre_b)
    original = pre_a["source"]["probes"]
    for native, left, right in zip(original, a["source"]["probes"], b["source"]["probes"], strict=True):
        assert left == right
        assert dict(native, candidates=[]) == dict(left, candidates=[])
        assert bool(left["candidates"]) != occupancy.blackout(native["visit_index"])
    assert count_a == count_b
    assert all(not result["source"]["qualified"] and result["provenance"]["detector_sha256"] is None for result in (a, b))
    assert all(row["candidates"] for row in original)


def test_independent_anchor_comparison_excludes_synthetic_labels(occupancy):
    evidence = occupancy.audit(packet("test"), "test")
    for radio in (0, 1):
        before = evidence["control"]["radio"][radio]
        after = evidence["treatment"]["radio"][radio]
        assert before["held"] == after["held"] == 16
        assert before["positive"] == 16
        assert after["positive"] == 12
        native = evidence["independent_native_anchors"]
        assert native["control"]["radio"][radio]["positive"] == native["treatment"]["radio"][radio]["positive"] == 12
        assert native["control"]["radio"][radio]["held"] == native["treatment"]["radio"][radio]["held"] == 12
