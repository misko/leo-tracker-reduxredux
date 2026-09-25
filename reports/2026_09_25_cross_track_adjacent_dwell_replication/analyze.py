from __future__ import annotations

import hashlib
import json
import math
from functools import cache
from pathlib import Path

import matplotlib
import numpy as np
import zstandard as zstd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPORT_DIR = Path(__file__).resolve().parent
SELECTION_PATH = REPORT_DIR / "selection.json"
RECORDING_ROOT = Path("/srv/bulk/leo/scanner-adaptive-recordings")
ANALYSIS_ROOT = Path("/srv/bulk/leo/scanner-adaptive-analysis")
WINDOW_SECONDS = 409.6e-6
STRIDE_SECONDS = 204.8e-6
FREQUENCY_POLYNOMIAL_DEGREE = 2
BOOTSTRAP_COUNT = 1_000
NULL_TRIALS = 2_000_000
RNG_SEED = 20_260_925
PRESELECTED_DETAIL_TRACK = "T3"


def wrap_rad(value: np.ndarray | float) -> np.ndarray:
    return (np.asarray(value) + np.pi) % (2 * np.pi) - np.pi


def circular_r(phase: np.ndarray) -> float:
    return float(abs(np.mean(np.exp(1j * np.asarray(phase)))))


def circular_mean_deg(phase: np.ndarray) -> float:
    return float(np.degrees(np.angle(np.mean(np.exp(1j * np.asarray(phase))))))


@cache
def load_manifest(session_id: str) -> dict:
    path = RECORDING_ROOT / session_id / "manifest.json"
    return json.loads(path.read_text())["manifest"]


@cache
def load_visit_metadata(session_id: str, visit_index: int) -> dict:
    roots = sorted((ANALYSIS_ROOT / session_id).glob("*/binding.v*.json"))
    if len(roots) != 1:
        raise RuntimeError(f"expected one analysis job for {session_id}, found {len(roots)}")
    matches = sorted(roots[0].parent.glob(f"visit-{visit_index:06d}.v*.json.zst"))
    if len(matches) != 1:
        raise RuntimeError(f"expected one visit document for {session_id}/{visit_index}")
    raw = zstd.ZstdDecompressor().decompress(matches[0].read_bytes())
    return json.loads(raw)["document"]


@cache
def load_chunk(path_text: str, maximum_bytes: int) -> np.ndarray:
    raw = zstd.ZstdDecompressor().decompress(
        Path(path_text).read_bytes(), max_output_size=maximum_bytes
    )
    return np.frombuffer(raw, dtype="<i2").reshape(-1, 2, 2)


