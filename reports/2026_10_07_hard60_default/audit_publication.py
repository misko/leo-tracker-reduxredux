"""Reprice a selected production-policy result with the original Python oracle."""

import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import nnls

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_score import PositionObjective
from leo.application.hard60_runner import HARD60_SCORE
from leo.application.regional_position_inputs import prepare_position_windows
from leo.contracts.regional_position import RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets
from leo.storage.regional_position_v2 import Hard60Store
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore


def audit(objective, vector, gradient, arm, center, radius):
    size = len(vector)
    scales = np.r_[1.0, 1.0, 200.0, 2.0, 200.0, 2.0, 200.0, np.ones(size - 7)]
    free = np.arange(size) if arm == "fitted-c" else np.delete(np.arange(size), 6)
    lower, upper = np.full(size, -np.inf), np.full(size, np.inf)
    lower[:2], upper[:2] = -250, 250
    lower[[3, 5]], upper[[3, 5]] = -60, 60
    lower[6:8], upper[6:8] = [-5000, -10], [5000, 10]
    slacks = list((vector - lower)[free]) + list((upper - vector)[free])
    normals = []
    for index in free:
        for slack, sign in ((vector[index] - lower[index], 1), (upper[index] - vector[index], -1)):
            if slack / scales[index] <= 1e-7:
                normal = np.zeros(size)
                normal[index] = sign / scales[index]
                normals.append(normal)
    for origin, bound in ((np.zeros(2), 250), (np.asarray(center), radius)):
        delta = vector[:2] - origin
        slack = bound**2 - delta @ delta
        slacks.append(slack)
        if slack <= 1e-6:
            normal = np.zeros(size)
            normal[:2] = -2 * delta
            normals.append(normal)
    matrix = np.zeros((len(objective.bank.numbers), size))
    matrix[:, 7], matrix[:, 8:] = 1, objective.basis
    shifts = matrix @ vector
    lo = max(-20.0, objective.bank.nodes_s[0] - objective.observations.times_s.min())
    hi = min(20.0, objective.bank.nodes_s[-1] - objective.observations.times_s.max())
    slacks.extend(shifts - lo)
    slacks.extend(hi - shifts)
    normals.extend(matrix[shifts - lo <= 1e-6])
    normals.extend(-matrix[hi - shifts <= 1e-6])
    residual = (gradient * scales)[free]
    if normals:
        active = (np.asarray(normals) * scales)[:, free].T
        multipliers, _ = nnls(active, residual, maxiter=100 * active.shape[1])
        residual -= active @ multipliers
    stationarity = float(max(abs(residual)))
    assert min(slacks) >= -1e-6 and stationarity <= 0.001
    assert arm != "zero-c" or vector[6] == 0
    return stationarity


def main(product_root, session, destination):
    doc = Hard60Store(Path(product_root)).status(session).manifest.document
    inputs = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        prepared = prepare_position_windows(inputs.load(session))
    finally:
        inputs.close()
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(prepared.start_utc_ns - 505_000_000_000)
    assert snapshot.digest == doc.diagnostics["snapshot_sha256"]
    payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    indices = np.array(
        [i for i, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")]
    )
    bank, _ = build_regional_bank(
        catalogue,
        indices,
        prepared.start_utc_ns,
        prepared.observations,
        RegionalPrior(),
        maximum_seconds=180,
    )
    lookup = {int(number): i for i, number in enumerate(bank.numbers)}
    rows = []
    for arm in doc.methods[0].arms:
        selected = arm.selected
        assert selected and selected.converged
        fitted = next(
            row["fit"]
            for row in doc.diagnostics["final_starts"]
            if row["arm"] == arm.name
            and row["basin"] == selected.source_basin
            and row["fit"]
            and row["fit"]["converged"]
            and abs(row["fit"]["objective"] - selected.objective) < 1e-9
        )
        calibration = doc.diagnostics["calibrations"][selected.source_basin]
        objective = PositionObjective(
            prepared.observations,
            bank.select([lookup[number] for number in selected.satellites]),
            RegionalPrior(),
            HARD60_SCORE,
            receiver_baseline_hz=np.asarray(calibration["receiver_baseline_hz"]),
        )
        vector = np.asarray(fitted["vector"])
        value, gradient, terms = objective.evaluate(vector)
        np.testing.assert_allclose(value, fitted["objective"], rtol=0, atol=1e-6)
        basin = next(
            b
            for b in doc.diagnostics["retained_basins"]
            if f"point:{b['east_km']:g}:{b['north_km']:g}" == selected.source_basin
        )
        stationarity = audit(
            objective,
            vector,
            gradient,
            arm.name,
            [basin["east_km"], basin["north_km"]],
            max(25, basin["spacing_km"] / np.sqrt(2)),
        )
        mass = terms.responsibilities.sum()
        rms = float(np.sqrt(np.sum(terms.responsibilities * terms.residual_hz**2) / mass))
        np.testing.assert_allclose(rms, selected.posterior_rms_hz, rtol=0, atol=1e-6)
        rows.append(
            {
                "arm": arm.name,
                "original_oracle_objective_delta": value - selected.objective,
                "original_oracle_projected_kkt": stationarity,
                "position_error_m": selected.horizontal_error_m,
                "frequency_rms_hz": rms,
                "final_slopes_hz_s": vector[[3, 5]].tolist(),
                "calibration_slopes_hz_s": np.asarray(calibration["postfit"]["vector"])[
                    [3, 5]
                ].tolist(),
                "c_hz_per_ghz": selected.coefficient_hz_per_ghz,
            }
        )
    result = {"session_id": session, "configuration_sha256": doc.configuration_sha256, "arms": rows}
    Path(destination).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main(*sys.argv[1:])
