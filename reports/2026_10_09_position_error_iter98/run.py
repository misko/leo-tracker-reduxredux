"""Validate a qualified100 postfit using immutable97, then continue immutable95."""

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = HERE.parent / "2026_10_09_position_error_iter95"
QUALIFICATION = HERE.parent / "2026_10_09_position_error_iter97"
SOURCE = HERE.parent / "2026_10_09_position_error_iter100"
SPEC = importlib.util.spec_from_file_location("postfit97_for98", QUALIFICATION / "run.py")
qualification = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qualification)
continuation = qualification.continuation


def qualified_calibration(objective, verification, fitted):
    vector = np.asarray(fitted["vector"], dtype=float)
    assert np.isfinite(vector).all()
    prefit = verification["prefit"]
    assert np.array_equal(vector[:2], np.asarray(prefit["vector"])[:2])
    value, gradient, terms = objective.evaluate(vector)
    assert np.isfinite(value) and np.isfinite(gradient).all()
    np.testing.assert_allclose(value, fitted["objective"], atol=1e-6, rtol=0)
    problem = continuation._Problem(
        objective, vector, fixed_position=True, rf_arm="fitted-c", slope_half_width_hz_s=60
    )
    stationarity = problem.stationarity(vector, gradient)
    assert fitted["converged"] and problem.feasible(vector) and stationarity <= 0.001
    np.testing.assert_allclose(stationarity, fitted["stationarity"], atol=1e-8, rtol=0)
    mass = float(terms.responsibilities.sum())
    fit = continuation.PositionFit(
        vector=vector.copy(),
        objective=float(value),
        posterior_rms_hz=float(
            np.sqrt(np.sum(terms.responsibilities * terms.residual_hz**2) / mass)
        )
        if mass
        else None,
        signal_windows=mass,
        stationarity=stationarity,
        converged=True,
        boundary=False,
        stop_reason="qualified-saved-postfit100",
        evaluations=int(fitted["evaluations"]),
        elapsed_s=0.0,
    )
    correction = verification["correction"]
    baseline = np.asarray(correction["values_hz"]) + objective.design[:, :4] @ vector[2:6]
    return dict(
        satellite_indices=verification["satellite_indices"],
        prefit=prefit,
        postfit=continuation.json_value(fit),
        correction=correction,
        receiver_baseline_hz=baseline.tolist(),
    )


def main():
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    digest = hashlib.sha256(protocol.read_bytes()).hexdigest()
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    if (HERE / "result.json").exists():
        assert continuation.read(HERE / "result.json")["protocol_sha256"] == digest
        return
    source = continuation.read(SOURCE / "result.json")
    assert (
        source["protocol_sha256"]
        == hashlib.sha256((SOURCE / "protocol.json").read_bytes()).hexdigest()
    )
    assert source["status"] == "complete" and source["fit"]["converged"]
    objective, _, verification = qualification.reconstruct()
    calibration = qualified_calibration(objective, verification, source["fit"])
    key = "recovered-calibration"
    path = HERE / "stages" / f"{continuation.canonical_digest(dict(key=key))[7:]}.json"
    value = dict(
        result=dict(
            calibration=calibration,
            postfit=calibration["postfit"],
            diagnostics={
                "source": "qualified100 reconstructed through97; no new calibration fit",
                "source_result_sha256": hashlib.sha256(
                    (SOURCE / "result.json").read_bytes()
                ).hexdigest(),
            },
        ),
        reason=None,
    )
    receipt = dict(protocol_sha256=digest, key=key, value=value)
    if path.exists():
        assert continuation.read(path) == receipt
    else:
        continuation.write(path, receipt)
    original_here = continuation.HERE
    try:
        continuation.HERE = HERE
        continuation.main()
    finally:
        continuation.HERE = original_here


if __name__ == "__main__":
    main()
