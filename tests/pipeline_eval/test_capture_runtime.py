from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification import capture_runtime as run
from tools.pipeline_eval.qualification.capture_runtime_results import audit


def test_selection_is_frozen_by_original_stratum_and_time():
    source = [
        dict(visit=i, kind=t, arbitrary_cpu=10 - i)
        for i, t in (
            (5, "matched"),
            (7, "matched"),
            (2, "miss"),
            (9, "miss"),
        )
    ]
    assert [r["visit"] for r in run.choose(source[::-1])] == [2, 5]


def test_valid_prefix_counts_independent_rf_lanes():
    frames = [(1, 50), (2, 55), (7, 50), (11, 55), (12, 50)]
    probes = [
        dict(visit_index=v, actual_rf_hz=rf, receiver_id=i) for v, rf in frames for i in (0, 1)
    ]
    assert run.lanes(probes, 11) == {1: 0, 2: 0, 7: 1, 11: 1}


def test_pair_audit_detects_nonempty_companion_and_changed_capture():
    native = [dict(receiver_id=rx, candidates=[]) for rx in (0, 1)]
    src = dict(
        visit=7,
        archive_probe={"edge": "upper"},
        kind="miss",
        iq_sha256="a",
        counter=23,
        receiver=1,
        target={"passed_fractional_margin_gate": False},
    )
    inventory = [dict(source=src, selected_lane=1, previous_capture=native)]
    records = [
        dict(visit=7, repeat=t, mode=m, probes=deepcopy(native), cpu_ns=3, wall_ns=4)
        for t in range(2)
        for m in run.MODES
    ]
    times, checked = audit("case", inventory, records)
    assert len(times) == 6 and len(checked) == 2
    records[2]["probes"][0]["candidates"] = ["impossible"]
    with pytest.raises(ValueError, match="physical receiver"):
        audit("case", inventory, records)
    records[0]["probes"][1]["receiver_id"] = 0
    with pytest.raises(ValueError, match="sealed measured rows"):
        audit("case", inventory, records)
