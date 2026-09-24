from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "run_followups.py"
SPEC = importlib.util.spec_from_file_location("ds2_successor_followups_tested", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
followups = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = followups
SPEC.loader.exec_module(followups)


def save(path: Path, value: dict) -> None:
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(text.encode()).hexdigest() + "\n"
    )


def fixture(tmp_path: Path, *, leaked: bool = False) -> tuple[Path, Path, Path]:
    sessions = [
        {
            "session_id": f"scan-fw-{index:016x}",
            "captured_at": f"2026-09-24T{index:02d}:00:00Z",
        }
        for index in range(22)
    ]
    manifest_path = tmp_path / "manifest.json"
    save(
        manifest_path,
        {
            "schema": "ds2-whole-corpus-manifest/v1",
            "manifest_sealed": True,
            "reference_coordinate_in_manifest": False,
            "position_evaluation": "external_post_inference_only",
            "sessions": sessions,
        },
    )
    parent_path = tmp_path / "joint-all22.json"
    save(
        parent_path,
        {
            "complete": True,
            "reference_coordinate_present": leaked,
            "reference_used_for_fit": False,
            "task_id": "joint-all22__equal-weight-joint-rate",
            "session_ids": [row["session_id"] for row in sessions],
            "estimated_position": {"latitude_deg": 38.0, "longitude_deg": -122.0},
            "global_tau_s": 0.0,
            "exact_sgp4_winner_gate": {"passed": True},
            "search_trace": [
                {
                    "stage": "exact_rate_finalist",
                    "latitude_deg": 38.0 + index / 1000,
                    "longitude_deg": -122.0,
                    "tau_s": 0.0,
                    "objective": 0.1 + index / 100,
                    "screening_objective": 0.2 + index / 100,
                }
                for index in range(2)
            ],
            "track_associations": [
                {"candidate_id": "12345", "session_id": sessions[index]["session_id"]}
                for index in (0, 1)
            ],
            "fitted": {"rate_corrections_s_h": {"12345": 0.01}},
        },
    )
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    return manifest_path, parent_path, cache_root


def test_plan_covers_whole_successor_without_holdout(tmp_path: Path) -> None:
    manifest, parent, cache = fixture(tmp_path)
    output = tmp_path / "followups"
    plan = followups.build_plan(manifest, cache, [parent], output)
    cap = json.loads((output / "cap800-manifest.json").read_text())
    child = json.loads((output / "missing-models-plan.json").read_text())

    groups = [group["task"]["session_ids"] for group in cap["groups"]]
    assert list(map(len, groups)) == [11, 11]
    assert sorted(groups[0] + groups[1]) == sorted(plan["session_ids"])
    assert set(groups[0]).isdisjoint(groups[1])
    assert cap["reference_coordinate_present"] is False
    assert all(
        group["task"]["options"]["cache_root"] == str(cache.resolve())
        for group in cap["groups"]
    )
    assert child["reference_coordinate_present"] is False
    assert len(child["residual_likelihood"]["finalists"]) == 2
    assert followups.sealed(output / "run-plan.json")


def test_parent_with_reference_is_rejected(tmp_path: Path) -> None:
    manifest, parent, cache = fixture(tmp_path, leaked=True)
    with pytest.raises(ValueError, match="reference or exact-replay gate"):
        followups.build_plan(manifest, cache, [parent], tmp_path / "followups")


def test_shared_norad_is_accounted_from_sealed_joint_fit(tmp_path: Path) -> None:
    manifest, parent, cache = fixture(tmp_path)
    output = tmp_path / "followups"
    followups.build_plan(manifest, cache, [parent], output)
    plan_path = output / "run-plan.json"
    plan = json.loads(plan_path.read_text())

    followups.run_shared_norad(plan, plan_path)

    result = json.loads((output / "shared-norad.json").read_text())
    assert result["state"] == "complete_shared_support"
    assert result["cross_session_shared_norad_count"] == 1
    assert result["shared_rate_corrections_s_h"] == {"12345": 0.01}
    assert result["reference_coordinate_present"] is False


def test_resume_rejects_output_from_another_plan(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    plan = tmp_path / "plan.json"
    save(plan, {"schema": "anything"})
    save(path, {"complete": True, "run_plan_sha256": "sha256:not-this-plan"})
    with pytest.raises(ValueError, match="another follow-up plan"):
        followups.completed(path, plan)


def test_discovers_coarse_and_refined_rate_parents(tmp_path: Path) -> None:
    _manifest, parent, _cache = fixture(tmp_path)
    output = tmp_path / "successor-output"
    plan_path = output / "portable" / "plan.json"
    save(
        plan_path,
        {
            "joint_task_prefix": "joint-all22",
            "tasks": [
                {
                    "task_id": "joint-all22__equal-weight-joint-rate",
                    "output_path": str(parent),
                }
            ],
        },
    )
    for stage in ("stage-one", "fine"):
        stage_parent = tmp_path / f"{stage}.json"
        stage_parent.write_text("{}\n")
        save(
            output / "portable" / "refinement" / stage / "index.json",
            {
                "models": [
                    {
                        "method": "equal-weight-joint-rate",
                        "final_artifact": str(stage_parent),
                    }
                ]
            },
        )

    assert followups.discover_parents(output) == [
        parent,
        tmp_path / "stage-one.json",
        tmp_path / "fine.json",
    ]
