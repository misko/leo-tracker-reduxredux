import socket

import pytest

from tools.pipeline_eval.qualification import parallel_acquisition as replay
from tools.pipeline_eval.qualification import parallel_acquisition_results as results


def test_exclusive_route_keeps_unassigned_distinct_from_invalid_and_busy(tmp_path):
    event = dict(visit=1, center_hz=12_209_687_500, status="processed")
    selected = event["center_hz"]
    a, b = socket.socketpair(type=socket.SOCK_SEQPACKET)
    with a, b, (tmp_path / "count").open("xb+", buffering=0) as counter:
        counter.write(replay.WORD.pack(0))
        fd = counter.fileno()
        assert replay.admit(event, "original", selected, fd, a) == "queued"
        assert replay.receive(b) == 1
        assert replay.admit(dict(event, visit=2), "original", selected, fd, a) == "queued"
        assert replay.admit(dict(event, visit=3), "original", selected, fd, a) == "dropped_busy"
        assert replay.admit(dict(event, visit=3), "wide", selected, fd, a) == "unassigned"
        assert replay.admit(dict(event, status="invalid_capture"), "wide", selected, fd, a) == (
            "invalid_capture"
        )
        replay.complete(fd)
        other = dict(event, center_hz=selected + 1)
        assert replay.admit(other, "wide", selected, fd, a) == "queued"
        assert replay.receive(b) == 2
        assert replay.receive(b) == 1


def test_trace_requires_one_assigned_branch_and_audits_cutoff():
    events = [
        dict(visit=0, status="processed", center_hz=100, arrival_ns=0),
        dict(visit=1, status="processed", center_hz=200, arrival_ns=20),
        dict(visit=2, status="invalid_capture", center_hz=None, arrival_ns=40),
    ]
    archive = [dict(visit=i) for i in range(len(events))]
    source = [
        dict(
            visit=i,
            released_ns=events[i]["arrival_ns"],
            outcomes={
                role: dict(admission=status, offered_ns=events[i]["arrival_ns"])
                for role, status in zip(replay.ROLES, dispositions, strict=True)
            },
        )
        for i, dispositions in enumerate(
            (("unassigned", "queued"), ("queued", "unassigned"), ("invalid_capture",) * 2)
        )
    ]
    for role, i, finish in (("original", 0, 40), ("wide", 1, 41)):
        output = [
            dict(
                visit=i,
                packet=archive[i],
                start_ns=20,
                finish_ns=finish,
                native_cpu_ns=5,
                native_wall_ns=10,
            )
        ]
        trace = results.assemble_trace(events, source, output, archive, role, selected_rf_hz=100)
        assert trace[i]["observed_by_cutoff"] is (role == "original")
        assert trace[1 - i]["admission"] == "unassigned"
        assert trace[1 - i]["packet"] is None
    source[0]["outcomes"]["wide"]["admission"] = "dropped_busy"
    with pytest.raises(ValueError, match="full bound physical visit"):
        results.assemble_trace(events, source, [], archive, "wide", selected_rf_hz=100)
