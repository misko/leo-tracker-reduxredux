from copy import deepcopy
from hashlib import sha256

import pytest

from reports.ALGO08.v3.same_build_raw_panel import summarize


def pair(name, stock, candidate, decision):
    admission = dict(case=name, raw_authority=name, issued=10, order=["stock", "candidate"],
                     stock="v3", route_flags=["fast"], host="one core", library_sha256={"a":"1"},
                     sources={"entry":"2"})
    runs = {}
    for i, (mode, elapsed) in enumerate((("stock", stock), ("candidate", candidate))):
        runs[mode] = dict(opportunities="same", process=dict(clock=dict(started_unix_ns=i, exit_code=0,
                         elapsed_s=elapsed, cpu_s=elapsed)), science=dict(raw_authority=name, receipt=dict(decision=decision)),
                         figures=list(range(8)) if decision == "complete" else [], time_boundaries=dict(
                         detections_file_s=elapsed*.5, terminal_file_s=elapsed*.8, exit_s=elapsed))
    errors = {m: dict(horizontal_error_km={"c0":1, "fitted_c":2}) for m in runs} if decision == "complete" else {}
    return dict(admission=admission, pre_score_sha256="sealed", original=runs, geographic=dict(runs=errors))


def test_both_gates_include_every_recording_but_only_fixes_have_errors():
    result = summarize([pair("a", 20, 5, "complete"), pair("b", 10, 10, "withheld")])
    assert result["summed_ratio"] == .5
    assert result["median_paired_ratio"] == .625
    assert result["fix_counts"] == dict(stock=1, candidate=1)
    assert result["rows"][1]["runs"]["candidate"]["errors_km"] == {}


def test_changed_libraries_repeated_recordings_and_missing_artifacts_fail():
    first = pair("a", 10, 8, "complete")
    second = deepcopy(first)
    with pytest.raises(ValueError, match="more than once"):
        summarize([first, second])
    second["admission"]["library_sha256"]["a"] = "replaced"
    with pytest.raises(ValueError, match="libraries"):
        summarize([first, second])
    first["original"]["candidate"]["figures"].pop()
    with pytest.raises(ValueError, match="media"):
        summarize([first])


def test_receiver_digest_participates_in_panel_identity_and_must_match_the_child():
    old = pair("a", 10, 8, "complete")
    new = pair("b", 12, 8, "complete")
    pin = "sha256:"+sha256(b'{"mode":"refined"}').hexdigest()
    new["admission"]["receiver_configuration"] = dict(recipe={"mode": "refined"}, detector_recipe_sha256=pin)
    new["original"]["candidate"]["bootstrap"] = dict(detector_recipe_sha256=pin)
    assert summarize([new])["fix_counts"] == dict(stock=1, candidate=1)
    with pytest.raises(ValueError, match="receiver configurations"):
        summarize([old, new])
    new["original"]["candidate"]["bootstrap"]["detector_recipe_sha256"] = "sha256:"+"0"*64
    with pytest.raises(ValueError, match="different enrolled receiver"):
        summarize([new])


def test_a_measured_failure_cannot_count_as_a_withhold_or_a_timing_row():
    failed = pair("a", 10, 8, "withheld")
    failed["original"]["candidate"]["process"]["clock"]["exit_code"] = 1
    failed["original"]["candidate"]["science"] = None
    with pytest.raises(ValueError, match="Invalid process clock"):
        summarize([failed])
