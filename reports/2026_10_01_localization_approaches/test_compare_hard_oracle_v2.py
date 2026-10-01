from __future__ import annotations

import hashlib
import json

import compare_hard_oracle_v2 as audit


def _fit(seed, objectives, iterations, **extra):
    return {"seed": {"east_km": seed, "north_km": -seed}, "objectives": objectives,
            "iterations": iterations, "mean": [seed, 0, 0, 0, 0],
            "satellite_epoch_s": [0], "associations": ["x"], "converged": False,
            "reason": "iteration_limit", **extra}


def test_restart_normalization_drops_only_duplicate_boundary():
    parent = _fit(1., [5., 4.], 2)
    child = {**_fit(1., [4., 3.], 2), "parent_seed": parent["seed"]}
    combined = audit._combine(parent, child, child_is_cumulative=False)
    assert combined["iterations"] == 4
    assert combined["objectives"] == [5., 4., 4., 3.]
    assert audit._normalize_restart(combined)["objectives"] == [5., 4., 3.]
    child["objectives"] = [3.9, 3.]
    distinct = audit._combine(parent, child, child_is_cumulative=False)
    assert audit._normalize_restart(distinct)["objectives"] == [5., 4., 3.9, 3.]


def test_partial_historical_continuation_preserves_unresumed_parent(tmp_path, monkeypatch):
    parent_a = _fit(1., [5., 4.], 2)
    parent_b = _fit(2., [6., 5.], 2)
    child = {**_fit(1., [4., 3.], 1), "parent_seed": parent_a["seed"]}

    primary_path = tmp_path / "primary.json"
    primary_path.write_text(json.dumps({"fits": [parent_a, parent_b]}))
    primary_digest = "sha256:" + hashlib.sha256(primary_path.read_bytes()).hexdigest()
    continuation_dir = tmp_path / "continuations"
    continuation_dir.mkdir()
    continuation_path = continuation_dir / "DS01-P01-F001-resume.json"
    continuation = {
        "parent_binding": {"path": "primary.json", "sha256": primary_digest},
        "parent_fits": [parent_a, parent_b],
        "resumed_fits": [child],
    }
    continuation_path.write_text(json.dumps(continuation))
    continuation_digest = "sha256:" + hashlib.sha256(
        continuation_path.read_bytes()
    ).hexdigest()
    continuation_path.with_suffix(".seal.json").write_text(
        json.dumps({"prediction_sha256": continuation_digest})
    )
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    monkeypatch.setattr(audit, "OLD_CONTINUATIONS", continuation_dir)

    final = audit._historical_final(
        primary_path,
        {"unit_id": "DS01-P01-F001", "sha256": primary_digest},
    )
    key = (1., -1.)
    assert final[(2., -2.)] == {**parent_b, "stage": "primary"}
    assert final[key]["iterations"] == 3
