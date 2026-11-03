from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = HERE.parent.parent / "2026_09_30_ds11_single10"
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as fast  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_explicit_additional_wrapper_matches_frozen_alpha050(tmp_path):
    fast.baseline.profile = fast.profile
    wrapper = load("source_temper_additional_wrapper_test", HERE / "additional_wrapper.py")
    frozen = load("source_temper_original_test", HERE / "model.py")
    plan_path = BASE / "plan.json"
    plan = json.loads(plan_path.read_text())
    documents = fast.load_documents({"config": plan["config"], "inputs": [plan["inputs"][0]]})

    sidecar = json.loads(
        (HERE.parent / "source_balance" / "catalogue_identities.json").read_text()
    )
    sidecar["schema"] = "ds11-source-balance-additional-identities/v1"
    sidecar["plan_path"] = str(plan_path.resolve())
    sidecar_path = tmp_path / "identities.json"
    sidecar_path.write_text(json.dumps(sidecar))

    runs = tmp_path / "runs"
    runs.mkdir()
    incumbent = json.loads((BASE / "runs/00_iid.json").read_text())
    incumbent["sources"] = {
        str(HERE / "model.py"): wrapper.digest(HERE / "model.py")
    }
    (runs / "00_iid.json").write_text(json.dumps(incumbent))
    (runs / "00_iid.receipt.json").write_text(json.dumps({"index": 0, "exit_code": 0}))

    explicit = wrapper.build_additional_model(
        documents,
        plan["config"],
        index=0,
        plan_path=plan_path,
        runs_dir=runs,
        identity_sidecar_path=sidecar_path,
    )
    expected = frozen.build_model(documents, plan["config"], "source_alpha050", index=0)
    x = np.asarray(incumbent["selected"]["x"])
    np.testing.assert_array_equal(explicit.weights, expected.weights)
    left, right = explicit.evaluate(x), expected.evaluate(x)
    assert left["score"] == right["score"]
    np.testing.assert_array_equal(left["gradient"], right["gradient"])
