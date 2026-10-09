"""Direct qualified prefit102 -> fresh correction/postfit -> immutable95 continuation."""

import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = HERE.parent / "2026_10_09_position_error_iter95"
SOURCE = HERE.parent / "2026_10_09_position_error_iter102"
sys.path.insert(0, str(OLD))
import continue_region as continuation  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "direct_qualification102_for103", SOURCE / "qualification.py"
)
qualification = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qualification)


def validated_postfit(objective, saved, point):
    vector = np.asarray(saved["vector"], float)
    np.testing.assert_array_equal(vector[:2], point)
    value, gradient, terms = objective.evaluate(vector)
    assert np.isfinite(value) and np.isfinite(gradient).all()
    np.testing.assert_allclose(value, saved["objective"], rtol=0, atol=1e-6)
    problem = continuation._Problem(
        objective, vector, fixed_position=True, rf_arm="fitted-c", slope_half_width_hz_s=60
    )
    stationarity = problem.stationarity(vector, gradient)
    assert saved["converged"] and problem.feasible(vector) and stationarity <= 0.001
    mass = float(terms.responsibilities.sum())
    return continuation.PositionFit(
        vector.copy(),
        float(value),
        float(np.sqrt(np.sum(terms.responsibilities * terms.residual_hz**2) / mass))
        if mass
        else None,
        mass,
        stationarity,
        True,
        False,
        "direct-chain-independent-qualified",
        int(saved["evaluations"]),
        float(saved.get("elapsed_s", 0.0)),
    )


def fresh_calibration(observations, base, prior, indices, prefit):
    """No97 reconstruction and no96 clock/correction state; correction is fresh."""
    begun = time.monotonic()
    receipt = dict(
        correction=None,
        calibration=None,
        postfit=None,
        qualification=None,
    )
    try:
        correction = continuation.receiver_correction(observations, base.evaluate(prefit.vector)[2])
        receipt["correction"] = continuation.json_value(correction)
        corrected = continuation.Hard60Objective(
            observations,
            base.bank,
            prior,
            continuation.HARD60_SCORE,
            receiver_baseline_hz=correction.values_hz,
        )
        postfit_begun = time.monotonic()
        postfit, diagnostics = continuation.fit_bounded_position(
            corrected,
            prefit.vector.copy(),
            fixed_position=True,
            rf_arm="fitted-c",
            slope_half_width_hz_s=60,
            maximum_seconds=20,
            maximum_iterations=600,
        )
        receipt["bounded_postfit_elapsed_s"] = time.monotonic() - postfit_begun
        if postfit is None:
            raise ValueError("Bounded postfit returned no saved state")
        receipt.update(
            postfit=continuation.json_value(postfit),
            diagnostics=continuation.json_value(diagnostics),
        )
        selected = receipt["postfit"]
        if not postfit.converged:
            attempt = qualification.qualify(
                corrected,
                postfit.vector,
                postfit.objective,
                retained=True,
                stage="calibration-postfit",
                independently_qualified=False,
                maximum_rounds=2,
                maximum_evaluations=100,
            )
            receipt["qualification"] = continuation.json_value(attempt)
            if not attempt["qualified"]:
                receipt["status"] = "calibration-unqualified"
                receipt["elapsed_s"] = time.monotonic() - begun
                return receipt
            selected = attempt["fit"]
        validated = validated_postfit(corrected, selected, prefit.vector[:2])
        baseline = correction.values_hz + corrected.design[:, :4] @ validated.vector[2:6]
        calibration = continuation.RegionalCalibration(
            tuple(indices), prefit, validated, correction, baseline
        )
        receipt.update(status="qualified", calibration=continuation.json_value(calibration))
    except (ValueError, TimeoutError, AssertionError) as error:
        receipt.update(status="calibration-failed", error=repr(error))
    receipt["elapsed_s"] = time.monotonic() - begun
    return receipt


def main():
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    digest = hashlib.sha256(protocol.read_bytes()).hexdigest()
    assert (
        plan["direct_postfit_polish_rounds"] == 2
        and plan["direct_postfit_polish_evaluations"] == 100
    )
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
    direct = source["attempts"]["calibration-prefit"]
    assert direct["qualified"] and direct["objective_verified"]
    document = continuation.read(continuation.PARENT / "published-v3.json")["manifest"]["document"]
    checkpoint = continuation.read(continuation.PARENT / "verified-checkpoints.json")
    observations, bank, prior, base, indices = continuation.load_case(document, checkpoint)
    point = np.array(
        [checkpoint["selected_basin"]["east_km"], checkpoint["selected_basin"]["north_km"]]
    )
    # The frozen inventory contains only the directly qualified102 prefit.
    prefit, selection = continuation.select_prefit(plan, base, point)
    np.testing.assert_array_equal(prefit.vector, direct["fit"]["vector"])
    record_path = HERE / "fresh-calibration.json"
    if record_path.exists():
        saved = continuation.read(record_path)
        assert saved["protocol_sha256"] == digest
        attempt = saved["attempt"]
    else:
        attempt = fresh_calibration(observations, base, prior, indices, prefit)
        continuation.write(
            record_path, dict(protocol_sha256=digest, prefit_selection=selection, attempt=attempt)
        )
    if attempt["calibration"] is None:
        continuation.write(
            HERE / "result.json",
            dict(
                protocol_sha256=digest,
                status=attempt["status"],
                prefit_selection=selection,
                calibration=attempt,
            ),
        )
        return
    key = "recovered-calibration"
    stage_path = HERE / "stages" / f"{continuation.canonical_digest(dict(key=key))[7:]}.json"
    value = dict(
        result=dict(
            calibration=attempt["calibration"],
            postfit=attempt["calibration"]["postfit"],
            diagnostics={"source": "direct102 prefit; fresh103 correction/postfit"},
        ),
        reason=None,
    )
    stage = dict(protocol_sha256=digest, key=key, value=value)
    if stage_path.exists():
        assert continuation.read(stage_path) == stage
    else:
        continuation.write(stage_path, stage)
    old_here = continuation.HERE
    try:
        continuation.HERE = HERE
        continuation.main()
    finally:
        continuation.HERE = old_here


if __name__ == "__main__":
    main()
