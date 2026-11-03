from __future__ import annotations

import importlib.util
import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pytest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = HERE.parent.parent / "2026_09_30_ds11_single10"
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as fast  # noqa: E402

spec = importlib.util.spec_from_file_location("ds11_source_temper_tested", HERE / "model.py")
model = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = model
spec.loader.exec_module(model)


def assignment(source, receiver, unambiguous=True):
    return {
        "source": source,
        "group": source + (receiver,) if unambiguous else source,
        "receiver_id": receiver,
        "unambiguous": unambiguous,
    }


def test_predeclared_powers_attenuate_only_frozen_source_weights():
    source = ("source", 0, 12345, 11_200_000_000.0)
    rows = [assignment(source, 0), assignment(source, 0), assignment(source, 1)]
    rows.append(assignment(("ambiguous", 0, 3), 0, False))
    original = model.source_balance.derive_weights(rows, "source_receiver_equal")
    np.testing.assert_allclose(original, [0.25, 0.25, 0.5, 1.0])
    np.testing.assert_allclose(model.tempered_weights(rows, 0.5), np.sqrt(original))
    np.testing.assert_allclose(model.tempered_weights(rows, 0.75), original**0.75)
    assert model.tempered_weights(rows, 0.5)[-1] == 1.0


def test_undeclared_power_is_rejected():
    with pytest.raises(ValueError, match="not predeclared"):
        model.tempered_weights([], 0.6)


@lru_cache
def real_case():
    fast.baseline.profile = fast.profile
    plan = json.loads((BASE / "plan.json").read_text())
    entry = plan["inputs"][0]
    documents = fast.load_documents({"config": plan["config"], "inputs": [entry]})
    x = np.asarray(json.loads((BASE / "runs/00_iid.json").read_text())["selected"]["x"])
    sidecar = json.loads(
        (HERE.parent / "source_balance" / "catalogue_identities.json").read_text()
    )["scans"]["0"]
    identities = [{key: row["candidate_norad"] for key, row in sidecar["tracks"].items()}]
    return plan["config"], documents, x, identities


def test_tempered_weighted_gradient_matches_central_difference():
    config, documents, x, identities = real_case()
    assignments = model.source_balance.freeze_assignments(documents, config, x, identities)
    weights = model.tempered_weights(assignments, 0.75)
    objective = model.source_balance.SourceBalancedIID(documents, config, weights, assignments)
    analytic = objective.evaluate(x, True)["gradient"]
    numerical = np.zeros(3)
    for axis, step in enumerate((1e-4, 1e-4, 1e-5)):
        delta = np.eye(3)[axis] * step
        numerical[axis] = (
            objective.evaluate(x + delta, False)["score"]
            - objective.evaluate(x - delta, False)["score"]
        ) / (2 * step)
    np.testing.assert_allclose(analytic, numerical, atol=2e-3, rtol=0)


def test_only_two_variants_and_screen_eight_are_declared():
    assert model.VARIANTS == {"source_alpha050": 0.5, "source_alpha075": 0.75}
    assert model.SCREEN_INDICES == (0, 4, 8, 12, 16, 20, 24, 28)
