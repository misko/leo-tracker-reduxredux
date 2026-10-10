import json
from types import SimpleNamespace

import batch
import pytest
import run


def fixture(monkeypatch, tmp_path):
    monkeypatch.setattr(run, "ROOT", tmp_path)
    monkeypatch.setattr(run, "HERE", tmp_path)
    plan = dict(
        members=[
            dict(label=f"m{i}", case_binding={}, parity_receipt="parity.json") for i in range(12)
        ],
        sources={},
        inputs={},
        optimizer_calls=0,
        arms=["fitted-c", "zero-c"],
        maximum_endpoint_evaluations_per_member=2,
        clean_protocol_sha256="clean",
    )
    (tmp_path / "protocol.json").write_text(json.dumps(plan))
    (tmp_path / "parity.json").write_text(
        json.dumps(dict(status="complete", label="m0", protocol_sha256="clean"))
    )
    for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.setenv(key, "1")
    monkeypatch.setattr(run.sys, "argv", ["run.py", "--label", "m0"])
    return plan


def test_actual_driver_preserves_support_and_refuses_repeat(monkeypatch, tmp_path):
    fixture(monkeypatch, tmp_path)
    events = []
    support = dict(rows=[dict(window_id="one", support_status="unavailable")])
    monkeypatch.setattr(run, "reconstruct", lambda *args: ("model", {"archive": "archive"}, {}))
    monkeypatch.setattr(run, "public_support", lambda *args: support)

    def audit(model, archive, received):
        events.append((model, archive, received))
        return dict(status="complete", optimizer_calls=0)

    monkeypatch.setattr(run, "audit", audit)
    run.main()
    result = json.loads((tmp_path / "results/m0.json").read_text())
    assert result["support"] == support
    assert events == [("model", "archive", support)]
    with pytest.raises(FileExistsError):
        run.main()
    assert len(events) == 1


def test_audit_failure_retains_support(monkeypatch, tmp_path):
    plan = fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(run, "reconstruct", lambda *args: (None, {"archive": {}}, {}))
    monkeypatch.setattr(run, "public_support", lambda *args: {"rows": ["all rows"]})

    def fail(*args):
        raise ValueError("endpoint mismatch")

    monkeypatch.setattr(run, "audit", fail)
    result = run.perform(plan, plan["members"][0])
    assert result["status"] == "failed"
    assert result["support"]["rows"] == ["all rows"]
    assert "endpoint mismatch" in result["error"]


@pytest.mark.parametrize("status,digest", [("failed", "clean"), ("complete", "foreign")])
def test_failed_or_foreign_prerequisite_never_reconstructs(monkeypatch, tmp_path, status, digest):
    plan = fixture(monkeypatch, tmp_path)
    (tmp_path / "parity.json").write_text(
        json.dumps(dict(status=status, label="m0", protocol_sha256=digest))
    )
    monkeypatch.setattr(run, "reconstruct", lambda *args: pytest.fail("must not reconstruct"))
    assert run.perform(plan, plan["members"][0])["status"] == "failed"


def test_changed_source_prevents_claim(monkeypatch, tmp_path):
    plan = fixture(monkeypatch, tmp_path)
    (tmp_path / "source").write_text("changed")
    plan["sources"] = {"source": "wrong"}
    (tmp_path / "protocol.json").write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="changed"):
        run.main()
    assert not (tmp_path / "results").exists()


def test_public_reload_identity_and_close_before_projection(monkeypatch):
    import leo.application.scanner_trajectory as trajectory
    import leo.storage.scanner_tracking_source as storage

    events = []

    class Store:
        def __init__(self, root):
            pass

        def load(self, session):
            return SimpleNamespace(
                session_id=session,
                input_manifest_sha256="changed",
                analysis_manifest_sha256="analysis",
            )

        def close(self):
            events.append("closed")

    monkeypatch.setattr(storage, "ScannerTrackingInputStore", Store)
    monkeypatch.setattr(
        trajectory, "project_scanner_candidates", lambda source: pytest.fail("no projection")
    )
    binding = dict(
        session_id="session",
        model_identity=dict(
            session_id="session", input_manifest_sha256="input", analysis_manifest_sha256="analysis"
        ),
        expected_input_binding={"observation_order_signature": "order"},
    )
    with pytest.raises(ValueError, match="identity changed"):
        run.public_support({}, binding)
    assert events == ["closed"]


def test_batch_stops_on_claimed_crash_and_keeps_failed_terminal(monkeypatch, tmp_path):
    fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(batch, "HERE", tmp_path)
    out = tmp_path / "results"
    out.mkdir()
    (out / "m0.json").write_text(
        json.dumps(
            dict(label="m0", status="failed", protocol_sha256=run.sha(tmp_path / "protocol.json"))
        )
    )
    (out / "m1.claim.json").write_text("{}")
    monkeypatch.setattr(batch.subprocess, "run", lambda *a, **k: pytest.fail("no retry"))
    with pytest.raises(ValueError, match="claimed"):
        batch.main()
