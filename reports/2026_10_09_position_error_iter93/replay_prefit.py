"""Four bounded-budget fixed-position diagnostics from an ordinary failed region."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.optimize import nnls

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.hard60_bounded_fit import _Problem, fit_bounded_position
from leo.analysis.hard60_score import Hard60Objective
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_fit import fit_position
from leo.application.hard60_runner import HARD60_SCORE
from leo.application.regional_position_inputs import prepare_position_windows
from leo.application.regional_position_runner import json_value
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(json_value(value), stream, indent=2, allow_nan=False)
        stream.write("\n")


def gradient_audit(objective, vector):
    """Identify the largest scaled KKT residual and check feasible small steps."""
    vector = np.asarray(vector, float)
    problem = _Problem(objective, vector, fixed_position=True, slope_half_width_hz_s=60)
    value, gradient, _ = objective.evaluate(vector)
    free, scales = problem.free, problem.scales
    derivative = (gradient * scales)[free]
    jacobian = (problem.jacobian(vector) * scales)[:, free]
    normals = list(jacobian[problem.constraints(vector) <= 1e-6])
    z = (vector / scales)[free]
    low, high = (problem.lower / scales)[free], (problem.upper / scales)[free]
    eye = np.eye(len(free))
    for i in range(len(free)):
        if z[i] <= low[i] + 1e-7:
            normals.append(eye[i])
        if z[i] >= high[i] - 1e-7:
            normals.append(-eye[i])
    projected = derivative.copy()
    if normals:
        active = np.asarray(normals).T
        multipliers, _ = nnls(active, derivative, maxiter=100 * active.shape[1])
        projected -= active @ multipliers
    winner = int(np.argmax(abs(projected)))
    coordinate = int(free[winner])
    checks = []
    for step in (1e-4, 1e-5, 1e-6):
        minus, plus = vector.copy(), vector.copy()
        minus[coordinate] -= step * scales[coordinate]
        plus[coordinate] += step * scales[coordinate]
        feasible_minus, feasible_plus = problem.feasible(minus), problem.feasible(plus)
        if feasible_minus and feasible_plus:
            difference = (objective.evaluate(plus)[0] - objective.evaluate(minus)[0]) / (2 * step)
            method = "central"
        elif feasible_plus:
            difference = (objective.evaluate(plus)[0] - value) / step
            method = "forward"
        elif feasible_minus:
            difference = (value - objective.evaluate(minus)[0]) / step
            method = "backward"
        else:
            difference, method = None, "no-feasible-coordinate-step"
        checks.append(dict(scaled_step=step, derivative=difference, method=method))
    names = {
        2: "RX0 intercept",
        3: "RX0 slope",
        4: "RX1 intercept",
        5: "RX1 slope",
        6: "RF coefficient c",
        7: "common timing",
    }
    return dict(
        objective=float(value),
        stationarity=float(np.max(abs(projected))),
        coordinate=coordinate,
        coordinate_name=names.get(coordinate, f"relative timing basis {coordinate - 8}"),
        scaled_raw_gradient=float(derivative[winner]),
        scaled_projected_gradient=float(projected[winner]),
        physical_scale=float(scales[coordinate]),
        active_normals=len(normals),
        feasible=problem.feasible(vector),
        finite_difference_checks=checks,
        caution="Finite differences check raw gradient; KKT projection reported separately",
    )


def reconstruct(document, checkpoint):
    inputs = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        source = inputs.load(document["session_id"])
    finally:
        inputs.close()
    for field in ("input_manifest_sha256", "analysis_manifest_sha256"):
        assert getattr(source, field) == document[field], field
    prepared = prepare_position_windows(source)
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(prepared.start_utc_ns - 505_000_000_000)
    assert snapshot.digest == document["diagnostics"]["snapshot_sha256"]
    assert snapshot.collected_utc_ns == document["diagnostics"]["snapshot_collected_utc_ns"]
    payload, exclusions = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    indices = np.array(
        [i for i, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")]
    )
    evidence = canonical_digest(
        dict(
            windows=prepared.evidence_sha256,
            tle=snapshot.digest,
            candidates=[int(catalogue.satellite_numbers[i]) for i in indices],
        )
    )
    assert evidence == document["evidence_sha256"]
    prior = RegionalPrior(**document["configuration"]["prior"])
    bank, receipt = build_regional_bank(
        catalogue,
        indices,
        prepared.start_utc_ns,
        prepared.observations,
        prior,
        maximum_seconds=180,
    )
    assert bank.numbers.tolist() == document["diagnostics"]["bank"]["retained_numbers"]
    original = checkpoint["checkpoints"]["b7-shared:" + checkpoint["point_key"]]["value"]["result"]
    objective = Hard60Objective(
        prepared.observations,
        bank.select(original["bootstrap"]["satellite_indices"]),
        prior,
        HARD60_SCORE,
    )
    fit = original["fits"]["V16"]["fit"]
    seed = np.asarray(fit["vector"])
    reconstructed = float(objective.evaluate(seed)[0])
    np.testing.assert_allclose(reconstructed, fit["objective"], atol=1e-6, rtol=0)
    return (
        objective,
        seed,
        dict(
            evidence_sha256=evidence,
            snapshot_sha256=snapshot.digest,
            bank=receipt,
            exclusions=exclusions,
            reconstructed_objective=reconstructed,
            original_objective=fit["objective"],
            original_stationarity=fit["stationarity"],
        ),
    )


def main():
    protocol_path = HERE / "prefit-protocol.json"
    plan = json.loads(protocol_path.read_text())
    assert plan["starts"] == ["ordinary-coarse", "zero-timing"]
    assert plan["solvers"] == ["legacy", "bounded"]
    assert plan["maximum_fits"] == 4 and plan["fixed_position"] is True
    assert plan["maximum_seconds"] == 20 and plan["maximum_iterations"] == 600
    assert plan["maximum_bank_seconds"] == 180
    assert plan["slope_half_width_hz_s"] == 60 and plan["stationarity_threshold"] == 0.001
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    digest = hashlib.sha256(protocol_path.read_bytes()).hexdigest()
    document = json.loads((HERE / "published-v3.json").read_text())["manifest"]["document"]
    checkpoint = json.loads((HERE / "verified-checkpoints.json").read_text())
    for row in checkpoint["checkpoints"].values():
        assert canonical_digest(row["value"]) == row["value_sha256"]
    objective, seed, receipt = reconstruct(document, checkpoint)
    path = HERE / "prefit-input-verification.json"
    if not path.exists():
        write(path, dict(protocol_sha256=digest, **receipt))
    else:
        assert json.loads(path.read_text())["protocol_sha256"] == digest
    for name in ("ordinary-coarse", "zero-timing"):
        start = seed.copy()
        if name == "zero-timing":
            start[7:] = 0
        for solver in ("legacy", "bounded"):
            path = HERE / "prefit-attempts" / f"{name}-{solver}.json"
            if path.exists():
                assert json.loads(path.read_text())["protocol_sha256"] == digest
                continue
            record = dict(protocol_sha256=digest, start=name, solver=solver, initial_vector=start)
            options = dict(
                rf_arm="fitted-c",
                fixed_position=True,
                slope_half_width_hz_s=60,
                maximum_seconds=20,
                maximum_iterations=600,
            )
            try:
                if solver == "legacy":
                    diagnostics = {}
                    fitted = fit_position(
                        objective, start.copy(), diagnostics=diagnostics, **options
                    )
                else:
                    fitted, diagnostics = fit_bounded_position(objective, start.copy(), **options)
                record.update(status="complete", fit=fitted, diagnostics=diagnostics)
                record["gradient_audits"] = dict(returned=gradient_audit(objective, fitted.vector))
                terminal = diagnostics.get("terminal")
                if terminal and terminal.get("vector") is not None:
                    record["gradient_audits"]["terminal"] = gradient_audit(
                        objective, terminal["vector"]
                    )
            except Exception as error:
                record.update(status="failed", error=repr(error))
            write(path, record)
            print(name, solver, record["status"], flush=True)


if __name__ == "__main__":
    main()
