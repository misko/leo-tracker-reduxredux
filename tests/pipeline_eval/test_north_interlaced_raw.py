import pytest

from reports.ALGO08.v3.north_interlaced_raw import GRAPH, streams_and_slots, strongest


def test_primary_schedule_moves_alternating_lane_and_wraps_only_within_each_triple():
    records = [(rank, 10_000_000 + rank, "lower") for _ in range(6) for rank in range(3)]
    _, paid = streams_and_slots(records, visits_per_stream=6, stream_count=3)
    assert paid == {
        (0, 1), (3, 0), (9, 1), (12, 0),
        (4, 0), (7, 1), (13, 0), (16, 1),
        (8, 1), (2, 0), (17, 1), (11, 0),
    }
    assert len({visit for visit, _ in paid}) == len(paid)


def test_northern_plan_requires_complete_balanced_triples():
    with pytest.raises(ValueError, match="complete stereo triples"):
        streams_and_slots([(0, 10, "lower")] * 4, visits_per_stream=4, stream_count=1)
    with pytest.raises(ValueError, match="complete stereo triples"):
        streams_and_slots([(0, 10, "lower")] * 3 + [(0, 11, "lower")] * 2,
                          visits_per_stream=3, stream_count=2)


def test_native_choice_uses_margin_then_original_rank_only():
    lower = dict(passed_fractional_margin_gate=True, fractional_margin=.2, candidate_rank=0)
    higher = dict(passed_fractional_margin_gate=True, fractional_margin=.5, candidate_rank=1)
    assert strongest([lower, higher]) is higher
    assert strongest([higher, dict(lower, fractional_margin=.5)])["candidate_rank"] == 0
    assert strongest([]) is None
    with pytest.raises(ValueError, match="unverified"):
        strongest([dict(higher, passed_fractional_margin_gate=False), lower])
    assert GRAPH == dict(max_degree=2, points_per_coefficient=2, min_points=6)
