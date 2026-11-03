"""Account for every retained GLRT peak in the truth versus south-500m comparison."""

from __future__ import annotations

import csv
import json
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, snapshot_files
from finite_set_likelihood import circular_residual, prepare_finite_set_likelihood
from prepare_scans import ROOT, load_scan
from rf_calibration_diagnostic import CalibrationObjective
from rough_smoke import serializable
from wrong_solution_attribution import group_metadata, weighted_residual_summary


def integrate_prediction_path(prepared, truth, south, visible, probability, order=16):
    nodes, weights = np.polynomial.legendre.leggauss(order)
    difference = south - truth
    contribution = np.zeros_like(truth)
    for fraction, weight in zip((nodes + 1) / 2, weights / 2, strict=True):
        result = prepared.evaluate(truth + fraction * difference, visible,
                                   sigma_hz=200., detection_probability=probability,
                                   clutter_rate=2., implementation="batched", return_gradient=True)
        contribution += weight * result["prediction_gradient"] * difference
    return contribution


def aggregate(values, keys):
    keys = np.asarray(keys)
    if keys.ndim == 1:
        keys = keys[:, None]
    return [{"key": key.tolist(), "count": int(np.sum(np.all(keys == key, axis=1))),
             "gain": float(np.sum(values[np.all(keys == key, axis=1)]))}
            for key in np.unique(keys, axis=0)]


def state(data, satellites, fit, probability, vector=None):
    objective = CalibrationObjective(data, fit["parameters"], satellites, False, 30.)
    objective.base.deadline = float("inf")
    objective.likelihood.detection_probability = probability
    vector = np.asarray(fit["vector"] if vector is None else vector, dtype=float)
    value, _ = objective.evaluate(vector)
    prediction, visible = objective.base.predict(vector[:objective.size])
    prediction = prediction + (objective.features @ vector[objective.size:])[:, None]
    prior, _ = objective.base.penalty(vector[:objective.size])
    return {"objective": float(value), "prior": float(prior), "prediction": prediction,
            "visible": visible, "likelihood": objective.likelihood.last_result,
            "residual": circular_residual(data.measured[:, None], prediction),
            "physical": objective.base.state(vector[:objective.size]), "vector": vector}


