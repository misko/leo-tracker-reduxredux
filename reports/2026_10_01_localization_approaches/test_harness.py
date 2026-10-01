from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "localization_receipt_audit", HERE / "audit_receipts.py"
)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_sealed(path: Path, receipt: dict) -> None:
    path.write_text(json.dumps(receipt))
    path.with_suffix(".seal.json").write_text(json.dumps({"prediction_sha256": _digest(path)}))


def _fixture(tmp_path: Path) -> tuple[dict, Path]:
    source = tmp_path / "solver.py"
    source.write_text("# frozen synthetic source\n")
    plan = {
        "ordered_units": [{"unit_id": "DS9-F001", "session_id": "scan-1"}],
        "authority_bindings": [],
    }
    receipt = {
        "schema": "localization-approach-attempt/v1",
        "unit_id": "DS9-F001",
        "session_id": "scan-1",
        "status": "unresolved",
        "config": {
            "arm": "A1",
            "degrees_of_freedom": 4.0,
            "seed_limit": 3,
            "max_iterations": 24,
            "primary_external_s": 90,
            "continuation_external_s": 90,
        },
        "prior_manifest_sha256": AUDIT.digest(AUDIT.DEFAULT_PLAN),
        "physical_observation_ids": [["a", "b"]],
        "planned_factors": 1,
        "candidate_ids": [101],
        "proposal": {
            "seeds": [
                {"east_km": 0.0, "north_km": 0.0},
                {"east_km": 1.0, "north_km": 0.0},
                {"east_km": 0.0, "north_km": 1.0},
            ]
        },
        "fits": [],
        "source_sha256": {str(source): _digest(source)},
        "wall_seconds_before_sealing": 12.0,
    }
    path = tmp_path / "receipt.json"
    return plan, path, receipt


def _fit(seed: dict) -> dict:
    return {
        "status": "complete",
        "mean": [0.0] * 5,
        "satellite_epoch_s": [0.0],
        "objectives": [2.0, 1.0],
        "accepted_step_norms": [0.1],
        "fit_seconds": 1.0,
        "converged": False,
        "seed": seed,
    }


def test_complete_synthetic_receipt_passes(tmp_path: Path) -> None:
    plan, path, receipt = _fixture(tmp_path)
    receipt["fits"] = [
        dict(_fit(seed), seed_index=index)
        for index, seed in enumerate(receipt["proposal"]["seeds"])
    ]
    receipt["source_snapshots"] = dict(receipt["source_sha256"])
    receipt["source_snapshots"] = {source: source for source in receipt["source_sha256"]}
    _write_sealed(path, receipt)
    result = AUDIT.audit_receipt(path, plan)
    assert result["passed"], result["failures"]


def test_missing_seed_outcome_and_duplicate_observation_fail_closed(tmp_path: Path) -> None:
    plan, path, receipt = _fixture(tmp_path)
    receipt["fits"] = [dict(_fit(receipt["proposal"]["seeds"][0]), seed_index=0)]
    receipt["source_snapshots"] = {source: source for source in receipt["source_sha256"]}
    receipt["physical_observation_ids"] = [["same"], ["same"]]
    receipt["planned_factors"] = 2
    _write_sealed(path, receipt)
    codes = {row["code"] for row in AUDIT.audit_receipt(path, plan)["failures"]}
    assert {"seed_outcome_completeness", "observation_reuse"} <= codes


def test_tampered_source_seal_and_wrong_session_fail_closed(tmp_path: Path) -> None:
    plan, path, receipt = _fixture(tmp_path)
    receipt["session_id"] = "wrong"
    receipt["fits"] = [
        dict(_fit(seed), seed_index=index)
        for index, seed in enumerate(receipt["proposal"]["seeds"])
    ]
    snapshot = tmp_path / "snapshot.py"
    source = Path(next(iter(receipt["source_sha256"])))
    snapshot.write_bytes(source.read_bytes())
    receipt["source_snapshots"] = {str(source): str(snapshot)}
    _write_sealed(path, receipt)
    source.write_text("# changed\n")
    result = AUDIT.audit_receipt(path, plan)
    codes = {row["code"] for row in result["failures"]}
    warnings = {row["code"] for row in result["warnings"]}
    assert "session_binding" in codes
    assert "working_source_changed" in warnings
    path.write_text(path.read_text() + " ")
    codes = {row["code"] for row in AUDIT.audit_receipt(path, plan)["failures"]}
    assert "seal_hash" in codes


def test_continuation_enforces_parent_identity_and_cumulative_budget(tmp_path: Path) -> None:
    plan, parent_path, parent = _fixture(tmp_path)
    parent["fits"] = [
        dict(_fit(seed), seed_index=index) for index, seed in enumerate(parent["proposal"]["seeds"])
    ]
    parent["source_snapshots"] = {source: source for source in parent["source_sha256"]}
    parent["wall_seconds_before_sealing"] = 89.0
    _write_sealed(parent_path, parent)
    child = json.loads(json.dumps(parent))
    child["parent"] = {"path": str(parent_path), "sha256": _digest(parent_path)}
    child["wall_seconds_before_sealing"] = 92.0
    child_path = tmp_path / "continuation.json"
    _write_sealed(child_path, child)
    codes = {row["code"] for row in AUDIT.audit_receipt(child_path, plan)["failures"]}
    assert {"external_budget", "cumulative_budget"} <= codes
