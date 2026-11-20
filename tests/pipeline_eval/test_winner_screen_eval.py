import gzip
import json

import pytest

from tools.pipeline_eval.__main__ import encoded, save_json
from tools.pipeline_eval.qualification import winner_screen_eval as study


def test_frozen_request_binds_distinct_screen_and_search_centers(tmp_path):
    native = tmp_path / "native.json"
    catalog = tmp_path / "catalog.json"
    request = tmp_path / "request.json"
    native.write_text("observation contents")
    catalog.write_text("causal catalogue contents")
    native_sha = study.digest(native)
    job = {
        "evaluation_reference": None,
        "native_input": {"sha256": "sha256:" + native_sha},
        "search_center": [1, 2],
        "screen_center": [3, 4],
    }
    save_json(request, {"job": job})
    item = {
        "id": "case-0",
        "regions": [{"center": [1, 2]}],
        "request": {"sha256": "original_request"},
        "native": {"sha256": native_sha},
        "catalog": {"sha256": study.digest(catalog)},
    }
    case = {
        "native_path": str(native),
        "catalog_path": str(catalog),
        "request_path": str(request),
    }
    binding = study.case_binding(item, case)
    assert binding["region"] == [{"center": [1, 2]}]
    assert binding["screen_center"] == [3, 4]
    assert binding["native_sha256"] == native_sha
    assert binding["request_sha256"] == "original_request"
    assert binding["execution_request_sha256"] == study.digest(request)
    job["evaluation_reference"] = [5, 6]
    save_json(request, {"job": job})
    with pytest.raises(ValueError, match="blind roof request"):
        study.case_binding(item, case)


def test_initializer_timing_observes_but_preserves_result(monkeypatch):
    clocks = iter([17.5, 20.0])
    monkeypatch.setattr(study, "cpu_elapsed", lambda: next(clocks))
    record = {}

    def infer(first, stage_s, *, select_initial):
        stage_s.append(select_initial(first))
        return "original output"

    stages = []
    answer = study.observe_initial(
        infer, record, "observation", stages, select_initial=lambda scan: f"same {scan}"
    )
    assert answer == "original output"
    assert record == {"initial_screen_cpu_s": 2.5}
    assert stages == ["same observation"]


def test_endpoint_scoring_keeps_position_frequency_and_coverage_separate():
    truth = [37.0, -121.0]
    ref = {"truth": truth, "reference": {r: {"c0": {"latlon": truth}} for r in study.ROLES}}
    original = {"latlon": truth, "rf_rms_hz": 85.0}
    different = {"latlon": [37.1, -121.0], "rf_rms_hz": 80.0}
    result = study.compare_endpoint("c0", different, original, ref)
    assert result["rms_delta_hz"] == -5.0
    assert result["position_error_km"] > 11.0
    assert result["control_error_km"] == 0.0
    assert all(result[f"{role}_v5_error_km"] == 0.0 for role in study.ROLES)
    assert not result["within_control_limits"]
    failure = study.compare_endpoint("c0", {"latlon": None}, original, ref)
    assert failure["position_error_km"] is None
    assert failure["conditional_rms_hz"] is None
    assert not failure["within_control_limits"]


def test_rejects_archive_changed_after_prediction_seal(tmp_path, monkeypatch):
    monkeypatch.setattr(study, "TIMING_IDS", ("case-0",))
    inputs = {"case-0": {"input_sha256": "recording_inputs"}}
    lock = tmp_path / "source-lock.json"
    save_json(lock, {"inputs": inputs})
    runs, files = {}, {}
    for method in (*study.METHODS, *study.CONTROLS.values()):
        path = tmp_path / f"{method}-positions.jsonl.gz"
        row = {
            "id": "case-0",
            "method": method,
            "input_sha256": "recording_inputs",
            "result": {
                "status": "withheld",
                "reason": "test does not publish a position",
                "boundary": "test boundary",
                "metrics": {},
            },
        }
        path.write_bytes(gzip.compress(encoded(row) + b"\n", mtime=0))
        files[path.name] = study.digest(path)
        runs[method] = {
            "method": method,
            "positions": path.name,
            "position_sha256": files[path.name],
        }
    receipt = {
        "cases": ["case-0"],
        "files": files,
        "runs": runs,
        "source_lock_sha256": study.digest(lock),
        "comparisons": [{"id": "case-0", **inputs["case-0"]}],
    }
    save_json(tmp_path / "receipt.json", receipt)
    assert set(study.sealed_predictions(tmp_path)[1]) == set(runs)
    damaged = tmp_path / runs["v5_screen_winner"]["positions"]
    damaged.write_bytes(gzip.compress(json.dumps({"id": "other"}).encode(), mtime=0))
    with pytest.raises(ValueError, match="prediction bytes"):
        study.sealed_predictions(tmp_path)


def test_scoring_counts_the_same_recording_at_each_distance_threshold(tmp_path, monkeypatch):
    ident = "case-0"
    reference = {
        "id": ident,
        "group": "DS26",
        "truth": [37.0, -121.0],
        "reference": {},
    }
    endpoint = {"latlon": [37.015, -121.0], "rf_rms_hz": 79.0}
    prediction = dict(
        worker_wall_s=1.0,
        result=dict(status="ok", metrics={}, arms={arm: endpoint for arm in study.ARMS}),
    )
    rows = {m: {ident: prediction} for m in (*study.METHODS, *study.CONTROLS.values())}
    monkeypatch.setattr(study, "TIMING_IDS", (ident,))
    monkeypatch.setattr(
        study, "sealed_predictions", lambda _: ({"original_rank": {ident: 0}}, rows)
    )
    monkeypatch.setattr(study, "references", lambda p, ids: (p, [reference]))
    study.score(tmp_path)
    scored = study.read(tmp_path / "scores.json")
    for group in scored["groups"]:
        assert group["within_km"]["position_error_km"] == {"1": 0, "2": 1, "5": 1, "10": 1}


def test_receipt_accepts_a_reported_full_budget_fallback_and_checks_normal_rank():
    ident, method = "case-0", "v5_screen_winner"
    kernel = str(study.orbit_projector.KERNEL.relative_to(study.ROOT))
    plan = {
        "schedule": {ident: {"cpu": 22, "order": [method]}},
        "inputs": {ident: {}},
        "source": {kernel: "kernel_sha"},
    }
    screen = dict(
        ranks=[0, 1, 2],
        screen_c0_scores=[None, 3, 2],
        winning_rank=None,
        fallback=True,
        early_fits=6,
        finish_fits=15,
        initial_phase_fits=21,
    )
    row = dict(
        id=ident,
        method=method,
        mode="reference",
        cpu=22,
        cap_s=480,
        order=0,
        source_lock_sha256="lock_sha",
        worker_wall_s=2.0,
        worker_cpu_s=1.0,
        result=dict(
            status="ok",
            boundary="test cavity",
            arms={a: {"latlon": [1, 2]} for a in study.ARMS},
            metrics=dict(
                kernel_sha256="kernel_sha",
                initial_screen_cpu_s=1.0,
                stage_s={"initial": 1.0},
                initial_screen=screen,
            ),
        ),
    )
    assert study.verify_row(row, plan, ident, method, "lock_sha") is row
    screen.update(
        screen_c0_scores=[2, 2, 1],
        winning_rank=0,
        fallback=False,
        finish_fits=3,
        initial_phase_fits=9,
    )
    with pytest.raises(ValueError, match="invalid initial screening receipt"):
        study.verify_row(row, plan, ident, method, "lock_sha")
    screen["winning_rank"] = 2
    assert study.verify_row(row, plan, ident, method, "lock_sha") is row
