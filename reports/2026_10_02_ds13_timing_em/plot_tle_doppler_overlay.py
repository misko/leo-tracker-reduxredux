"""Plot archived TLE Doppler and calibrated alias-assigned GLRT observations."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np
from all_visible_bank import load_expanded_scan
from compact_satellite_selection import SESSIONS, timing_prior
from finite_set_fit import assert_snapshot_unchanged, digest, snapshot_files
from finite_set_likelihood import circular_residual, prepare_finite_set_likelihood
from prediction_jacobian import paired_prediction_jacobian
from prediction_plan import SharedPredictionPlan
from prepare_scans import ROOT
from rf_calibration_diagnostic import rf_features
from rough_smoke import serializable

CARRIER_HZ = 11.085e9
POSTERIOR_THRESHOLD = 0.8
PROMINENT = (64013, 58484, 65745, 62739)
OUTPUT = ROOT / "tle-doppler-overlay"


def orbital_curve(data, parameters, satellites, times, *, carrier_hz=CARRIER_HZ):
    """Evaluate the existing physical predictor at arbitrary receive times and fixed RF."""
    times = np.asarray(times, dtype=float)
    satellites = np.asarray(satellites, dtype=int)
    if times.ndim != 1 or not len(times) or np.any(~np.isfinite(times)):
        raise ValueError("times must be a nonempty finite vector")
    if not np.isfinite(carrier_hz) or carrier_hz <= 0:
        raise ValueError("carrier must be positive and finite")
    geometry = SimpleNamespace(
        times=times, rf=np.full(len(times), carrier_hz),
        receiver=np.zeros(len(times), dtype=int), reference_time_s=150.0,
        numbers=data.numbers, nodes=data.nodes, position=data.position, velocity=data.velocity,
    )
    orbital_parameters = np.asarray(parameters, dtype=float).copy()
    orbital_parameters[2:6] = 0.0
    rows = np.repeat(np.arange(len(times)), len(satellites))
    paired = np.tile(satellites, len(times))
    prediction, visible, _ = paired_prediction_jacobian(
        geometry, orbital_parameters, rows, paired
    )
    shape = (len(times), len(satellites))
    return prediction.reshape(shape), visible.reshape(shape)


def calibrated_points(measured, raw_prediction, rf, nuisance, alias_hz):
    """Choose the nearest fitted alias, remove RX/RF terms, normalize carrier."""
    measured = np.asarray(measured, dtype=float)
    raw_prediction = np.asarray(raw_prediction, dtype=float)
    rf = np.asarray(rf, dtype=float)
    nuisance = np.asarray(nuisance, dtype=float)
    if (raw_prediction.ndim != 2 or raw_prediction.shape[0] != len(measured)
            or rf.shape != measured.shape or nuisance.shape != measured.shape
            or np.any(~np.isfinite(rf)) or np.any(rf <= 0)):
        raise ValueError("invalid aligned observation/calibration arrays")
    residual = circular_residual(measured[:, None], raw_prediction, alias_hz)
    dealiased = raw_prediction + residual
    factor = CARRIER_HZ / rf[:, None]
    return {
        "doppler_hz": (dealiased - nuisance[:, None]) * factor,
        "residual_hz": residual * factor,
        "modeled_doppler_hz": (raw_prediction - nuisance[:, None]) * factor,
        "alias_integer": np.rint((dealiased - measured[:, None]) / alias_hz).astype(int),
    }


def prepare_plot_data(session):
    path = ROOT / "pruned-position-profile-grid" / f"{session}.json"
    profile = json.loads(path.read_text())
    if profile.get("session") != session or profile.get("sigma_hz") != 200:
        raise ValueError("unexpected profile identity or width")
    assert_snapshot_unchanged(profile["source_hashes"])
    hashes = {**profile["source_hashes"], **snapshot_files([
        __file__, path, ROOT / "all_visible_bank.py",
        ROOT / "all-visible-bank" / session / "receipt.json",
        ROOT / "all-visible-bank" / session / "expanded.npz",
    ])}
    point = next(item for item in profile["positions"] if item["label"] == "truth")
    fit = point["best"]
    if fit is None:
        raise ValueError("reference-position fit unavailable")
    data = load_expanded_scan(session)
    parameters = np.asarray(fit["parameters"], dtype=float)
    satellites = np.asarray(profile["satellite_indices"], dtype=int)
    if not np.array_equal(parameters[:2], point["fixed_position_km"]):
        raise ValueError("sealed parameters are not at the requested reference position")
    if not np.array_equal(data.numbers[satellites], profile["catalog_numbers"]):
        raise ValueError("selected catalogue mapping changed")
    prediction, visibility, _ = SharedPredictionPlan(data, satellites).predict(parameters)
    prediction = prediction.reshape(len(data.times), len(satellites))
    visibility = visibility.reshape(prediction.shape)
    center, features = rf_features(data.rf, data.receiver, False)
    coefficient = np.asarray(fit["rf_coefficient_hz_per_ghz"], dtype=float)
    rf_term = (features @ coefficient).ravel()
    receiver = np.asarray(data.receiver, dtype=int)
    rx_term = parameters[2 + 2 * receiver] + parameters[3 + 2 * receiver] * (
        data.times - data.reference_time_s)
    raw_prediction = prediction + rf_term[:, None]
    prepared = prepare_finite_set_likelihood(data.measured, data.group)
    likelihood = prepared.evaluate(
        raw_prediction, visibility, sigma_hz=200,
        detection_probability=profile["detection_probability"], clutter_rate=2,
    )
    objective = -likelihood["total_log_likelihood"] + timing_prior(parameters[6 + satellites])
    if not np.isclose(objective, fit["objective"], rtol=0, atol=1e-6):
        raise ValueError("sealed fit likelihood does not reproduce")
    points = calibrated_points(data.measured, raw_prediction, data.rf,
                               rx_term + rf_term, prepared.alias_hz)
    physical, physical_visible = orbital_curve(data, parameters, satellites, data.times)
    maximum_error = float(np.max(np.abs(physical - points["modeled_doppler_hz"])))
    if maximum_error > 1e-7 or not np.array_equal(physical_visible, visibility):
        raise ValueError("dense physical predictor disagrees with actual fitted predictions")
    dense_times = np.arange(0.0, 300.0 + 0.125, 0.25)
    dense, dense_visible = orbital_curve(data, parameters, satellites, dense_times)
    unshifted = parameters.copy()
    unshifted[6:] = 0.0
    pinned, _ = orbital_curve(data, unshifted, satellites, dense_times)
    posterior = likelihood["row_association_probability"]
    accepted = (posterior >= POSTERIOR_THRESHOLD) & visibility
    arrays = {
        "times_s": data.times, "receiver": receiver, "channel": data.channel,
        "rf_hz": data.rf, "measured_raw_hz": data.measured,
        "group": data.group, "catalog_numbers": data.numbers[satellites],
        "satellite_indices": satellites, "parameters": parameters,
        "dense_times_s": dense_times, "dense_doppler_hz": dense,
        "dense_visible": dense_visible, "unshifted_tle_doppler_hz": pinned,
        "posterior": posterior, "accepted": accepted, **points,
    }
    metadata = {
        "session": session, "source_profile": str(path), "source_hashes": hashes,
        "fixed_position_km": parameters[:2], "reference_position_conditioned": True,
        "fit_success": fit["success"], "fit_status": fit["status"],
        "sealed_objective": fit["objective"], "reproduced_objective": objective,
        "maximum_prediction_parity_error_hz": maximum_error,
        "catalog_numbers": data.numbers[satellites],
        "total_timing_shifts_s": parameters[6 + satellites],
        "rf_center_hz": center, "rf_coefficient_hz_per_ghz": coefficient,
        "tle_provenance": data.bank_receipt["tle"],
        "high_posterior_points_by_satellite": accepted.sum(axis=0),
        "residual_median_hz_by_satellite": [
            float(np.median(points["residual_hz"][accepted[:, column], column]))
            if accepted[:, column].any() else None for column in range(len(satellites))
        ],
    }
    return arrays, metadata


def satellite_panel(figure, slot, arrays, column, title):
    layout = slot.subgridspec(2, 1, height_ratios=[2.5, 1], hspace=0.10)
    main = figure.add_subplot(layout[0])
    residual_axis = figure.add_subplot(layout[1], sharex=main)
    times = arrays["dense_times_s"]
    main.plot(times, arrays["unshifted_tle_doppler_hz"][:, column] / 1000,
              color="0.65", linestyle=":", linewidth=1, label="Pinned TLE, zero timing shift")
    main.plot(times, arrays["dense_doppler_hz"][:, column] / 1000,
              color="black", linewidth=1.15, label="TLE + profiled timing")
    markers = ("o", "s", "^", "D", "v", "P", "X")
    channels = np.unique(arrays["channel"])
    for receiver, color in ((0, "#0072B2"), (1, "#D55E00")):
        for channel_index, channel in enumerate(channels):
            mask = (arrays["accepted"][:, column] & (arrays["receiver"] == receiver)
                    & (arrays["channel"] == channel))
            options = {"s": 9, "color": color, "marker": markers[channel_index % len(markers)],
                       "alpha": 0.7, "linewidths": 0}
            main.scatter(arrays["times_s"][mask], arrays["doppler_hz"][mask, column] / 1000,
                         **options)
            residual_axis.scatter(arrays["times_s"][mask],
                                  arrays["residual_hz"][mask, column], **options)
    residual_axis.axhline(0, color="black", linewidth=0.6)
    residual_axis.axhline(100, color="0.65", linestyle=":", linewidth=0.6)
    residual_axis.axhline(-100, color="0.65", linestyle=":", linewidth=0.6)
    values = arrays["residual_hz"][arrays["accepted"][:, column], column]
    extent = max(150.0, float(np.max(np.abs(values))) * 1.08 if len(values) else 150.0)
    residual_axis.set_ylim(-extent, extent)
    main.set_title(f"{title} · {int(arrays['accepted'][:, column].sum())} points", fontsize=10)
    main.set_ylabel("Doppler (kHz)")
    residual_axis.set_ylabel("O−M (Hz)")
    residual_axis.set_xlabel("Receive time since capture start (s)")
    main.tick_params(labelbottom=False)
    for axis in (main, residual_axis):
        axis.set_xlim(0, 300)
        axis.grid(alpha=0.18)


def decorate(figure, title):
    from matplotlib.lines import Line2D

    figure.suptitle(title + "\nReference position; sealed profiled timing/RX/RF nuisance", y=0.995)
    figure.legend(handles=[
        Line2D([], [], color="black", label="Timing-adjusted TLE Doppler"),
        Line2D([], [], color="0.6", linestyle=":", label="Pinned TLE, zero timing shift"),
        Line2D([], [], color="#0072B2", marker="o", linestyle="", label="RX0 GLRT"),
        Line2D([], [], color="#D55E00", marker="o", linestyle="", label="RX1 GLRT"),
    ], loc="upper center", bbox_to_anchor=(0.5, 0.955), ncol=4, fontsize=8)
    figure.text(0.5, 0.012,
                "Points: posterior ≥0.8; nearest fitted alias; RX line + RF coefficient removed; "
                "scaled to 11.085 GHz.\nChannel marker shapes differ; "
                "points are calibrated/assigned, "
                "not raw CFO. Residuals use the timing-adjusted curve; dotted guides ±100 Hz.\n"
                "Dense curves: archived 0.25 s position/velocity bank, evaluated over all 0–300 s. "
                "No new parameters fitted.", ha="center", fontsize=8)


def main():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    started = time.monotonic()
    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    OUTPUT.mkdir()
    receipts = []
    prominent = plt.figure(figsize=(15, 11))
    grid = prominent.add_gridspec(2, 2, left=0.07, right=0.98, bottom=0.11,
                                top=0.88, wspace=0.22, hspace=0.35)
    artifacts = []
    for scan_index, session in enumerate(SESSIONS):
        arrays, metadata = prepare_plot_data(session)
        count = len(arrays["catalog_numbers"])
        overview = plt.figure(figsize=(15, 3.6 * int(np.ceil(count / 2)) + 2))
        overview_grid = overview.add_gridspec(int(np.ceil(count / 2)), 2,
                                            left=0.07, right=0.98, bottom=0.075,
                                            top=0.92, hspace=0.45, wspace=0.22)
        for column, number in enumerate(arrays["catalog_numbers"]):
            title = f"Scan {'AB'[scan_index]} · NORAD {number}"
            satellite_panel(overview, overview_grid[column // 2, column % 2],
                            arrays, column, title)
            if int(number) in PROMINENT:
                index = PROMINENT.index(int(number))
                satellite_panel(prominent, grid[index // 2, index % 2], arrays, column, title)
        decorate(overview, f"DS13 scan {'AB'[scan_index]} · all {count} selected satellites")
        for extension in ("png", "svg"):
            path = OUTPUT / f"{session}-overview.{extension}"
            overview.savefig(path, dpi=160)
            artifacts.append(path)
        plt.close(overview)
        array_path = OUTPUT / f"{session}-plot-data.npz"
        np.savez_compressed(array_path, **arrays)
        artifacts.append(array_path)
        assert_snapshot_unchanged(metadata["source_hashes"])
        receipts.append(metadata)
        if time.monotonic() - started > 110:
            raise TimeoutError("plotting exceeded cooperative budget")
    decorate(prominent, "DS13 · four prominent satellite Doppler tracks")
    for extension in ("png", "svg"):
        path = OUTPUT / f"prominent-four.{extension}"
        prominent.savefig(path, dpi=170)
        artifacts.append(path)
    plt.close(prominent)
    for receipt in receipts:
        assert_snapshot_unchanged(receipt["source_hashes"])
    result = {
        "schema": "ds13-tle-doppler-overlay/v1", "scans": receipts,
        "carrier_hz": CARRIER_HZ, "posterior_threshold": POSTERIOR_THRESHOLD,
        "dense_receive_time_spacing_s": 0.25, "elapsed_s": time.monotonic() - started,
        "artifact_sha256": {str(path): digest(path) for path in artifacts},
        "semantics": "Orbit-derived Doppler evaluated at sealed reference-position fits. "
                     "Points depend on fitted nuisance, posterior selection and alias assignment; "
                     "they are not independent calibration or raw CFO. Dotted zero-timing TLE "
                     "is a visual comparison only. Full curves include below-horizon intervals; "
                     "points require fitted visibility and posterior>=0.8. No refitting.",
        "sealed_utc": datetime.now(UTC).isoformat(),
    }
    with (OUTPUT / "receipt.json").open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    print(json.dumps({"output": str(OUTPUT), "elapsed_s": result["elapsed_s"],
                      "maximum_parity_error_hz": max(
                          item["maximum_prediction_parity_error_hz"] for item in receipts)}))


if __name__ == "__main__":
    main()
