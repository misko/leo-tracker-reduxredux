import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))
import ds7_streaming_residual_audit as audit  # noqa: E402


def test_boundary_control_retained_without_blocking_all88(monkeypatch, tmp_path):
    request_path, joint_path, index_path = [
        tmp_path / n for n in ("request.json", "response.json", "index.json")
    ]
    rows = [{"session_id": f"s{i}", "artifacts": []} for i in range(88)]
    request_path.write_text(
        json.dumps({"inputs": rows, "unit": {"unit_id": "full88"}, "config": {}})
    )
    joint_path.write_text("{}")
    index_path.write_text(
        json.dumps(
            {
                "responses": [
                    {
                        "session_id": f"s{i}",
                        "response_path": f"single-{i + 1:03}",
                        "response_sha256": "hash",
                    }
                    for i in range(88)
                ]
            }
        )
    )

    def sealed(path, unit, sessions):
        return {
            "status": "ok",
            "converged": True,
            "boundary_hit": unit == "single-062",
            "unit": unit,
        }, {}

    def parameters(response):
        assert response["boundary_hit"] is False
        return np.zeros(90 if response["unit"] == "full88" else 3)

    calls = []

    def documents(request):
        assert len(request["inputs"]) == 1
        calls.append(request["inputs"][0]["session_id"])
        return [{"tracks": [{"times_s": [0, 1]}], "eligibility_exclusions": []}]

    track = {
        "training_observations": 2,
        "held_observations": 1,
        "training_log_score": -4.0,
        "held_predictive_log_density": -2.0,
        "training_rms_hz": 3.0,
        "held_rms_hz": 4.0,
    }
    monkeypatch.setattr(audit.original, "load_sealed_response", sealed)
    monkeypatch.setattr(audit.original, "response_x", parameters)
    monkeypatch.setattr(audit.original, "digest", lambda p: "hash")
    monkeypatch.setattr(audit.original.solver, "load_documents", documents)
    monkeypatch.setattr(audit.original.solver, "Stationary", lambda d, c: None)
    monkeypatch.setattr(audit.original, "audit_track", lambda *a: dict(track))
    summary = audit.run(request_path, joint_path, index_path, tmp_path / "result")
    assert summary["joint_recordings"] == 88
    assert summary["paired_qualified_recordings"] == 87
    assert calls == [f"s{i}" for i in range(88)]
    boundary = summary["recordings"][61]
    assert boundary["independent"] is None and boundary["joint_minus_independent_held"] is None
    assert boundary["joint"]["tracks"] == 1
    assert boundary["independent_status"]["boundary_hit"] is True


def test_totals_weight_rms_by_observations():
    rows = [
        {
            "training_observations": n,
            "held_observations": n,
            "training_log_score": -n,
            "held_predictive_log_density": -n,
            "training_rms_hz": rms,
            "held_rms_hz": rms,
        }
        for n, rms in [(1, 2), (3, 4)]
    ]
    result = audit.totals(rows)
    assert result["held_observations"] == 4
    assert result["held_rms_hz"] == pytest.approx(np.sqrt(13))
