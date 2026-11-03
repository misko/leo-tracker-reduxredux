from __future__ import annotations

import copy
import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np


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
    sidecar = json.loads((HERE / "catalogue_identities.json").read_text())["scans"]["0"]
    candidates = [{key: value["candidate_norad"] for key, value in sidecar["tracks"].items()}]
    return plan["config"], documents, np.asarray(incumbent), candidates


def test_unity_weights_reproduce_original_iid_score_and_gradient():
    config, documents, x, _ = real_case()
    original = fast.baseline.Stationary(documents[0], config)
    expected_score, expected_gradient = original.evaluate(x, True)
    challenger = model.SourceBalancedIID(
        documents, config, np.ones(len(documents[0]["tracks"])), []
    ).evaluate(x, True)
    assert abs(challenger["score"] - expected_score) < 1e-10
    np.testing.assert_allclose(challenger["gradient"], expected_gradient, atol=1e-10, rtol=0)


def _assignment(source, receiver, track):
    group = source + (receiver,)
    return {
        "source": source,
        "group": group,
        "receiver_id": receiver,
        "track_id": track,
    }


def test_equal_weight_variants_are_invariant_to_repeated_group_count():
    source = ("source", 0, 12345, 11_200_000_000.0)
    rows = [_assignment(source, 0, f"a{i}") for i in range(3)]
    rows += [_assignment(source, 1, "b0")]
    rows += [{"source": ("ambiguous", 0, 4), "group": ("ambiguous", 0, 4),
             "receiver_id": 0, "track_id": "ambiguous"}]
    equal = model.derive_weights(rows, "group_equal")
    assert equal[:3].sum() == 1.0
    assert equal[3] == 1.0 and equal[4] == 1.0
    receiver_equal = model.derive_weights(rows, "source_receiver_equal")
    assert receiver_equal[:3].sum() == 0.5
    assert receiver_equal[3] == 0.5
    assert receiver_equal[:4].sum() == 1.0
    assert receiver_equal[4] == 1.0


def test_weighted_gradient_matches_central_difference():
    config, documents, x, candidates = real_case()
    assignments = model.freeze_assignments(documents, config, x, candidates)
    weights = model.derive_weights(assignments, "source_receiver_equal")
    challenger = model.SourceBalancedIID(documents, config, weights, assignments)
    analytic = challenger.evaluate(x, True)["gradient"]
    numerical = np.zeros(3)
    for axis, step in enumerate((1e-4, 1e-4, 1e-5)):
        delta = np.eye(3)[axis] * step
        numerical[axis] = (
            challenger.evaluate(x + delta, False)["score"]
            - challenger.evaluate(x - delta, False)["score"]
        ) / (2 * step)
    np.testing.assert_allclose(analytic, numerical, atol=2e-3, rtol=0)


def test_group_freeze_ignores_held_observations_and_reference_metadata():
    config, documents, x, candidates = real_case()
    expected = model.freeze_assignments(documents, config, x, candidates)
    changed = copy.copy(documents)
    changed[0] = copy.copy(documents[0])
    changed[0]["reference_position_deg"] = [0.0, 0.0]
    changed[0]["tracks"] = []
    for original in documents[0]["tracks"]:
        track = copy.copy(original)
        track["y"] = original["y"].copy()
        track["y"][~track["mask"]] += 1_000_000_000.0
        track["held_reference_label"] = "must be ignored"
        changed[0]["tracks"].append(track)
    actual = model.freeze_assignments(changed, config, x, candidates)
    fields = ("track_id", "norad", "confidence", "unambiguous", "source", "group")
    assert [[row[field] for field in fields] for row in actual] == [
        [row[field] for field in fields] for row in expected
    ]


def test_public_builder_declares_only_three_frozen_challengers():
    assert model.VARIANTS == (
        "group_sqrt",
        "group_equal",
        "source_receiver_equal",
    )
