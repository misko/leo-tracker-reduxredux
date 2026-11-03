from __future__ import annotations

import copy
import json
import math
import shutil
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pytest
from scipy.special import logsumexp


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
    incumbent = json.loads((BASE / "runs/00_iid.json").read_text())["selected"]["x"]
    scan = json.loads(
        (HERE.parent / "source_balance/catalogue_identities.json").read_text()
    )["scans"]["0"]
    candidates = [{key: value["candidate_norad"] for key, value in scan["tracks"].items()}]
    return plan["config"], documents, np.asarray(incumbent), candidates


class SyntheticEngine:
    def __init__(self, document, config):
        self.document = document

    def prediction(self, track, x):
        base = np.asarray(track["prediction"], dtype=float)
        slopes = np.asarray(track["slopes"], dtype=float)
        prediction = base + np.einsum("coj,j->co", slopes, np.asarray(x))
        return prediction, np.asarray(track.get("visible", [True] * len(base)), dtype=bool)


def synthetic_track(track_id, receiver, rf_hz, y, prediction, slopes, *, catalogue=100):
    y = np.asarray(y, dtype=float)
    return {
        "track_id": track_id,
        "receiver_id": receiver,
        "rf_hz": rf_hz,
        "y": y,
        "mask": np.asarray([True] * (len(y) - 1) + [False]),
        "catalogue_size": catalogue,
        "prediction": np.asarray(prediction, dtype=float),
        "slopes": np.asarray(slopes, dtype=float),
    }


def synthetic_case():
    slopes_a = [
        [[1.2, -0.3, 0.1], [0.8, 0.1, -0.2], [1.0, 0.2, 0.3]],
        [[-0.4, 0.7, 0.2], [-0.2, 0.5, 0.1], [-0.3, 0.6, -0.2]],
    ]
    slopes_b = [
        [[0.5, 0.4, -0.1], [0.7, 0.2, 0.2], [0.6, 0.3, 0.1]],
        [[-0.1, 0.9, 0.3], [-0.4, 0.8, -0.2], [-0.2, 0.7, 0.2]],
    ]
    tracks = [
        synthetic_track("a", 0, 10.0, [110, 120, 130],
                        [[10, 21, 28], [50, 58, 69]], slopes_a),
        synthetic_track("b", 1, 20.0, [210, 225, 235],
                        [[105, 119, 133], [160, 173, 181]], slopes_b),
    ]
    documents = [{"session_id": "synthetic", "tracks": tracks}]
    candidates = [{"a": [11, 22], "b": [11, 22]}]
    group = {
        "document_index": 0,
        "norad": 11,
        "members": ((0, 0), (0, 1)),
        "candidate_norad": (11, 22),
        "strata": ((0, 10.0), (1, 20.0)),
    }
    challenger = model.JointIdentity(
        documents, {}, candidates, [group], (), model_factory=SyntheticEngine
    )
    return documents, candidates, group, challenger


def test_all_singletons_exactly_reproduce_original_iid_score_and_gradient():
    config, documents, x, candidates = real_case()
    original = fast.baseline.Stationary(documents[0], config)
    expected_score, expected_gradient = original.evaluate(x, True)
    singletons = tuple((0, index) for index in range(len(documents[0]["tracks"])))
    challenger = model.JointIdentity(documents, config, candidates, [], singletons)
    actual = challenger.evaluate(x, True)
    assert abs(actual["score"] - expected_score) < 1e-10
    np.testing.assert_allclose(actual["gradient"], expected_gradient, atol=1e-10, rtol=0)


def test_two_track_joint_score_gradient_and_single_catalogue_normalizer():
    documents, _, _, challenger = synthetic_case()
    x = np.asarray([0.2, -0.4, 0.1])
    candidate_scores = []
    candidate_gradients = []
    for candidate in range(2):
        score_total = 0.0
        gradient_total = np.zeros(3)
        for track in documents[0]["tracks"]:
            engine = SyntheticEngine(documents[0], {})
            prediction, _ = engine.prediction(track, x)
            residual = track["y"][None, :] - prediction
            score, _, audits, offsets = fast.profile(residual, track["mask"])
            assert all(row["converged"] for row in audits)
            score_total += score[candidate]
            centered = residual[candidate, track["mask"]] - offsets[candidate]
            slope = 5 * centered / (40000 + centered**2)
            gradient_total += np.sum(
                slope[:, None]
                * np.asarray(track["slopes"])[candidate, track["mask"], :], axis=0
            )
        candidate_scores.append(score_total)
        candidate_gradients.append(gradient_total)
    normal = logsumexp(candidate_scores)
    responsibility = np.exp(np.asarray(candidate_scores) - normal)
    expected_score = normal - math.log(100)
    expected_gradient = responsibility @ np.asarray(candidate_gradients)
    actual = challenger.evaluate(x, True)
    assert abs(actual["score"] - expected_score) < 1e-10
    np.testing.assert_allclose(actual["gradient"], expected_gradient, atol=1e-10, rtol=0)


