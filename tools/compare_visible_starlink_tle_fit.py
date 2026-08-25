#!/usr/bin/env python3
"""Fit causal TLE Doppler curves to one counter-continuous CFO trajectory.

The comparison is intentionally candidate-only.  It uses a reviewed observer
preset because the capture has no position or antenna-boresight authority, and
it allows exactly two nuisance parameters per catalogue object: a time shift
and a constant frequency offset.  No scale, slope, or curvature is fitted to a
TLE curve.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import matplotlib
import numpy as np
from numpy.typing import NDArray

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.projections.polar import PolarAxes

from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import (
    MINIMUM_PLAUSIBLE_ALTITUDE_KM,
    ElementSetCatalogue,
    parse_element_set_records,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import MAX_ANGULAR_RATE_DEG_S, SamplingGrid
from leo.sky.screening import ObservedTracks, observe_grid
from leo.sky.sites import resolve_preset

STREAM_FIRST_SAMPLE_UTC_NS = 1_787_670_485_580_127_359
RF_FREQUENCY_HZ = 11_440_312_498.0
TLE_COLLECTED_UTC_NS = 1_787_666_532_658_586_719
PRIMARY_SHIFT_LIMIT_S = 2.0
PRIMARY_SHIFT_STEP_S = 0.005
WIDE_SHIFT_LIMIT_S = 30.0
WIDE_SHIFT_STEP_S = 0.05
MODEL_GRID_STEP_S = 0.005
COARSE_VISIBILITY_STEP_S = 0.1
TRAIN_FRACTION = 0.6

ROOT = Path(__file__).parents[1]
DEFAULT_ROWS = (
    ROOT
    / "reports"
    / "figures"
    / "2026_08_25_joint_cfo_delay_acceleration"
    / "joint-model-rows.jsonl"
)
DEFAULT_MANIFEST = Path(
    "/srv/bulk/leo/recordings/2026/08/25/cap-20260825T150802-473cb5bbcbd6/manifest.json"
)
DEFAULT_TLE = Path(
    "/tmp/leo-last10-tle-worktree-staged/archive/space-track/"
    "1787666532658586719-"
    "9bb59fcf68fa36ce234ae9be79a492f0b92abc23bcf4f040bb5b64b61d3e31ad.tle"
)
DEFAULT_PRIOR_TLE = Path(
    "/mnt/qnap01/mouse9911/tle/raw/space-track/"
    "ac79e846bc149d9bbe4a1847eda5fddc9ca6af9fbe3432d6c58cdc33345ceb8a.tle"
)


FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class ShiftFit:
    shift_s: float
    offset_hz: float
    training_rms_hz: float
    evaluation_rms_hz: float
    full_rms_hz: float
    shift_at_boundary: bool


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def iso_utc(utc_ns: int) -> str:
    seconds, nanoseconds = divmod(utc_ns, 1_000_000_000)
    stamp = datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{stamp}.{nanoseconds:09d}Z"


def sampling_grid(start_utc_ns: int, stop_utc_ns: int, spacing_s: float) -> SamplingGrid:
    if stop_utc_ns <= start_utc_ns:
        raise ValueError("sampling stop must be after start")
    count = max(3, int(math.ceil((stop_utc_ns - start_utc_ns) / 1e9 / spacing_s)) + 1)
    instants = np.rint(np.linspace(start_utc_ns, stop_utc_ns, count)).astype(np.int64)
    anchor = count // 2
    achieved = float(np.median(np.diff(instants)) / 1e9)
    return SamplingGrid(tuple(int(value) for value in instants), anchor, achieved)


def load_measurements(path: Path) -> tuple[FloatArray, FloatArray]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    times = np.asarray([row["cfo_measurement_time_s"] for row in rows], dtype=np.float64)
    cfo = np.asarray([row["tracking_cfo_hz"] for row in rows], dtype=np.float64)
    if times.size < 10 or times.shape != cfo.shape:
        raise ValueError("CFO row ledger is empty or malformed")
    if not np.isfinite(times).all() or not np.isfinite(cfo).all():
        raise ValueError("CFO row ledger contains non-finite values")
    if np.any(np.diff(times) <= 0.0):
        raise ValueError("CFO measurement times must be strictly increasing")
    return times, cfo


def fit_shift_offset_from_prediction_matrix(
    prediction_hz: FloatArray,
    observed_hz: FloatArray,
    shifts_s: FloatArray,
    training_mask: BoolArray,
    evaluation_mask: BoolArray,
) -> tuple[ShiftFit, int]:
    """Profile a constant offset and select the time shift on training rows."""

    if prediction_hz.ndim != 2 or prediction_hz.shape[1] != observed_hz.size:
        raise ValueError("prediction matrix must be shift by observation")
    if shifts_s.shape != (prediction_hz.shape[0],):
        raise ValueError("shift vector does not match prediction matrix")
    if training_mask.shape != observed_hz.shape or evaluation_mask.shape != observed_hz.shape:
        raise ValueError("fit masks do not match observations")
    if not training_mask.any() or not evaluation_mask.any():
        raise ValueError("both training and evaluation masks need support")

    offsets = np.mean(observed_hz[None, training_mask] - prediction_hz[:, training_mask], axis=1)
    residual = observed_hz[None, :] - prediction_hz - offsets[:, None]
    training_rms = np.sqrt(np.mean(np.square(residual[:, training_mask]), axis=1))
    selected = int(np.argmin(training_rms))
    evaluation_rms = float(np.sqrt(np.mean(np.square(residual[selected, evaluation_mask]))))
    full_rms = float(np.sqrt(np.mean(np.square(residual[selected]))))
    return (
        ShiftFit(
            shift_s=float(shifts_s[selected]),
            offset_hz=float(offsets[selected]),
            training_rms_hz=float(training_rms[selected]),
            evaluation_rms_hz=evaluation_rms,
            full_rms_hz=full_rms,
            shift_at_boundary=bool(shifts_s.size > 1 and selected in (0, shifts_s.size - 1)),
        ),
        selected,
    )


def prediction_matrix(
    model_time_s: FloatArray,
    model_hz: FloatArray,
    observation_time_s: FloatArray,
    shifts_s: FloatArray,
) -> FloatArray:
    query = observation_time_s[None, :] + shifts_s[:, None]
    if query.min() < model_time_s[0] or query.max() > model_time_s[-1]:
        raise ValueError("model support does not cover shifted observation times")
    return np.interp(query.ravel(), model_time_s, model_hz).reshape(query.shape)


def fit_candidate(
    model_time_s: FloatArray,
    model_hz: FloatArray,
    observation_time_s: FloatArray,
    observed_hz: FloatArray,
    shifts_s: FloatArray,
) -> tuple[ShiftFit, ShiftFit, ShiftFit, FloatArray]:
    predicted = prediction_matrix(model_time_s, model_hz, observation_time_s, shifts_s)
    split = int(math.ceil(TRAIN_FRACTION * observed_hz.size))
    indexes = np.arange(observed_hz.size)
    early_training = indexes < split
    late_evaluation = indexes >= split
    late_training = indexes >= observed_hz.size - split
    early_evaluation = indexes < observed_hz.size - split
    forward, _ = fit_shift_offset_from_prediction_matrix(
        predicted, observed_hz, shifts_s, early_training, late_evaluation
    )
    reverse, _ = fit_shift_offset_from_prediction_matrix(
        predicted, observed_hz, shifts_s, late_training, early_evaluation
    )
    all_rows = np.ones(observed_hz.size, dtype=np.bool_)
    full, selected = fit_shift_offset_from_prediction_matrix(
        predicted, observed_hz, shifts_s, all_rows, all_rows
    )
    return forward, reverse, full, predicted[selected] + full.offset_hz


def _tracks_for(
    catalogue: ElementSetCatalogue,
    grid: SamplingGrid,
    observer_name: str,
    indices: NDArray[np.intp] | None = None,
) -> ObservedTracks:
    propagated = propagate_grid(catalogue, grid, None if indices is None else indices.tolist())
    return observe_grid(propagated, resolve_preset(observer_name), grid)


def visible_catalogue_indices(
    catalogue: ElementSetCatalogue,
    start_utc_ns: int,
    stop_utc_ns: int,
    observer_name: str,
) -> tuple[NDArray[np.intp], dict[str, int | float]]:
    coarse_grid = sampling_grid(start_utc_ns, stop_utc_ns, COARSE_VISIBILITY_STEP_S)
    tracks = _tracks_for(catalogue, coarse_grid, observer_name)
    margin = MAX_ANGULAR_RATE_DEG_S * coarse_grid.spacing_s / 2.0
    plausible = tracks.usable & (np.min(tracks.altitude_km, axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM)
    candidates = np.flatnonzero(plausible & (np.max(tracks.elevation_deg, axis=1) > -margin))
    accounting: dict[str, int | float] = {
        "catalogue_count": len(catalogue),
        "propagation_usable_count": int(np.count_nonzero(tracks.usable)),
        "plausible_altitude_count": int(np.count_nonzero(plausible)),
        "excluded_below_120_km_count": int(np.count_nonzero(tracks.usable & ~plausible)),
        "coarse_horizon_candidate_count": int(candidates.size),
        "coarse_spacing_s": coarse_grid.spacing_s,
        "coarse_margin_deg": margin,
    }
    del tracks
    gc.collect()
    return candidates, accounting


def _rms_pair(forward: ShiftFit, reverse: ShiftFit, observed_count: int) -> float:
    split = int(math.ceil(TRAIN_FRACTION * observed_count))
    evaluation_count = observed_count - split
    return math.sqrt(
        (
            evaluation_count * forward.evaluation_rms_hz**2
            + evaluation_count * reverse.evaluation_rms_hz**2
        )
        / (2 * evaluation_count)
    )


def _render_fit(
    output: Path,
    time_s: FloatArray,
    observed_hz: FloatArray,
    results: list[dict[str, Any]],
    curves: dict[int, FloatArray],
    shift_profiles: dict[int, tuple[FloatArray, FloatArray]],
) -> None:
    ranked = sorted(results, key=lambda row: row["bidirectional_holdout_rms_hz"])
    top = ranked[:5]
    colors = plt.get_cmap("tab10")
    fig, axes = plt.subplots(2, 2, figsize=(16, 10), constrained_layout=True)
    relative = time_s - time_s[0]

    ax = axes[0, 0]
    ax.scatter(
        relative,
        observed_hz / 1e3,
        s=7,
        color="0.25",
        alpha=0.38,
        label="550 GLRT64 CFO observations",
    )
    for rank, row in enumerate(top, start=1):
        ax.plot(
            relative,
            curves[row["norad_id"]] / 1e3,
            linewidth=1.8,
            color=colors(rank - 1),
            label=f"{rank}. {row['name']} ({row['norad_id']})",
        )
    ax.set_title("Observed CFO and five best full-data TLE shapes")
    ax.set_xlabel("Seconds from first CFO centroid")
    ax.set_ylabel("CFO (kHz)")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, ncols=2)

    ax = axes[0, 1]
    for rank, row in enumerate(top, start=1):
        residual = observed_hz - curves[row["norad_id"]]
        ax.plot(
            relative,
            residual,
            linewidth=1.0,
            color=colors(rank - 1),
            label=f"{rank}. {row['norad_id']}",
        )
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.set_title("Full-data residuals (descriptive, not ranking data)")
    ax.set_xlabel("Seconds from first CFO centroid")
    ax.set_ylabel("Observed − fitted TLE CFO (Hz)")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, ncols=2)

    ax = axes[1, 0]
    rms = np.asarray([row["bidirectional_holdout_rms_hz"] for row in ranked])
    elevation = np.asarray([row["maximum_elevation_deg"] for row in ranked])
    scatter = ax.scatter(
        np.arange(1, len(ranked) + 1), rms, c=elevation, s=13, cmap="viridis", alpha=0.75
    )
    for rank, row in enumerate(top, start=1):
        ax.scatter(
            rank, row["bidirectional_holdout_rms_hz"], s=45, color=colors(rank - 1), zorder=3
        )
        ax.annotate(
            str(row["norad_id"]),
            (rank, row["bidirectional_holdout_rms_hz"]),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
        )
    ax.set_yscale("log")
    ax.set_title("Every geometric-horizon candidate, ranked only on held-out rows")
    ax.set_xlabel("Candidate rank")
    ax.set_ylabel("Bidirectional held-out RMS (Hz, log scale)")
    ax.grid(alpha=0.25, which="both")
    fig.colorbar(scatter, ax=ax, label="Peak elevation (deg)")

    ax = axes[1, 1]
    for rank, row in enumerate(top, start=1):
        shifts, profile = shift_profiles[row["norad_id"]]
        ax.plot(
            shifts,
            profile,
            color=colors(rank - 1),
            linewidth=1.6,
            label=f"{rank}. {row['norad_id']}",
        )
        ax.axvline(row["full_fit"]["shift_s"], color=colors(rank - 1), alpha=0.35, linewidth=0.8)
    ax.set_title("Profiled full-data RMS versus time shift")
    ax.set_xlabel("TLE evaluation shift τ (s)")
    ax.set_ylabel("RMS after constant offset (Hz)")
    ax.set_yscale("log")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, ncols=2)

    fig.suptitle(
        "Aug-25 counter-continuous branch · all above-horizon Starlinks\n"
        "candidate-only fits: observed CFO = TLE Doppler(t + τ) + constant",
        fontsize=16,
    )
    fig.savefig(output, dpi=180)
    plt.close(fig)


def _render_sky(
    output: Path,
    model_time_s: FloatArray,
    actual_mask: BoolArray,
    visible_tracks: ObservedTracks,
    visible_indices: NDArray[np.intp],
    catalogue: ElementSetCatalogue,
    results: list[dict[str, Any]],
) -> None:
    ranked = sorted(results, key=lambda row: row["bidirectional_holdout_rms_hz"])
    top_ids = [int(row["norad_id"]) for row in ranked[:10]]
    row_for_catalogue = {int(index): row for row, index in enumerate(visible_indices)}
    number_to_catalogue = {
        number: index for index, number in enumerate(catalogue.satellite_numbers)
    }
    colors = plt.get_cmap("tab10")

    fig = plt.figure(figsize=(15, 7.5), constrained_layout=True)
    sky = cast(PolarAxes, fig.add_subplot(1, 2, 1, projection="polar"))
    for row in range(visible_indices.size):
        sky.plot(
            np.deg2rad(visible_tracks.azimuth_deg[row, actual_mask]),
            90.0 - visible_tracks.elevation_deg[row, actual_mask],
            color="0.55",
            linewidth=0.45,
            alpha=0.18,
        )
    midpoint = int(np.flatnonzero(actual_mask)[len(np.flatnonzero(actual_mask)) // 2])
    for rank, norad in enumerate(top_ids, start=1):
        catalogue_index = number_to_catalogue[norad]
        row = row_for_catalogue[catalogue_index]
        theta = np.deg2rad(visible_tracks.azimuth_deg[row, actual_mask])
        radius = 90.0 - visible_tracks.elevation_deg[row, actual_mask]
        sky.plot(theta, radius, color=colors(rank - 1), linewidth=2.0)
        sky.scatter(
            np.deg2rad(visible_tracks.azimuth_deg[row, midpoint]),
            90.0 - visible_tracks.elevation_deg[row, midpoint],
            color=colors(rank - 1),
            s=24,
            zorder=3,
        )
        sky.annotate(str(norad), (theta[len(theta) // 2], radius[len(radius) // 2]), fontsize=7)
    sky.set_theta_zero_location("N")
    sky.set_theta_direction(-1)
    sky.set_ylim(90, 0)
    sky.set_yticks([90, 60, 30, 0])
    sky.set_yticklabels(["0°", "30°", "60°", "90°"])
    sky.set_title("Sky tracks: every horizon-visible object; top 10 highlighted")

    elevation_ax = fig.add_subplot(1, 2, 2)
    actual_time = model_time_s[actual_mask]
    for row in range(visible_indices.size):
        elevation_ax.plot(
            actual_time,
            visible_tracks.elevation_deg[row, actual_mask],
            color="0.6",
            linewidth=0.4,
            alpha=0.12,
        )
    for rank, norad in enumerate(top_ids, start=1):
        catalogue_index = number_to_catalogue[norad]
        row = row_for_catalogue[catalogue_index]
        elevation_ax.plot(
            actual_time,
            visible_tracks.elevation_deg[row, actual_mask],
            color=colors(rank - 1),
            linewidth=1.8,
            label=f"{rank}. {norad}",
        )
    elevation_ax.axhline(0.0, color="black", linewidth=0.8)
    elevation_ax.axhline(10.0, color="black", linewidth=0.8, linestyle="--", alpha=0.7)
    elevation_ax.set_title("Elevation during the fitted branch")
    elevation_ax.set_xlabel("Seconds from dwell start")
    elevation_ax.set_ylabel("Elevation (deg)")
    elevation_ax.grid(alpha=0.25)
    elevation_ax.legend(fontsize=8, ncols=2)
    fig.suptitle(
        "Conditional Sausalito geometry · no capture-bound site or antenna boresight",
        fontsize=15,
    )
    fig.savefig(output, dpi=180)
    plt.close(fig)


def run(arguments: argparse.Namespace) -> dict[str, Any]:
    rows_path = arguments.rows.resolve()
    manifest_path = arguments.capture_manifest.resolve()
    tle_path = arguments.tle.resolve()
    prior_tle_path = arguments.prior_tle.resolve()
    output_root = arguments.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    if sha256_file(tle_path) != arguments.tle_sha256:
        raise ValueError("TLE payload digest does not match the frozen input")
    if sha256_file(manifest_path) != arguments.manifest_sha256:
        raise ValueError("capture manifest digest does not match the frozen input")
    if sha256_file(prior_tle_path) != arguments.prior_tle_sha256:
        raise ValueError("adjacent-prior TLE digest does not match the frozen input")
    times_s, observed_hz = load_measurements(rows_path)
    tle_text = tle_path.read_bytes().decode("ascii")
    prior_tle_text = prior_tle_path.read_bytes().decode("ascii")
    catalogue = parse_element_sets(tle_text)
    element_epochs = np.asarray(catalogue.element_epoch_utc_ns(), dtype=np.int64)
    current_records = {
        record.satellite_number: record.text for record in parse_element_set_records(tle_text)
    }
    prior_records = {
        record.satellite_number: record.text for record in parse_element_set_records(prior_tle_text)
    }
    changed_element_ids = sorted(
        satellite_number
        for satellite_number in set(current_records) | set(prior_records)
        if current_records.get(satellite_number) != prior_records.get(satellite_number)
    )

    observed_utc_ns = STREAM_FIRST_SAMPLE_UTC_NS + np.rint(times_s * 1e9).astype(np.int64)
    actual_start_ns = int(observed_utc_ns[0])
    actual_stop_ns = int(observed_utc_ns[-1])
    candidates, accounting = visible_catalogue_indices(
        catalogue, actual_start_ns, actual_stop_ns, arguments.observer
    )

    model_padding_s = WIDE_SHIFT_LIMIT_S + 2.0 * MODEL_GRID_STEP_S
    model_start_ns = actual_start_ns - int(round(model_padding_s * 1e9))
    model_stop_ns = actual_stop_ns + int(round(model_padding_s * 1e9))
    model_grid = sampling_grid(model_start_ns, model_stop_ns, MODEL_GRID_STEP_S)
    tracks = _tracks_for(catalogue, model_grid, arguments.observer, candidates)
    model_time_s = (
        np.asarray(model_grid.utc_ns, dtype=np.int64) - STREAM_FIRST_SAMPLE_UTC_NS
    ) / 1e9
    actual_mask = (model_time_s >= times_s[0]) & (model_time_s <= times_s[-1])
    plausible = tracks.usable & (np.min(tracks.altitude_km, axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM)
    visible_rows = np.flatnonzero(
        plausible & (np.max(tracks.elevation_deg[:, actual_mask], axis=1) > 0.0)
    )
    visible_indices = candidates[visible_rows]
    visible_tracks = ObservedTracks(
        azimuth_deg=tracks.azimuth_deg[visible_rows],
        elevation_deg=tracks.elevation_deg[visible_rows],
        range_km=tracks.range_km[visible_rows],
        range_rate_km_s=tracks.range_rate_km_s[visible_rows],
        altitude_km=tracks.altitude_km[visible_rows],
        usable=tracks.usable[visible_rows],
        anchor_index=tracks.anchor_index,
    )
    accounting["geometric_horizon_union_count"] = int(visible_rows.size)
    accounting["visible_throughout_count"] = int(
        np.count_nonzero(np.min(visible_tracks.elevation_deg[:, actual_mask], axis=1) >= 0.0)
    )
    accounting["ten_degree_union_count"] = int(
        np.count_nonzero(np.max(visible_tracks.elevation_deg[:, actual_mask], axis=1) >= 10.0)
    )
    accounting["ten_degree_throughout_count"] = int(
        np.count_nonzero(np.min(visible_tracks.elevation_deg[:, actual_mask], axis=1) >= 10.0)
    )
    visible_norad_ids = {
        int(catalogue.satellite_numbers[int(catalogue_index)])
        for catalogue_index in visible_indices
    }

    primary_shifts = np.arange(
        -PRIMARY_SHIFT_LIMIT_S,
        PRIMARY_SHIFT_LIMIT_S + PRIMARY_SHIFT_STEP_S / 2.0,
        PRIMARY_SHIFT_STEP_S,
    )
    wide_shifts = np.arange(
        -WIDE_SHIFT_LIMIT_S,
        WIDE_SHIFT_LIMIT_S + WIDE_SHIFT_STEP_S / 2.0,
        WIDE_SHIFT_STEP_S,
    )
    results: list[dict[str, Any]] = []
    full_curves: dict[int, FloatArray] = {}
    primary_profiles: dict[int, tuple[FloatArray, FloatArray]] = {}
    midpoint = int(np.flatnonzero(actual_mask)[len(np.flatnonzero(actual_mask)) // 2])
    reference_utc_ns = STREAM_FIRST_SAMPLE_UTC_NS + int(round(44.4875 * 1e9))

    for row, catalogue_index in enumerate(visible_indices):
        model_hz = np.asarray(
            doppler_shift_hz(RF_FREQUENCY_HZ, visible_tracks.range_rate_km_s[row]),
            dtype=np.float64,
        )
        forward, reverse, full, curve = fit_candidate(
            model_time_s, model_hz, times_s, observed_hz, primary_shifts
        )
        wide_forward, wide_reverse, wide_full, _ = fit_candidate(
            model_time_s, model_hz, times_s, observed_hz, wide_shifts
        )
        zero_forward, zero_reverse, zero_full, _ = fit_candidate(
            model_time_s,
            model_hz,
            times_s,
            observed_hz,
            np.asarray([0.0], dtype=np.float64),
        )
        prediction = prediction_matrix(model_time_s, model_hz, times_s, primary_shifts)
        profile_offsets = np.mean(observed_hz[None, :] - prediction, axis=1)
        profile = np.sqrt(
            np.mean(np.square(observed_hz[None, :] - prediction - profile_offsets[:, None]), axis=1)
        )
        norad = int(catalogue.satellite_numbers[int(catalogue_index)])
        full_curves[norad] = curve
        primary_profiles[norad] = (primary_shifts, profile)
        elevation = visible_tracks.elevation_deg[row, actual_mask]
        result = {
            "name": catalogue.names[int(catalogue_index)],
            "norad_id": norad,
            "catalogue_index": int(catalogue_index),
            "element_epoch_utc_ns": int(element_epochs[int(catalogue_index)]),
            "element_epoch_utc": iso_utc(int(element_epochs[int(catalogue_index)])),
            "element_age_at_reference_h": (
                reference_utc_ns - int(element_epochs[int(catalogue_index)])
            )
            / 3.6e12,
            "minimum_elevation_deg": float(np.min(elevation)),
            "maximum_elevation_deg": float(np.max(elevation)),
            "visible_fraction": float(np.mean(elevation >= 0.0)),
            "ten_degree_fraction": float(np.mean(elevation >= 10.0)),
            "midpoint_azimuth_deg": float(visible_tracks.azimuth_deg[row, midpoint]),
            "midpoint_elevation_deg": float(visible_tracks.elevation_deg[row, midpoint]),
            "midpoint_range_km": float(visible_tracks.range_km[row, midpoint]),
            "midpoint_range_rate_km_s": float(visible_tracks.range_rate_km_s[row, midpoint]),
            "forward_fit": asdict(forward),
            "reverse_fit": asdict(reverse),
            "full_fit": asdict(full),
            "bidirectional_holdout_rms_hz": _rms_pair(forward, reverse, observed_hz.size),
            "zero_shift_forward_fit": asdict(zero_forward),
            "zero_shift_reverse_fit": asdict(zero_reverse),
            "zero_shift_full_fit": asdict(zero_full),
            "zero_shift_bidirectional_holdout_rms_hz": _rms_pair(
                zero_forward, zero_reverse, observed_hz.size
            ),
            "wide_forward_fit": asdict(wide_forward),
            "wide_reverse_fit": asdict(wide_reverse),
            "wide_full_fit": asdict(wide_full),
            "wide_bidirectional_holdout_rms_hz": _rms_pair(
                wide_forward, wide_reverse, observed_hz.size
            ),
        }
        results.append(result)

    ranked = sorted(results, key=lambda item: item["bidirectional_holdout_rms_hz"])
    wide_holdout_ranked = sorted(
        results, key=lambda item: item["wide_bidirectional_holdout_rms_hz"]
    )
    wide_full_ranked = sorted(results, key=lambda item: item["wide_full_fit"]["full_rms_hz"])
    rank_by_norad = {int(item["norad_id"]): rank for rank, item in enumerate(ranked, start=1)}
    wide_holdout_rank_by_norad = {
        int(item["norad_id"]): rank for rank, item in enumerate(wide_holdout_ranked, start=1)
    }
    wide_full_rank_by_norad = {
        int(item["norad_id"]): rank for rank, item in enumerate(wide_full_ranked, start=1)
    }
    for item in results:
        item["primary_rank"] = rank_by_norad[int(item["norad_id"])]
        item["wide_holdout_rank"] = wide_holdout_rank_by_norad[int(item["norad_id"])]
        item["wide_full_rank"] = wide_full_rank_by_norad[int(item["norad_id"])]
    results.sort(key=lambda item: item["primary_rank"])

    fit_png = output_root / "all-visible-satellite-fits.png"
    sky_png = output_root / "all-visible-sky-geometry.png"
    _render_fit(fit_png, times_s, observed_hz, results, full_curves, primary_profiles)
    _render_sky(
        sky_png,
        model_time_s,
        actual_mask,
        visible_tracks,
        visible_indices,
        catalogue,
        results,
    )

    element_age = np.asarray([item["element_age_at_reference_h"] for item in results])
    evidence: dict[str, Any] = {
        "schema": "org.leo.research.visible-starlink-tle-fit/v1",
        "candidate_only": True,
        "input": {
            "capture_id": "cap-20260825T150802-473cb5bbcbd6",
            "stream_id": "stream-1",
            "receiver_id": 1,
            "edge": "upper",
            "capture_manifest_path": str(manifest_path),
            "capture_manifest_sha256": sha256_file(manifest_path),
            "cfo_rows_path": str(rows_path),
            "cfo_rows_sha256": sha256_file(rows_path),
            "cfo_measurement_count": int(observed_hz.size),
            "cfo_measurement_time_semantics": "mean GLRT64 correlation sample centroid",
            "stream_first_sample_utc_ns": STREAM_FIRST_SAMPLE_UTC_NS,
            "stream_first_sample_utc": iso_utc(STREAM_FIRST_SAMPLE_UTC_NS),
            "analysis_start_utc_ns": actual_start_ns,
            "analysis_start_utc": iso_utc(actual_start_ns),
            "analysis_stop_utc_ns": actual_stop_ns,
            "analysis_stop_utc": iso_utc(actual_stop_ns),
            "rf_frequency_hz": RF_FREQUENCY_HZ,
            "frequency_authority": "applied IF plus nominal 9.750 GHz LNB LO; uncalibrated",
            "tle_path": str(tle_path),
            "tle_sha256": sha256_file(tle_path),
            "tle_collected_utc_ns": TLE_COLLECTED_UTC_NS,
            "tle_collected_utc": iso_utc(TLE_COLLECTED_UTC_NS),
            "tle_collection_age_at_first_sample_s": (
                STREAM_FIRST_SAMPLE_UTC_NS - TLE_COLLECTED_UTC_NS
            )
            / 1e9,
            "tle_provider": "Space-Track GP 3LE",
            "analysis_tool_sha256": sha256_file(Path(__file__).resolve()),
        },
        "adjacent_prior_tle_sensitivity": {
            "path": str(prior_tle_path),
            "sha256": sha256_file(prior_tle_path),
            "changed_element_norad_ids": changed_element_ids,
            "changed_element_count": len(changed_element_ids),
            "changed_elements_intersect_visible_population": bool(
                visible_norad_ids.intersection(changed_element_ids)
            ),
        },
        "observer": {
            **resolve_preset(arguments.observer).model_dump(mode="json"),
            "capture_bound": False,
            "antenna_boresight_known": False,
        },
        "method": {
            "model": "observed_CFO(t) = TLE_Doppler(t + tau) + constant_offset",
            "doppler_sign": "received-minus-transmitted; receding range rate is negative shift",
            "nuisance_parameters": ["time_shift_s", "constant_frequency_offset_hz"],
            "forbidden_nuisance_parameters": ["scale", "linear_drift", "curvature"],
            "candidate_set": "plausible Starlinks above geometric horizon at any actual-time knot",
            "candidate_selection_independent_of_time_shift": True,
            "primary_shift_range_s": [-PRIMARY_SHIFT_LIMIT_S, PRIMARY_SHIFT_LIMIT_S],
            "primary_shift_step_s": PRIMARY_SHIFT_STEP_S,
            "wide_sensitivity_shift_range_s": [-WIDE_SHIFT_LIMIT_S, WIDE_SHIFT_LIMIT_S],
            "wide_sensitivity_shift_step_s": WIDE_SHIFT_STEP_S,
            "train_fraction": TRAIN_FRACTION,
            "forward_split": "first 60% train, last 40% held out",
            "reverse_split": "last 60% train, first 40% held out",
            "ranking_metric": "sample-count-weighted RMS of forward and reverse holdouts",
            "propagation_time_semantics": "SGP4 at receive time; no light-time iteration",
        },
        "accounting": accounting,
        "element_age_at_reference_h": {
            "minimum": float(np.min(element_age)),
            "median": float(np.median(element_age)),
            "maximum": float(np.max(element_age)),
        },
        "headline": {
            "primary_best": results[0],
            "wide_holdout_best": wide_holdout_ranked[0],
            "wide_full_best": wide_full_ranked[0],
            "top_ten": results[:10],
        },
        "candidates": results,
        "interpretation_limits": [
            "catalogue candidates are not satellite identifications",
            "observer site is a reviewed preset, not capture-bound GPS",
            "antenna boresight and gain pattern are unknown",
            "constant frequency offsets absorb transmitter, receiver, and LNB offsets",
            "time shift absorbs TLE along-track error, receive-time convention, and clock error",
            "time shift and constant offset are locally confounded for nearly linear Doppler",
            "the wide search is a multiplicity/degeneracy sensitivity, not a clock estimate",
        ],
        "artifacts": {
            "fit_png": {"path": fit_png.name, "sha256": sha256_file(fit_png)},
            "sky_png": {"path": sky_png.name, "sha256": sha256_file(sky_png)},
        },
    }
    evidence_path = output_root / "visible-starlink-tle-fit-evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return evidence


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=Path, default=DEFAULT_ROWS)
    parser.add_argument("--capture-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--tle", type=Path, default=DEFAULT_TLE)
    parser.add_argument("--prior-tle", type=Path, default=DEFAULT_PRIOR_TLE)
    parser.add_argument(
        "--tle-sha256",
        default="9bb59fcf68fa36ce234ae9be79a492f0b92abc23bcf4f040bb5b64b61d3e31ad",
    )
    parser.add_argument(
        "--prior-tle-sha256",
        default="ac79e846bc149d9bbe4a1847eda5fddc9ca6af9fbe3432d6c58cdc33345ceb8a",
    )
    parser.add_argument(
        "--manifest-sha256",
        default="ab55917851a9cd37af94b6145cc719f7b8d9d0809f2202a2dcd1ac38c3e7a31e",
    )
    parser.add_argument("--observer", default="spinnaker-sausalito")
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    evidence = run(arguments())
    best = evidence["headline"]["primary_best"]
    print(
        json.dumps(
            {
                "visible_count": evidence["accounting"]["geometric_horizon_union_count"],
                "best_norad_id": best["norad_id"],
                "best_name": best["name"],
                "best_bidirectional_holdout_rms_hz": best["bidirectional_holdout_rms_hz"],
                "best_full_shift_s": best["full_fit"]["shift_s"],
                "best_full_offset_hz": best["full_fit"]["offset_hz"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
