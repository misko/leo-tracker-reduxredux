from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification.one_lane_whole_raw import stereo_slots
from tools.pipeline_eval.variants import one_lane_schedule as policy


def recording():
    rows = [
        dict(visit_index=visit, receiver_id=rx, channel=channel, edge="upper", candidates=[visit])
        for visit, channel in ((0, 1), (1, 2), (3, 1), (4, 2), (5, 1))
        for rx in (0, 1)
    ]
    return dict(
        delivery_clocks=list(range(6)),
        source=dict(input_manifest_sha256="recording", probes=rows),
        provenance=dict(
            window_count=6,
            processed_windows=5,
            invalid_capture=1,
            excluded_windows=[{"visit": 2}],
        ),
    )


RF = {(1, "upper"): 100, (2, "upper"): 200}


def test_projection_alternates_independently_at_each_real_rf_and_preserves_metadata():
    doc = recording()
    former = deepcopy(doc)
    projected, visits = policy.project(doc, RF)
    assert former == doc
    assert [row["visit"] for row in visits] == [0, 1, 3, 4, 5]
    assert [row["selected_receiver"] for row in visits] == [0, 0, 1, 1, 0]
    assert [row["rf_center_hz"] for row in visits] == [100, 200, 100, 200, 100]
    assert [row["candidates"] for row in projected["source"]["probes"]] == [
        [0],
        [],
        [1],
        [],
        [],
        [3],
        [],
        [4],
        [5],
        [],
    ]
    assert projected["delivery_clocks"] == doc["delivery_clocks"]
    assert projected["provenance"]["excluded_windows"] == [{"visit": 2}]
    assert "detector_sha256" not in projected["provenance"]
    assert policy.project(projected, RF) == (projected, visits)


def test_projection_rejects_an_inconsistent_rf_or_incomplete_physical_inventory():
    doc = recording()
    doc["source"]["probes"][1]["channel"] = 2
    with pytest.raises(ValueError, match="share an authenticated RF"):
        policy.project(doc, RF)
    doc = recording()
    doc["provenance"]["excluded_windows"] = [{"visit": 3}]
    with pytest.raises(ValueError, match="every valid visit and exact exclusions"):
        policy.project(doc, RF)


@pytest.mark.parametrize("lane", [0, 1])
def test_native_adapter_preserves_selected_physical_row_and_empties_only_partner(lane):
    observed = {"receiver_id": lane, "candidates": [5]}
    result = {"rows": [observed]}
    rows = stereo_slots(result, lane)["rows"]
    assert [row["receiver_id"] for row in rows] == [0, 1]
    assert rows[lane] == observed
    assert rows[1 - lane]["candidates"] == []
    assert result == {"rows": [observed]}
    with pytest.raises(ValueError, match="selected physical lane"):
        stereo_slots(result, 1 - lane)
