import pytest

from tools.pipeline_eval.qualification import arrival_clock as analysis


def visits():
    return [
        [0, 0, "detector", 10, 12],
        [1, 2, "invalid_capture", 0, 0],
        [2, 3, "detector", 5, 5],
        [3, 10, "detector", 2, 2],
        [4, 10, "schedule_skipped", 0, 0],
    ]


def test_fcfs_waiting_slots_release_on_dispatch_and_count_physical_events():
    blocked = analysis.simulate(visits(), 1, 0)
    assert blocked["counts"] == dict(detector=3, invalid_capture=1, schedule_skipped=1, dropped=1)
    assert blocked["completed"] == [(0, 0, 0, 10), (3, 10, 10, 12)]
    assert blocked["drain_ns"] == 2
    waiting = analysis.simulate(visits(), 1, 1)
    assert waiting["completed"] == [(0, 0, 0, 10), (2, 3, 10, 15), (3, 10, 15, 17)]
    assert waiting["drain_ns"] == 7
    assert waiting["max_waiting"] == 1
    parallel = analysis.simulate(visits(), 2, 0)
    assert parallel["completed"] == [(0, 0, 0, 10), (2, 3, 3, 8), (3, 10, 10, 12)]
    assert parallel["max_waiting"] == 0


def test_wall_service_ties_and_zero_service_slots():
    a = analysis.simulate(visits(), 1, 1, wall=True)
    assert a["counts"]["dropped"] == 1
    assert a["completed"][-1] == (2, 3, 12, 17)
    bad = visits()
    bad[1][3] = 1
    with pytest.raises(ValueError, match="excluded visit"):
        analysis.simulate(bad, 1)
    bad = visits()
    bad[4][1] = 7
    with pytest.raises(ValueError, match="malformed physical"):
        analysis.simulate(bad, 2)


def test_measured_event_ledgers_retain_all_slots_and_never_score_dropped_positions(tmp_path):
    baseline = analysis.REPORT
    rows = analysis.gzip_json(baseline / analysis.TRACE)
    assert len(rows) == 4
    for ident, physical, invalid in (("DS26-0036", 6769, 4), ("DS29-0082", 6772, 1904)):
        original, scheduled = (row for row in rows if row["id"] == ident)
        assert [orig[:2] for orig in original["events"]] == [
            item[:2] for item in scheduled["events"]
        ]
        assert len(original["events"]) == physical
        assert sum(item[2] == "invalid_capture" for item in original["events"]) == invalid
        for record in (original, scheduled):
            scores = list(analysis.queue_rows(record))
            assert all(
                item["earliest_complete_position_after_last_delivery_s"] is None
                for item in scores
                if item["dropped"]
            )
    analysis.score(baseline, tmp_path)
    for file in ("queue.csv", "summary.json", "paced-visits.csv", "paced-summary.json"):
        assert (tmp_path / file).read_bytes() == (baseline / file).read_bytes()
