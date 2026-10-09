import hashlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.regional_position_bootstrap import PositionBootstrap
from leo.analysis.regional_position_search import SpatialEvaluation, SpatialSearch

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("driver116_test", HERE / "driver.py")
D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D)


def test_cache_reuses_success_failure_and_binds_identity(tmp_path):
    cache = D.DurableCache(tmp_path, "digest", 100, clock=lambda: 0)
    assert cache.fetch(["ok"], lambda: {"x": 3}) == {"x": 3}
    assert cache.fetch(["ok"], lambda: pytest.fail("recomputed")) == {"x": 3}
    with pytest.raises(D.CachedFailure):
        cache.fetch(["bad"], lambda: (_ for _ in ()).throw(ValueError("bad")))
    with pytest.raises(D.CachedFailure):
        cache.fetch(["bad"], lambda: pytest.fail("retried failure"))
    with pytest.raises(ValueError, match="binding"):
        D.DurableCache(tmp_path, "other", 100, clock=lambda: 0).fetch(["ok"], lambda: None)


def test_crash_claim_blocks_retry_and_deadline_prevents_claim(tmp_path):
    cache = D.DurableCache(tmp_path, "digest", 100, clock=lambda: 0)
    with pytest.raises(KeyboardInterrupt):
        cache.fetch(["crash"], lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(D.ClaimedWithoutReceipt):
        cache.fetch(["crash"], lambda: pytest.fail("retried crash"))
    with pytest.raises(D.SliceExpired):
        D.DurableCache(tmp_path, "digest", 1, clock=lambda: 0).fetch(["late"], lambda: None)
    assert len(list(tmp_path.glob("*.claim.json"))) == 1


def setup(tmp_path, monkeypatch):
    source = tmp_path / "bound.txt"
    source.write_text("sealed")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    identity = dict.fromkeys(
        (
            "input_manifest_sha256",
            "analysis_manifest_sha256",
            "evidence_sha256",
            "bank_sha256",
            "prior_sha256",
            "observations_sha256",
        ),
        "bound",
    )
    plan = dict(
        slice_count=12,
        slice_seconds=500,
        source_sha256={"bound.txt": digest},
        input_sha256={"bound.txt": digest},
        identity=identity,
        binding={},
        native_baseline=[dict(east_km=0, north_km=0, spacing_km=40, score=7.0)],
    )
    case = dict(
        observations=None,
        bank=None,
        prior=SimpleNamespace(radius_km=50),
        tracks=[],
        identity=identity,
    )
    monkeypatch.setattr(D, "case_identity", lambda c: c["identity"])
    calls = []

    class Evaluator:
        def __init__(self, *args):
            self.seeds = {}
            self.bootstrap = lambda *a, **k: PositionBootstrap((0, 1), np.zeros(9), ())

        def __call__(self, e, n, arm):
            calls.append(arm)
            return {"scores": {m: {"objective": 7.0} for m in ("native", "fixed")}}

    def hierarchy(evaluate, **kwargs):
        assert kwargs["budget_points"] == 400
        return SpatialSearch((SpatialEvaluation(0, 0, 40, evaluate(0, 0)),), 3, "point-budget")

    monkeypatch.setattr(D, "hierarchical_search", hierarchy)
    return plan, case, Evaluator, calls


def test_actual_driver_cache_gate_and_idempotent_terminal(tmp_path, monkeypatch):
    plan, case, evaluator, calls = setup(tmp_path, monkeypatch)
    output = tmp_path / "results"
    row = D.run_slice(plan, tmp_path, output, lambda binding: case, evaluator_factory=evaluator)
    assert row["status"] == "complete" and len(row["searches"]) == 4
    assert calls == ["fitted-c", "zero-c"]
    assert D.read(output / "native-parity.json")["status"] == "verified"
    assert (
        D.run_slice(plan, tmp_path, output, lambda b: pytest.fail("loaded"))["status"] == "complete"
    )


def test_baseline_mismatch_prevents_candidate_search(tmp_path, monkeypatch):
    plan, case, evaluator, calls = setup(tmp_path, monkeypatch)
    plan["native_baseline"][0]["score"] = 8
    row = D.run_slice(
        plan, tmp_path, tmp_path / "results", lambda binding: case, evaluator_factory=evaluator
    )
    assert row["status"] == "failed" and "baseline" in row["reason"]
    assert calls == ["fitted-c"]


def test_aggregate_cap_and_crashed_slice_never_reset(tmp_path, monkeypatch):
    plan, case, evaluator, calls = setup(tmp_path, monkeypatch)
    digest = D.verify_plan(plan, tmp_path)
    output = tmp_path / "results"
    for slot in range(1, 13):
        D.append(output / "slices" / f"{slot:02}.started.json", dict(protocol_sha256=digest))
        D.append(
            output / "slices" / f"{slot:02}.finished.json",
            dict(protocol_sha256=digest, elapsed_s=0.1),
        )
    assert (
        D.run_slice(plan, tmp_path, output, lambda b: pytest.fail("loaded"))["status"]
        == "budget-exhausted"
    )
    crash = tmp_path / "crash"
    D.append(crash / "slices/01.started.json", dict(protocol_sha256=digest))
    with pytest.raises(D.ClaimedWithoutReceipt):
        D.run_slice(plan, tmp_path, crash, lambda b: pytest.fail("loaded"))


def test_frozen_source_mismatch_before_launch(tmp_path, monkeypatch):
    plan, _, _, _ = setup(tmp_path, monkeypatch)
    (tmp_path / "bound.txt").write_text("changed")
    with pytest.raises(ValueError, match="frozen file"):
        D.run_slice(plan, tmp_path, tmp_path / "results", lambda b: pytest.fail("loaded"))
    assert not (tmp_path / "results").exists()


def test_failed_point_is_not_complete_even_when_search_continues(tmp_path, monkeypatch):
    plan, case, evaluator, _ = setup(tmp_path, monkeypatch)

    class Failure(evaluator):
        def __call__(self, e, n, arm):
            if arm == "zero-c":
                raise ValueError("rescore failure")
            return super().__call__(e, n, arm)

    row = D.run_slice(
        plan, tmp_path, tmp_path / "results", lambda b: case, evaluator_factory=Failure
    )
    assert row["status"] == "incomplete" and not row["complete"]
    assert row["point_failure_count"] == 1
    assert row["point_failures"][0]["arm"] == "zero-c"


def test_loader_overrun_is_persisted_and_no_point_work_starts(tmp_path, monkeypatch):
    plan, case, evaluator, calls = setup(tmp_path, monkeypatch)
    moments = iter([0.0, 501.0, 502.0])
    row = D.run_slice(
        plan,
        tmp_path,
        tmp_path / "results",
        lambda b: case,
        clock=lambda: next(moments),
        evaluator_factory=evaluator,
    )
    assert row["status"] == "pending" and row["elapsed_s"] == 502
    assert calls == []


def test_pending_resume_reuses_point_and_trace_without_refitting(tmp_path, monkeypatch):
    plan, case, evaluator, calls = setup(tmp_path, monkeypatch)
    normal = D.hierarchical_search
    interrupted = False

    def hierarchy(evaluate, **kwargs):
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            evaluate(0, 0)
            raise D.SliceExpired("synthetic checkpoint")
        return normal(evaluate, **kwargs)

    monkeypatch.setattr(D, "hierarchical_search", hierarchy)
    output = tmp_path / "results"
    first = D.run_slice(plan, tmp_path, output, lambda b: case, evaluator_factory=evaluator)
    assert first["status"] == "pending" and calls == ["fitted-c"]
    second = D.run_slice(plan, tmp_path, output, lambda b: case, evaluator_factory=evaluator)
    assert second["status"] == "complete" and second["slices"] == 2
    assert calls == ["fitted-c", "zero-c"]
    assert second["elapsed_s"] >= first["elapsed_s"]


def test_nonfinite_baseline_and_invalid_cache_status_rejected(tmp_path):
    search = SpatialSearch((SpatialEvaluation(0, 0, 40, 7),), 0, "point-budget")
    with pytest.raises(ValueError, match="nonfinite"):
        D.native_parity(search, [dict(east_km=0, north_km=0, spacing_km=40, score=float("nan"))])
    key = ["badstatus"]
    path = tmp_path / (D.canonical_digest(key).split(":")[-1] + ".json")
    D.append(path, dict(protocol_sha256="digest", key=key, status="pending", value=3))
    with pytest.raises(ValueError, match="cached status"):
        D.DurableCache(tmp_path, "digest", 100, clock=lambda: 0).fetch(key, lambda: None)
