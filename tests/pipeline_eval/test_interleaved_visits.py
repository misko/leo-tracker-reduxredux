from collections import Counter
from copy import deepcopy

import pytest

from tools.pipeline_eval.__main__ import OPT_IN_VARIANTS, module_name
from tools.pipeline_eval.qualification import interleaved_trial
from tools.pipeline_eval.qualification.interleaved_results import publish
from tools.pipeline_eval.variants import interleaved_visits as schedule


def capture(count, excluded=()):
    probes = [
        dict(visit_index=i, channel=i % 8 + 1, receiver_id=rx, candidates=[i + rx])
        for i in range(count)
        if i not in excluded
        for rx in (0, 1)
    ]
    return dict(
        delivery_clocks=[{"realtime_ns": i + 1} for i in range(count)],
        source={"probes": probes},
        provenance=dict(
            window_count=count,
            processed_windows=count - len(excluded),
            excluded_windows=[{"visit": i} for i in excluded],
        ),
    )


def test_schedule_is_known_before_detection_and_keeps_three_visits_per_channel_per_four_sweeps():
    visits = [i for i in range(32) if schedule.scheduled(i, i % 8 + 1)]
    assert Counter(i % 8 + 1 for i in visits) == dict.fromkeys(range(1, 9), 3)
    assert Counter(i // 8 for i in visits) == dict.fromkeys(range(4), 6)
    assert schedule.METHOD in OPT_IN_VARIANTS
    assert module_name(schedule.METHOD) == schedule.__name__


def test_selection_preserves_clocks_captured_values_partial_sweeps_and_exclusions():
    doc = capture(35, excluded=(1, 19, 34))
    original = deepcopy(doc)
    view, audit = schedule.select_document(doc)
    expected = [
        p for p in doc["source"]["probes"] if schedule.scheduled(p["visit_index"], p["channel"])
    ]
    assert view["source"]["probes"] == expected and doc == original
    assert view["delivery_clocks"] == doc["delivery_clocks"]
    assert view["provenance"] == original["provenance"]
    assert audit["valid_visits"] == 32 and audit["retained_visits"] == len(expected) // 2
    assert {p["visit_index"] for p in expected} >= {33}


@pytest.mark.parametrize("defect", ["missing_rx", "duplicate_rx", "channel", "excluded", "clock"])
def test_partial_native_artifacts_cannot_silently_change_the_workload(defect):
    doc = capture(9, excluded=(8,))
    if defect == "missing_rx":
        doc["source"]["probes"].pop()
    elif defect == "duplicate_rx":
        doc["source"]["probes"].append(doc["source"]["probes"][0])
    elif defect == "channel":
        doc["source"]["probes"][0]["channel"] = 2
    elif defect == "excluded":
        doc["provenance"]["excluded_windows"][0]["visit"] = 1
    else:
        doc["delivery_clocks"].pop()
    with pytest.raises(ValueError):
        schedule.select_document(doc)


def test_stored_roster_draw_uses_only_ids_and_has_two_reserves_from_each_dataset():
    ids = interleaved_trial.baseline.frozen_inputs()
    expected = ["DS26-0036", "DS29-0082", "DS26-0094", "DS26-0066", "DS29-0604", "DS29-0519"]
    assert interleaved_trial.roster({i: None for i in ids}) == expected
    assert interleaved_trial.roster(list(reversed(ids))) == expected


def test_offline_scores_and_chart_rebuild_from_the_sealed_six_capture_dataset(tmp_path):
    report = interleaved_trial.REPORT
    publish(report, tmp_path)
    for name in ("scores.csv", "figures.json", "figure-lock.json"):
        assert (tmp_path / name).read_bytes() == (report / name).read_bytes()
