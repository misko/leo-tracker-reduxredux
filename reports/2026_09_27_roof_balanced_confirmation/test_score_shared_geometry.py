import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import score_shared_geometry as subject


SESSIONS = ("s0", "s1", "s2", "s3")
PRIORS = {"sacramento": (1., 2., 3.), "reno": (4., 5., 6.)}
CODE_FILES = ("run_shared_geometry_replay.py", "shared_effect_evaluator.py",
              "detection_random_intercept_refined.py", "mixture_geometry_models.py",
              "paired_reception_evaluator.py", "run_consistent_replay.py")


def digest(payload):
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value))
    return digest(path.read_bytes())


def setup_fake(monkeypatch, tmp_path, *, corrupt=False):
    entries = [{"session_id": sid, "cache_sha256": f"cache-{sid}",
                "input_manifest_sha256": f"input-{sid}",
                "analysis_manifest_sha256": f"analysis-{sid}"} for sid in SESSIONS]
    monkeypatch.setattr(subject, "HERE", tmp_path)
    monkeypatch.setattr(subject.runner.balanced, "inputs", lambda: (entries, {}))
    monkeypatch.setattr(subject.runner.base, "PRIORS", PRIORS)
    monkeypatch.setattr(subject.runner.base, "digest", digest)
    monkeypatch.setattr(subject.runner.base, "atomic",
                        lambda path, value: path.write_text(json.dumps(value)))
    bundle = SimpleNamespace(calibration_sha256="cal", calibration_sessions=("c",),
                             source_hashes={"source": "hash"}, artifact_sha256={"a": "b"})
    monkeypatch.setattr(subject.runner.mixture_geometry_models,
                        "load_geometry_bundle", lambda: bundle)
    random_binding = {"aggregate_sha256": "random", "advancement_checks": {"x": True}}
    monkeypatch.setattr(subject.runner, "random_effect_binding",
                        lambda: (random_binding, 2.5))
    for name in CODE_FILES + ("score_shared_geometry.py", "shared_geometry_reporting.py",
                              "score_consistent_replay.py"):
        (tmp_path / name).write_text(name)
    contract_sha = write(tmp_path / "contract.json", {"contract": 1})
    protocol_sha = write(tmp_path / "SHARED_GEOMETRY_PROTOCOL.md", {"protocol": 1})
    grid_report_sha = write(tmp_path / "local-grid-distances.json", {"complete": True})
    audit_sha = write(tmp_path / "audit_source_topology.json", {"sessions": []})
    source_report = {"complete": True, "replay_sha256": {}}
    sources = {}; grids = {}
    for sid in SESSIONS:
        grid = {"finished": True, "session_id": sid, "deduplicate_reception": False,
                "branches": {prior: {"grid": prior} for prior in PRIORS}}
        grid_sha = write(tmp_path / f"local-grid-{sid}.json", grid); grids[sid] = grid
        source = {"finished": True, "session_id": sid, "source_grid_sha256": grid_sha,
                  "evidence_sha256": f"evidence-{sid}", "snapshot_digest": f"snap-{sid}",
                  "topology_receipt": {"sid": sid}, "parameters": {"p": 1},
                  "model_hashes": {"m": 1},
                  "branches": {prior: {"origin": list(PRIORS[prior][:2])} for prior in PRIORS}}
        source_sha = write(tmp_path / f"mixture-geometry-replay-{sid}.json", source)
        sources[sid] = source; source_report["replay_sha256"][sid] = source_sha
    source_report_sha = write(tmp_path / "mixture-geometry-distances.json", source_report)
    common = {"contract_sha256": contract_sha,
              "shared_geometry_protocol_sha256": protocol_sha,
              "random_effect_binding": random_binding,
              "calibration_sha256": "cal", "calibration_sessions": ["c"],
              "calibration_source_hashes": {"source": "hash"},
              "calibration_artifact_sha256": {"a": "b"},
              "source_replay_report_sha256": source_report_sha,
              "source_grid_report_sha256": grid_report_sha,
              "topology_audit_sha256": audit_sha}
    code = {name: digest((tmp_path / name).read_bytes()) for name in CODE_FILES}
    for number, entry in enumerate(entries):
        sid = entry["session_id"]; source = sources[sid]
        result = {**common, **entry, "session_id": sid, "finished": True,
                  "source_replay_sha256": source_report["replay_sha256"][sid],
                  "source_grid_sha256": source["source_grid_sha256"],
                  "evidence_sha256": source["evidence_sha256"],
                  "snapshot_digest": source["snapshot_digest"],
                  "topology_receipt": source["topology_receipt"],
                  "parameters": source["parameters"], "model_hashes": source["model_hashes"],
                  "code_sha256": code,
                  "branches": {prior: {"origin": list(PRIORS[prior][:2]),
                                        "parity": {"sid": sid, "prior": prior},
                                        "point_components": [], "selected": {}}
                               for prior in PRIORS}}
        if corrupt and number == 0:
            result["calibration_sha256"] = "changed"
        write(tmp_path / f"shared-geometry-replay-{sid}.json", result)
    manifest = {"sessions": [{"pose": {"session_id": sid,
                 "pose_authority": {"latitude_deg": 10., "longitude_deg": 20.}}}
                for sid in SESSIONS]}
    write(tmp_path / "manifest.json", manifest)
    monkeypatch.setattr(subject.reporting, "validate_branch",
                        lambda _saved, result: {"selected": result.get("selected", {})})
    monkeypatch.setattr(subject.runner, "parity_report",
                        lambda _source, _rows: {"sid": _source.get("sid", None)} )
    # Keep producer parity equality deterministic without exercising already-tested branch math.
    for sid in SESSIONS:
        path = tmp_path / f"shared-geometry-replay-{sid}.json"
        value = json.loads(path.read_text())
        for prior in PRIORS:
            value["branches"][prior]["parity"] = {"sid": None}
        path.write_text(json.dumps(value))
    monkeypatch.setattr(subject.reporting, "distance_row",
                        lambda sid, prior, _saved, _valid, _ref: {
                            "session_id": sid, "prior": prior,
                            "errors_km": {"D": 1., "old": 1., "mixture": 1., "shared": 1.}})
    monkeypatch.setattr(subject.reporting, "summarize",
                        lambda rows, sessions: {"rows": len(rows), "sessions": len(sessions)})


def test_complete_fake_cohort_writes_eight_case_report(monkeypatch, tmp_path):
    setup_fake(monkeypatch, tmp_path)
    subject.main()
    output = json.loads((tmp_path / "shared-geometry-distances.json").read_text())
    assert output["complete"] is True
    assert len(output["rows"]) == 8
    assert output["summary"] == {"rows": 8, "sessions": 4}
    assert set(output["replay_sha256"]) == set(SESSIONS)


def test_binding_failure_occurs_before_reference_is_opened(monkeypatch, tmp_path):
    setup_fake(monkeypatch, tmp_path, corrupt=True)
    original = Path.read_bytes; opened = []
    def guarded(path):
        if path.name == "manifest.json":
            opened.append(path)
            raise AssertionError("reference opened before binding gate")
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", guarded)
    with pytest.raises(ValueError, match="binding changed"):
        subject.main()
    assert opened == []
