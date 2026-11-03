from __future__ import annotations

import copy
import importlib.util
import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = HERE.parent.parent / "2026_09_30_ds11_single10"
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as fast  # noqa: E402

spec = importlib.util.spec_from_file_location("ds11_source_count_tested", HERE / "model.py")
model = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = model
spec.loader.exec_module(model)


def synthetic_case():
    counts = (4, 16, 8)
    documents = [{"tracks": [
        {"mask": np.ones(count, dtype=bool)} for count in counts
    ]}]
    source = ("source", 0, 12345, 11_200_000_000.0)
    assignments = [
        {"document_index": 0, "track_index": 0, "source": source},
        {"document_index": 0, "track_index": 1, "source": source},
        {"document_index": 0, "track_index": 2, "source": ("ambiguous", 0, 2)},
    ]
    return documents, assignments


def test_declared_count_weights_and_global_normalization():
    documents, assignments = synthetic_case()
    sqrt = model.derive_weights(assignments, documents, "count_sqrt")
    equal = model.derive_weights(assignments, documents, "count_equal")
    source = model.derive_weights(assignments, documents, "source_count_equal")
    for weights in (sqrt, equal, source):
        assert abs(weights.mean() - 1.0) < 1e-15
    np.testing.assert_allclose(sqrt / sqrt[0], [1.0, 0.5, 2 ** -0.5])
    np.testing.assert_allclose(equal / equal[0], [1.0, 0.25, 0.5])
    np.testing.assert_allclose(source / source[0], [1.0, 1.0, 2.5])


@lru_cache
def real_case():
    fast.baseline.profile = fast.profile
    plan = json.loads((BASE / "plan.json").read_text())
    entry = plan["inputs"][0]
    documents = fast.load_documents({"config": plan["config"], "inputs": [entry]})
    incumbent = np.asarray(json.loads((BASE / "runs/00_iid.json").read_text())["selected"]["x"])
    identities = json.loads(
        (HERE.parent / "source_balance" / "catalogue_identities.json").read_text()
    )["scans"]["0"]
    candidate_norad = [{
        key: value["candidate_norad"] for key, value in identities["tracks"].items()
    }]
    return plan["config"], documents, incumbent, candidate_norad


def test_weighted_score_gradient_matches_central_difference():
    config, documents, x, candidate_norad = real_case()
    assignments = model.source_balance.freeze_assignments(
        documents, config, x, candidate_norad
    )
    weights = model.derive_weights(assignments, documents, "source_count_equal")
    objective = model.source_balance.SourceBalancedIID(
        documents, config, weights, assignments
    )
    analytic = objective.evaluate(x, True)["gradient"]
    numerical = np.zeros(3)
    for axis, step in enumerate((1e-4, 1e-4, 1e-5)):
        delta = np.eye(3)[axis] * step
        numerical[axis] = (
            objective.evaluate(x + delta, False)["score"]
            - objective.evaluate(x - delta, False)["score"]
        ) / (2 * step)
    np.testing.assert_allclose(analytic, numerical, atol=2e-3, rtol=0)


def test_held_values_and_reference_metadata_cannot_change_count_weights():
    config, documents, x, candidate_norad = real_case()
    expected_assignments = model.source_balance.freeze_assignments(
        documents, config, x, candidate_norad
    )
    expected = model.derive_weights(expected_assignments, documents, "source_count_equal")
    changed = [copy.copy(documents[0])]
    changed[0]["reference_position_deg"] = [0.0, 0.0]
    changed[0]["tracks"] = []
    for original in documents[0]["tracks"]:
        track = copy.copy(original)
        track["y"] = original["y"].copy()
        track["y"][~track["mask"]] -= 1_000_000_000.0
        changed[0]["tracks"].append(track)
    actual_assignments = model.source_balance.freeze_assignments(
        changed, config, x, candidate_norad
    )
    actual = model.derive_weights(actual_assignments, changed, "source_count_equal")
    np.testing.assert_array_equal(actual, expected)


def test_exactly_three_wave_two_variants_declared():
    assert model.VARIANTS == ("count_sqrt", "count_equal", "source_count_equal")
