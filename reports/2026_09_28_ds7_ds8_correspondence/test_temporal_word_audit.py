from temporal_word_audit import branches, periodic_conflicts


def test_period_is_tested_within_groups_and_allows_missing_frames():
    rows = [dict(group="a", frame=f, word=str(f % 3)) for f in [0, 1, 3, 4, 7]]
    rows.append(dict(group="b", frame=0, word="different"))
    assert periodic_conflicts(rows, 3) == 0
    assert periodic_conflicts(rows, 2) > 0


def test_branch_requires_adjacent_frames_in_same_visit():
    rows = [dict(group="a", frame=f, word=w) for f, w in enumerate(["a", "b", "a", "c"])]
    assert len(branches(rows)) == 1
    rows[-1]["frame"] = 5
    assert not branches(rows)
