"""Actual generic pilot driver with synthetic ports, no recording evaluation."""

import copy
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location("pilot105", Path(__file__).with_name("run.py"))
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "HERE", tmp_path)
    monkeypatch.setattr(driver, "ROOT", tmp_path)
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.setenv(name, "1")
    driver.write(
        tmp_path / "protocol.json",
        dict(
            slice_seconds=500,
            maximum_slices_per_phase=6,
            maximum_workers=2,
            b7_policy=driver.B7_POLICY,
            source_sha256={},
            labels=["member"],
        ),
    )
    driver.write(
        tmp_path / "source-snapshot.json",
        {
            "members": [
                {"label": "member", "document": {}, "checkpoints": {}, "source_version": "B7"}
            ]
        },
    )
    monkeypatch.setattr(
        driver,
        "load_case",
        lambda document: (
            "obs",
            "bank",
            "prior",
            "tracks",
            dict(input_digest="input", score_signature="score", bank_signature="bank"),
        ),
    )
    monkeypatch.setattr(
        driver, "source_compatibility", lambda document: {"eligible": False, "reasons": []}
    )


def test_three_passes_fresh_baseline_and_separate_candidate_joint(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    separations = []

    def regional(obs, bank, prior, tracks, checkpoints, *, configuration, maximum_seconds):
        separations.append(configuration.basin_separation_km)
        assert configuration.point_budget == 400 and configuration.final_iterations == 600
        return dict(
            points={},
            searches={"V16": {"evaluations": []}},
            failures=[],
            finals=[],
            calibrations={},
        )

    monkeypatch.setattr(driver, "run_hard60", regional)
    joint_calls = []

    def joint(obs, bank, prior, regions, stage):
        joint_calls.append(tuple(regions))
        receipt = stage("shared-key", 90, lambda: {"invocation": len(joint_calls)})
        return {arm: receipt["result"] for arm in ("zero-c", "fitted-c")}, {}, []

    monkeypatch.setattr(driver, "run_joint_stages", joint)
    driver.main("member", "baseline")
    baseline = driver.read(tmp_path / "results/member/baseline.json")
    assert baseline["status"] == "complete" and separations == [12.5, 25.0, 50.0]
    driver.main("member", "candidate")
    candidate = driver.read(tmp_path / "results/member/candidate.json")
    assert candidate["status"] == "complete"
    assert candidate["operational"]["fitted-c"]["invocation"] == 2
    assert candidate["baseline_operational"]["fitted-c"]["invocation"] == 1
    assert candidate["regions"] == baseline["regions"]
    driver.main("member", "baseline")
    assert len(separations) == 3 and len(joint_calls) == 2


def test_six_pending_slices_terminal_without_restart_reset(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    calls = []

    def pending(document):
        calls.append(True)
        raise driver.core.RegionalSliceExpired("synthetic-cap")

    monkeypatch.setattr(driver, "load_case", pending)
    for _ in range(6):
        driver.main("member", "baseline")
    result = driver.read(tmp_path / "results/member/baseline.json")
    assert result["status"] == "budget-exhausted" and result["fallback_available"] is False
    driver.main("member", "baseline")
    assert len(calls) == 6
    with pytest.raises(AssertionError):
        driver.main("member", "candidate")


def test_input_failure_stays_in_coverage(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)

    def invalid(document):
        raise ValueError("input identity changed")

    monkeypatch.setattr(driver, "load_case", invalid)
    driver.main("member", "baseline")
    result = driver.read(tmp_path / "results/member/baseline.json")
    assert result["status"] == "failed" and "input identity changed" in result["reason"]
    assert result["operational"] == {}


def test_stale_baseline_rejected_before_input_loading(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    driver.write(
        tmp_path / "results/member/baseline.json", dict(status="complete", protocol_sha256="stale")
    )
    monkeypatch.setattr(
        driver, "load_case", lambda document: pytest.fail("No load for stale baseline")
    )
    with pytest.raises(AssertionError):
        driver.main("member", "candidate")


def test_source_compatibility_excludes_only_renderer(tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "ROOT", tmp_path)
    names = [
        "application/hard60_runner.py",
        "analysis/hard60_score.py",
        "analysis/regional_position_fit.py",
        "analysis/regional_position_bootstrap.py",
        "analysis/regional_position_calibration.py",
        "application/regional_position_inputs.py",
        "application/regional_position_report.py",
    ]
    hashes = {}
    for name in names:
        path = tmp_path / "src/leo" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("current-source")
        hashes[name] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    hashes["application/regional_position_report.py"] = "sha256:old-renderer"
    document = {
        "configuration": {
            "source_digests": hashes,
            "scores": {"V16": driver.core.json_value(driver.core.HARD60_SCORE)},
            "run": driver.core.json_value(driver.Hard60Configuration()),
        }
    }
    result = driver.source_compatibility(document)
    assert result["eligible"]
    assert result["ignored_nonnumeric_mismatches"] == ["application/regional_position_report.py"]
    changed = copy.deepcopy(document)
    changed["configuration"]["source_digests"]["analysis/hard60_score.py"] = "sha256:changed"
    assert not driver.source_compatibility(changed)["eligible"]
    changed = copy.deepcopy(document)
    changed["configuration"]["run"]["point_budget"] = 399
    assert not driver.source_compatibility(changed)["eligible"]


def test_recovered_region_matched_arms_uses_generic_radius_and_records_projection(monkeypatch):
    radius = 40 / np.sqrt(2)
    trigger = dict(key="point:10:20", identity={"local_radius_km": radius})
    monkeypatch.setattr(
        driver, "recover_calibration", lambda *args: {"calibration": {"saved": True}}
    )
    correction = SimpleNamespace(knots_hz=np.zeros((2, 3)))
    cal = SimpleNamespace(correction=correction, receiver_baseline_hz=np.zeros(1))
    monkeypatch.setattr(driver.core, "_calibration", lambda value: cal)
    bank = SimpleNamespace(numbers=np.array([1]))
    bank.select = lambda indices: bank
    seed = np.arange(10, dtype=float)
    seed[:2] = [10 + radius + 5e-7, 20]
    monkeypatch.setattr(
        driver.core,
        "associate_calibration",
        lambda *args, **kwargs: {
            "selected_indices": [0],
            "initial_vector": seed.tolist(),
            "selection": {},
        },
    )
    monkeypatch.setattr(driver.core, "Hard60Objective", lambda *args, **kwargs: object())
    fits = []

    def bounded(model, start, **options):
        fits.append((start.copy(), options))
        if options["rf_arm"] == "zero-c":
            start[6] = 0
        return driver.core.PositionFit(
            start, 1.0, 2.0, 3.0, 0.0001, True, False, "synthetic", 1, 0.01
        ), {}

    monkeypatch.setattr(driver.core, "fit_bounded_position", bounded)
    budgets = []

    def stage(key, budget, operation):
        budgets.append(budget)
        return {"result": driver.core.json_value(operation()), "reason": None}

    result = driver.recovered_region("obs", bank, SimpleNamespace(radius_km=250), trigger, stage)
    assert budgets == [90, 60] + [20] * 6
    assert len(fits) == 6
    assert [row["arm"] for row in result["finals"]] == ["zero-c"] * 3 + ["fitted-c"] * 3
    for start, options in fits:
        assert options["local_radius_km"] == radius
        assert options["maximum_seconds"] == 20 and options["maximum_iterations"] == 600
        assert np.linalg.norm(start[:2] - np.array([10, 20])) <= radius
    assert result["finals"][0]["seed_audit"]["position_delta_km"][0] < 0
    assert result["finals"][0]["seed_audit"]["original"] == seed.tolist()
