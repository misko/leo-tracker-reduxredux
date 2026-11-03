"""All-peak RF-calibrated width sweep; no location reference enters fitting."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, snapshot_files
from prepare_scans import ROOT, load_scan
from rf_calibration_diagnostic import CalibrationObjective
from rough_smoke import serializable
from soft_solvers import _fisher_system
from truth_start_diagnostic import optimize

WIDTHS = (400., 100., 50.)


class WidthObjective(CalibrationObjective):
    def __init__(self, data, initial, satellites, sigma_hz):
        if not np.isfinite(sigma_hz) or sigma_hz <= 0:
            raise ValueError("positive finite frequency width required")
        super().__init__(data, initial, satellites, False, 30.)
        self.base.sigma_hz = float(sigma_hz)

    def curvature(self, vector):
        base_vector = vector[:self.size]
        base_hessian, _ = _fisher_system(self.base, base_vector, self.base.last)
        _, _, jacobian = self.base.predict(base_vector, with_jacobian=True)
        weights = self.likelihood.last_result["row_association_probability"] / self.base.sigma_hz**2
        hessian = np.zeros((len(vector), len(vector)))
        hessian[:self.size, :self.size] = base_hessian
        for column in range(self.features.shape[1]):
            physical = jacobian.transpose_multiply(
                (weights * self.features[:, column, None]).ravel())
            cross = self.base.vector_gradient(physical, base_vector)
            hessian[:self.size, self.size + column] = cross
            hessian[self.size + column, :self.size] = cross
        hessian[self.size:, self.size:] = self.features.T @ (
            weights.sum(axis=1)[:, None] * self.features)
        return hessian


def run_case(cell):
    session, sigma_hz = cell
    output = ROOT / "glrt-width-information" / f"{session}-{int(sigma_hz)}.json"
    if output.exists():
        raise FileExistsError(output)
    parent_path = (ROOT / "glrt-width-information" / f"{session}-100.json" if sigma_hz == 50
                   else ROOT / "rf-calibration-diagnostic" / f"{session}-common.json")
    parent = json.loads(parent_path.read_text())
    seed_path = ROOT / "scans" / session / "seed.json"
    seed = json.loads(seed_path.read_text())
    hashes = {**parent["source_hashes"], **snapshot_files(
        [__file__, parent_path, seed_path, ROOT / "truth_start_diagnostic.py"])}
    assert_snapshot_unchanged(hashes)
    satellites = np.asarray(seed["satellites"], dtype=int)
    _, data = load_scan(session)
    parent_fit = parent["fit"]
    objective = WidthObjective(data, parent_fit["parameters"], satellites, sigma_hz)
    start = objective.initial.copy()
    start[-1] = parent_fit["rf_coefficient_hz_per_ghz"][0]
    fitted = optimize(objective, start, objective.bounds)
    state = objective.base.state(fitted["vector"][:objective.size])
    fitted.update(parameters=state["parameters"],
                  rf_coefficient_hz_per_ghz=fitted["vector"][objective.size:],
                  effective_ppm=fitted["vector"][objective.size:] / 1000.)
    objective.base.deadline = float("inf")
    value, _ = objective.evaluate(fitted["vector"])
    if not np.isclose(value, fitted["objective"], rtol=0, atol=1e-6):
        raise ValueError("sweep fit does not reproduce")
    posterior = objective.likelihood.last_result["row_association_probability"]
    record = {"schema": "ds13-glrt-width-information/v1", "session": session,
              "sigma_hz": sigma_hz, "fit": fitted, "source_hashes": hashes,
              "observations": len(data.times), "source_groups": len(np.unique(data.group)),
              "expected_signal_peaks": float(posterior.sum()),
              "confident_rows": int(np.sum(posterior.max(axis=1) >= .8)),
              "reference_read_in_fitter": False,
              "scope": "All stored alias-family representative GLRT peaks retained. Same "
                       "common RF coefficient and RX/time/orbit model; only Gaussian width "
                       "changes. 400/100 Hz start from previous 200 Hz fit; 50 Hz from 100 Hz. "
                       "Development comparison, not independent validation."}
    assert_snapshot_unchanged(hashes)
    output.parent.mkdir(exist_ok=True)
    with output.open("x") as stream:
        json.dump(serializable(record), stream, indent=2, allow_nan=False)
    return {"session": session, "sigma_hz": sigma_hz, "success": fitted["success"],
            "objective": fitted["objective"], "confident_rows": record["confident_rows"]}


if __name__ == "__main__":
    sessions = json.loads((ROOT / "protocol-soft.json").read_text())["sessions"]
    for width in WIDTHS:
        with ProcessPoolExecutor(max_workers=2) as executor:
            for row in executor.map(run_case, [(session, width) for session in sessions]):
                print(json.dumps(row), flush=True)
