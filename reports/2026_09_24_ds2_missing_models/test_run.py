from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def load(name: str):
    path = HERE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_offset_coordinate_is_symmetric() -> None:
    run = load("run")
    left = run.offset_coordinate(38.0, -122.0, -1.0, 0.0)
    right = run.offset_coordinate(38.0, -122.0, 1.0, 0.0)
    assert np.isclose(left["longitude_deg"] + right["longitude_deg"], -244.0)


def test_weighted_mean_uses_track_weights() -> None:
    run = load("run")
    rows = [{"weight_s": 1.0}, {"weight_s": 3.0}]
    value = run.weighted_mean(rows, [np.asarray([1.0]), np.asarray([3.0])])
    assert value == 2.5


def test_gaussian_profile_recovers_scale() -> None:
    run = load("run")
    rows = [
        {
            "weight_s": 1.0,
            "raw": np.asarray([-2.0, 0.0, 2.0]),
        }
    ]
    fit = run.gaussian_profile(rows)
    # The configured 5-Hz lower guard is deliberately active here.
    assert fit["scale_hz"] == 5.0


def test_plan_contains_six_truth_free_finalists() -> None:
    build = load("build_plan")
    assert len(build.rate_stage_paths()) == 3
    for stage, path in zip(("coarse", "refined", "fine"), build.rate_stage_paths(), strict=True):
        rows = build.exact_finalists(path, stage)
        assert len(rows) == 2
        assert all("reference" not in row for row in rows)


def test_generated_inference_is_sealed_and_exact_gated() -> None:
    path = HERE / "inference.json"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        HERE / "inference.json.sha256"
    ).read_text().strip()
    document = json.loads(path.read_text())
    assert document["session_count"] == 20
    assert document["reference_coordinate_present"] is False
    assert document["reference_used_for_fit"] is False
    assert document["truth_used_for_fit"] is False
    residual = document["robust_residual_likelihood"]
    assert len(residual["rows"]) == 6
    assert all(row["exact_gate"]["passed"] for row in residual["rows"])


def test_postseal_evaluation_binds_inference() -> None:
    inference = HERE / "inference.json"
    evaluation = json.loads((HERE / "evaluation.json").read_text())
    assert evaluation["inference"]["sha256"] == (
        "sha256:" + hashlib.sha256(inference.read_bytes()).hexdigest()
    )
    assert evaluation["reference_coordinate"]["role"].startswith(
        "introduced only after inference.json was sealed"
    )
