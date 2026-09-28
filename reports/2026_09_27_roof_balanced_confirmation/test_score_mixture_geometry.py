import json
from types import SimpleNamespace

import pytest

import score_mixture_geometry as score


def test_incomplete_cohort_does_not_load_models_or_reference(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(score, "HERE", tmp_path)
    entries = [{"session_id": f"s{i}"} for i in range(4)]
    monkeypatch.setattr(score.runner.balanced, "inputs", lambda: (entries, {}))
    def prohibited():
        raise AssertionError("calibration loaded before complete cohort")
    monkeypatch.setattr(score.models, "load_geometry_bundle", prohibited)
    (tmp_path / "manifest.json").write_text("not parseable")
    (tmp_path / "mixture-geometry-replay-s0.json").write_text(json.dumps({"finished": False}))
    score.main()
    result = json.loads(capsys.readouterr().out)
    assert result["complete"] is False and len(result["pending_sessions"]) == 4
    assert not (tmp_path / "mixture-geometry-distances.json").exists()


def complete_cohort(tmp_path, monkeypatch):
    """Exercise the complete reporter, not only branch helpers."""
    monkeypatch.setattr(score, "HERE", tmp_path)
    first = tmp_path / "first"
    first.mkdir()
    monkeypatch.setattr(score.runner, "PREVIOUS", first)
    def write(path, value):
        path.write_text(json.dumps(value))
        return score.runner.base.digest(path.read_bytes())
    for name in ("contract.json", "MIXTURE_GEOMETRY_PROTOCOL.md", "audit_source_topology.json",
                 "run_mixture_geometry_replay.py", "mixture_geometry_models.py",
                 "paired_reception_evaluator.py", "run_consistent_replay.py",
                 "score_mixture_geometry.py", "mixture_geometry_reporting.py",
                 "score_consistent_replay.py"):
        write(tmp_path / name, {"fixture": name})
    write(first / "audit_source_topology.json", {})
    bundle = SimpleNamespace(calibration_sha256="cal", source_hashes={}, artifact_sha256={},
                             calibration_sessions=("cal1",))
    monkeypatch.setattr(score.models, "load_geometry_bundle", lambda: bundle)
    entries = [{"session_id": f"s{i}", "cache_sha256": "cache",
                "input_manifest_sha256": "input", "analysis_manifest_sha256": "analysis"}
               for i in range(4)]
    monkeypatch.setattr(score.runner.balanced, "inputs", lambda: (entries, {}))
    grids, results, grid_hashes = {}, {}, {}
    def digest(name): return score.runner.base.digest((tmp_path / name).read_bytes())
    for entry in entries:
        sid = entry["session_id"]
        grid = {"session_id": sid, "finished": True, "deduplicate_reception": False,
                "contract_sha256": digest("contract.json"),
                "topology_audit_sha256": digest("audit_source_topology.json"),
                "evidence_sha256": "evidence", "snapshot_digest": "snapshot",
                "model_hashes": {}, "parameters": {}, "topology_receipt": {}, "branches": {}}
        result = {**entry, **{k: v for k, v in grid.items() if k != "branches"},
                  "calibration_sha256": "cal", "calibration_source_hashes": {},
                  "calibration_artifact_sha256": {}, "calibration_sessions": ["cal1"],
                  "geometry_protocol_sha256": digest("MIXTURE_GEOMETRY_PROTOCOL.md"),
                  "calibration_topology_audit_sha256": score.runner.base.digest(
                      (first / "audit_source_topology.json").read_bytes()),
                  "code_sha256": {name: digest(name) for name in (
                      "run_mixture_geometry_replay.py", "mixture_geometry_models.py",
                      "paired_reception_evaluator.py", "run_consistent_replay.py")},
                  "branches": {}}
        for prior, (lat, lon, radius) in score.runner.base.PRIORS.items():
            points = [{"east_km": float(i), "north_km": 0., "latitude_deg": 37.,
                       "longitude_deg": -122. + i / 100.,
                       "scores": {"D": float(i + 1), "D_plus_geometry": float(2 - i)}}
                      for i in range(2)]
            saved = {"origin": [lat, lon], "radius_km": radius,
                     "seed": {"east_km": 0., "north_km": 0.},
                     "grid_count": 2, "point_components": points,
                     "arms": {"D": {"selected": {**points[0], "tracks": []}},
                              "D_plus_geometry": {"selected": {**points[1], "tracks": []}}}}
            rows = [{**{k: v for k, v in point.items() if k != "scores"},
                     "variant_scores": {name: dict(point["scores"]) for name in ("old", "mean", "mixture")}}
                    for point in points]
            rows[0]["variant_scores"]["mixture"]["D_plus_geometry"] = 0.
            branch = {"origin": [lat, lon], "grid_count": 2, "point_components": rows,
                      "selected": {"old": rows[1], "mean": rows[1], "mixture": rows[0]},
                      "parity": score.runner.parity_report(saved, rows)}
            grid["branches"][prior] = saved
            result["branches"][prior] = branch
        grid_hashes[sid] = write(tmp_path / f"local-grid-{sid}.json", grid)
        result["source_grid_sha256"] = grid_hashes[sid]
        grids[sid], results[sid] = grid, result
    report_sha = write(tmp_path / "local-grid-distances.json", {
        "complete": True, "deduplicate_reception": False, "artifact_sha256": grid_hashes})
    for sid, result in results.items():
        result["source_grid_report_sha256"] = report_sha
        write(tmp_path / f"mixture-geometry-replay-{sid}.json", result)
    write(tmp_path / "manifest.json", {"sessions": [
        {"pose": {"session_id": entry["session_id"],
                  "pose_authority": {"latitude_deg": 37., "longitude_deg": -122.}}}
        for entry in entries]})


def test_complete_cohort_reports_all_priors_and_minima(tmp_path, monkeypatch):
    complete_cohort(tmp_path, monkeypatch)
    score.main()
    output = json.loads((tmp_path / "mixture-geometry-distances.json").read_text())
    assert output["complete"] and len(output["rows"]) == 8
    assert output["summary"]["combined"]["mean_error_km"]["mixture"] == 0.
    assert output["summary"]["combined"]["mixture_vs"]["mean"]["improved"] == 8


def test_changed_complete_binding_rejected_before_reference_read(tmp_path, monkeypatch):
    complete_cohort(tmp_path, monkeypatch)
    path = tmp_path / "mixture-geometry-replay-s3.json"
    result = json.loads(path.read_text())
    result["calibration_sha256"] = "changed"
    path.write_text(json.dumps(result))
    (tmp_path / "manifest.json").write_text("must not parse this")
    with pytest.raises(ValueError, match="binding changed"):
        score.main()
    assert not (tmp_path / "mixture-geometry-distances.json").exists()
