#!/usr/bin/env python3
"""Deepen the 470384 RX0 alias audit with slope, corpus, TLE, and IQ evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np

from leo.analysis.starlink.acquisition import (
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
    acquire_symbolwise,
)
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
from leo.contracts.sky import ObserverSiteV1
from leo.contracts.states import StarlinkEdge
from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid
from leo.sky.screening import observe_grid
from leo.storage import RecordingStore

SESSION_ID = "cap-20260821T140820-470384cc9284"
STREAM_ID = "stream-0"
RECEIVER_ID = 0
SAMPLE_RATE_HZ = 2_500_000
DOWNLINK_FREQUENCY_HZ = 11_459_687_500.0
LOWER_RAW_ID = "e86860c"
UPPER_RAW_ID = "a9aab7e8"
LOWER_BRANCH_ID = "e7f9ee27"
UPPER_BRANCH_ID = "5852a936"
OBSERVED_GAP_HZ = 220_768.939
GAP_TOLERANCE_HZ = 7_503.329
SLOPE_TOLERANCE_HZ_S = 799.225
MINIMUM_OVERLAP_S = 2.825
GLRT_MARGIN_GATE = 0.05
SITE = ObserverSiteV1(
    latitude_deg=37.858988,
    longitude_deg=-122.478103,
    altitude_m=-29.0,
    label="Spinnaker, Sausalito (illustrative preset; not capture-bound)",
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-root", type=Path, required=True)
    parser.add_argument("--recordings-root", type=Path, required=True)
    parser.add_argument("--tle-snapshot", type=Path, required=True)
    parser.add_argument("--corpus-index", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    return parser.parse_args()


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _representative(document: dict[str, Any], short_id: str) -> dict[str, Any]:
    return next(
        row for row in document["replayed_representatives"] if short_id in row["trajectory_id"]
    )


def _selected_model(document: dict[str, Any], short_id: str) -> dict[str, Any]:
    branch = next(row for row in document["branches"] if short_id in row["branch_id"])
    return next(row for row in branch["models"] if row["model_id"] == branch["selected_model_id"])


def evaluate_model(model: dict[str, Any], time_s: np.ndarray) -> np.ndarray:
    """Evaluate one persisted descending-power CFO polynomial."""

    return np.polyval(
        np.asarray(model["coefficients_hz"], dtype=float),
        np.asarray(time_s, dtype=float) - float(model["reference_time_s"]),
    )


def evaluate_slope(model: dict[str, Any], time_s: np.ndarray) -> np.ndarray:
    """Evaluate the instantaneous derivative of one persisted CFO polynomial."""

    coefficients = np.asarray(model["coefficients_hz"], dtype=float)
    return np.polyval(
        np.polyder(coefficients),
        np.asarray(time_s, dtype=float) - float(model["reference_time_s"]),
    )


def slope_pair_facts(
    lower: dict[str, Any], upper: dict[str, Any], *, points: int = 128
) -> dict[str, Any]:
    """Measure both model slopes over their exact shared interval."""

    start = max(float(lower["start_s"]), float(upper["start_s"]))
    end = min(float(lower["end_s"]), float(upper["end_s"]))
    if end <= start:
        raise ValueError("models do not overlap")
    times = np.linspace(start, end, points)
    lower_slope = evaluate_slope(lower, times)
    upper_slope = evaluate_slope(upper, times)
    difference = upper_slope - lower_slope

    def row(model: dict[str, Any], slopes: np.ndarray) -> dict[str, float]:
        endpoints = np.asarray([start, (start + end) / 2.0, end])
        samples = evaluate_slope(model, endpoints)
        frequency = evaluate_model(model, np.asarray([start, end]))
        return {
            "start_hz_s": float(samples[0]),
            "midpoint_hz_s": float(samples[1]),
            "end_hz_s": float(samples[2]),
            "median_hz_s": float(np.median(slopes)),
            "chord_hz_s": float((frequency[1] - frequency[0]) / (end - start)),
        }

    return {
        "overlap_start_s": start,
        "overlap_end_s": end,
        "overlap_duration_s": end - start,
        "lower": row(lower, lower_slope),
        "upper": row(upper, upper_slope),
        "upper_minus_lower": {
            "median_hz_s": float(np.median(difference)),
            "rms_hz_s": float(np.sqrt(np.mean(difference**2))),
            "maximum_absolute_hz_s": float(np.max(np.abs(difference))),
            "minimum_hz_s": float(np.min(difference)),
            "maximum_hz_s": float(np.max(difference)),
            "chord_hz_s": float(
                row(upper, upper_slope)["chord_hz_s"]
                - row(lower, lower_slope)["chord_hz_s"]
            ),
        },
    }


def pearson_with_fisher_interval(left: np.ndarray, right: np.ndarray) -> dict[str, float]:
    """Return Pearson r and its ordinary Fisher-z 95% interval."""

    x = np.asarray(left, dtype=float)
    y = np.asarray(right, dtype=float)
    if x.shape != y.shape or x.ndim != 1 or x.size < 4:
        raise ValueError("correlation vectors must have the same length of at least four")
    correlation = float(np.corrcoef(x, y)[0, 1])
    clipped = min(max(correlation, -0.999999999), 0.999999999)
    center = math.atanh(clipped)
    half_width = 1.959963984540054 / math.sqrt(x.size - 3)
    return {
        "sample_count": int(x.size),
        "pearson_r": correlation,
        "fisher_95_low": math.tanh(center - half_width),
        "fisher_95_high": math.tanh(center + half_width),
    }


def _initial_pair_facts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    lower_margin = np.asarray([row["lower_glrt_margin"] for row in rows], dtype=float)
    upper_margin = np.asarray([row["upper_glrt_margin"] for row in rows], dtype=float)
    lower_cfo = np.asarray([row["lower_tracking_cfo_hz"] for row in rows], dtype=float)
    upper_cfo = np.asarray([row["upper_tracking_cfo_hz"] for row in rows], dtype=float)
    lower_acquired = np.asarray([row["lower_acquired_cfo_hz"] for row in rows], dtype=float)
    upper_acquired = np.asarray([row["upper_acquired_cfo_hz"] for row in rows], dtype=float)
    epoch_difference = np.asarray(
        [abs(row["upper_local_epoch_sample"] - row["lower_local_epoch_sample"]) for row in rows],
        dtype=int,
    )
    circular_epoch_difference = np.minimum(epoch_difference, 3333 - epoch_difference)
    return {
        "margin_correlation": pearson_with_fisher_interval(lower_margin, upper_margin),
        "tracking_cfo_correlation": pearson_with_fisher_interval(lower_cfo, upper_cfo),
        "acquired_cfo_correlation": pearson_with_fisher_interval(lower_acquired, upper_acquired),
        "circular_epoch_separation_samples": {
            "minimum": int(np.min(circular_epoch_difference)),
            "median": float(np.median(circular_epoch_difference)),
            "maximum": int(np.max(circular_epoch_difference)),
            "median_microseconds": float(
                np.median(circular_epoch_difference) / SAMPLE_RATE_HZ * 1_000_000.0
            ),
            "within_20_samples": int(np.sum(circular_epoch_difference <= 20)),
        },
    }


def _dechirp(
    samples: np.ndarray, sample_start: int, model: dict[str, Any]
) -> np.ndarray:
    times = (sample_start + np.arange(samples.size, dtype=float)) / SAMPLE_RATE_HZ
    delta = times - float(model["reference_time_s"])
    integral = np.polyint(np.asarray(model["coefficients_hz"], dtype=float))
    phase_cycles = np.polyval(integral, delta) - np.polyval(integral, 0.0)
    return np.ascontiguousarray(samples * np.exp(-2j * np.pi * phase_cycles))


def focused_known_pilot_correlation(
    recordings_root: Path,
    matched_rows: list[dict[str, Any]],
    models: dict[str, dict[str, Any]],
    *,
    workers: int,
) -> tuple[dict[str, Any], int]:
    """Replay the shared probes and correlate each trajectory with the known pilot."""

    if not 1 <= workers <= 16:
        raise ValueError("workers must lie in 1..16")
    store = RecordingStore.open_read_only(recordings_root)
    bundle = store.inspect(SESSION_ID)
    source = store.reader(bundle, STREAM_ID, verify=True)
    first = min(int(row["sample_start"]) for row in matched_rows)
    stop = max(int(row["sample_start"]) for row in matched_rows) + 50_000
    payload = source.read(first, stop - first, receiver_ids=(RECEIVER_ID,))
    values = (
        payload[:, 0, 0].astype(np.float64) + 1j * payload[:, 0, 1].astype(np.float64)
    ) / 32_768.0
    calibration = ReceiverFrequencyCalibration("focused-replay", 0.0, "0" * 64)
    acquisition = SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=-20_000.0,
        residual_cfo_max_hz=20_000.0,
        coarse_cfo_step_hz=10_000.0,
        fine_cfo_radius_hz=20_000.0,
        retained_candidate_count=2,
        maximum_probe_samples=50_000,
    )

    def evaluate(task: tuple[str, dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
        name, model, row = task
        sample_start = int(row["sample_start"])
        local = values[sample_start - first : sample_start - first + 50_000]
        corrected = _dechirp(local, sample_start, model)
        acquired = acquire_symbolwise(
            corrected,
            SAMPLE_RATE_HZ,
            calibration,
            edge=StarlinkEdge.UPPER,
            config=acquisition,
        )
        winner = acquired.winner
        if winner is None:
            raise ValueError("focused replay unexpectedly produced no acquisition winner")
        score = conditioned_glrt64_score(
            corrected,
            SAMPLE_RATE_HZ,
            epoch_sample=winner.refined_epoch_sample,
            acquired_cfo_hz=winner.absolute_cfo_hz,
            edge=StarlinkEdge.UPPER,
        )
        return {
            "hypothesis": name,
            "sample_start": sample_start,
            "time_s": float(row["time_s"]),
            "epoch_sample": int(winner.refined_epoch_sample),
            "acquired_residual_cfo_hz": float(winner.absolute_cfo_hz),
            "tracking_residual_cfo_hz": float(score.tracking_cfo_hz),
            "exact_score": float(score.exact_score),
            "control_score": float(score.control_score),
            "margin": float(score.margin),
        }

    tasks = [
        (name, model, row)
        for row in matched_rows
        for name, model in (("lower", models["lower"]), ("upper", models["upper"]))
    ]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        evaluated = list(executor.map(evaluate, tasks))
    evaluated.sort(key=lambda row: (row["time_s"], row["hypothesis"]))
    by_name = {
        name: [row for row in evaluated if row["hypothesis"] == name]
        for name in ("lower", "upper")
    }

    def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        margins = np.asarray([row["margin"] for row in rows], dtype=float)
        return {
            "probe_count": int(margins.size),
            "median_margin": float(np.median(margins)),
            "minimum_margin": float(np.min(margins)),
            "maximum_margin": float(np.max(margins)),
            "q10_margin": float(np.quantile(margins, 0.10)),
            "q90_margin": float(np.quantile(margins, 0.90)),
            "passing_probe_count": int(np.sum(margins >= GLRT_MARGIN_GATE)),
        }

    lower_margin = np.asarray([row["margin"] for row in by_name["lower"]])
    upper_margin = np.asarray([row["margin"] for row in by_name["upper"]])
    stream = next(item for item in bundle.manifest.streams if item.stream_id == STREAM_ID)
    first_sample_utc_ns = int(stream.timing.first_sample.estimate_utc_ns)
    return (
        {
            "method": (
                "trajectory-dechirp, bounded +/-20 kHz symbolwise acquisition, then exact "
                "upper-edge Qin GLRT64/control correlation"
            ),
            "margin_gate": GLRT_MARGIN_GATE,
            "lower": summary(by_name["lower"]),
            "upper": summary(by_name["upper"]),
            "paired_margin_correlation": pearson_with_fisher_interval(
                lower_margin, upper_margin
            ),
            "rows": evaluated,
        },
        first_sample_utc_ns,
    )


def _bulk_product_path(bulk_root: Path, logical_uri: str) -> Path:
    prefix = "bulk://analysis/"
    if not logical_uri.startswith(prefix):
        raise ValueError("corpus index contains a non-analysis URI")
    relative = PurePosixPath(logical_uri.removeprefix("bulk://"))
    if relative.is_absolute() or ".." in relative.parts or len(relative.parts) < 2:
        raise ValueError("corpus index contains an unsafe URI")
    return bulk_root.joinpath(*relative.parts)


def _zero_event_upper_95(trials: int) -> float:
    return 1.0 - 0.05 ** (1.0 / trials)


def corpus_coincidence_facts(index_path: Path, bulk_root: Path) -> dict[str, Any]:
    """Audit replay-validated trajectory pairs in one frozen current-product export."""

    index_rows = list(csv.DictReader(index_path.read_text(encoding="utf-8").splitlines()))
    products: list[tuple[dict[str, str], dict[str, Any]]] = []
    for row in index_rows:
        path = _bulk_product_path(bulk_root, row["logical_uri"])
        payload = path.read_bytes()
        if len(payload) != int(row["byte_size"]):
            raise ValueError(f"catalog byte count mismatch for product {row['id']}")
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        if digest != row["digest"]:
            raise ValueError(f"catalog digest mismatch for product {row['id']}")
        products.append((row, json.loads(payload)))

    pairs = []
    for row, document in products:
        trajectories = document["trajectories"]
        for left_index, left in enumerate(trajectories):
            for right in trajectories[left_index + 1 :]:
                start = max(float(left["start_s"]), float(right["start_s"]))
                end = min(float(left["end_s"]), float(right["end_s"]))
                if end <= start:
                    continue
                times = np.linspace(start, end, 128)
                left_model = {
                    "coefficients_hz": left["absolute_coefficients_hz"],
                    "reference_time_s": left["reference_time_s"],
                }
                right_model = {
                    "coefficients_hz": right["absolute_coefficients_hz"],
                    "reference_time_s": right["reference_time_s"],
                }
                gap = np.abs(evaluate_model(right_model, times) - evaluate_model(left_model, times))
                slope_difference = evaluate_slope(right_model, times) - evaluate_slope(
                    left_model, times
                )
                pairs.append(
                    {
                        "product_id": int(row["id"]),
                        "session_id": row["session_id"],
                        "stream_id": row["stream_id"],
                        "receiver_id": int(row["receiver_id"]),
                        "overlap_s": end - start,
                        "median_gap_hz": float(np.median(gap)),
                        "maximum_slope_difference_hz_s": float(
                            np.max(np.abs(slope_difference))
                        ),
                    }
                )
    duration = [row for row in pairs if row["overlap_s"] >= MINIMUM_OVERLAP_S]
    similar_slope = [
        row
        for row in duration
        if row["maximum_slope_difference_hz_s"] <= SLOPE_TOLERANCE_HZ_S
    ]
    target_gap_any_overlap = [
        row
        for row in pairs
        if abs(row["median_gap_hz"] - OBSERVED_GAP_HZ) <= GAP_TOLERANCE_HZ
    ]
    target = [
        row
        for row in similar_slope
        if abs(row["median_gap_hz"] - OBSERVED_GAP_HZ) <= GAP_TOLERANCE_HZ
    ]
    session_count = len({row["session_id"] for row in index_rows})
    return {
        "index_sha256": _sha256(index_path),
        "product_count": len(products),
        "session_count": session_count,
        "product_id_minimum": min(int(row["id"]) for row in index_rows),
        "product_id_maximum": max(int(row["id"]) for row in index_rows),
        "created_at_minimum": min(row["created_at"] for row in index_rows),
        "created_at_maximum": max(row["created_at"] for row in index_rows),
        "verified_product_count": len(products),
        "final_trajectory_count": sum(len(document["trajectories"]) for _, document in products),
        "overlapping_pair_count": len(pairs),
        "minimum_duration_pair_count": len(duration),
        "minimum_duration_path_count": len({row["product_id"] for row in duration}),
        "similar_slope_pair_count": len(similar_slope),
        "similar_slope_path_count": len({row["product_id"] for row in similar_slope}),
        "target_gap_pair_count_at_any_overlap": len(target_gap_any_overlap),
        "target_like_pair_count": len(target),
        "zero_event_path_rate_upper_95": _zero_event_upper_95(len(products)),
        "zero_event_session_rate_upper_95": _zero_event_upper_95(session_count),
        "largest_gap_among_similar_slope_pairs_hz": (
            max(row["median_gap_hz"] for row in similar_slope) if similar_slope else None
        ),
        "criteria": {
            "minimum_overlap_s": MINIMUM_OVERLAP_S,
            "maximum_slope_difference_hz_s": SLOPE_TOLERANCE_HZ_S,
            "target_median_gap_hz": OBSERVED_GAP_HZ,
            "gap_tolerance_hz": GAP_TOLERANCE_HZ,
        },
        "minimum_duration_pairs": duration,
    }


def tle_geometry_facts(tle_path: Path, capture_start_utc_ns: int) -> dict[str, Any]:
    """Measure illustrative all-sky Starlink pair geometry at the overlap midpoint."""

    catalogue = parse_element_sets(tle_path.read_text(encoding="utf-8"))
    overlap_midpoint_s = (33.65 + 36.475) / 2.0
    overlap_half_width_s = (36.475 - 33.65) / 2.0
    midpoint = capture_start_utc_ns + round(overlap_midpoint_s * 1_000_000_000)
    half_width_ns = round(overlap_half_width_s * 1_000_000_000)
    grid = SamplingGrid(
        (midpoint - half_width_ns, midpoint, midpoint + half_width_ns),
        1,
        overlap_half_width_s,
    )
    tracks = observe_grid(propagate_grid(catalogue, grid), SITE, grid)
    doppler = doppler_shift_hz(DOWNLINK_FREQUENCY_HZ, tracks.range_rate_km_s)
    slopes = (doppler[:, 2] - doppler[:, 0]) / (2.0 * overlap_half_width_s)
    masks = {}
    scatter_20 = []
    for elevation_mask in (0, 10, 20, 30):
        visible = np.flatnonzero(
            tracks.usable
            & (tracks.elevation_deg[:, 1] >= elevation_mask)
            & (tracks.altitude_km[:, 1] >= 120.0)
        )
        pairs = []
        for position, left in enumerate(visible):
            for right in visible[position + 1 :]:
                gap = abs(float(doppler[left, 1] - doppler[right, 1]))
                slope_difference = abs(float(slopes[left] - slopes[right]))
                pairs.append((gap, slope_difference, int(left), int(right)))
        similar_slope = [row for row in pairs if row[1] <= SLOPE_TOLERANCE_HZ_S]
        target = [
            row
            for row in similar_slope
            if abs(row[0] - OBSERVED_GAP_HZ) <= GAP_TOLERANCE_HZ
        ]
        masks[str(elevation_mask)] = {
            "visible_object_count": int(visible.size),
            "pair_count": len(pairs),
            "similar_slope_pair_count": len(similar_slope),
            "target_relative_geometry_pair_count": len(target),
            "target_relative_geometry_pair_fraction": len(target) / len(pairs),
            "minimum_slope_hz_s": float(np.min(slopes[visible])),
            "maximum_slope_hz_s": float(np.max(slopes[visible])),
        }
        if elevation_mask == 20:
            scatter_20 = [
                {"doppler_gap_hz": row[0], "slope_difference_hz_s": row[1]} for row in pairs
            ]
    return {
        "snapshot_sha256": _sha256(tle_path),
        "snapshot_path_name": tle_path.name,
        "catalogue_object_count": len(catalogue),
        "capture_start_utc_ns": capture_start_utc_ns,
        "overlap_midpoint_utc_ns": midpoint,
        "slope_interval_s": 2.0 * overlap_half_width_s,
        "downlink_frequency_hz": DOWNLINK_FREQUENCY_HZ,
        "observer": SITE.model_dump(mode="json"),
        "observer_is_capture_bound": False,
        "antenna_pointing_available": False,
        "elevation_masks": masks,
        "pairs_above_20_degrees": scatter_20,
    }


def _plot_slopes_and_correlation(
    path: Path,
    raw_models: dict[str, dict[str, Any]],
    slopes: dict[str, Any],
    focused: dict[str, Any],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 1, figsize=(14, 10), constrained_layout=True)
    times = np.linspace(slopes["overlap_start_s"], slopes["overlap_end_s"], 300)
    axes[0].plot(
        times,
        evaluate_slope(raw_models["lower"], times) / 1_000.0,
        color="#c2410c",
        linewidth=2.5,
        label=f"lower {LOWER_RAW_ID}",
    )
    axes[0].plot(
        times,
        evaluate_slope(raw_models["upper"], times) / 1_000.0,
        color="#0369a1",
        linewidth=2.5,
        label=f"upper {UPPER_RAW_ID}",
    )
    axes[0].set_ylabel("Instantaneous CFO slope (kHz/s)")
    axes[0].set_title(
        "A · the cubic models have nearly identical chord slopes, but their derivatives cross"
    )
    axes[0].grid(alpha=0.25)
    axes[0].legend()
    axes[0].text(
        0.02,
        0.05,
        f"chord: lower {slopes['lower']['chord_hz_s']/1000:.3f}, "
        f"upper {slopes['upper']['chord_hz_s']/1000:.3f} kHz/s\n"
        f"difference: {slopes['upper_minus_lower']['chord_hz_s']:.1f} Hz/s; "
        f"max instantaneous |difference| "
        f"{slopes['upper_minus_lower']['maximum_absolute_hz_s']:.1f} Hz/s",
        transform=axes[0].transAxes,
        fontsize=10,
        bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "#d1d5db"},
    )

    rows = focused["rows"]
    for name, color, marker in (("lower", "#c2410c", "x"), ("upper", "#0369a1", "o")):
        selected = [row for row in rows if row["hypothesis"] == name]
        axes[1].plot(
            [row["time_s"] for row in selected],
            [row["margin"] for row in selected],
            color=color,
            marker=marker,
            markersize=5,
            linewidth=1.2,
            label=(
                f"{name}: median {focused[name]['median_margin']:.4f}, "
                f"{focused[name]['passing_probe_count']}/{focused[name]['probe_count']} pass"
            ),
        )
    axes[1].axhline(
        GLRT_MARGIN_GATE,
        color="black",
        linestyle=":",
        linewidth=1.5,
        label="automatic absolute-margin floor",
    )
    axes[1].set_xlabel("Time from capture start (s)")
    axes[1].set_ylabel("Exact − control GLRT64 margin")
    axes[1].set_title(
        "B · same-IQ known-pilot correlation is coherent only on the upper trajectory"
    )
    axes[1].grid(alpha=0.25)
    axes[1].legend(fontsize=9, ncol=2)
    figure.suptitle(
        "470384 RX0 · slope similarity is real; independent pilot coherence is not",
        fontweight="bold",
    )
    figure.savefig(path, dpi=180, metadata={"Software": "leo-470384-deep-audit"})
    plt.close(figure)


def _plot_geometry_vs_corpus(
    path: Path, tle: dict[str, Any], corpus: dict[str, Any]
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    figure, axes = plt.subplots(1, 2, figsize=(15, 6.5), constrained_layout=True, sharex=True)
    panels = (
        (
            axes[0],
            tle["pairs_above_20_degrees"],
            "A · TLE geometry above 20° (presence only)",
            "#64748b",
        ),
        (
            axes[1],
            corpus["minimum_duration_pairs"],
            "B · replay-validated final tracks (472 path products)",
            "#0f766e",
        ),
    )
    for axis, rows, title, color in panels:
        x_key = "doppler_gap_hz" if "doppler_gap_hz" in rows[0] else "median_gap_hz"
        y_key = (
            "slope_difference_hz_s"
            if "slope_difference_hz_s" in rows[0]
            else "maximum_slope_difference_hz_s"
        )
        axis.scatter(
            [row[x_key] / 1_000.0 for row in rows],
            [row[y_key] / 1_000.0 for row in rows],
            s=10 if len(rows) > 500 else 28,
            alpha=0.25 if len(rows) > 500 else 0.65,
            color=color,
            edgecolors="none",
        )
        axis.add_patch(
            Rectangle(
                ((OBSERVED_GAP_HZ - GAP_TOLERANCE_HZ) / 1_000.0, 0.0),
                2 * GAP_TOLERANCE_HZ / 1_000.0,
                SLOPE_TOLERANCE_HZ_S / 1_000.0,
                facecolor="#f59e0b",
                edgecolor="#b45309",
                alpha=0.25,
                linewidth=1.5,
                label="470384 relative-geometry window",
            )
        )
        axis.set_xlim(0, 240)
        axis.set_ylim(0, 4)
        axis.set_title(title)
        axis.set_xlabel("Pair frequency/Doppler gap (kHz)")
        axis.grid(alpha=0.2)
        axis.legend(fontsize=8, loc="upper right")
    axes[0].set_ylabel("Maximum/instantaneous slope difference (kHz/s)")
    axes[0].text(
        0.03,
        0.95,
        f"{tle['elevation_masks']['20']['target_relative_geometry_pair_count']} pairs in window",
        transform=axes[0].transAxes,
        va="top",
        fontweight="bold",
    )
    axes[1].text(
        0.03,
        0.95,
        f"{corpus['target_like_pair_count']} pairs in window",
        transform=axes[1].transAxes,
        va="top",
        fontweight="bold",
    )
    figure.suptitle(
        "Two-satellite geometry is plausible; simultaneous validated RF evidence is absent",
        fontweight="bold",
    )
    figure.savefig(path, dpi=180, metadata={"Software": "leo-470384-deep-audit"})
    plt.close(figure)


def main() -> int:
    args = _arguments()
    args.output_root.mkdir(parents=True, exist_ok=True)
    raw = _read(args.artifacts_root / "standard.trajectory-bank.v2.json")
    dealiased = _read(args.artifacts_root / "standard.dealiased-trajectory-bank.v3.json")
    prior = _read(
        Path("reports/figures/2026_08_21_470384_alias_offsets/facts.json")
    )
    raw_models = {
        "lower": _representative(raw, LOWER_RAW_ID),
        "upper": _representative(raw, UPPER_RAW_ID),
    }
    seeded_models = {
        "lower": _selected_model(dealiased, LOWER_BRANCH_ID),
        "upper": _selected_model(dealiased, UPPER_BRANCH_ID),
    }
    slopes = slope_pair_facts(raw_models["lower"], raw_models["upper"])
    seeded_slopes = slope_pair_facts(seeded_models["lower"], seeded_models["upper"])
    matched_rows = prior["matched_probe_rows"]
    focused, capture_start_utc_ns = focused_known_pilot_correlation(
        args.recordings_root,
        matched_rows,
        seeded_models,
        workers=args.workers,
    )
    corpus = corpus_coincidence_facts(args.corpus_index, args.recordings_root)
    tle = tle_geometry_facts(args.tle_snapshot, capture_start_utc_ns)
    _plot_slopes_and_correlation(
        args.output_root / "slope-and-known-pilot-correlation.png",
        raw_models,
        slopes,
        focused,
    )
    _plot_geometry_vs_corpus(
        args.output_root / "geometry-versus-validated-corpus.png", tle, corpus
    )
    tle_pairs = tle["pairs_above_20_degrees"]
    persisted_tle = {key: value for key, value in tle.items() if key != "pairs_above_20_degrees"}
    persisted_tle["pairs_above_20_degrees_sha256"] = hashlib.sha256(
        json.dumps(tle_pairs, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    facts = {
        "session_id": SESSION_ID,
        "scope": "radio_pluto_5d4d / stream-0 / RX0",
        "raw_model_slopes": slopes,
        "seeded_model_slopes": seeded_slopes,
        "initial_same_probe_relationship": _initial_pair_facts(matched_rows),
        "focused_known_pilot_correlation": focused,
        "current_final_corpus": corpus,
        "illustrative_tle_geometry": persisted_tle,
        "interpretation_boundaries": {
            "tle_proves_transmission": False,
            "observer_is_capture_bound": False,
            "antenna_pointing_available": False,
            "raw_frequency_shifted_self_correlation_is_independent_evidence": False,
            "known_pilot_exact_control_correlation_is_independent_absolute_evidence": True,
        },
    }
    (args.output_root / "deeper-facts.json").write_text(
        json.dumps(facts, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
