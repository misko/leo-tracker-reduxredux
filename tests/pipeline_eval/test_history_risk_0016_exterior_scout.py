from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3.region import SearchRegion
from reports.ALGO08.v3 import history_risk_0016_exterior_scout as scout
from tools.pipeline_eval.variants.experimental import regional_reassignment as kernel
from tools.pipeline_eval.variants.experimental.regional_exterior_veto import evaluate
from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import evaluate_terminal, probe_layout


def scores(x, y, first, second):
    return dict(side="inside" if max(abs(x), abs(y)) < 12.5 else "exterior", xy_km=[x, y],
                receiver_scores={"1": first, "2": second})


def test_scout_layout_uses_only_the_offered_width_and_original_normals():
    region = SearchRegion((37.906, -120.545), 25)
    points = scout.axial_points(region, kernel.NORMALS)
    assert [point["xy_km"] for point in points] == [
        [100, 0], [-100, 0], [0, 100], [0, -100], [200, 0], [-200, 0], [0, 200], [0, -200]]
    assert all(np.allclose(point["latlon"], region.latlon(point["xy_km"])) for point in points)


def test_distinguishes_wider_bilateral_evidence_from_separation_tie_and_weaker_score():
    original = [scores(0, 0, 1, 1), scores(-62.5, 0, 3, 1), scores(62.5, 0, 1, 3)]
    assert scout.maxima(original, 25)["separation_km"] == 125
    good = scores(-200, 0, 4, 4)
    assert scout.maxima(original, 25, [good])["bilateral_wider"]
    assert not scout.maxima(original, 25, [good, scores(200, 0, 4, 4)])["bilateral"]
    assert not scout.maxima(original, 25, [scores(-200, 0, 4, 2)])["bilateral"]
    weak = scout.maxima(original[:1], 25, [scores(-100, 0, 0, 0), scores(-200, 0, -1, -1)])
    assert not weak["bilateral"]


def test_probe_capture_preserves_scores_and_records_exact_candidate_stages(monkeypatch):
    catalogue = SimpleNamespace(names=("a", "b", "c"), satellites=(None,)*3, satellite_numbers=(111, 222, 333))
    region = SearchRegion((0., 0.), 25)
    rows = [dict(observation_id=f"{rx}-{i}", receiver=rx) for rx in (1, 2) for i in range(3)]
    tracks = [dict(key=f"t{rx}", times=np.arange(3), values=np.arange(3), receiver=rx, channel=rx, rf_hz=11.5e9,
                   observation_ids=[f"{rx}-{i}" for i in range(3)]) for rx in (1, 2)]
    graph = dict(observations=rows, tracks=tracks, metadata={"anchor_utc_ns": 5})

    def states(cat, _origin, times):
        good = np.array([key != 222 for key in cat.satellite_numbers])
        if len(good) == 2:
            good[-1] = False
        values = np.zeros((len(good), len(times), 3))
        return values, values, good

    monkeypatch.setattr(kernel, "ecef_states", states)
    monkeypatch.setattr(kernel, "phase_shifted_states", lambda state, *_: (state["position_km"], None))
    monkeypatch.setattr(kernel, "possible_horizon", lambda pos, *_: np.ones(pos.shape[:2], dtype=bool))
    monkeypatch.setattr(kernel, "prepare_phase_geometry", lambda *_: True)
    monkeypatch.setattr(kernel, "phase_linear_frequency", lambda *_: (
        np.arange(3)[None, :], np.ones((1, 3)), np.zeros((1, 3))))
    actual, terms = scout.probe_bank(kernel, graph, catalogue, region, original_order=probe_layout)
    uninstrumented = kernel.evaluate(graph, catalogue, region)
    assert actual["points"] == uninstrumented["points"]
    assert actual["propagation"] == dict(first_propagation=[111, 333], horizon_candidates=[111, 333], usable=[111])
    assert len(actual["score_clocks"]) == 2
    assert scout.graph_membership(graph)["missing_points_by_receiver"] == {"1": 0, "2": 0}
    assert scout.compact_terms(terms)[0][0]["visible_packbits_hex"] == "80"
    assert set(scout.family_terms(terms[0], (111, 333))[0]) == {"111"}
    stock = evaluate_terminal(uninstrumented["points"], region.width_km, lambda p: p["receiver_scores"])
    expected = {**actual["meta"], **stock, "snapshots": ["test"], "evaluated": True, "bound_arms": ["c0"]}
    expected["receiver_points"] = {"1": 3, "2": 3}
    assert scout.gate_replay(actual, 25, expected, ["test"], evaluate, evaluate_terminal)["terminal"] == stock
    with pytest.raises(ValueError, match="no longer matches"):
        scout.gate_replay(actual, 25, expected, ["different"], evaluate, evaluate_terminal)
