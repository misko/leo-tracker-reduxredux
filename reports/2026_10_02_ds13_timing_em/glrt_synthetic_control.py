"""Matched-model geometry sanity control; not evidence of real-data accuracy."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from finite_set_fit import array_digest, assert_snapshot_unchanged, snapshot_files
from finite_set_likelihood import circular_residual, prepare_finite_set_likelihood
from glrt_width_information import WidthObjective
from joint_inputs import _coordinates, _ecef
from oracle_position_diagnostic import reference_coordinates
from prepare_scans import ROOT, load_scan
from rf_calibration_diagnostic import CalibratedLikelihood, rf_features
from rough_smoke import serializable
from timing_model import TimingObjective
from truth_start_diagnostic import optimize


class SyntheticData:
    def __init__(self, source, measured):
        self.source = source
        self.measured = np.asarray(measured).copy()

    def __getattr__(self, name):
        return getattr(self.source, name)


def simulate_peaks(prepared, prediction, association, *, seed, sigma_hz=100.):
    generator = np.random.default_rng(seed)
    measured = np.empty(prepared.row_count)
    injected = []
    for unique_index, rows in enumerate(prepared.clusters):
        satellite = int(np.argmax(association[unique_index]))
        signal = association[unique_index, satellite] >= .8
        if signal:
            value = prediction[rows[0], satellite] + generator.normal(0., sigma_hz)
        else:
            value = generator.uniform(-prepared.alias_hz / 2, prepared.alias_hz / 2)
        measured[rows] = circular_residual(value, alias_hz=prepared.alias_hz)
        if signal:
            injected.append({"peak_index": unique_index, "satellite_column": satellite})
    return measured, injected


def run_case(cell):
    session, random_seed = cell
    output = ROOT / "glrt-synthetic-control" / f"{session}-{random_seed}.json"
    if output.exists():
        raise FileExistsError(output)
    parent_path = ROOT / "rf-calibration-diagnostic" / f"{session}-common.json"
    reference_path = ROOT / "scans" / session / "evaluation.json"
    seed_path = ROOT / "scans" / session / "seed.json"
    parent = json.loads(parent_path.read_text())
    seed = json.loads(seed_path.read_text())
    hashes = {**parent["source_hashes"], **snapshot_files(
        [__file__, ROOT / "glrt_width_information.py", ROOT / "truth_start_diagnostic.py",
         parent_path, reference_path, seed_path])}
    assert_snapshot_unchanged(hashes)
    _, data = load_scan(session)
    satellites = np.asarray(seed["satellites"], dtype=int)
    parameters = np.asarray(parent["fit"]["parameters"])
    prepared = prepare_finite_set_likelihood(data.measured, data.group)
    _, features = rf_features(data.rf, data.receiver, False)
    likelihood = CalibratedLikelihood(prepared, .8 / len(satellites), features)
    coefficients = np.asarray(parent["fit"]["rf_coefficient_hz_per_ghz"])
    likelihood.coefficients = coefficients.copy()
    model = TimingObjective(data, parameters, satellites, likelihood, 200.)
    model.evaluate(model.initial_vector)
    associations = likelihood.last_result["association_probability"].copy()
    reference = json.loads(reference_path.read_text())["reference_site"]
    true_position = reference_coordinates(reference["latitude_deg"], reference["longitude_deg"])
    truth_vector = model.initial_vector
    truth_vector[:2] = true_position
    prediction, _ = model.predict(truth_vector)
    prediction += (features @ coefficients)[:, None]
    measured, injected = simulate_peaks(prepared, prediction, associations, seed=random_seed)
    synthetic = SyntheticData(data, measured)
    fitted_parameters = parameters.copy()
    fitted_coefficients = coefficients.copy()
    stages = []
    for width, budget in ((400., 15.), (100., 30.)):
        objective = WidthObjective(synthetic, fitted_parameters, satellites, width)
        vector = objective.initial.copy()
        vector[-1] = fitted_coefficients[0]
        fitted = optimize(objective, vector, objective.bounds, budget_s=budget)
        fitted_parameters = objective.base.state(fitted["vector"][:objective.size])["parameters"]
        fitted_coefficients = fitted["vector"][objective.size:]
        stages.append({"sigma_hz": width, "fit": fitted})
    actual = _ecef(*_coordinates(fitted_parameters[:2]))
    truth = _ecef(reference["latitude_deg"], reference["longitude_deg"])
    result = {"schema": "ds13-glrt-synthetic-control/v1", "session": session,
              "random_seed": random_seed, "source_hashes": hashes,
              "synthetic_measured_sha256": array_digest(measured),
              "noise_sigma_hz": 100., "injected_signal_peaks": len(injected),
              "clutter_peaks": prepared.unique_peak_count - len(injected),
              "initial_position_km": parameters[:2], "true_position_km": true_position,
              "final_parameters": fitted_parameters, "stages": stages,
              "final_error_km": float(np.linalg.norm(actual - truth)),
              "success": stages[-1]["fit"]["success"], "reference_used_for_generation": True,
              "scope": "Synthetic positive control only. Same observation times, RF channels, "
                       "receivers, bank and per-group peak counts; confident fitted associations "
                       "define signal slots. Replace every frequency with a model-consistent "
                       "signal at known position plus Gaussian noise, or uniform clutter. "
                       "Preserve exact duplicate clusters. Nuisance initialization equals "
                       "generating values; position starts from the displaced real-data fit. "
                       "Cannot establish recoverable real-data accuracy or realistic uncertainty."}
    assert_snapshot_unchanged(hashes)
    output.parent.mkdir(exist_ok=True)
    with output.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {"session": session, "random_seed": random_seed, "error_km": result["final_error_km"],
            "success": result["success"], "signal_peaks": len(injected)}


if __name__ == "__main__":
    sessions = json.loads((ROOT / "protocol-soft.json").read_text())["sessions"]
    with ProcessPoolExecutor(max_workers=2) as executor:
        for row in executor.map(run_case, [(session, seed) for seed in (101, 202)
                                          for session in sessions]):
            print(json.dumps(row), flush=True)
