import importlib
from pathlib import Path

import pytest


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return importlib.import_module("quiet_cycle")


def packet(channels, present):
    rows = []
    for visit, channel in enumerate(channels):
        for radio in (0, 1):
            rows.append(dict(visit_index=visit, receiver_id=radio, channel=channel, edge="lower",
                             actual_rf_hz=channel, candidates=(
                                 [dict(passed_fractional_margin_gate=True)] if (radio, visit) in present else [])))
    return dict(source=dict(probes=rows), provenance=dict(processed_windows=len(channels),
                window_count=len(channels), invalid_capture=0))


def test_right_anchor_veto_and_incomplete_tail(quiet):
    result = quiet.census(packet([1] * 16, {(1, 8), (0, 10)}))
    assert result["short_lanes"] == 28
    assert result["short_positive_lanes"] == 1
    assert result["policies"]["individual"]["oracle_veto_skipped_calls"] == 6
    assert result["policies"]["stereo"]["skipped_calls"] == 0


def test_oracle_reinstates_entire_group(quiet):
    result = quiet.census(packet([1] * 9, {(0, 1), (0, 5)}))
    individual, stereo = (result["policies"][kind] for kind in ("individual", "stereo"))
    assert individual["skipped_calls"] == stereo["skipped_calls"] == 12
    assert individual["lost_positive_lanes"] == stereo["lost_positive_lanes"] == 2
    assert individual["oracle_veto_skipped_calls"] == 6
    assert stereo["oracle_veto_skipped_calls"] == 0


def test_stream_specific_midpoints_and_overlapping_anchor(quiet):
    result = quiet.census(packet([1, 2] * 17, {(0, 8), (0, 16)}))
    assert result["policies"]["stereo"]["tested_groups"] == 4
    assert result["policies"]["stereo"]["skipped_calls"] == 24
    assert result["policies"]["individual"]["skipped_calls"] == 36
    assert result["policies"]["stereo"]["lost_positive_lanes"] == 0
