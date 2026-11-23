from types import SimpleNamespace

import numpy as np
import pytest

from reports.ALGO08.v3 import cross_roster_0155 as crossed


def test_phase_transport_uses_satellite_identity_and_zero_for_missing_labels():
    source = crossed.family_phase([10, 11], [1.5,-0.5])
    assert crossed.transport(source, [11, 19, 10]).tolist() == [-0.5, 0., 1.5]
    with pytest.raises(ValueError):
        crossed.family_phase([10], [1.,2.])


def test_likelihood_rows_preserve_native_curve_mask_and_predictive_arc_order():
    tracks = [dict(key="curve", observation_ids=["drop", "a", "b"]),
              dict(key="line", observation_ids=["p", "q"], values=[1.,2.])]
    problem = SimpleNamespace(scan=SimpleNamespace(tracks=tracks), rows=[dict(candidate_norad=15)], members=[0],
                              slices=[slice(0,3)], alias=[-1], keep=np.array([0,1,1], bool),
                              values=[0.,4.,5.], point_noise=[100.,110.,120.])
    ctx = dict(problems={"c0": (problem, None)}, powers=[.33], entries=[dict(track_index=1, norad=14, alias=2,
                                                                          observation_ids=["p","q"])])
    actual = crossed.row_data(ctx, "c0")
    assert actual == [["a",15,"conditional","curve",-1,4.,110.,.33], ["b",15,"conditional","curve",-1,5.,120.,.33],
                      ["p",14,"predictive","line",2,1.,None,None], ["q",14,"predictive","line",2,2.,None,None]]
    with pytest.raises(ValueError, match="cannot own one observation twice"):
        crossed.witnessed_roles(actual+actual[:1])


def test_refitter_origin_preserves_exact_returned_history_object():
    seen = {}
    record = {"history": [{"phase": 1}]}
    assert crossed.clocked_refitter(lambda: record, "event_position", seen)() is record
    history, method = seen[id(record["history"])]
    assert history is record["history"] and method == "event_position"
