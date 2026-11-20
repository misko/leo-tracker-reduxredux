from copy import deepcopy
from hashlib import sha256

import pytest

from tools.pipeline_eval.qualification.differential_position import MODES, splice
from tools.pipeline_eval.qualification.differential_position_results import (
    graph_members,
    graph_point,
)


def probe(visit, receiver, cfo):
    return dict(
        visit_index=visit,
        receiver_id=receiver,
        valid_start_counter=visit * 10000,
        channel=1,
        edge="upper",
        actual_rf_hz=10.94e9,
        candidates=[
            dict(
                candidate_rank=0,
                passed_fractional_margin_gate=True,
                fractional_margin=0.1,
                fractional_tracking_cfo_hz=cfo,
            )
        ],
    )


def plan():
    a, b, c, d, e = (probe(i, rx, 100) for i, rx in ((1, 0), (1, 1), (2, 0), (2, 1), (3, 0)))
    document = dict(
        schema_version=2,
        source=dict(probes=[a, b, c, d, e], session_id="session", timing={"retune": 20}),
        provenance={"run_id": "run"},
        clock_anchor={"sample_counter": 10000},
    )
    planned = dict(receiver=1, receiver_ids=[0, 1], kind="miss", iq_sha256="exact-iq")
    processed = dict(
        planned,
        status="processed",
        visit=1,
        counter=10000,
        baseline=[a, b],
        probes=dict(
            stock=[a, b], off=[a, b], causal=[a, probe(1, 1, 220)], sham=[a, probe(1, 1, -600)]
        ),
    )
    missing = dict(planned, status="unavailable", visit=2, counter=20000, baseline=[c, d])
    return document, [("primary", processed), ("confirmation", missing)]


def test_replaces_complete_packets_and_retains_unavailable_schedule():
    document, rows = plan()
    old = deepcopy(document)
    derived, receipt = splice(document, rows, "native", "kernel", "evidence")
    assert document == old == derived["stock"]
    assert len(receipt) == 2 * 2 * len(MODES)
    for mode in MODES[1:]:
        result = derived[mode]
        assert result["source"]["probes"] == (
            rows[0][1]["probes"][mode] + document["source"]["probes"][2:]
        )
        assert result["clock_anchor"] == document["clock_anchor"]
        assert result["source"]["timing"] == document["source"]["timing"]
        assert result["provenance"] == document["provenance"]
        assert sum(x["changed"] for x in receipt if x["mode"] == mode) == 1
    assert len([x for x in receipt if x["status"] == "unavailable"]) == 6


@pytest.mark.parametrize("mode", ("stock", "off", "causal"))
def test_rejects_misbinding_and_changes_to_unhinted_lane(mode):
    document, rows = plan()
    rows[0][1]["probes"][mode][0] = probe(1, 0, 555)
    with pytest.raises(ValueError, match="differs from archived stock|unhinted physical lane"):
        splice(document, rows, "native", "kernel", "evidence")


def test_rejects_retiming_even_on_designated_lane():
    document, rows = plan()
    rows[0][1]["probes"]["causal"][1]["valid_start_counter"] += 1
    with pytest.raises(ValueError, match="sample interval"):
        splice(document, rows, "native", "kernel", "evidence")


def test_graph_membership_binds_raw_winner_and_physical_counter():
    point_id = "sha256:" + sha256(b"capture:1:12345").hexdigest()
    track = dict(
        id="track", members=[point_id, "other"], curved=True, start_s=3.0, end_s=25.0, quality="ok"
    )
    graph = dict(session="capture", winners={point_id: 130.0}, tracks=[track])
    audit = dict(receiver=1, counter=12345, winner_cfo_hz=130.0)
    point = graph_point(graph, audit, graph_members(graph))
    assert (point["graph_id"], point["graph_span_s"], point["graph_curved"]) == ("track", 22, True)
    with pytest.raises(ValueError, match="raw probe receipt"):
        graph_point(graph, dict(audit, counter=12346), graph_members(graph))
