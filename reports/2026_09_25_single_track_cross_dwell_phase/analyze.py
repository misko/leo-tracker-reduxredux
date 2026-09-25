from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path

import matplotlib
import numpy as np
import zstandard as zstd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.sky.frames import (  # noqa: E402
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets, propagate_grid  # noqa: E402
from leo.sky.sampling import SamplingGrid  # noqa: E402

ROOT = Path("/srv/bulk/leo")
REPORT_DIR = Path(__file__).resolve().parent
SESSION_ID = "scan-fw-e78bf49faf433d04"
RX0_TRACK_ID = "sha256:fa5df2c75d35c6b80c4eadf91c2b7f1070f2979a1bbb9e424d57b7dced2416ca"
RX1_TRACK_ID = "sha256:534fa8ef6d8fb48d167f50c280a5f7ea179d2cd7dab080cd2718732d406e55c5"
SAMPLE_RATE_HZ = 10_000_000
DWELL_SECONDS = 0.120
WINDOW_SAMPLES = 32_768
STRIDE_SAMPLES = 16_384
SYMBOL_RATE_HZ = 250_000_000 / 1100
RX0_RATE_HZ_S = -2943.5589153260344
RX1_RATE_HZ_S = -3128.264324831953
ANCHOR_TIME_S = 100.24439089888244
RX0_ANCHOR_CFO_HZ = -292478.1249999973
RX1_ANCHOR_CFO_HZ = 155405.47901852813
COMMON_START_S = 86.356610555
COMMON_STOP_S = 111.344584533
MAXIMUM_TRACK_RESIDUAL_HZ = 3_500.0
SPEED_OF_LIGHT_M_S = 299_792_458.0
MECHANICAL_BASELINE_M = 0.08
CANDIDATE_CATALOG_NUMBER = 64797
RF_HZ = 11_460_000_000.0
TLE_PATH = Path(
    "/var/lib/leo/tle/archive/space-track/"
    "1790323491043032610-59c9756a5d70ec5681cc6eb84159a5b3ba231d030e895d36741f590391485ef7.tle"
)
OBSERVER = {
    "latitude_deg": 37.858988,
    "longitude_deg": -122.478103,
    "altitude_m": -29.0,
}
EXACT_SHARED_VISITS = (
    637, 638, 644, 654, 655, 657, 661, 665, 668, 670, 674, 677, 679, 682, 687, 688,
    689, 690, 692, 694, 700, 701, 705, 706, 707, 708, 710, 717, 720, 722, 724, 739,
    745, 756, 766, 767, 773, 775, 776, 778, 780, 786, 788, 797, 809, 814, 820,
)


def wrap_rad(value: np.ndarray | float) -> np.ndarray:
    return (np.asarray(value) + np.pi) % (2 * np.pi) - np.pi


def circular_r(phase: np.ndarray, weight: np.ndarray | None = None) -> float:
    phase = np.asarray(phase)
    if weight is None:
        weight = np.ones_like(phase, dtype=float)
    keep = np.isfinite(phase) & np.isfinite(weight) & (weight > 0)
    if not np.any(keep):
        return float("nan")
    return float(abs(np.sum(weight[keep] * np.exp(1j * phase[keep]))) / np.sum(weight[keep]))


def circular_mean(phase: np.ndarray, weight: np.ndarray | None = None) -> float:
    phase = np.asarray(phase)
    if weight is None:
        weight = np.ones_like(phase, dtype=float)
    keep = np.isfinite(phase) & np.isfinite(weight) & (weight > 0)
    return float(np.angle(np.sum(weight[keep] * np.exp(1j * phase[keep]))))


def load_glrt_track_points() -> tuple[dict[int, dict], dict[int, dict], dict]:
    """Bind visits by GLRT lane, support time, and the persisted track line."""
    shared_path = ROOT / "scanner-shared-tracking-v14" / SESSION_ID / "manifest.json"
    shared = json.loads(shared_path.read_text())["document"]
    analysis_root = ROOT / "scanner-adaptive-analysis" / SESSION_ID
    bindings = sorted(analysis_root.glob("*/binding.v8.json"))
    if len(bindings) != 1:
        raise RuntimeError(f"expected one GLRT job, found {len(bindings)}")
    job_root = bindings[0].parent
    binding = json.loads(bindings[0].read_text())["document"]
    rx_points: list[dict[int, dict]] = [{}, {}]
    decompressor = zstd.ZstdDecompressor()
    for visit_path in sorted(job_root.glob("visit-*.v8.json.zst")):
        document = json.loads(decompressor.decompress(visit_path.read_bytes()))["document"]
        if document["target"]["channel"] != 4 or document["target"]["edge"] != "lower":
            continue
        for probe in document["probes"]:
            receiver_id = int(probe["receiver_id"])
            if receiver_id not in (0, 1):
                continue
            passed = [item for item in probe["candidates"] if item["passed_fractional_margin_gate"]]
            if not passed:
                continue
            rate = RX0_RATE_HZ_S if receiver_id == 0 else RX1_RATE_HZ_S
            anchor = RX0_ANCHOR_CFO_HZ if receiver_id == 0 else RX1_ANCHOR_CFO_HZ

            def residual(item: dict, anchor_hz: float = anchor, rate_hz_s: float = rate) -> float:
                expected = anchor_hz + rate_hz_s * (item["fractional_time_s"] - ANCHOR_TIME_S)
                return float(item["fractional_tracking_cfo_hz"] - expected)

            candidate = min(passed, key=lambda item: abs(residual(item)))
            time_s = float(candidate["fractional_time_s"])
            line_residual_hz = residual(candidate)
            visit_index = int(document["visit_index"])
            if visit_index not in EXACT_SHARED_VISITS:
                continue
            rx_points[receiver_id][visit_index] = {
                "visit_index": visit_index,
                "receiver_id": receiver_id,
                "tracking_cfo_hz": float(candidate["fractional_tracking_cfo_hz"]),
                "tracking_time_s": time_s,
                "track_line_residual_hz": line_residual_hz,
                "candidate_rank": int(candidate["candidate_rank"]),
                "valid_start_counter": int(document["valid_start_counter"]),
            }
    authority = {
        "shared_tracking_analysis_id": shared["analysis_id"],
        "shared_tracking_input_manifest_sha256": shared["input_manifest_sha256"],
        "glrt_binding_path": str(bindings[0]),
        "glrt_input_manifest_sha256": binding["input_manifest_sha256"],
        "track_binding_method": "phase-blind lane/time/line-residual replay",
        "maximum_track_residual_hz": MAXIMUM_TRACK_RESIDUAL_HZ,
    }
    return rx_points[0], rx_points[1], authority


@lru_cache(maxsize=1)
def _load_chunk(path_text: str, maximum_bytes: int) -> np.ndarray:
    compressed = Path(path_text).read_bytes()
    raw = zstd.ZstdDecompressor().decompress(compressed, max_output_size=maximum_bytes)
    return np.frombuffer(raw, dtype="<i2").reshape(-1, 2, 2)


def load_visit(visit_index: int) -> tuple[np.ndarray, dict]:
    session_root = ROOT / "scanner-adaptive-recordings" / SESSION_ID
    manifest = json.loads((session_root / "manifest.json").read_text())["manifest"]
    if manifest["timing"]["sample_rate_hz"] != SAMPLE_RATE_HZ:
        raise RuntimeError("sample-rate mismatch")
    chunk = next(
        item
        for item in manifest["chunks"]
        if item["first_visit_index"]
        <= visit_index
        < item["first_visit_index"] + item["visit_count"]
    )
    compressed = (session_root / chunk["relative_path"]).read_bytes()
    if "sha256:" + hashlib.sha256(compressed).hexdigest() != chunk["compressed_sha256"]:
        raise RuntimeError("compressed IQ digest mismatch")
    packed = _load_chunk(str(session_root / chunk["relative_path"]), chunk["uncompressed_bytes"])
    sample_count = round(SAMPLE_RATE_HZ * DWELL_SECONDS)
    offset = (visit_index - chunk["first_visit_index"]) * sample_count
    packed = packed[offset : offset + sample_count]
    iq = np.empty((sample_count, 2), dtype=np.complex64)
    iq.real = packed[:, :, 0]
    iq.imag = packed[:, :, 1]
    return iq, {"chunk_compressed_sha256": chunk["compressed_sha256"]}


def window_starts() -> np.ndarray:
    sample_count = round(SAMPLE_RATE_HZ * DWELL_SECONDS)
    starts = (
        np.arange(0, sample_count - STRIDE_SAMPLES + 1, STRIDE_SAMPLES, dtype=int)
        - STRIDE_SAMPLES // 2
    )
    return starts[(starts >= 0) & (starts + WINDOW_SAMPLES <= sample_count)]


def correction_cycles(times_s: np.ndarray, frequency_hz: float, rate_hz_s: float) -> np.ndarray:
    centered = times_s - DWELL_SECONDS / 2
    return frequency_hz * times_s + 0.5 * rate_hz_s * (
        centered**2 - (DWELL_SECONDS / 2) ** 2
    )


def direct_phasors(
    iq: np.ndarray, frequency_hz: float, rate_hz_s: float, starts: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    taper = np.hanning(WINDOW_SAMPLES)
    phasors = []
    coherence = []
    for start in starts:
        times = np.arange(start, start + WINDOW_SAMPLES) / SAMPLE_RATE_HZ
        left = iq[start : start + WINDOW_SAMPLES, 0].astype(np.complex128)
        right = iq[start : start + WINDOW_SAMPLES, 1].astype(np.complex128)
        right *= np.exp(-2j * np.pi * correction_cycles(times, frequency_hz, rate_hz_s))
        phasor = np.sum(np.conj(left) * right * taper**2)
        denominator = math.sqrt(
            max(float(np.sum(abs(left * taper) ** 2) * np.sum(abs(right * taper) ** 2)), 1e-30)
        )
        phasors.append(phasor)
        coherence.append(abs(phasor) / denominator)
    centers = (starts + (WINDOW_SAMPLES - 1) / 2) / SAMPLE_RATE_HZ
    return np.asarray(phasors), np.asarray(coherence), centers


def fit_relative_carrier(
    iq: np.ndarray, seed_hz: float, starts: np.ndarray
) -> tuple[float, float, float]:
    seeded, _, centers = direct_phasors(iq, seed_hz, 0.0, starts)
    coarse_offsets = np.arange(-100.0, 100.001, 1.0)
    coarse_score = abs(
        np.exp(-2j * np.pi * coarse_offsets[:, None] * centers[None, :]) @ seeded
    )
    constant = seed_hz + float(coarse_offsets[int(np.argmax(coarse_score))])
    constant_phasors, _, centers = direct_phasors(iq, constant, 0.0, starts)
    centered = centers - DWELL_SECONDS / 2
    frequency_offsets = np.arange(-30.0, 30.001, 0.5)
    frequency_rotation = np.exp(-2j * np.pi * frequency_offsets[:, None] * centers[None, :])
    best = (-1.0, 0.0, 0.0)
    for rate in np.arange(-3000.0, 3000.1, 25.0):
        rate_phasors = constant_phasors * np.exp(
            -1j * np.pi * rate * (centered**2 - (DWELL_SECONDS / 2) ** 2)
        )
        score = abs(frequency_rotation @ rate_phasors)
        index = int(np.argmax(score))
        candidate = (float(score[index]), float(frequency_offsets[index]), float(rate))
        if candidate[0] > best[0]:
            best = candidate
    frequency_hz = constant + best[1]
    final, _, _ = direct_phasors(iq, frequency_hz, best[2], starts)
    return frequency_hz, best[2], circular_r(np.angle(final), abs(final))


def branch_resolve(raw_delta_hz: float, reference_hz: float) -> float:
    branch = round((reference_hz - raw_delta_hz) / SYMBOL_RATE_HZ)
    return raw_delta_hz + branch * SYMBOL_RATE_HZ


def expected_satellite_phase(rows: list[dict], track_points: dict) -> dict:
    """Predict zero-referenced geometric phase for fixed baseline orientations."""
    recording_path = ROOT / "scanner-adaptive-recordings" / SESSION_ID / "manifest.json"
    timing = json.loads(recording_path.read_text())["manifest"]["timing"]
    first_utc_ns = int(timing["first_sample_estimate_utc_ns"])
    session_counter = int(timing["session_start_device_sample_counter"])
    reference_counter = min(int(point["valid_start_counter"]) for point in track_points["rx0"])
    utc_ns = tuple(
        first_utc_ns
        + round(
            (reference_counter + row["track_time_s"] * SAMPLE_RATE_HZ - session_counter)
            * 1e9
            / SAMPLE_RATE_HZ
        )
        for row in rows
    )
    spacing_s = float(np.median(np.diff([row["track_time_s"] for row in rows])))
    grid = SamplingGrid(utc_ns, 0, spacing_s)
    catalogue = parse_element_sets(TLE_PATH.read_text())
    try:
        candidate_index = catalogue.satellite_numbers.index(CANDIDATE_CATALOG_NUMBER)
    except ValueError as error:
        raise RuntimeError("candidate satellite is absent from the frozen TLE snapshot") from error
    propagated = propagate_grid(catalogue, grid, indices=[candidate_index])
    if not bool(propagated.usable[0]):
        raise RuntimeError("candidate TLE propagation failed")
    julian_day, fraction = julian_day_from_utc_ns(np.asarray(utc_ns, dtype=np.int64))
    gmst = greenwich_mean_sidereal_time_rad(julian_day, fraction)
    position_ecef, _ = teme_to_ecef(
        propagated.position_teme_km[0], propagated.velocity_teme_km_s[0], gmst
    )
    receiver_ecef = geodetic_to_ecef_km(**OBSERVER)
    relative_ecef = position_ecef - receiver_ecef
    enu = relative_ecef @ ecef_to_enu_matrix(
        OBSERVER["latitude_deg"], OBSERVER["longitude_deg"]
    ).T
    unit_enu = enu / np.linalg.norm(enu, axis=1)[:, None]
    scale_deg = 360.0 * RF_HZ * MECHANICAL_BASELINE_M / SPEED_OF_LIGHT_M_S
    orientations = {
        "north–south (az 0°)": np.asarray([0.0, 1.0, 0.0]),
        "northeast (az 45°)": np.asarray([math.sqrt(0.5), math.sqrt(0.5), 0.0]),
        "nominal axis (az 79°)": np.asarray(
            [math.sin(math.radians(79.0)), math.cos(math.radians(79.0)), 0.0]
        ),
        "east–west (az 90°)": np.asarray([1.0, 0.0, 0.0]),
        "vertical": np.asarray([0.0, 0.0, 1.0]),
    }
    curves = {}
    for label, baseline_unit in orientations.items():
        absolute_deg = scale_deg * (unit_enu @ baseline_unit)
        curves[label] = (absolute_deg - absolute_deg[0]).tolist()
    direction_change = unit_enu - unit_enu[0]
    envelope_deg = scale_deg * np.linalg.norm(direction_change, axis=1)
    azimuth_deg = np.mod(np.degrees(np.arctan2(unit_enu[:, 0], unit_enu[:, 1])), 360.0)
    elevation_deg = np.degrees(
        np.arctan2(unit_enu[:, 2], np.hypot(unit_enu[:, 0], unit_enu[:, 1]))
    )
    return {
        "candidate_catalog_number": CANDIDATE_CATALOG_NUMBER,
        "candidate_only": True,
        "identity_claimed": False,
        "rf_hz": RF_HZ,
        "mechanical_baseline_m": MECHANICAL_BASELINE_M,
        "reference_policy": (
            "geometric phase change relative to first shared dwell; no phase intercept"
        ),
        "track_time_s": [row["track_time_s"] for row in rows],
        "utc_ns": list(utc_ns),
        "azimuth_deg": azimuth_deg.tolist(),
        "elevation_deg": elevation_deg.tolist(),
        "orientation_phase_change_deg": curves,
        "unknown_orientation_envelope_deg": envelope_deg.tolist(),
    }


def analyze() -> dict:
    rx0_points, rx1_points, authority = load_glrt_track_points()
    shared_visits = sorted(set(rx0_points) & set(rx1_points))
    if not shared_visits:
        raise RuntimeError("selected tracks have no shared visits")
    raw_deltas = np.asarray(
        [
            rx1_points[index]["tracking_cfo_hz"] - rx0_points[index]["tracking_cfo_hz"]
            for index in shared_visits
        ]
    )
    # A single phase-blind session-level receiver-offset seed is used for every dwell.
    # The whole-dwell IQ fit then refines frequency and rate independently per dwell.
    branch_reference_hz = 674_853.3580860491
    resolved_seeds = np.full(len(shared_visits), branch_reference_hz)
    starts = window_starts()
    rows = []
    traces = []
    reference_counter = min(rx0_points[index]["valid_start_counter"] for index in shared_visits)
    for visit_index, raw_delta_hz, seed_hz in zip(
        shared_visits, raw_deltas, resolved_seeds, strict=True
    ):
        iq, provenance = load_visit(visit_index)
        frequency_hz, rate_hz_s, fitted_r = fit_relative_carrier(iq, float(seed_hz), starts)
        phasors, coherence, centers = direct_phasors(iq, frequency_hz, rate_hz_s, starts)
        phase = np.angle(phasors)
        mean_phase = circular_mean(phase, abs(phasors))
        absolute_centers = (
            rx0_points[visit_index]["valid_start_counter"] - reference_counter
        ) / SAMPLE_RATE_HZ + centers
        row = {
            "visit_index": visit_index,
            "track_time_s": float(np.mean(absolute_centers)),
            "start_time_s": float(absolute_centers[0]),
            "stop_time_s": float(absolute_centers[-1]),
            "rx0_tracking_cfo_hz": rx0_points[visit_index]["tracking_cfo_hz"],
            "rx1_tracking_cfo_hz": rx1_points[visit_index]["tracking_cfo_hz"],
            "rx0_track_line_residual_hz": rx0_points[visit_index]["track_line_residual_hz"],
            "rx1_track_line_residual_hz": rx1_points[visit_index]["track_line_residual_hz"],
            "raw_track_delta_hz": float(raw_delta_hz),
            "branch_resolved_seed_hz": float(seed_hz),
            "fitted_relative_frequency_hz": frequency_hz,
            "fitted_relative_rate_hz_s": rate_hz_s,
            "phase_resultant": fitted_r,
            "mean_phase_deg": math.degrees(mean_phase),
            "median_coherence": float(np.median(coherence)),
            "window_count": len(starts),
            **provenance,
        }
        rows.append(row)
        traces.append(
            {
                "visit_index": visit_index,
                "dwell_time_ms": centers * 1000,
                "track_time_s": absolute_centers,
                "phase_deg": np.degrees(phase),
                "unwrapped_phase_deg": np.degrees(np.unwrap(phase)),
                "centered_phase_deg": np.degrees(wrap_rad(phase - mean_phase)),
                "coherence": coherence,
            }
        )
        print(
            f"visit {visit_index}: seed={seed_hz:.3f} Hz fit={frequency_hz:.3f} Hz "
            f"rate={rate_hz_s:.1f} Hz/s R={fitted_r:.3f} coh={np.median(coherence):.4f}",
            flush=True,
        )

    phases = np.radians([row["mean_phase_deg"] for row in rows])
    adjacent_steps = wrap_rad(np.diff(phases))
    absolute_resultant = circular_r(phases)
    adjacent_step_resultant = circular_r(adjacent_steps) if len(adjacent_steps) else float("nan")
    centered = np.asarray([trace["centered_phase_deg"] for trace in traces])
    shape_pair_r = []
    adjacent_shape_r = []
    for left in range(len(centered)):
        for right in range(left + 1, len(centered)):
            delta = np.radians(centered[left] - centered[right])
            similarity = circular_r(delta)
            shape_pair_r.append(similarity)
            if right == left + 1:
                adjacent_shape_r.append(similarity)
    rng = np.random.default_rng(20260925)
    permutation_adjacent_r = []
    permutation_adjacent_shape = []
    for _ in range(10_000):
        order = rng.permutation(len(phases))
        permutation_adjacent_r.append(circular_r(wrap_rad(np.diff(phases[order]))))
        permutation_adjacent_shape.append(
            float(
                np.median(
                    [
                        circular_r(np.radians(centered[left] - centered[right]))
                        for left, right in zip(order[:-1], order[1:], strict=True)
                    ]
                )
            )
        )
    uniform_resultants = np.asarray(
        [circular_r(rng.uniform(-np.pi, np.pi, len(phases))) for _ in range(10_000)]
    )
    summary = {
        "shared_dwell_count": len(rows),
        "track_span_s": rows[-1]["track_time_s"] - rows[0]["track_time_s"],
        "median_within_dwell_phase_resultant": float(
            np.median([row["phase_resultant"] for row in rows])
        ),
        "minimum_within_dwell_phase_resultant": float(
            np.min([row["phase_resultant"] for row in rows])
        ),
        "absolute_dwell_mean_phase_resultant": absolute_resultant,
        "absolute_phase_uniform_null_p": float(
            (1 + np.sum(uniform_resultants >= absolute_resultant)) / 10_001
        ),
        "adjacent_phase_step_resultant": adjacent_step_resultant,
        "adjacent_step_order_permutation_p": float(
            (1 + np.sum(np.asarray(permutation_adjacent_r) >= adjacent_step_resultant)) / 10_001
        ),
        "median_abs_adjacent_phase_step_deg": float(np.median(abs(np.degrees(adjacent_steps))))
        if len(adjacent_steps)
        else None,
        "median_centered_shape_pair_resultant": float(np.median(shape_pair_r))
        if shape_pair_r
        else None,
        "median_adjacent_centered_shape_resultant": float(np.median(adjacent_shape_r)),
        "adjacent_shape_order_permutation_p": float(
            (
                1
                + np.sum(
                    np.asarray(permutation_adjacent_shape) >= float(np.median(adjacent_shape_r))
                )
            )
            / 10_001
        ),
        "continuous_cycle_count_resolved": False,
        "per_dwell_phase_intercepts_fitted": False,
        "relative_timing_delay_samples": 0,
        "complex_channel_response_used": False,
    }
    serialized_track_points = {
        "rx0": [rx0_points[index] for index in sorted(rx0_points)],
        "rx1": [rx1_points[index] for index in sorted(rx1_points)],
    }
    satellite_phase = expected_satellite_phase(rows, serialized_track_points)
    return {
        "schema_version": 1,
        "session_id": SESSION_ID,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "track_ids": [RX0_TRACK_ID, RX1_TRACK_ID],
        "channel": 4,
        "edge": "lower",
        "selection_uses_phase": False,
        "branch_reference_hz": branch_reference_hz,
        "carrier_seed_policy": "one fixed phase-blind session seed for every dwell",
        "authority": authority,
        "track_points": serialized_track_points,
        "expected_satellite_phase": satellite_phase,
        "rows": rows,
        "traces": [
            {
                key: value.tolist() if isinstance(value, np.ndarray) else value
                for key, value in trace.items()
            }
            for trace in traces
        ],
        "adjacent_steps_deg": np.degrees(adjacent_steps).tolist(),
        "summary": summary,
    }


def plot(document: dict) -> None:
    rows = document["rows"]
    traces = document["traces"]
    count = len(rows)
    columns = 3
    rows_count = math.ceil(count / columns)
    figure, axes = plt.subplots(
        rows_count,
        columns,
        figsize=(14.0, 2.75 * rows_count),
        sharex=True,
        sharey=True,
        squeeze=False,
    )
    for axis, row, trace in zip(axes.flat, rows, traces, strict=False):
        axis.plot(trace["dwell_time_ms"], trace["phase_deg"], ".-", linewidth=1.0, markersize=2.5)
        axis.set_title(
            f"visit {row['visit_index']} · t={row['track_time_s']:.2f} s · "
            f"R={row['phase_resultant']:.3f}"
        )
        axis.set_ylim(-185, 185)
        axis.set_yticks([-180, -90, 0, 90, 180])
        axis.grid(alpha=0.22)
    for axis in axes.flat[count:]:
        axis.set_visible(False)
    for axis in axes[-1]:
        axis.set_xlabel("time within dwell (ms)")
    for axis in axes[:, 0]:
        axis.set_ylabel("RX1−RX0 phase (deg)")
    figure.suptitle("One dual-RX track: absolute per-window phase in every shared dwell")
    figure.tight_layout(rect=(0, 0, 1, 0.985))
    figure.savefig(REPORT_DIR / "all-dwell-phase.png", dpi=180, facecolor="white")
    plt.close(figure)

    figure, axes = plt.subplots(
        rows_count,
        columns,
        figsize=(14.0, 2.75 * rows_count),
        sharex=True,
        sharey=False,
        squeeze=False,
    )
    for axis, row, trace in zip(axes.flat, rows, traces, strict=False):
        axis.plot(
            trace["dwell_time_ms"],
            trace["unwrapped_phase_deg"],
            ".-",
            linewidth=1.0,
            markersize=2.5,
        )
        axis.set_title(f"visit {row['visit_index']} · R={row['phase_resultant']:.3f}")
        axis.grid(alpha=0.22)
    for axis in axes.flat[count:]:
        axis.set_visible(False)
    for axis in axes[-1]:
        axis.set_xlabel("time within dwell (ms)")
    for axis in axes[:, 0]:
        axis.set_ylabel("unwrapped phase (deg)")
    figure.suptitle("One dual-RX track: unwrapped phase within each dwell (no cross-dwell unwrap)")
    figure.tight_layout(rect=(0, 0, 1, 0.985))
    figure.savefig(REPORT_DIR / "all-dwell-phase-unwrapped.png", dpi=180, facecolor="white")
    plt.close(figure)

    figure, axes = plt.subplots(2, 1, figsize=(13.5, 8.0), sharex=False)
    for trace in traces:
        axes[0].plot(trace["track_time_s"], trace["phase_deg"], ".-", linewidth=1.0, markersize=2.3)
    axes[0].set_ylabel("absolute RX1−RX0 phase (deg)")
    axes[0].set_ylim(-185, 185)
    axes[0].set_yticks([-180, -90, 0, 90, 180])
    axes[0].set_xlabel("track time (s)")
    axes[0].grid(alpha=0.22)
    axes[0].set_title("Absolute phase: dwells are not joined across retunes")
    x = [row["track_time_s"] for row in rows]
    y = [row["mean_phase_deg"] for row in rows]
    axes[1].plot(x, y, "o-", linewidth=1.0)
    for row in rows:
        axes[1].annotate(
            str(row["visit_index"]),
            (row["track_time_s"], row["mean_phase_deg"]),
            xytext=(0, 7),
            textcoords="offset points",
            ha="center",
            fontsize=7,
        )
    axes[1].set_ylim(-185, 185)
    axes[1].set_yticks([-180, -90, 0, 90, 180])
    axes[1].set_xlabel("track time (s)")
    axes[1].set_ylabel("circular mean phase (deg)")
    axes[1].grid(alpha=0.22)
    axes[1].set_title("Dwell-level absolute phase summary")
    figure.suptitle("Cross-dwell phase relationship on the same phase-blind track")
    figure.tight_layout()
    figure.savefig(REPORT_DIR / "track-timeline.png", dpi=180, facecolor="white")
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(11.5, 5.2))
    for row, trace in zip(rows, traces, strict=True):
        axis.plot(
            trace["dwell_time_ms"],
            trace["centered_phase_deg"],
            linewidth=0.85,
            alpha=0.75,
            label=str(row["visit_index"]),
        )
    axis.set_xlabel("time within dwell (ms)")
    axis.set_ylabel("phase minus dwell circular mean (deg)")
    axis.set_ylim(-185, 185)
    axis.grid(alpha=0.22)
    axis.set_title("Shape-only comparison (centering is display-only, not fitted)")
    axis.legend(title="visit", ncol=5, fontsize=7)
    figure.tight_layout()
    figure.savefig(REPORT_DIR / "centered-shape-comparison.png", dpi=180, facecolor="white")
    plt.close(figure)

    figure, axes = plt.subplots(
        rows_count,
        columns,
        figsize=(14.0, 2.75 * rows_count),
        sharex=True,
        sharey=True,
        squeeze=False,
    )
    for axis, row, trace in zip(axes.flat, rows, traces, strict=False):
        mean_phase = row["mean_phase_deg"]
        axis.plot(
            trace["dwell_time_ms"],
            trace["phase_deg"],
            ".-",
            color="0.68",
            linewidth=0.8,
            markersize=2.0,
            label="window phase",
        )
        axis.axhline(
            mean_phase,
            color="tab:orange",
            linewidth=1.8,
            label="circular mean",
        )
        axis.set_title(
            f"visit {row['visit_index']} · mean={mean_phase:+.1f}° · "
            f"R={row['phase_resultant']:.3f}"
        )
        axis.set_ylim(-185, 185)
        axis.set_yticks([-180, -90, 0, 90, 180])
        axis.grid(alpha=0.22)
    for axis in axes.flat[count:]:
        axis.set_visible(False)
    for axis in axes[-1]:
        axis.set_xlabel("time within dwell (ms)")
    for axis in axes[:, 0]:
        axis.set_ylabel("RX1−RX0 phase (deg)")
    figure.suptitle("Circular-aware mean phase in every shared dwell", y=0.996)
    figure.tight_layout(rect=(0, 0, 1, 0.975))
    figure.savefig(REPORT_DIR / "all-dwell-circular-means.png", dpi=180, facecolor="white")
    plt.close(figure)

    track_time = np.asarray([row["track_time_s"] for row in rows])
    mean_phase = np.asarray([row["mean_phase_deg"] for row in rows])
    resultant = np.asarray([row["phase_resultant"] for row in rows])
    full_track_mean = math.degrees(circular_mean(np.radians(mean_phase)))
    full_track_r = circular_r(np.radians(mean_phase))
    figure, axis = plt.subplots(figsize=(13.5, 5.6))
    scatter = axis.scatter(
        track_time,
        mean_phase,
        c=resultant,
        cmap="viridis",
        vmin=0.5,
        vmax=1.0,
        s=58,
        zorder=3,
    )
    for row in rows:
        axis.annotate(
            str(row["visit_index"]),
            (row["track_time_s"], row["mean_phase_deg"]),
            xytext=(0, 7),
            textcoords="offset points",
            ha="center",
            fontsize=7,
        )
    axis.axhline(
        full_track_mean,
        color="tab:orange",
        linestyle="--",
        linewidth=1.3,
        label=f"full-track circular mean {full_track_mean:+.1f}° (R={full_track_r:.3f})",
    )
    axis.set_xlabel("track time from first shared dwell (s)")
    axis.set_ylabel("circular-aware RX1−RX0 mean phase (deg)")
    axis.set_ylim(-185, 185)
    axis.set_yticks([-180, -90, 0, 90, 180])
    axis.grid(alpha=0.22)
    axis.set_title("Per-dwell circular mean over the full dual-RX track")
    axis.legend(loc="lower left", frameon=False)
    axis.text(
        0.995,
        0.02,
        "−180° and +180° are the same circular direction",
        transform=axis.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        color="0.35",
    )
    colorbar = figure.colorbar(scatter, ax=axis, pad=0.015)
    colorbar.set_label("within-dwell phase concentration R")
    figure.tight_layout()
    figure.savefig(REPORT_DIR / "circular-mean-over-track.png", dpi=180, facecolor="white")
    plt.close(figure)

    geometry = document["expected_satellite_phase"]
    geometry_time = np.asarray(geometry["track_time_s"])
    figure, axes = plt.subplots(2, 1, figsize=(13.5, 9.0), sharex=True)
    phase_scatter = axes[0].scatter(
        track_time,
        mean_phase,
        c=resultant,
        cmap="viridis",
        vmin=0.5,
        vmax=1.0,
        s=48,
        zorder=3,
    )
    axes[0].set_ylabel("measured circular mean (deg)")
    axes[0].set_ylim(-185, 185)
    axes[0].set_yticks([-180, -90, 0, 90, 180])
    axes[0].grid(alpha=0.22)
    axes[0].set_title("Measured absolute RX1−RX0 phase (instrument-inclusive)")
    colorbar = figure.colorbar(phase_scatter, ax=axes[0], pad=0.015)
    colorbar.set_label("within-dwell R")
    east_west = np.asarray(
        geometry["orientation_phase_change_deg"]["east–west (az 90°)"]
    )
    axes[1].plot(
        geometry_time,
        east_west,
        linewidth=2.0,
        label="RX1 east of RX0",
    )
    axes[1].plot(
        geometry_time,
        -east_west,
        linewidth=2.0,
        linestyle="--",
        label="RX1 west of RX0",
    )
    axes[1].axhline(0.0, color="0.2", linewidth=0.8)
    axes[1].set_xlabel("track time from first shared dwell (s)")
    axes[1].set_ylabel("expected geometric phase change (deg)")
    axes[1].grid(alpha=0.22)
    axes[1].set_title(
        "Candidate 64797 progression for the known east–west baseline "
        "(zero-referenced; sign depends on receiver order)"
    )
    axes[1].legend(loc="best", frameon=False)
    figure.suptitle("Measured dwell means and east–west satellite phase progression")
    figure.tight_layout()
    figure.savefig(
        REPORT_DIR / "expected-satellite-phase-progression.png", dpi=180, facecolor="white"
    )
    plt.close(figure)


def main() -> None:
    document = analyze()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "results.json").write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    plot(document)
    print(json.dumps(document["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
