from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "official_localization_audit", HERE / "audit_official.py"
)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def _freeze(tmp_path: Path) -> tuple[dict, Path, Path]:
    plan = tmp_path / "benchmark.json"
    plan.write_text("{}")
    sources = {}
    for name in (
        "PROTOCOL.md",
        "adapter.py",
        "batch.py",
        "replay_approach.py",
        "localization_evaluation.py",
        "localization_fast.py",
        "localization_soft.py",
        "batch_physics.py",
    ):
        path = tmp_path / name
        path.write_text(name)
        sources[str(path)] = AUDIT.digest(path)
    config = {
        "predictor": "selected",
        "seed_source": "fresh",
        "degrees_of_freedom": 4.0,
        "seed_limit": 3,
        "max_iterations": 24,
        "primary_external_s": 90,
        "continuation_external_s": 90,
        "acquisition_budget_seconds": 50.0,
    }
    freeze = {
        "schema": "localization-approach-freeze/v1",
        "plan_path": plan.name,
        "plan_sha256": AUDIT.digest(plan),
        "source_sha256": sources,
        "config": config,
        "admitted_arms": ["A1", "B1"],
    }
    freeze_path = tmp_path / "FREEZE.json"
    freeze_path.write_text(json.dumps(freeze))
    digest_path = tmp_path / "FREEZE.sha256"
    digest_path.write_text(AUDIT.digest(freeze_path) + "\n")
    return freeze, freeze_path, digest_path


def _attempt(freeze: dict, arm: str = "A1") -> tuple[dict, dict]:
    receipt = {
        "config": {"arm": arm, **freeze["config"]},
        "source_sha256": dict(freeze["source_sha256"]),
    }
    launch = {
        "arm": arm,
        "command": [
            "python",
            "replay.py",
            "U",
            "--arm",
            arm,
            "--seed-source",
            "fresh",
            "--predictor",
            "selected",
            "--acquisition-budget",
            "50.0",
        ],
    }
    return receipt, launch


def test_detached_freeze_digest_and_every_source_are_verified(tmp_path: Path) -> None:
    freeze, freeze_path, digest_path = _freeze(tmp_path)
    loaded, failures = AUDIT.audit_freeze(freeze_path, digest_path, tmp_path)
    assert loaded == freeze
    assert not failures
    Path(next(iter(freeze["source_sha256"]))).write_text("changed")
    codes = {
        failure["code"] for failure in AUDIT.audit_freeze(freeze_path, digest_path, tmp_path)[1]
    }
    assert "frozen_source_hash" in codes


def test_official_attempt_requires_exact_fresh_selected_50s_config(tmp_path: Path) -> None:
    freeze, _freeze_path, _digest_path = _freeze(tmp_path)
    receipt, launch = _attempt(freeze)
    assert not AUDIT.audit_attempt_config(receipt, launch, freeze)
    receipt["config"]["acquisition_budget_seconds"] = 40.0
    launch["command"][-1] = "40.0"
    codes = {failure["code"] for failure in AUDIT.audit_attempt_config(receipt, launch, freeze)}
    assert {"official_config", "launch_config"} <= codes


def test_arm_specific_frozen_sources_are_required(tmp_path: Path) -> None:
    freeze, _freeze_path, _digest_path = _freeze(tmp_path)
    receipt, launch = _attempt(freeze, "B1")
    receipt["source_sha256"] = {
        path: value
        for path, value in receipt["source_sha256"].items()
        if Path(path).name != "batch_physics.py"
    }
    codes = {failure["code"] for failure in AUDIT.audit_attempt_config(receipt, launch, freeze)}
    assert "required_frozen_sources" in codes


def test_minimal_b1_source_set_does_not_require_a1_protocol_module(tmp_path: Path) -> None:
    freeze, _freeze_path, _digest_path = _freeze(tmp_path)
    receipt, launch = _attempt(freeze, "B1")
    required = {
        "PROTOCOL.md",
        "adapter.py",
        "batch.py",
        "replay_approach.py",
        "localization_soft.py",
        "batch_physics.py",
    }
    receipt["source_sha256"] = {
        path: value
        for path, value in receipt["source_sha256"].items()
        if Path(path).name in required
    }
    assert not AUDIT.audit_attempt_config(receipt, launch, freeze)


def test_proposal_identity_ignores_timing_only() -> None:
    left = {"seeds": [{"east_km": 1.0}], "wall_seconds": 4.0, "track_count": 3}
    right = {"seeds": [{"east_km": 1.0}], "wall_seconds": 9.0, "track_count": 3}
    assert AUDIT._proposal_identity(left) == AUDIT._proposal_identity(right)
    right["seeds"][0]["east_km"] = 2.0
    assert AUDIT._proposal_identity(left) != AUDIT._proposal_identity(right)
