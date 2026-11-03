"""Descriptive all-visible trajectory crowding audit, not a replacement likelihood."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from all_visible_bank import load_expanded_scan
from finite_set_fit import assert_snapshot_unchanged, snapshot_files
from finite_set_likelihood import DEFAULT_ALIAS_HZ, circular_residual, prepare_finite_set_likelihood
from prepare_scans import ROOT
from rf_calibration_diagnostic import rf_features
from south_point_attribution import write_csv


def circular_coverage(centers, radius, period=DEFAULT_ALIAS_HZ):
    centers = np.asarray(centers, dtype=float)
    if not 0 <= radius <= period / 2:
        raise ValueError("radius must lie between zero and half the alias period")
    if not len(centers):
        return 0.
    centers = np.sort(np.mod(centers, period))
    gaps = np.diff(np.r_[centers, centers[0] + period])
    return float(1 - np.maximum(gaps - 2 * radius, 0.).sum() / period)


def run_case(session):
    source = ROOT / "pruned-position-profile-grid" / f"{session}.json"
    parent = ROOT / "south-point-attribution" / f"{session}-pruned"
    destination = ROOT / "south-all-sky-audit" / session
    if destination.exists():
        raise FileExistsError(destination)
    record = json.loads(source.read_text())
    hashes = {**record["source_hashes"], **snapshot_files([
        __file__, source, parent / "evidence.npz", ROOT / "south_point_attribution.py"])}
    assert_snapshot_unchanged(hashes)
    data = load_expanded_scan(session)
    prepared = prepare_finite_set_likelihood(data.measured, data.group)
    group_first = np.array([rows[0] for rows in prepared.group_row_indices])
    group_for_row = prepared.unique_group_index[prepared.original_to_unique]
    satellites = np.asarray(record["satellite_indices"], dtype=int)
    _, features = rf_features(data.rf, data.receiver, False)
    evidence = np.load(parent / "evidence.npz")
    states = {}
    summaries = {}
    for name, label in (("truth", "truth"), ("south", "S-500m")):
        fit = next(point["best"] for point in record["positions"] if point["label"] == label)
        parameters = np.asarray(fit["parameters"]).copy()
        selected_shifts = parameters[6 + satellites].copy()
        parameters[6:] = np.mean(selected_shifts)
        parameters[6 + satellites] = selected_shifts
        prediction = np.empty((len(group_first), len(data.numbers)))
        visible = np.zeros_like(prediction, dtype=bool)
        for begin in range(0, len(data.numbers), 64):
            columns = np.arange(begin, min(begin + 64, len(data.numbers)))
            rows = np.repeat(group_first, len(columns))
            indices = np.tile(columns, len(group_first))
            values, valid = data.predict(parameters, rows=rows, satellites=indices)
            prediction[:, columns] = values.reshape(len(group_first), len(columns))
            visible[:, columns] = valid.reshape(len(group_first), len(columns))
        prediction += (features[group_first] @ np.asarray(
            fit["rf_coefficient_hz_per_ghz"]))[:, None]
        distances = np.abs(circular_residual(data.measured[:, None], prediction[group_for_row]))
        distances = np.where(visible[group_for_row], distances, np.inf)
        winner = np.argmin(distances, axis=1)
        nearest = distances[np.arange(len(data.times)), winner]
        coverage = {radius: np.array([circular_coverage(values[valid], radius)
                                     for values, valid in zip(prediction, visible, strict=True)])
                    for radius in (50., 100., 200.)}
        posterior = evidence[f"{name}_posterior"]
        low_association = posterior.sum(axis=1) < .2
        summaries[name] = {
            "mean_visible_satellites_per_group": float(visible.sum(axis=1).mean()),
            "coverage": [{"tolerance_hz": radius,
                          "mean_uniform_frequency_coverage": float(values.mean()),
                          "fraction_observed_rows_with_any_sky_match": float(
                              np.mean(nearest <= radius)),
                          "fraction_low_association_rows_with_any_sky_match": float(
                              np.mean(nearest[low_association] <= radius))}
                         for radius, values in coverage.items()],
            "low_selected_association_rows": int(low_association.sum()),
            "nearest_selected_fraction": float(np.mean(np.isin(winner, satellites))),
        }
        states[name] = {"distance": nearest, "number": np.asarray(data.numbers)[winner]}
    rows = [{"row": index, "time_s": float(data.times[index]),
             "receiver": int(data.receiver[index]), "channel": int(data.channel[index]),
             "truth_nearest_catalog_number": int(states["truth"]["number"][index]),
             "south_nearest_catalog_number": int(states["south"]["number"][index]),
             "truth_nearest_distance_hz": float(states["truth"]["distance"][index]),
             "south_nearest_distance_hz": float(states["south"]["distance"][index])}
            for index in range(len(data.times))]
    result = {"schema": "ds13-south-all-sky-crowding/v1", "session": session,
              "source_hashes": hashes, "candidate_count": len(data.numbers), "states": summaries,
              "scope": "Map every candidate in the finite-grid visible bank, retaining fitted "
                       "timing for active satellites and global mean timing for others. No "
                       "additional per-candidate timing search. Uniform-frequency coverage is "
                       "geometrical crowding, not a false-positive p-value. Nearest-satellite "
                       "mapping is not the competitive sparse model and cannot validate a match."}
    assert_snapshot_unchanged(hashes)
    destination.mkdir(parents=True)
    write_csv(destination / "all-sky-nearest-per-point.csv", rows)
    with (destination / "summary.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    return {"session": session, **summaries}


if __name__ == "__main__":
    sessions = json.loads((ROOT / "position-profile-protocol.json").read_text())["sessions"]
    with ProcessPoolExecutor(max_workers=2) as executor:
        for result in executor.map(run_case, sessions):
            print(json.dumps(result), flush=True)
