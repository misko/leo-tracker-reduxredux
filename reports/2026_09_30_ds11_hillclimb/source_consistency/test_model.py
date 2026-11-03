from __future__ import annotations

import copy
import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pytest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = HERE.parent.parent / "2026_09_30_ds11_single10"
sys.path[:0] = [str(HERE), str(ROOT / "tools")]
import ds7_fast_baseline_adapter as fast  # noqa: E402
import model  # noqa: E402


@lru_cache
def real_case():
    fast.baseline.profile = fast.profile
    plan = json.loads((BASE / "plan.json").read_text())
    entry = plan["inputs"][0]
    documents = fast.load_documents({"config": plan["config"], "inputs": [entry]})
    x = np.asarray(json.loads((BASE / "runs/00_iid.json").read_text())["selected"]["x"])
    scan = json.loads((HERE / "source_groups.json").read_text())["scans"]["0"]
    return plan["config"], documents, x, scan


def test_no_conflicts_retains_every_track_and_exactly_replays_iid():
    config, documents, x, _ = real_case()
    rows = [
        {"track_id": track["track_id"], "groups": [f"g-{index}"],
         "training_count": int(track["mask"].sum())}
        for index, track in enumerate(documents[0]["tracks"])
    ]
    chosen = model.select(rows)
    assert set(chosen["track_ids"]) == {track["track_id"] for track in documents[0]["tracks"]}
    expected_score, expected_gradient = fast.baseline.Stationary(
        documents[0], config
    ).evaluate(x, True)
    actual = model.SourceConsistentIID(documents, config).evaluate(x, True)
    assert actual["score"] == expected_score
    np.testing.assert_array_equal(actual["gradient"], expected_gradient)


def test_selected_training_sources_are_disjoint_and_maximize_declared_greedy_alternatives():
    rows = [
        {"track_id": "a", "groups": ["shared", "a"], "training_count": 8},
        {"track_id": "b", "groups": ["shared", "b"], "training_count": 10},
        {"track_id": "c", "groups": ["c"], "training_count": 7},
    ]
    chosen = model.select(rows)
    assert chosen["track_ids"] == ("b", "c")
    assert chosen["training_count"] == 17
    config, documents, _, scan = real_case()
    actual, source_rows = model.selection_from_sidecar(documents[0], scan)
    ids = set(actual["track_ids"])
    groups = [group for row in source_rows if row["track_id"] in ids for group in row["groups"]]
    assert len(groups) == len(set(groups))


def test_selection_and_training_objective_ignore_held_values_and_reference():
    config, documents, x, scan = real_case()
    selected, _ = model.selection_from_sidecar(documents[0], scan)
    ids = set(selected["track_ids"])
    original_document = dict(
        documents[0], tracks=[track for track in documents[0]["tracks"] if track["track_id"] in ids]
    )
    expected = model.SourceConsistentIID([original_document], config).evaluate(x, True)
    changed = copy.deepcopy(documents)
    changed[0]["reference_position_deg"] = [0.0, 0.0]
    for track in changed[0]["tracks"]:
        track["y"][~track["mask"]] += 1e9
        track["candidate_position_km"][:, :, ~track["mask"], :] += 1e6
        track["candidate_velocity_km_s"][:, :, ~track["mask"], :] -= 1e6
    changed_selected, _ = model.selection_from_sidecar(changed[0], scan)
    assert changed_selected == selected
    changed_document = dict(
        changed[0], tracks=[track for track in changed[0]["tracks"] if track["track_id"] in ids]
    )
    actual = model.SourceConsistentIID([changed_document], config).evaluate(x, True)
    assert actual["score"] == expected["score"]
    np.testing.assert_array_equal(actual["gradient"], expected["gradient"])


def test_public_builder_binds_source_sidecar_partition_session_and_hashes():
    config, documents, _, scan = real_case()
    built = model.build_model(documents, config, "training_source_consistent", index=0)
    assert model.VARIANTS == ("training_source_consistent",)
    assert built.metadata["retained_tracks"] < built.metadata["original_tracks"]
    assert 0.60 <= built.metadata["retained_training_fraction"] < 1.0
    assert len(built.metadata["resource_sha256"]) == 5

    wrong_session = copy.deepcopy(documents)
    wrong_session[0]["session_id"] = "wrong"
    with pytest.raises(ValueError, match="session or index binding mismatch"):
        model.build_model(wrong_session, config, "training_source_consistent", index=0)

    wrong_partition = copy.deepcopy(scan)
    track_id = documents[0]["tracks"][0]["track_id"]
    wrong_partition["tracks"][track_id][0]["training"] = not (
        wrong_partition["tracks"][track_id][0]["training"]
    )
    with pytest.raises(ValueError, match="partition mismatch"):
        model.selection_from_sidecar(documents[0], wrong_partition)


def test_selected_model_gradient_matches_central_difference():
    config, documents, x, _ = real_case()
    challenger = model.build_model(documents, config, "training_source_consistent", index=0)
    center = x + [0.2, -0.3, 0.1]
    analytic = challenger.evaluate(center, True)["gradient"]
    numerical = np.zeros(3)
    for axis, step in enumerate((1e-4, 1e-4, 1e-5)):
        delta = np.eye(3)[axis] * step
        numerical[axis] = (
            challenger.evaluate(center + delta, False)["score"]
            - challenger.evaluate(center - delta, False)["score"]
        ) / (2 * step)
    np.testing.assert_allclose(analytic, numerical, atol=2e-3, rtol=0)