def load_visit(session_id: str, visit_index: int) -> tuple[np.ndarray, float, int]:
    manifest = load_manifest(session_id)
    rate = float(manifest["timing"]["sample_rate_hz"])
    chunk = next(
        row
        for row in manifest["chunks"]
        if row["first_visit_index"]
        <= visit_index
        < row["first_visit_index"] + row["visit_count"]
    )
    path = RECORDING_ROOT / session_id / chunk["relative_path"]
    compressed = path.read_bytes()
    if "sha256:" + hashlib.sha256(compressed).hexdigest() != chunk["compressed_sha256"]:
        raise RuntimeError("compressed IQ digest mismatch")
    packed = load_chunk(str(path), int(chunk["uncompressed_bytes"]))
    samples_per_visit = int(chunk["sample_count"] // chunk["visit_count"])
    offset = (visit_index - chunk["first_visit_index"]) * samples_per_visit
    packed = packed[offset : offset + samples_per_visit]
    iq = np.empty((samples_per_visit, 2), dtype=np.complex64)
    iq.real = packed[:, :, 0]
    iq.imag = packed[:, :, 1]
    valid_start = int(load_visit_metadata(session_id, visit_index)["valid_start_counter"])
    return iq, rate, valid_start


def pair_phasors(session_id: str, visits: tuple[int, int], seed_hz: float) -> dict:
    loaded = [load_visit(session_id, visit) for visit in visits]
    rates = {row[1] for row in loaded}
    if len(rates) != 1:
        raise RuntimeError("sample-rate mismatch inside pair")
    rate = rates.pop()
    window = round(WINDOW_SECONDS * rate)
    stride = round(STRIDE_SECONDS * rate)
    reference_counter = min(row[2] for row in loaded)
    taper = np.hanning(window) ** 2
    times, phasors, coherence, labels = [], [], [], []
    for visit_index, (iq, _, valid_start) in zip(visits, loaded, strict=True):
        for start in np.arange(0, len(iq) - window + 1, stride):
            sample = np.arange(start, start + window)
            global_time = (valid_start - reference_counter + sample) / rate
            left = iq[start : start + window, 0].astype(np.complex128)
            right = iq[start : start + window, 1].astype(np.complex128)
            right *= np.exp(-2j * np.pi * seed_hz * global_time)
            phasor = np.sum(np.conj(left) * right * taper)
            denominator = math.sqrt(
                max(
                    float(
                        np.sum(abs(left * np.sqrt(taper)) ** 2)
                        * np.sum(abs(right * np.sqrt(taper)) ** 2)
                    ),
                    1e-30,
                )
            )
            times.append(
                (valid_start - reference_counter + start + (window - 1) / 2) / rate
            )
            phasors.append(phasor)
            coherence.append(abs(phasor) / denominator)
            labels.append(visit_index)
    return {
        "rate_hz": rate,
        "window_samples": window,
        "stride_samples": stride,
        "time_s": np.asarray(times),
        "phasor": np.asarray(phasors),
        "coherence": np.asarray(coherence),
        "visit_index": np.asarray(labels),
        "valid_start_counter": {visit: row[2] for visit, row in zip(visits, loaded, strict=True)},
        "reference_counter": reference_counter,
        "samples_per_visit": len(loaded[0][0]),
    }


def fit_increment_model(
    series: dict, degree: int, train_indices: np.ndarray | None = None
) -> dict:
    time_s = series["time_s"]
    phasor = series["phasor"]
    labels = series["visit_index"]
    delta_time = np.diff(time_s)
    midpoint = (time_s[1:] + time_s[:-1]) / 2
    delta_phase = np.angle(phasor[1:] * np.conj(phasor[:-1]))
    same_dwell = labels[1:] == labels[:-1]
    boundary_index = int(np.flatnonzero(~same_dwell)[0])
    center_s = float(np.mean(midpoint))
    centered_midpoint = midpoint - center_s
    frequency_hz = delta_phase / (2 * np.pi * delta_time)
    weight = np.sqrt(abs(phasor[1:] * phasor[:-1]))
    design = np.column_stack(
        [centered_midpoint**power for power in range(degree + 1)]
    )
    available = np.flatnonzero(same_dwell)
    selected = available if train_indices is None else np.asarray(train_indices)
    coefficients = np.linalg.lstsq(
        design[selected] * weight[selected, None],
        frequency_hz[selected] * weight[selected],
        rcond=None,
    )[0]

    def integral(at_time: np.ndarray) -> np.ndarray:
        centered = np.asarray(at_time) - center_s
        return sum(
            coefficients[power] * centered ** (power + 1) / (power + 1)
            for power in range(degree + 1)
        )

    predicted_cycles = float(
        integral(time_s[boundary_index + 1]) - integral(time_s[boundary_index])
    )
    boundary_residual = float(
        wrap_rad(delta_phase[boundary_index] - 2 * np.pi * predicted_cycles)
    )
    corrected_phase = wrap_rad(np.angle(phasor) - 2 * np.pi * integral(time_s))
    return {
        "coefficients": coefficients,
        "available_indices": available,
        "boundary_index": boundary_index,
        "boundary_residual_deg": math.degrees(boundary_residual),
        "corrected_phase_rad": corrected_phase,
    }


def null_probability(sample_count: int, observed_r: float, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    exceedances = 0
    completed = 0
    while completed < NULL_TRIALS:
        count = min(100_000, NULL_TRIALS - completed)
        phase = rng.uniform(-np.pi, np.pi, (count, sample_count))
        resultant = abs(np.mean(np.exp(1j * phase), axis=1))
        exceedances += int(np.sum(resultant >= observed_r))
        completed += count
    return {
        "trials": NULL_TRIALS,
        "exceedances": exceedances,
        "plus_one_tail_probability": (exceedances + 1) / (NULL_TRIALS + 1),
    }


def consecutive_pairs(visits: list[int]) -> list[tuple[int, int]]:
    return [
        (left, right)
        for left, right in zip(visits, visits[1:], strict=False)
        if right == left + 1
    ]


def analyze() -> dict:
    selection = json.loads(SELECTION_PATH.read_text())
    rng = np.random.default_rng(RNG_SEED)
    rows = []
    detail = None
    for track in selection["tracks"]:
        seed_hz = float(np.median(track["relative_carrier_seeds_hz"]))
        for visits in consecutive_pairs(track["selected_visits"]):
            series = pair_phasors(track["session_id"], visits, seed_hz)
            fitted = fit_increment_model(series, FREQUENCY_POLYNOMIAL_DEGREE)
            boundary = fitted["boundary_index"]
            bootstrap = []
            available = fitted["available_indices"]
            for _ in range(BOOTSTRAP_COUNT):
                selected = np.sort(
                    rng.choice(available, len(available) // 2, replace=False)
                )
                bootstrap.append(
                    fit_increment_model(
                        series, FREQUENCY_POLYNOMIAL_DEGREE, selected
                    )["boundary_residual_deg"]
                )
            bootstrap_array = np.asarray(bootstrap)
            rate = series["rate_hz"]
            valid_start = series["valid_start_counter"]
            manifest = load_manifest(track["session_id"])
            timing = manifest["timing"]
            boundary_counter = [
                series["reference_counter"] + series["time_s"][index] * rate
                for index in (boundary, boundary + 1)
            ]
            boundary_utc_ns = [
                int(timing["first_sample_estimate_utc_ns"])
                + round(
                    (value - int(timing["session_start_device_sample_counter"]))
                    * 1e9
                    / rate
                )
                for value in boundary_counter
            ]
            row = {
                "track": track["track"],
                "session_id": track["session_id"],
                "channel": track["channel"],
                "edge": track["edge"],
                "phase_blind_priority": track["phase_blind_priority"],
                "visits": list(visits),
                "sample_rate_hz": rate,
                "carrier_seed_hz": seed_hz,
                "window_samples": series["window_samples"],
                "stride_samples": series["stride_samples"],
                "valid_payload_gap_us": (
                    valid_start[visits[1]]
                    - valid_start[visits[0]]
                    - series["samples_per_visit"]
                )
                / rate
                * 1e6,
                "analysis_window_center_separation_us": (
                    series["time_s"][boundary + 1] - series["time_s"][boundary]
                )
                * 1e6,
                "boundary_window_center_device_counter": boundary_counter,
                "boundary_window_center_utc_ns": boundary_utc_ns,
                "seed_only_boundary_change_deg": float(
                    np.degrees(
                        np.angle(
                            series["phasor"][boundary + 1]
                            * np.conj(series["phasor"][boundary])
                        )
                    )
                ),
                "held_boundary_residual_deg": fitted["boundary_residual_deg"],
                "bootstrap_median_deg": float(np.median(bootstrap_array)),
                "bootstrap_5_95_deg": np.quantile(
                    bootstrap_array, [0.05, 0.95]
                ).tolist(),
                "minimum_boundary_window_coherence": float(
                    min(series["coherence"][boundary : boundary + 2])
                ),
            }
            rows.append(row)
            if track["track"] == PRESELECTED_DETAIL_TRACK:
                detail = {
                    "track": track["track"],
                    "visits": list(visits),
                    "time_s": series["time_s"].tolist(),
                    "visit_index": series["visit_index"].tolist(),
                    "corrected_phase_deg": np.degrees(
                        fitted["corrected_phase_rad"]
                    ).tolist(),
                    "boundary_index": boundary,
                }
    phase = np.radians([row["held_boundary_residual_deg"] for row in rows])
    seed_only = np.radians([row["seed_only_boundary_change_deg"] for row in rows])
    modeled_r = circular_r(phase)
    per_track = []
    for track in selection["tracks"]:
        selected = [row for row in rows if row["track"] == track["track"]]
        selected_phase = np.radians(
            [row["held_boundary_residual_deg"] for row in selected]
        )
        per_track.append(
            {
                "track": track["track"],
                "pair_count": len(selected),
                "resultant": circular_r(selected_phase),
                "circular_mean_deg": circular_mean_deg(selected_phase),
                "median_absolute_residual_deg": float(
                    np.median(abs(np.degrees(selected_phase)))
                ),
            }
        )
    return {
        "schema_version": 1,
        "selection_id": selection["selection_id"],
        "estimator": {
            "window_seconds": WINDOW_SECONDS,
            "stride_seconds": STRIDE_SECONDS,
            "frequency_polynomial_degree": FREQUENCY_POLYNOMIAL_DEGREE,
            "relative_timing_delay_samples": 0,
            "complex_channel_response_used": False,
            "phase_intercept_used": False,
            "boundary_increment_used_in_fit": False,
            "carrier_seed_policy": "track median of frozen per-dwell carrier estimates",
        },
        "summary": {
            "track_count": len(selection["tracks"]),
            "pair_count": len(rows),
            "seed_only_boundary_resultant": circular_r(seed_only),
            "modeled_boundary_resultant": modeled_r,
            "modeled_boundary_circular_mean_deg": circular_mean_deg(phase),
            "median_absolute_residual_deg": float(
                np.median(abs(np.degrees(phase)))
            ),
            "pairs_within_5_deg": int(np.sum(abs(np.degrees(phase)) < 5.0)),
            "uniform_phase_null": null_probability(len(rows), modeled_r, RNG_SEED + 1),
        },
        "per_track": per_track,
        "pairs": rows,
        "preselected_detail": detail,
    }


def plot(result: dict) -> None:
    rows = result["pairs"]
    labels = [
        f"{row['track']} {row['visits'][0]}→{row['visits'][1]}" for row in rows
    ]
    modeled = np.asarray([row["held_boundary_residual_deg"] for row in rows])
    seed_only = np.asarray([row["seed_only_boundary_change_deg"] for row in rows])
    low = np.asarray([row["bootstrap_5_95_deg"][0] for row in rows])
    high = np.asarray([row["bootstrap_5_95_deg"][1] for row in rows])
    tracks = [row["track"] for row in rows]
    unique_tracks = list(dict.fromkeys(tracks))
    color_map = {
        track: plt.get_cmap("tab10")(index) for index, track in enumerate(unique_tracks)
    }
    colors = [color_map[track] for track in tracks]
    x = np.arange(len(rows))
    figure, axes = plt.subplots(2, 1, figsize=(13.5, 8.5))
    for index, color in enumerate(colors):
        axes[0].errorbar(
            x[index],
            modeled[index],
            yerr=np.asarray(
                [[modeled[index] - low[index]], [high[index] - modeled[index]]]
            ),
            fmt="none",
            ecolor=color,
            capsize=3,
            alpha=0.8,
        )
    axes[0].scatter(x, modeled, c=colors, s=55, zorder=3)
    axes[0].axhspan(-5.0, 5.0, color="0.92", zorder=-1, label="±5°")
    axes[0].axhline(0.0, color="0.2", linewidth=0.8)
    axes[0].set_xticks(x, labels, rotation=30, ha="right")
    axes[0].set_ylabel("held boundary residual (deg)")
    axes[0].set_title(
        "Frozen adjacent-dwell estimator on five independent strong tracks; "
        f"R={result['summary']['modeled_boundary_resultant']:.3f}"
    )
    axes[0].grid(axis="y", alpha=0.22)
    for track, color in color_map.items():
        axes[0].plot([], [], "o", color=color, label=track)
    axes[0].legend(frameon=False, ncol=6)

    for index, _row in enumerate(rows):
        axes[1].plot(
            [0, 1],
            [abs(seed_only[index]), abs(modeled[index])],
            "o-",
            color=colors[index],
            alpha=0.8,
        )
    axes[1].set_xticks([0, 1], ["fixed carrier seed only", "whole-pair frequency fit"])
    axes[1].set_xlim(-0.15, 1.18)
    axes[1].set_ylabel("absolute boundary residual (deg)")
    axes[1].set_title("Effect of the frozen carrier model on each boundary")
    axes[1].grid(axis="y", alpha=0.22)
    figure.suptitle("Cross-track replication of adjacent-dwell phase transport")
    figure.tight_layout()
    figure.savefig(REPORT_DIR / "cross-track-replication.png", dpi=180, facecolor="white")
    plt.close(figure)

    detail = result["preselected_detail"]
    time_s = np.asarray(detail["time_s"])
    visits = np.asarray(detail["visit_index"])
    phase = np.unwrap(np.radians(detail["corrected_phase_deg"]))
    boundary = int(detail["boundary_index"])
    phase -= phase[boundary]
    boundary_time = (time_s[boundary] + time_s[boundary + 1]) / 2
    figure, axis = plt.subplots(figsize=(13.0, 5.2))
    for visit, color in zip(detail["visits"], ("tab:blue", "tab:orange"), strict=True):
        keep = visits == visit
        axis.plot(
            (time_s[keep] - boundary_time) * 1000,
            np.degrees(phase[keep]),
            ".-",
            markersize=2,
            linewidth=0.8,
            color=color,
            label=f"visit {visit}",
        )
    selected_row = next(row for row in rows if row["track"] == detail["track"])
    axis.axvline(0.0, color="0.2", linewidth=0.8)
    axis.set_xlabel("time from dwell boundary (ms)")
    axis.set_ylabel("carrier-corrected phase (deg)")
    axis.set_title(
        f"Phase-blind strongest track {detail['track']}: visits "
        f"{detail['visits'][0]}→{detail['visits'][1]}, held residual "
        f"{selected_row['held_boundary_residual_deg']:+.2f}°"
    )
    axis.legend(frameon=False)
    axis.grid(alpha=0.22)
    figure.tight_layout()
    figure.savefig(REPORT_DIR / "preselected-strong-track-bridge.png", dpi=180, facecolor="white")
    plt.close(figure)


def main() -> None:
    result = analyze()
    (REPORT_DIR / "results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    plot(result)
    print(json.dumps(result["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
