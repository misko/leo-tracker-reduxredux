from types import SimpleNamespace

import pytest
from regions import ReplayCheckpoints

from leo.analysis.regional_position_search import SpatialEvaluation, SpatialSearch, distinct_basins


def test_separation_preserves_remote_region_with_same_three_slot_budget():
    search = SpatialSearch(
        tuple(
            SpatialEvaluation(e, n, 5, s)
            for e, n, s in [
                (47.5, -137.5, 1),
                (62.5, -142.5, 2),
                (52.5, -122.5, 3),
                (-87.5, -97.5, 4),
                (62.5, -167.5, 5),
            ]
        ),
        0,
        "test",
    )
    narrow = distinct_basins(search, count=3, minimum_separation_km=12.5)
    broad = distinct_basins(search, count=3, minimum_separation_km=25)
    assert len(narrow) == len(broad) == 3
    assert all(p.east_km > 0 for p in narrow)
    assert broad[1].east_km == -87.5
    assert broad[0] == narrow[0]


def test_replay_cannot_borrow_recovery_or_write_original_cache():
    original = {"point:1:2": {"result": "seed"}, "recovery:x": {"result": "old"}}
    fresh = {}
    borrowed = set()
    replay = ReplayCheckpoints(
        SimpleNamespace(checkpoint=original.__getitem__),
        SimpleNamespace(get=fresh.get, put=fresh.__setitem__),
        "new:",
        borrowed,
    )
    assert replay.get("new:point:1:2") == original["point:1:2"]
    assert replay.get("new:recovery:x") is None
    assert replay.get("new:point:3:4") is None
    replay.put("new:recovery:x", {"result": "new"})
    assert replay.get("new:recovery:x") == {"result": "new"}
    assert original["recovery:x"] == {"result": "old"}
    assert borrowed == {"point:1:2"}
    with pytest.raises(AssertionError):
        replay.get("wrong:point:1:2")