def write_csv(path, rows):
    with path.open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_case(cell):
    session, variant = cell
    source_directory = ("position-profile-balanced" if variant == "current"
                        else "pruned-position-profile-grid")
    source_path = ROOT / source_directory / f"{session}.json"
    directory = ROOT / "south-point-attribution" / f"{session}-{variant}"
    if directory.exists():
        raise FileExistsError(directory)
    record = json.loads(source_path.read_text())
    hashes = {**record["source_hashes"], **snapshot_files([
        __file__, source_path, ROOT / "wrong_solution_attribution.py"])}
    assert_snapshot_unchanged(hashes)
    if variant == "current":
        _, data = load_scan(session)
    else:
        from all_visible_bank import load_expanded_scan

        data = load_expanded_scan(session)
    satellites = np.asarray(record["satellite_indices"], dtype=int)
    numbers = np.asarray(data.numbers)[satellites]
    fits = {name: next(point["best"] for point in record["positions"]
                      if point["label"] == label)
            for name, label in (("truth", "truth"), ("south", "S-500m"))}
    probability = float(record["detection_probability"])
    states = {name: state(data, satellites, fit, probability) for name, fit in fits.items()}
    for name, fitted in fits.items():
        np.testing.assert_allclose(states[name]["objective"], fitted["objective"], atol=1e-6,
                                   rtol=0)
    truth, south = states["truth"], states["south"]
    prepared = prepare_finite_set_likelihood(data.measured, data.group)
    def evaluate(predicted, visible):
        return prepared.evaluate(predicted, visible, sigma_hz=200.,
                                 detection_probability=probability, clutter_rate=2.,
                                 implementation="batched", return_gradient=True)
    fixed_visibility_south = evaluate(south["prediction"], truth["visible"])
    group_gain = south["likelihood"]["log_likelihood"] - truth["likelihood"]["log_likelihood"]
    visibility_gain = (south["likelihood"]["log_likelihood"]
                       - fixed_visibility_south["log_likelihood"])
    frequency_gain = fixed_visibility_south["total_log_likelihood"] - truth["likelihood"][
        "total_log_likelihood"]
    integrated = integrate_prediction_path(prepared, truth["prediction"], south["prediction"],
                                           truth["visible"], probability)
    if abs(integrated.sum() - frequency_gain) > 1e-6:
        integrated = integrate_prediction_path(prepared, truth["prediction"], south["prediction"],
                                               truth["visible"], probability, order=32)
    np.testing.assert_allclose(integrated.sum(), frequency_gain, rtol=0, atol=1e-5)
    row_gain = integrated.sum(axis=1)
    posterior = truth["likelihood"]["row_association_probability"]
    posterior_south = south["likelihood"]["row_association_probability"]
    fixed_assignment_gain = posterior * (truth["residual"]**2 - south["residual"]**2) / 80000.
    truth_winner = posterior.argmax(axis=1)
    south_winner = posterior_south.argmax(axis=1)
    row_indices = np.arange(len(data.times))
    truth_probability = posterior[row_indices, truth_winner]
    south_probability = posterior_south[row_indices, south_winner]
    stable = (truth_winner == south_winner) & (truth_probability >= .8) & (south_probability >= .8)
    metadata = group_metadata(data, prepared)
    group_for_row = prepared.unique_group_index[prepared.original_to_unique]
    allocated_groups = np.bincount(group_for_row, weights=row_gain, minlength=len(group_gain))
    np.testing.assert_allclose(allocated_groups + visibility_gain, group_gain, rtol=0, atol=1e-5)
    vector = truth["vector"].copy()
    vector[:2] = south["vector"][:2]
    position_only = state(data, satellites, fits["truth"], probability, vector)
    vector = south["vector"].copy()
    vector[:2] = truth["vector"][:2]
    nuisance_only = state(data, satellites, fits["south"], probability, vector)
    movement = south["prediction"] - truth["prediction"]
    satellite_rows = []
    for column, number in enumerate(numbers):
        weights = posterior[:, column]
        satellite_rows.append({
            "catalog_number": int(number),
            "path_attributed_data_gain": float(integrated[:, column].sum()),
            "truth_assignment_gain": float(fixed_assignment_gain[:, column].sum()),
            "truth_residual": weighted_residual_summary(truth["residual"][:, column], weights),
            "south_residual_same_weights": weighted_residual_summary(
                south["residual"][:, column], weights),
            "profiled_prediction_shift": weighted_residual_summary(movement[:, column], weights),
            "position_only_shift": weighted_residual_summary(
                position_only["prediction"][:, column] - truth["prediction"][:, column], weights),
            "truth_timing_s": truth["physical"]["total_shifts_s"][column],
            "south_timing_s": south["physical"]["total_shifts_s"][column],
        })
    row_records = []
    original_rows = np.asarray(getattr(data, "original_rows", row_indices))
    for row in row_indices:
        before, after = truth_winner[row], south_winner[row]
        row_records.append({
            "row": int(row), "original_row": int(original_rows[row]),
            "group": int(data.group[row]), "time_s": float(data.times[row]),
            "receiver": int(data.receiver[row]), "channel": int(data.channel[row]),
            "measured_hz": float(data.measured[row]), "margin": float(data.margin[row]),
            "path_attributed_data_gain": float(row_gain[row]),
            "truth_assignment_gain": float(fixed_assignment_gain[row].sum()),
            "whole_group_data_gain_not_additive_per_row": float(group_gain[group_for_row[row]]),
            "truth_satellite": int(numbers[before]), "south_satellite": int(numbers[after]),
            "truth_match_probability": float(truth_probability[row]),
            "south_match_probability": float(south_probability[row]),
            "truth_residual_hz": float(truth["residual"][row, before]),
            "south_residual_same_satellite_hz": float(south["residual"][row, before]),
            "south_residual_winner_hz": float(south["residual"][row, after]),
            "prediction_shift_same_satellite_hz": float(movement[row, before]),
            "stable_confident_match": bool(stable[row]),
        })
    groups = [{"group": int(group), "time_s": float(metadata["times"][index]),
               "receiver": int(metadata["receiver"][index]),
               "channel": int(metadata["channel"][index]), "data_gain": float(group_gain[index]),
               "visibility_gain": float(visibility_gain[index])}
              for index, group in enumerate(prepared.group_values)]
    parameter_names = ["east_km", "north_km", "rx0_intercept_hz", "rx0_slope_hz_s",
                       "rx1_intercept_hz", "rx1_slope_hz_s", "global_timing_s"]
    result = {
        "schema": "ds13-south-point-attribution/v1", "session": session, "variant": variant,
        "source_hashes": hashes, "sigma_hz": 200., "rows": len(row_indices),
        "groups": len(group_gain), "unique_peaks": prepared.unique_peak_count,
        "data_gain": float(group_gain.sum()), "visibility_gain": float(visibility_gain.sum()),
        "prior_gain": truth["prior"] - south["prior"],
        "total_gain": truth["objective"] - south["objective"],
        "path_integration_error": float(integrated.sum() - frequency_gain),
        "fixed_truth_assignment_gain": float(fixed_assignment_gain.sum()),
        "reassignment_bonus_fixed_visibility": float(frequency_gain - fixed_assignment_gain.sum()),
        "visibility_entries_changed": int(np.sum(truth["visible"] != south["visible"])),
        "groups_improved": int(np.sum(group_gain > 1e-8)),
        "groups_worsened": int(np.sum(group_gain < -1e-8)),
        "positive_group_gain": float(group_gain[group_gain > 0].sum()),
        "negative_group_gain": float(group_gain[group_gain < 0].sum()),
        "rows_improved": int(np.sum(row_gain > 1e-8)),
        "rows_worsened": int(np.sum(row_gain < -1e-8)),
        "stable_confident_rows": int(stable.sum()),
        "stable_confident_path_gain": float(row_gain[stable].sum()),
        "strong_identity_switches": int(np.sum((truth_winner != south_winner)
                                                & (truth_probability >= .8)
                                                & (south_probability >= .8))),
        "counterfactual_objectives": {"truth": truth["objective"], "south": south["objective"],
                                      "position_only": position_only["objective"],
                                      "nuisance_only": nuisance_only["objective"]},
        "parameter_changes": {name: {"truth": truth["vector"][index],
                                     "south": south["vector"][index],
                                     "change": south["vector"][index] - truth["vector"][index]}
                              for index, name in enumerate(parameter_names)},
        "rf_coefficient_change_hz_per_ghz": south["vector"][-1] - truth["vector"][-1],
        "by_receiver_channel": aggregate(group_gain, np.column_stack(
            [metadata["receiver"], metadata["channel"]])),
        "by_time_30s": aggregate(group_gain, np.floor(metadata["times"] / 30).astype(int)),
        "satellites": sorted(satellite_rows, key=lambda row: -row["path_attributed_data_gain"]),
        "top_improving_points": sorted(
            row_records, key=lambda row: -row["path_attributed_data_gain"])[:20],
        "scope": "Exact group-level finite-set likelihood decomposition of sealed converged "
                 "states. Peak/satellite contributions are integrated gradients along a straight "
                 "prediction-frequency path, not independent point likelihoods or causal truth. "
                 "Visibility change separated. All representative rows exported, duplicates "
                 "retain original likelihood weights. Fixed-assignment Q uses wrapped residuals "
                 "at sigma200Hz versus227kHz aliases; reassignment bonus includes latent member "
                 "and clutter uncertainty. No new fitting, no full GLRT response surfaces.",
    }
    assert_snapshot_unchanged(hashes)
    directory.mkdir(parents=True)
    write_csv(directory / "all-points.csv", row_records)
    write_csv(directory / "all-groups.csv", groups)
    np.savez_compressed(directory / "evidence.npz", times=data.times, receiver=data.receiver,
                        channel=data.channel, measured=data.measured, margin=data.margin,
                        catalog_numbers=numbers, truth_prediction=truth["prediction"],
                        south_prediction=south["prediction"], truth_residual=truth["residual"],
                        south_residual=south["residual"], truth_posterior=posterior,
                        south_posterior=posterior_south, path_contribution=integrated,
                        stable_confident=stable, group_values=prepared.group_values,
                        group_gain=group_gain, group_time_s=metadata["times"])
    with (directory / "summary.json").open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {key: result[key] for key in ("session", "variant", "total_gain", "data_gain",
                                        "prior_gain", "fixed_truth_assignment_gain",
                                        "reassignment_bonus_fixed_visibility",
                                        "stable_confident_path_gain", "strong_identity_switches")}


if __name__ == "__main__":
    sessions = json.loads((ROOT / "position-profile-protocol.json").read_text())["sessions"]
    with ProcessPoolExecutor(max_workers=2) as executor:
        cases = [(session, variant) for variant in ("current", "pruned") for session in sessions]
        for result in executor.map(run_case, cases):
            print(json.dumps(result), flush=True)
