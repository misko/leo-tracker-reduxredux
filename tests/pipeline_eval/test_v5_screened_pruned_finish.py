import json
from contextlib import contextmanager

import pytest

from tools.pipeline_eval.qualification import screened_pruned_eval
from tools.pipeline_eval.variants import v5_screened_pruned_finish as receiver


def test_discovery_sharing_ends_before_the_three_named_nodes_are_screened(monkeypatch):
    scan = object()
    metrics, calls = {}, []

    @contextmanager
    def sharing(actual):
        assert actual is scan
        calls.append("open")
        yield {"association_reused": 6}
        calls.append("close")

    def ranked(actual):
        assert actual is scan and calls == ["open"]
        return ["a", "b", "c", "d"]

    def screen(actual, nodes, record):
        assert actual is scan and calls == ["open", "close"]
        assert nodes == ["a", "b", "c"]
        record["initial_phase_fits"] = 9
        return {"selected_hypothesis": 1}, 3

    monkeypatch.setattr(receiver.v5_shared_search, "shared_associations", sharing)
    monkeypatch.setattr(receiver.v5_core, "ranked_initial_nodes", ranked)
    monkeypatch.setattr(receiver.v5_screen_winner, "screen_nodes", screen)
    assert receiver.initial(scan, metrics) == ({"selected_hypothesis": 1}, 3)
    assert metrics == {
        "discovery_sharing": {"association_reused": 6},
        "initial_screen": {"initial_phase_fits": 9},
    }


def test_worker_uses_pruned_final_decision_and_restores_initial_port(monkeypatch, tmp_path):
    target = tmp_path / "position.json"
    original = receiver.v5_core.initial_selection
    fixed = dict(
        status="ok",
        arms={"c0": {"latlon": [1, 2]}, "fitted_c": {"latlon": [2, 3]}},
        metrics=dict(ordered_phase_seeds={}, finish_eligibility={}, position_optimizer={}),
    )

    def initial(_scan, metrics):
        metrics.update(
            discovery_sharing={"association_reused": 9}, initial_screen={"winning_rank": 1}
        )
        return "selected"

    def pruned(_request, output, _library):
        assert receiver.v5_core.initial_selection(None) == "selected"
        output.write_text(json.dumps(fixed))

    monkeypatch.setattr(receiver, "initial", initial)
    monkeypatch.setattr(receiver.v5_pruned_finish, "worker", pruned)
    receiver.worker("request", target, "library")
    row = json.loads(target.read_bytes())
    assert row["arms"] == fixed["arms"]
    assert row["metrics"]["initial_screen"] == {"winning_rank": 1}
    assert row["boundary"] == receiver.BOUNDARY
    assert receiver.v5_core.initial_selection is original

    fixed["metrics"].pop("finish_eligibility")
    with pytest.raises(ValueError, match="integrated stage"):
        receiver.worker("request", target, "library")


def test_comparison_keeps_original_presentation_rms_separate_from_conditional_fit():
    def row(lat, rms):
        return dict(
            id="case",
            cpu=0,
            worker_cpu_s=0.5,
            worker_wall_s=0.8,
            result=dict(
                status="ok",
                metrics={"c0_conditional_rms_hz": rms},
                arms={"c0": {"latlon": [lat, 0]}, "fitted_c": {"latlon": [lat, 0.03]}},
            ),
        )

    originals = {
        "baseline": {arm: {"latlon": [0, 0], "published_rms_hz": 70} for arm in ("c0", "fitted_c")}
    }
    score = screened_pruned_eval.compare(row(0.001, 12), row(0.002, 10), originals, [0, 0])
    c0 = score["candidate"]["arms"]["c0"]
    assert c0["rf_rms_hz"] == 12
    assert score["aligned"]["arms"]["c0"]["rf_rms_hz"] == 10
    assert c0["originals"]["baseline"]["published_rms_hz"] == 70
    assert c0["aligned_shift_km"] == pytest.approx(0.111195, rel=1e-4)
    assert score["candidate"]["arms"]["fitted_c"]["rf_rms_hz"] is None
