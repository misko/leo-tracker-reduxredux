from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).parent
SOURCE = HERE / "iteration4_group_union.py"


def module():
    spec = importlib.util.spec_from_file_location("iteration4_union_test", SOURCE)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def point(lat, lon, tau, objective):
    return {
        "latitude_deg": lat,
        "longitude_deg": lon,
        "tau_s": tau,
        "selection_objective": objective,
    }


def test_shortlist_deduplicates_and_retains_both_finalists():
    runner = module()
    traces = [point(1.0 + n, 2.0, 0.0, n) for n in range(10)]
    data = {
        "results": [
            {
                "task_id": "iteration3--train-20260921_00--prefix-6--reno",
                "screen_trace": traces,
                "winner": point(30, 2, 0, 30),
            },
            {
                "task_id": "iteration3--train-20260921_00--prefix-6--sacramento",
                "screen_trace": traces,
                "winner": point(40, 2, 0, 40),
            },
        ]
    }
    selected = runner.shortlist(data, "20260921_00")
    assert len(selected) == 10
    assert {row["latitude_deg"] for row in selected} >= {30, 40}


def test_source_task_excludes_reference():
    runner = module()
    source = {
        "task_id": "x",
        "group_id": "20260921_00",
        "session_ids": ["scan"],
        "session_groups": {"scan": "20260921_00"},
        "prior": {},
    }
    assert "reference" not in runner.source_task(source)
