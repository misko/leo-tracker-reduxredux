from tools.research.bind_independent_phase_arc import random_visits, select_arc


def test_arc_selection_uses_span_and_lexical_identity_only():
    rows = [
        {"track_id": "b", "times_s": [0, 40], "measured_hz": [0, 0]},
        {"track_id": "a", "times_s": [10, 50], "measured_hz": [1e9, -1e9]},
        {"track_id": "c", "times_s": [0, 39], "measured_hz": [0, 0]},
    ]
    assert select_arc(rows)["track_id"] == "a"
    rows[1]["measured_hz"] = [0, 0]
    assert select_arc(list(reversed(rows)))["track_id"] == "a"


def test_new_random_split_preserves_whole_visits_and_temporal_coverage():
    rows = [{"visit_index": i, "time_s": float(i)} for i in range(27)]
    first = random_visits(rows)
    second = random_visits(rows)
    assert first == second
    assert sum(row["partition"] == "train" for row in first) == 15
    assert sum(row["partition"] == "held" for row in first) == 12
    for start in (0, 9, 18):
        assert {row["partition"] for row in first[start : start + 9]} == {"train", "held"}
