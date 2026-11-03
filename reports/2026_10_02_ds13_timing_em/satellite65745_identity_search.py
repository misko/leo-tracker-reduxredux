"""Fixed-position whole-segment satellite identity search over absolute +/-10s timing."""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SESSION = "scan-fw-ffa1cc19d8d7c09f"
OUTPUT = ROOT / "satellite65745-identity-search"


def weighted_cost(residual, visible, weights):
    return np.sum(np.where(visible, residual ** 2, (1 / 4.4e-6 / 2) ** 2)
                  * weights, axis=-1) / np.sum(weights)


def local_minima(values):
    values = np.asarray(values)
    indices = np.flatnonzero((values <= np.r_[np.inf, values[:-1]])
                            & (values <= np.r_[values[1:], np.inf]))
    return indices[np.r_[True, np.diff(indices) > 1]]


def run():
    from all_visible_bank import load_expanded_scan
    from finite_set_fit import assert_snapshot_unchanged, snapshot_files
    from finite_set_likelihood import circular_residual
    from rf_calibration_diagnostic import rf_features
    from scipy.optimize import minimize_scalar

    started = time.monotonic()
    output_source = ROOT / "tle-doppler-overlay" / f"{SESSION}-plot-data.npz"
    profile_path = ROOT / "pruned-position-profile-grid" / f"{SESSION}.json"
    profile = json.loads(profile_path.read_text())
    hashes = {**profile["source_hashes"], **snapshot_files([__file__, output_source, profile_path])}
    assert_snapshot_unchanged(hashes)
    arrays = np.load(output_source)
    target_column = list(arrays["catalog_numbers"]).index(65745)
    mask = (arrays["accepted"][:, target_column] & (arrays["times_s"] >= 240)
            & (arrays["times_s"] <= 290))
    rows = np.flatnonzero(mask)
    weights = arrays["posterior"][rows, target_column]
    data = load_expanded_scan(SESSION)
    parameters = arrays["parameters"].copy()
    fit = next(item["best"] for item in profile["positions"] if item["label"] == "truth")
    _, features = rf_features(data.rf, data.receiver, False)
    rf_term = (features @ np.asarray(fit["rf_coefficient_hz_per_ghz"])).ravel()[rows]
    measured = data.measured[rows]
    offsets = np.linspace(-10, 10, 401)
    satellite_count = len(data.numbers)
    grid_cost = np.empty((satellite_count, len(offsets)))
    paired_rows = np.broadcast_to(rows, (satellite_count, len(rows)))
    paired_satellites = np.broadcast_to(np.arange(satellite_count)[:, None], paired_rows.shape)
    for offset_index, offset in enumerate(offsets):
        parameters[6:] = offset
        predicted, visible = data.predict(parameters, paired_rows, paired_satellites)
        residual = circular_residual(measured[None, :], predicted + rf_term[None, :])
        grid_cost[:, offset_index] = weighted_cost(residual, visible, weights)
    candidates = []
    for satellite, number in enumerate(data.numbers):
        if time.monotonic() - started > 150:
            raise TimeoutError("identity search exceeded 150s budget; no partial ranking published")
        def evaluate(offset, details=False, satellite=satellite):
            parameters[6 + satellite] = offset
            predicted, visible = data.predict(parameters, rows, np.full(len(rows), satellite))
            residual = circular_residual(measured, predicted + rf_term)
            cost = float(weighted_cost(residual, visible, weights))
            return (cost, residual, visible) if details else cost

        grid = grid_cost[satellite]
        best_index = int(np.argmin(grid))
        best_offset, best_cost = float(offsets[best_index]), float(grid[best_index])
        minima = local_minima(grid)
        for index in minima:
            lower, upper = offsets[max(0, index - 1)], offsets[min(len(offsets) - 1, index + 1)]
            result = minimize_scalar(evaluate, bounds=(lower, upper), method="bounded",
                                     options={"xatol": 1e-7, "maxiter": 40})
            if result.fun < best_cost:
                best_offset, best_cost = float(result.x), float(result.fun)
        _, residual, visible = evaluate(best_offset, True)
        trend = np.polyfit(data.times[rows] - 265, residual, 1, w=np.sqrt(weights))
        candidates.append({
            "satellite": int(number), "absolute_timing_s": best_offset,
            "all_points_visible": bool(np.all(visible)), "visible_count": int(visible.sum()),
            "weighted_rms_hz": float(np.sqrt(np.average(residual ** 2, weights=weights))),
            "unweighted_rms_hz": float(np.sqrt(np.mean(residual ** 2))),
            "median_absolute_residual_hz": float(np.median(np.abs(residual))),
            "within_100hz": int(np.sum(np.abs(residual) <= 100)),
            "within_200hz": int(np.sum(np.abs(residual) <= 200)),
            "residual_slope_hz_s": float(trend[0]), "grid_local_minima_refined": len(minima),
            "boundary_hit": abs(best_offset) > 9.9999,
        })
    candidates.sort(key=lambda item: (not item["all_points_visible"], item["weighted_rms_hz"]))
    OUTPUT.mkdir(exist_ok=False)
    with (OUTPUT / "candidates.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(candidates[0]))
        writer.writeheader()
        writer.writerows(candidates)
    top = [item for item in candidates if item["all_points_visible"]][:10]
    curves = []
    for item in top:
        satellite = int(np.flatnonzero(data.numbers == item["satellite"])[0])
        parameters[6 + satellite] = item["absolute_timing_s"]
        prediction, _ = data.predict(parameters, rows, np.full(len(rows), satellite))
        curves.append(circular_residual(measured, prediction + rf_term))
    np.savez_compressed(OUTPUT / "top-residuals.npz", times_s=data.times[rows], rows=rows,
                        receiver=data.receiver[rows], channel=data.channel[rows], weights=weights,
                        satellites=np.array([item["satellite"] for item in top]),
                        residual_hz=np.asarray(curves), grid_offsets_s=offsets,
                        grid_cost=grid_cost, catalogue_numbers=data.numbers)
    assert_snapshot_unchanged(hashes)
    summary = {"session": SESSION, "source_hashes": hashes, "row_count": len(rows),
               "rx_counts": {str(rx): int(np.sum(data.receiver[rows] == rx)) for rx in (0, 1)},
               "candidate_count": satellite_count, "top10": top,
               "fully_visible_candidate_count": sum(
                   item["all_points_visible"] for item in candidates),
               "original_target_total_timing_s": float(arrays["parameters"][
                   6 + np.flatnonzero(data.numbers == 65745)[0]]),
               "elapsed_s": time.monotonic() - started,
               "scope": "Known-position-conditioned, frozen original posterior>=0.8 membership "
                        "and weights, 240..290s. Fixed RX lines and RF correction. No candidate "
                        "frequency intercepts, slopes, position changes, or timing priors. Timing "
                        "is absolute shift from archived TLE, not extra shift from fitted tau. "
                        "Bank coverage is inherited from the expanded visible-catalogue export. "
                        "Wrapped residual permits existing GLRT aliases. Weighted RMS of the whole "
                        "segment, not a full-scan finite-set likelihood or raw-IQ likelihood. "
                        "0.05s grid followed by bounded refinement of every sampled local minimum; "
                        "not a mathematical proof of global optimality. Candidates must be above "
                        "horizon at all selected observations to enter top10."}
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False))
    print(json.dumps({key: value for key, value in summary.items() if key != "source_hashes"},
                     indent=2))


if __name__ == "__main__":
    run()
