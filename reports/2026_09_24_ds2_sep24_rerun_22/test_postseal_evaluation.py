from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("postseal22", HERE / "postseal_evaluation.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules["postseal22"] = mod
spec.loader.exec_module(mod)


def seal(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(path.read_bytes()).hexdigest() + "\n"
    )


def result(task: str) -> dict:
    return {
        "task_id": task,
        "estimated_position": {"latitude_deg": 1.0, "longitude_deg": 2.0},
        "session_ids": ["s"],
        "reference_coordinate_present": False,
        "reference_used_for_fit": False,
    }


def test_collect_requires_sealed_reference_free_inputs(tmp_path: Path):
    seal(tmp_path / "portable/execution.json", {"complete": True, "rows": [{"task_id": "a"}]})
    seal(tmp_path / "portable/inference/a.json", result("a"))
    for stage in ("stage-one", "fine"):
        artifact = tmp_path / "portable/refinement" / stage / "a.json"
        seal(artifact, result(stage))
        seal(
            tmp_path / "portable/refinement" / stage / "index.json",
            {"complete": True, "models": [{"method": "m", "final_artifact": str(artifact)}] * 6},
        )
    seal(
        tmp_path / "geometry/inference.json",
        {"complete": True, "reference_used_for_inference": False, "results": []},
    )
    seal(
        tmp_path / "followups-v2/run-plan.json",
        {
            "complete": True,
            "reference_coordinate_present": False,
            "reference_used_for_fit": False,
            "outputs": {
                "consistent-cap800": str(tmp_path / "followups-v2/cap800.json"),
                "rate-aware-screen": str(tmp_path / "followups-v2/rate.json"),
            },
        },
    )
    seal(
        tmp_path / "followups-v2/cap800.json",
        {
            "complete": True,
            "reference_coordinate_present": False,
            "reference_used_for_fit": False,
            "winner": {
                "latitude_deg": 1.0,
                "longitude_deg": 2.0,
                "balanced_exact_capped_loss": 0.25,
            },
        },
    )
    seal(
        tmp_path / "followups-v2/rate.json",
        {
            "complete": True,
            "reference_coordinate_present": False,
            "reference_used_for_fit": False,
            "winners": {
                "rate_aware": {
                    "latitude_deg": 1.0,
                    "longitude_deg": 2.0,
                    "rate_aware": {"selection_objective": 0.2},
                },
                "nominal_control": {
                    "latitude_deg": 1.5,
                    "longitude_deg": 2.5,
                    "nominal_control": {"selection_objective": 0.3},
                },
            },
        },
    )
    rows, _ = mod.collect(tmp_path, (0.0, 0.0), expected_portable=1)
    assert len(rows) == 16
    cap800 = next(row for row in rows if row["method"] == "consistent-cap800")
    assert cap800["rf_objective"] == 0.25
    assert {row["method"] for row in rows} >= {
        "rate-aware-screen:rate-aware",
        "rate-aware-screen:nominal-control",
    }
    bad = result("bad")
    bad["reference_used_for_fit"] = True
    path = tmp_path / "bad.json"
    seal(path, bad)
    with pytest.raises(ValueError, match="reference-free"):
        mod.sealed(path)
