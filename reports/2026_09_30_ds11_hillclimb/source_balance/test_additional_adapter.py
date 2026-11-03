from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest


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


def test_explicit_path_adapter_reproduces_original_path_builder(tmp_path):
    fast.baseline.profile = fast.profile
    frozen = load("source_balance_frozen_test", HERE / "model.py")
    adapter = load("source_balance_additional_test", HERE / "additional_adapter.py")
    plan = json.loads((BASE / "plan.json").read_text())
    entry = plan["inputs"][0]
    documents = fast.load_documents({"config": plan["config"], "inputs": [entry]})
    original_sidecar = json.loads((HERE / "catalogue_identities.json").read_text())
    additional_sidecar = {
        **original_sidecar,
        "schema": "ds11-source-balance-additional-identities/v1",
        "plan_path": str((BASE / "plan.json").resolve()),
    }
    sidecar_path = tmp_path / "identities.json"
    sidecar_path.write_text(json.dumps(additional_sidecar))
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    incumbent = json.loads((BASE / "runs/00_iid.json").read_text())
    incumbent["sources"] = {str(HERE / "model.py"): adapter.digest(HERE / "model.py")}
    (runs_dir / "00_iid.json").write_text(json.dumps(incumbent))
    (runs_dir / "00_iid.receipt.json").write_text(json.dumps({"index": 0, "exit_code": 0}))
    explicit = adapter.build_additional_model(
        documents,
        plan["config"],
        index=0,
        plan_path=BASE / "plan.json",
        runs_dir=runs_dir,
        identity_sidecar_path=sidecar_path,
    )
    expected = frozen.build_model(
        documents, plan["config"], "source_receiver_equal", index=0
    )
    x = np.asarray(json.loads((BASE / "runs/00_iid.json").read_text())["selected"]["x"])
    left, right = explicit.evaluate(x), expected.evaluate(x)
    assert left["score"] == right["score"]
    np.testing.assert_array_equal(left["gradient"], right["gradient"])
    np.testing.assert_array_equal(explicit.weights, expected.weights)


def test_document_session_mismatch_is_rejected():
    adapter = load("source_balance_additional_document_mismatch", HERE / "additional_adapter.py")
    with pytest.raises(ValueError, match="session or index binding"):
        adapter._require_same_session("wrong", "expected", "expected")


def test_plan_entry_session_mismatch_is_rejected():
    adapter = load("source_balance_additional_entry_mismatch", HERE / "additional_adapter.py")
    with pytest.raises(ValueError, match="session or index binding"):
        adapter._require_same_session("expected", "wrong", "expected")


def test_sidecar_session_mismatch_is_rejected():
    adapter = load("source_balance_additional_sidecar_mismatch", HERE / "additional_adapter.py")
    with pytest.raises(ValueError, match="session or index binding"):
        adapter._require_same_session("expected", "expected", "wrong")


def valid_iid_files(tmp_path, adapter, *, session="expected", receipt=True):
    source = tmp_path / "source.py"
    source.write_text("# bound source\n")
    start = {
        "x": [0.0, 0.0, 0.0], "score": -1.0, "success": True,
        "boundary": False, "gradient": 0.001, "audit": 0.001, "qualified": True,
    }
    record = {
        "index": 0, "session": session, "method": "iid", "starts": [start],
        "selected": dict(start), "sources": {str(source): adapter.digest(source)},
    }
    (tmp_path / "00_iid.json").write_text(json.dumps(record))
    if receipt:
        (tmp_path / "00_iid.receipt.json").write_text(
            json.dumps({"index": 0, "exit_code": 0})
        )
    return source


def test_unreceipted_iid_input_is_rejected(tmp_path):
    adapter = load("source_balance_additional_unreceipted", HERE / "additional_adapter.py")
    valid_iid_files(tmp_path, adapter, receipt=False)
    with pytest.raises(ValueError, match="no terminal receipt"):
        adapter._load_validated_incumbent(0, "expected", tmp_path)


def test_wrong_session_iid_input_is_rejected(tmp_path):
    adapter = load("source_balance_additional_wrong_iid_session", HERE / "additional_adapter.py")
    valid_iid_files(tmp_path, adapter, session="stale")
    with pytest.raises(ValueError, match="identity mismatch"):
        adapter._load_validated_incumbent(0, "expected", tmp_path)


def test_stale_declared_source_is_rejected(tmp_path):
    adapter = load("source_balance_additional_stale_source", HERE / "additional_adapter.py")
    source = valid_iid_files(tmp_path, adapter)
    source.write_text("# changed after fit\n")
    with pytest.raises(ValueError, match="source hash mismatch"):
        adapter._load_validated_incumbent(0, "expected", tmp_path)
