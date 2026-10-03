"""Association boundaries stay conservative and receiver/target specific."""

from types import SimpleNamespace

import pytest

from leo.analysis.starlink.partial_band_segments import associate_partial_band_segments


def probe(time, frequency, *, channel=1, edge="upper", receiver=0, passed=True):
    return SimpleNamespace(
        channel=channel, edge=edge, receiver_id=receiver, time_s=time,
        visit_index=int(time * 10), probe_index=0,
        candidates=[SimpleNamespace(passed=passed, cfo_hz=frequency, rank=0)],
    )


def test_linear_track_and_explicit_candidate_only_evidence():
    rows = [probe(i * 0.1, 10000 - i * 100) for i in range(8)]
    result = associate_partial_band_segments(rows)
    assert len(result) == 1
    assert result[0]["candidate_only"] is True
    assert result[0]["slope_hz_s"] == pytest.approx(-1000)
    assert len(result[0]["observations"]) == 8


@pytest.mark.parametrize("change", [{"channel": 2}, {"edge": "lower"}, {"receiver": 1}])
def test_target_and_receiver_never_share_support(change):
    rows = [probe(i * 0.1, 10000) for i in range(3)]
    rows += [probe(i * 0.1, 10000, **change) for i in range(3, 6)]
    assert associate_partial_band_segments(rows) == []


def test_large_gap_and_failed_candidates_cannot_extend_track():
    rows = [probe(i * 0.1, 10000) for i in range(3)]
    rows += [probe(0.3, 10000, passed=False), probe(3.0, 10000)]
    assert associate_partial_band_segments(rows) == []
