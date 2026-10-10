"""Pure metadata fixtures; no recordings, storage ports or numerical models."""
import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("grouping159_test", Path(__file__).with_name("grouping.py"))
grouping = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grouping)

IDENTITY = dict(session_id="s", input_manifest_sha256="capture",
                raw_recording_authority_digest="raw", radio_id="radio",
                stream_generation="stream", sample_rate_hz=10_000_000)


def support(segments):
    rows = [dict(index=i, visit_index=v, receiver=r, probe_index=i,
                 window_id=f"w{i}", candidate_id=f"c{i}", support_status="available",
                 support_reason=None, device_sample_start=a, device_sample_end=b)
            for i, (v, r, a, b) in enumerate(segments)]
    return dict(rows=rows, observations=len(rows), available=len(rows), unavailable_reasons={})


def alternating(monkeypatch):
    assigned = {}
    def fold(group_id, seed):
        return assigned.setdefault(group_id, len(assigned) % 2)
    monkeypatch.setattr(grouping, "fold_for", fold)


def test_whole_visit_both_receivers_and_transitive_overlap(monkeypatch):
    alternating(monkeypatch)
    data = support([(1,0,0,10), (1,1,100,110), (2,0,105,115),
                    (3,1,114,120), (4,0,200,210)])
    before = copy.deepcopy(data)
    result = grouping.group_support(data, IDENTITY, seed="declared")
    assert result["groups"][0]["visits"] == [1,2,3]
    assert result["row_fold"] == [0,0,0,0,1]
    assert sorted(result["folds"]["0"] + result["folds"]["1"]) == list(range(5))
    assert data == before


def test_interval_holes_and_touching_edges_do_not_merge(monkeypatch):
    alternating(monkeypatch)
    result = grouping.group_support(support([(1,0,0,10),(1,1,100,110),
                                             (2,0,40,50),(3,1,10,20)]), IDENTITY, seed="declared")
    assert [g["visits"] for g in result["groups"]] == [[1],[2],[3]]


def test_large_integer_counters_no_float_rounding(monkeypatch):
    alternating(monkeypatch)
    n = 2**60
    result = grouping.group_support(support([(1,0,n,n+1),(2,1,n+1,n+2)]), IDENTITY, seed="declared")
    assert result["group_count"] == 2


def test_hash_assignment_deterministic_and_outcome_blind():
    assert grouping.fold_for("group", "seed") == grouping.fold_for("group", "seed")
    data = support([(v,0,v*100,v*100+10) for v in range(32)])
    # Fixed synthetic inventory/seed, never adapted to recording results.
    first = grouping.group_support(data, IDENTITY, seed="159-test-fixed")
    for row in data["rows"]:
        row.update(measured_hz=float("nan"), margin=-100, position_error="ignored")
    assert grouping.group_support(data, IDENTITY, seed="159-test-fixed") == first


@pytest.mark.parametrize("fault", ["missing", "float", "bool", "reversed", "index", "duplicate",
                                  "probe", "count", "oversize", "receiver", "reason"])
def test_bad_inventory_rejects_whole_recording(fault):
    data = support([(1,0,0,10),(2,1,20,30)])
    options = {}
    if fault == "missing": data["rows"][0]["support_status"] = "unavailable"
    if fault == "float": data["rows"][0]["device_sample_start"] = 0.0
    if fault == "bool": data["rows"][0]["visit_index"] = True
    if fault == "reversed": data["rows"][0]["device_sample_end"] = 0
    if fault == "index": data["rows"][1]["index"] = 0
    if fault == "duplicate": data["rows"][1]["window_id"] = "w0"
    if fault == "probe": data["rows"][1].update(visit_index=1, receiver=0, probe_index=0)
    if fault == "count": data["observations"] = 3
    if fault == "oversize": options["maximum_rows"] = 1
    if fault == "receiver": data["rows"][0]["receiver"] = 2
    if fault == "reason": data["unavailable_reasons"] = {"missing": 1}
    with pytest.raises(ValueError):
        grouping.group_support(data, IDENTITY, seed="declared", **options)


def test_single_component_or_hash_empty_fold_rejected(monkeypatch):
    monkeypatch.setattr(grouping, "fold_for", lambda *args: 0)
    with pytest.raises(ValueError, match="nonempty"):
        grouping.group_support(support([(1,0,0,10),(2,1,20,30)]), IDENTITY, seed="fixed")
