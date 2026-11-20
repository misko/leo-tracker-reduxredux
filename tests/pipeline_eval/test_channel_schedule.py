import gzip
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from tools.pipeline_eval.qualification.duty_results import REPORT
from tools.pipeline_eval.variants import channel_schedule as schedule


def test_opposite_schedules_partition_original_visits_without_changing_clock_or_identity():
    rows = [
        dict(visit_index=2 * i, channel=i + 1, receiver_id=j, candidates=[(i, j)])
        for i in range(8)
        for j in (0, 1)
    ]
    document = {
        "clock_anchor": {"sample_counter": 19},
        "last_sample_counter": 9041,
        "source": {"session_id": "a", "probes": rows},
        "provenance": {"processed_windows": 8},
    }
    before = deepcopy(document)
    retained = []
    for method in schedule.SCHEDULES:
        scan, metrics = schedule.selected_probes(document, method)
        picked = scan["source"]["probes"]
        assert all(any(row is original for original in rows) for row in picked)
        assert [row["channel"] for row in picked] == [
            c for c in schedule.SCHEDULES[method] for _ in (0, 1)
        ]
        assert metrics["kept_valid_visits"] == 4 and metrics["original_valid_visits"] == 8
        assert (
            scan["clock_anchor"] is document["clock_anchor"] and scan["last_sample_counter"] == 9041
        )
        retained.extend(r["visit_index"] for r in picked)
    assert sorted(retained) == sorted(r["visit_index"] for r in rows) and document == before
    rows[1]["channel"] = 3
    with pytest.raises(ValueError, match="different RF"):
        schedule.selected_probes(document, "glrt_even_channels")


def test_schedule_acts_before_the_detector_and_keeps_both_receivers():
    window = SimpleNamespace(target={"channel": 6}, receiver_ids=["left", "right"])
    called = []

    def analyze(window, receivers, extra, policy):
        called.append((window, receivers, extra, policy))
        return "analyzed"

    assert schedule.analyze_scheduled(window, "glrt_odd_channels", analyze, "policy") is None
    assert not called
    assert schedule.analyze_scheduled(window, "glrt_even_channels", analyze, "policy") == "analyzed"
    assert called == [(window, window.receiver_ids, None, "policy")]
    for invalid in (0, 9, True, 1.25):
        with pytest.raises(ValueError):
            schedule.scheduled("glrt_odd_channels", invalid)


def test_final_channel_wrapper_reproduces_both_measured_versions_on_ds29():
    with gzip.open(REPORT / "channel-repeat.jsonl.gz", "rt") as stream:
        repeats = list(map(json.loads, stream))
    with gzip.open(REPORT / "channel-pairs.jsonl.gz", "rt") as stream:
        originals = {(r["id"], r["method"]): r for r in map(json.loads, stream)}
    assert len(repeats) == 2 and {r["method"] for r in repeats} == set(schedule.SCHEDULES)
    assert len({r["implementation_sha256"] for r in repeats}) == 1
    assert len({originals["DS29-0082", r["method"]]["implementation_sha256"] for r in repeats}) == 2
    for row in repeats:
        assert row["id"] == "DS29-0082"
        original = originals[row["id"], row["method"]]
        assert row["input_sha256"] == original["input_sha256"]
        assert row["result"]["arms"] == original["result"]["arms"]
        for name in ("kept_probes", "original_probes", "valid_visits_by_channel", "tracks"):
            assert row["result"]["metrics"][name] == original["result"]["metrics"][name]
