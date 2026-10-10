import json

import pytest

from report_downstream import load_records, summarize


def operation():
    return dict(
        fit=dict(converged=True, objective=20.0, posterior_rms_hz=100.0, stationarity=0.0001)
    )


def test_evaluation_gate_and_full_failures_no_fallback():
    failed_region = dict(recovery=dict(result=None, reason="calibration rejected"), finals=[])
    records = dict(
        native=dict(
            status="complete",
            regions={"retained-0": failed_region},
            operational={"fitted-c": operation()},
        ),
        fixed=dict(status="missing"),
    )
    with pytest.raises(ValueError, match="both sealed"):
        summarize(records, evaluate=lambda *args: pytest.fail("reference accessed"))
    result = summarize(records)
    assert not result["both_terminal"]
    assert result["branches"]["native"]["regions"][0]["failure_reason"] == "calibration rejected"
    assert result["branches"]["native"]["arms"]["zero-c"]["status"] == "no-selected-endpoint"
    records["fixed"] = dict(status="failed", reason="explicit failure", operational={})
    seen = []
    result = summarize(records, evaluate=lambda *args: seen.append(args[:2]) or dict(error_km=1.0))
    assert seen == [("native", "fitted-c")]
    assert result["both_terminal"] and not result["comparison_complete"]
    assert result["branches"]["fixed"]["arms"]["fitted-c"]["status"] == "no-selected-endpoint"


def test_loader_rejects_foreign_or_fallback_receipts(tmp_path):
    folder = tmp_path / "native"
    folder.mkdir()
    path = folder / "result.json"
    row = dict(
        status="complete", branch="native", protocol_sha256="bound", fallback_available=False
    )
    path.write_text(json.dumps(row))
    records, hashes = load_records(tmp_path, "bound")
    assert records["fixed"]["status"] == "missing" and len(hashes) == 1
    row["fallback_available"] = True
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="fallback"):
        load_records(tmp_path, "bound")


def test_public_reference_callback_rejects_unsealed_before_any_read(monkeypatch):
    import publish_downstream

    monkeypatch.setattr(publish_downstream, "sha", lambda path: pytest.fail("authority read"))
    records = dict(native=dict(status="complete"), fixed=dict(status="missing"))
    with pytest.raises(ValueError, match="must seal"):
        publish_downstream.evaluation_callback({}, records)