def test_physical_candidate_slot_permutation_is_invariant_and_duplicates_rejected():
    documents, candidates, group, challenger = synthetic_case()
    x = np.asarray([0.2, -0.4, 0.1])
    expected = challenger.evaluate(x, True)
    changed = copy.deepcopy(documents)
    changed[0]["tracks"][1]["prediction"] = changed[0]["tracks"][1]["prediction"][[1, 0]]
    changed[0]["tracks"][1]["slopes"] = changed[0]["tracks"][1]["slopes"][[1, 0]]
    changed_candidates = [{"a": [11, 22], "b": [22, 11]}]
    actual = model.JointIdentity(
        changed, {}, changed_candidates, [group], (), model_factory=SyntheticEngine
    ).evaluate(x, True)
    assert abs(actual["score"] - expected["score"]) < 1e-10
    np.testing.assert_allclose(actual["gradient"], expected["gradient"], atol=1e-10, rtol=0)
    with pytest.raises(ValueError, match="duplicate physical NORAD"):
        model.JointIdentity(
            documents, {}, [{"a": [11, 11], "b": [11, 22]}], [group], (),
            model_factory=SyntheticEngine,
        )


def test_each_track_profiles_an_independent_cfo(monkeypatch):
    documents, candidates, group, _ = synthetic_case()
    documents = copy.deepcopy(documents)
    documents[0]["tracks"][1]["y"] += 500.0
    calls = []
    original = model.fast.profile

    def recording_profile(residual, mask):
        result = original(residual, mask)
        calls.append(result[3].copy())
        return result

    monkeypatch.setattr(model.fast, "profile", recording_profile)
    challenger = model.JointIdentity(
        documents, {}, candidates, [group], (), model_factory=SyntheticEngine
    )
    challenger.evaluate(np.zeros(3), False)
    assert len(calls) == 2
    assert np.all(calls[1] - calls[0] > 350.0)
    assert calls[0] is not calls[1]


def test_grouped_gradient_matches_central_difference():
    config, documents, x, candidates = real_case()
    assignments = model.freeze_assignments(documents, config, x, candidates)
    groups, singletons = model.freeze_groups(assignments, candidates)
    challenger = model.JointIdentity(documents, config, candidates, groups, singletons)
    analytic = challenger.evaluate(x + [0.4, -0.3, 0.2], True)["gradient"]
    center = x + [0.4, -0.3, 0.2]
    numerical = np.zeros(3)
    for axis, step in enumerate((1e-4, 1e-4, 1e-5)):
        delta = np.eye(3)[axis] * step
        numerical[axis] = (
            challenger.evaluate(center + delta, False)["score"]
            - challenger.evaluate(center - delta, False)["score"]
        ) / (2 * step)
    np.testing.assert_allclose(analytic, numerical, atol=2e-3, rtol=0)


def test_freeze_and_objective_ignore_held_and_reference_fields():
    documents, candidates, group, challenger = synthetic_case()
    x = np.asarray([0.2, -0.4, 0.1])
    expected = challenger.evaluate(x, True)
    changed = copy.deepcopy(documents)
    changed[0]["reference_position_deg"] = [89.0, 179.0]
    for track in changed[0]["tracks"]:
        track["y"][-1] += 1e9
        track["prediction"][:, -1] -= 1e8
        track["held_reference_label"] = "ignored"
    actual_model = model.JointIdentity(
        changed, {}, candidates, [group], (), model_factory=SyntheticEngine
    )
    actual = actual_model.evaluate(x, True)
    assert actual["score"] == expected["score"]
    np.testing.assert_array_equal(actual["gradient"], expected["gradient"])


def test_intersection_and_track_accounting_guards():
    assignments = [
        {"document_index": 0, "track_index": 0, "track_id": "a", "receiver_id": 0,
         "rf_hz": 10.0, "norad": 11, "unambiguous": True},
        {"document_index": 0, "track_index": 1, "track_id": "b", "receiver_id": 1,
         "rf_hz": 20.0, "norad": 11, "unambiguous": True},
    ]
    with pytest.raises(ValueError, match="empty physical candidate intersection"):
        model.freeze_groups(assignments, [{"a": [11], "b": [22]}])
    documents, candidates, group, _ = synthetic_case()
    with pytest.raises(ValueError, match="every track exactly once"):
        model.JointIdentity(
            documents, {}, candidates, [group], ((0, 0),), model_factory=SyntheticEngine
        )


def test_public_builder_binds_receipt_session_and_sources(tmp_path, monkeypatch):
    config, documents, _, _ = real_case()
    built = model.build_model(documents, config, "joint_identity", index=0)
    assert model.VARIANTS == ("joint_identity",)
    assert built.metadata["tracks"] == (
        built.metadata["joint_group_tracks"] + built.metadata["independent_tracks"]
    )
    changed = copy.deepcopy(documents)
    changed[0]["session_id"] = "wrong-session"
    with pytest.raises(ValueError, match="session or index binding mismatch"):
        model.build_model(changed, config, "joint_identity", index=0)

    fake_base = tmp_path / "base"
    (fake_base / "runs").mkdir(parents=True)
    shutil.copy(BASE / "runs/00_iid.json", fake_base / "runs/00_iid.json")
    shutil.copy(BASE / "runs/00_iid.receipt.json", fake_base / "runs/00_iid.receipt.json")
    monkeypatch.setattr(model, "BASE", fake_base)
    (fake_base / "runs/00_iid.receipt.json").unlink()
    with pytest.raises(ValueError, match="result or receipt missing"):
        model._qualified_incumbent(0, documents[0]["session_id"])
