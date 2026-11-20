import json
from hashlib import sha256
from pathlib import Path

import pytest

from tools.pipeline_eval import __main__ as bench_entry
from tools.pipeline_eval.variants import lean_receiver_cli as lean
from tools.pipeline_eval.variants import lean_receiver_cli_benchmark as bridge


def test_clock_provenance_and_user_region_are_checked():
    tile = {"id": "arbitrary", "center": [5.0, 130.0], "width_km": 8.0}
    lean.interface(tile, 14, 12, 11, 8)
    with pytest.raises(ValueError, match="precede the cutoff"):
        lean.interface(tile, 14, 12, 12, 8)
    with pytest.raises(ValueError, match="clock bracket"):
        lean.interface(tile, 11, 12, 10, 8)
    with pytest.raises(ValueError, match="latitude/longitude"):
        lean.interface(dict(tile, center=[5.0, 360.0]), 14, 12, 11, 8)


def test_input_bindings_hash_explicit_files_and_capture_anchor(tmp_path):
    path = tmp_path / "capture.json"
    payload = lean.encoded(
        {"clock_anchor": {"before": {"realtime_ns": 11}, "after": {"realtime_ns": 17}}}
    )
    path.write_bytes(payload)
    assert lean.capture_anchor(path) == 14
    assert lean.input_file(path, 128) == (path, sha256(payload).hexdigest())
    with pytest.raises(ValueError, match="regular nonempty file"):
        lean.input_file(path, 4)
    with pytest.raises(ValueError, match="SHA-256"):
        lean.input_file(path, 128, "sha256:not-a-digest")


def test_bundle_has_only_required_scientific_files_and_selected_solver(tmp_path):
    joint = lean.source_manifest("joint", tmp_path)
    clock = lean.source_manifest("smooth-clock")
    expected = {str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*.py")}
    assert expected == set(joint) < set(clock)
    assert set(clock) - expected == {"tools/pipeline_eval/variants/joint_clock_model.py"}
    assert not any(
        any(key in name for key in ("qualification/", "v5_", "reports/")) for name in clock
    )


def test_prepared_only_benchmark_case_cannot_be_promoted(tmp_path):
    item = {"id": "prepared", "observation": "tracks", "regions": [{"id": "tile"}]}
    case = bridge.project(item, tmp_path)
    result = bridge.run(case, "joint")
    assert result["status"] == "unavailable"
    assert result["arms"] == {key: {"latlon": None, "forced_latlon": None} for key in lean.ARMS}
    assert "input_binding" not in result


def test_private_worker_rejects_unmounted_and_prepared_paths_before_import(monkeypatch):
    limits = []
    monkeypatch.setattr(
        lean, "setrlimit", lambda resource, values: limits.append((resource, values))
    )
    with pytest.raises(ValueError, match="three mounted native inputs"):
        lean.worker({"capture_utc_ns": 14, "request": {"mode": "prepared"}}, "joint")
    assert limits == [(lean.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))]


def test_standard_worker_path_forwards_public_native_fields(monkeypatch, tmp_path):
    case = dict(id="case", files={"native": "/provided"}, capture=14, expected={})
    request, target = tmp_path / "request.json", tmp_path / "target.json"
    request.write_bytes(lean.encoded(case))
    binding = {"input_sha256": "actual-request"}

    def run(actual, solver):
        assert actual == case and solver == "smooth-clock"
        return dict(lean.failed("withheld", "fixture")["result"], input_binding=binding)

    monkeypatch.setattr(bridge, "run", run)
    bench_entry.child("portable_native_clock", request, target, tmp_path)
    out = json.loads(target.read_bytes())
    assert out["input_binding"] == binding
    assert out["input_sha256"] == "actual-request"
    assert Path(bridge.__file__).stem == "lean_receiver_cli_benchmark"
