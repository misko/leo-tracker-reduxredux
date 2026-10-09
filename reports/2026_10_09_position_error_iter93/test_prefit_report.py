"""Synthetic reporting preserves audit failures and immutable fit receipts."""

import hashlib
import json

import report_prefit


def test_failed_instrumentation_is_retained_with_returned_fit(tmp_path, monkeypatch):
    monkeypatch.setattr(report_prefit, "HERE", tmp_path)
    monkeypatch.setattr(report_prefit, "ROOT", tmp_path)
    plan = dict(
        starts=["ordinary-coarse", "zero-timing"],
        solvers=["legacy", "bounded"],
        source_sha256={},
        stationarity_threshold=0.001,
    )
    raw = json.dumps(plan).encode()
    (tmp_path / "prefit-protocol.json").write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    inputs = dict(protocol_sha256=digest, original_objective=10, reconstructed_objective=10)
    (tmp_path / "prefit-input-verification.json").write_text(json.dumps(inputs))
    (tmp_path / "prefit-attempts").mkdir()
    original = {}
    for start in plan["starts"]:
        for solver in plan["solvers"]:
            fit = dict(
                vector=[1, 2],
                objective=11,
                stationarity=0.0005,
                converged=True,
                evaluations=1,
                elapsed_s=0.1,
                posterior_rms_hz=2,
                signal_windows=3,
            )
            row = dict(
                protocol_sha256=digest,
                start=start,
                solver=solver,
                initial_vector=[1, 2],
                status="failed" if solver == "bounded" else "complete",
                fit=fit,
            )
            path = tmp_path / "prefit-attempts" / f"{start}-{solver}.json"
            path.write_text(json.dumps(row))
            original[path] = path.read_bytes()
    report_prefit.main()
    assert all(path.read_bytes() == before for path, before in original.items())
    verified = json.loads((tmp_path / "prefit-report-verification.json").read_text())
    assert verified["driver_statuses"] == dict(complete=2, failed=2)
    assert verified["numerical_returns"] == 4
    assert (
        "terminal finite-difference audits are missing"
        in (tmp_path / "PREFIT_RESULTS.md").read_text()
    )
    assert (tmp_path / "prefit-comparison.png").read_bytes().startswith(b"\x89PNG")
