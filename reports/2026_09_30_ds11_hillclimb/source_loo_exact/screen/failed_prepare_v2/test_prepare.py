import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ds11_screen_prepare_test", HERE / "prepare.py")
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_cache_artifact_binding_accepts_plan_chain_and_rejects_tamper(tmp_path):
    artifact = tmp_path / "observations.json"
    artifact.write_text("frozen observations")
    entry = {
        "session_id": "scan",
        "artifacts": [{"path": str(artifact), "sha256": "sha256:" + sha(artifact)}],
    }
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"inputs": [entry]}))
    required = [
        prepare.HILL / "source_loo" / "diagnose.py",
        prepare.HILL / "source_loo" / "exact_audit.py",
        prepare.ROOT / "tools" / "ds7_baseline_adapter.py",
        prepare.ROOT / "tools" / "ds7_fast_baseline_adapter.py",
    ]
    row = {"sources": {str(plan.resolve()): sha(plan)}}
    row["sources"].update({str(path.resolve()): sha(path) for path in required})
    sources = prepare.Sources()
    prepare.require_bound_dependencies(row, "iid_t4_scale100", plan, entry, 0, sources)
    assert str(artifact.resolve()) not in row["sources"]
    missing = {"sources": {key: value for key, value in row["sources"].items()
                           if key != str(plan.resolve())}}
    with pytest.raises(ValueError, match="cache omits bound dependency"):
        prepare.require_bound_dependencies(
            missing, "iid_t4_scale100", plan, entry, 0, prepare.Sources()
        )
    wrong = {"sources": {**row["sources"], str(plan.resolve()): "0" * 64}}
    with pytest.raises(ValueError, match="source hash mismatch"):
        prepare.require_bound_dependencies(
            wrong, "iid_t4_scale100", plan, entry, 0, prepare.Sources()
        )
    artifact.write_text("tampered")
    with pytest.raises(ValueError, match="artifact digest mismatch"):
        prepare.require_bound_dependencies(
            row, "iid_t4_scale100", plan, entry, 0, prepare.Sources()
        )
