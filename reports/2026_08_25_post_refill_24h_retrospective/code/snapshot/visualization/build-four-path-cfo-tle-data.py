from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import platform
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from leo.sky import (
    SamplingGrid,
    doppler_shift_hz,
    observe_grid,
    propagate_grid,
    resolve_preset,
)
from leo.sky.propagation import parse_element_sets


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "four-path-cfo-tle-data.json"
ANALYSIS_ROOT = Path(
    "/srv/bulk/leo/analysis/cap-20260825T085623-c725d27cbf0f/"
    "capture-9f6504cc63dd4932a32fc4f010e40456"
)
STANDARD_ROOT = ANALYSIS_ROOT / "scientific/path-standard"
MANIFEST = ANALYSIS_ROOT / "manifest.json"
TLE = Path(
    "/home/mouse9911/.codex/visualizations/2026/08/22/"
    "01a02af8-cec4-7703-a883-75760f132c40/"
    "radio1-rx1-catalog-search-agent/causal-space-track-ac36512e.tle"
)

SESSION_ID = "cap-20260825T085623-c725d27cbf0f"
RUN_ID = "capture-9f6504cc63dd4932a32fc4f010e40456"
INPUT_MANIFEST_DIGEST = (
    "sha256:f3743932040b9f7b289404ddff96c24cd096129ce0d6be2773b86ecb7597da45"
)
PIPELINE_RELEASE_ID = "d331df8eaf4f64bfb2cec75e1c664af10aebbdd8"

STREAM_0_START_NS = 1_787_648_186_162_000_696
STREAM_1_START_NS = 1_787_648_186_294_998_567
STREAM_0_RF_HZ = 10_709_687_498.0
STREAM_1_RF_HZ = 10_940_312_500.0
REFERENCE_RF_HZ = STREAM_0_RF_HZ
REFERENCE_TIME_FROM_STREAM_0_S = 56.25
STREAM_START_SKEW_UNCERTAINTY_NS = 2_173_278

TLE_SNAPSHOT_COLLECTED_NS = 1_787_594_647_459_418_079
TLE_CATALOG_NUMBER = 58_610
TLE_GRID_START_S = 52.8
TLE_GRID_STOP_S = 60.125
TLE_GRID_STEP_S = 0.025

PATH_SPECS = (
    {
        "path_id": f"{SESSION_ID}/stream-0/rx-0",
        "scope_key": "sha256:501eae76b12bd783172d0a4081bc2b200d80ee6fb1c548f167549928b7d9b506",
        "branch_id": "sha256:93ef0f347e7a456df56580c50b932568db73810eb14e098323c1221e4561ff3b",
        "radio_id": "radio_pluto_5d4d",
        "stream_id": "stream-0",
        "receiver_id": 0,
        "stream_start_ns": STREAM_0_START_NS,
        "rf_hz": STREAM_0_RF_HZ,
    },
    {
        "path_id": f"{SESSION_ID}/stream-0/rx-1",
        "scope_key": "sha256:a8afe8faba0dc22279af6dc84247ecfdc22ad3e42114c76151267a308e4c6895",
        "branch_id": "sha256:9100343321c2afa94c4c24efee7ac882a79efdda0f99ffb5278ce66b659ed106",
        "radio_id": "radio_pluto_5d4d",
        "stream_id": "stream-0",
        "receiver_id": 1,
        "stream_start_ns": STREAM_0_START_NS,
        "rf_hz": STREAM_0_RF_HZ,
    },
    {
        "path_id": f"{SESSION_ID}/stream-1/rx-0",
        "scope_key": "sha256:ab9276d1f62d5b86f2471a5f3bd5faa4d0dae28c2b0979057f9955d284a5b387",
        "branch_id": "sha256:e6e4475dd27539872632b6ac8cf43796d2c0eada043118ef1b87d9a0b2b22a20",
        "radio_id": "radio_pluto_19f2",
        "stream_id": "stream-1",
        "receiver_id": 0,
        "stream_start_ns": STREAM_1_START_NS,
        "rf_hz": STREAM_1_RF_HZ,
    },
    {
        "path_id": f"{SESSION_ID}/stream-1/rx-1",
        "scope_key": "sha256:cc3132e1951a9c53c51306527ac74a4579d8f11757ed565526e6b449cbab7459",
        "branch_id": "sha256:c9a8c62a0f80f94d46e9c2f5a29548a0961a55def8dd1d0cc1fb46c7137a19db",
        "radio_id": "radio_pluto_19f2",
        "stream_id": "stream-1",
        "receiver_id": 1,
        "stream_start_ns": STREAM_1_START_NS,
        "rf_hz": STREAM_1_RF_HZ,
    },
)


def file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def utc_ns_text(value: int) -> str:
    seconds, nanoseconds = divmod(value, 1_000_000_000)
    prefix = datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{prefix}.{nanoseconds:09d}Z"


def rounded(value: float, digits: int) -> float:
    result = round(float(value), digits)
    return 0.0 if result == 0.0 else result


def rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.asarray(values, dtype=np.float64) ** 2)))


def model_value(model: dict[str, Any], time_s: float) -> float:
    coefficients = model["coefficients_hz"]
    if len(coefficients) != 2 or model["polynomial_degree"] != 1:
        raise ValueError("selected persisted model is not linear")
    centered_time = float(time_s) - float(model["reference_time_s"])
    return float(coefficients[0]) * centered_time + float(coefficients[1])


def source_file_record(
    path: Path, path_id: str, role: str, document: dict[str, Any]
) -> dict[str, Any]:
    return {
        "algorithm_version": document["algorithm_version"],
        "byte_size": path.stat().st_size,
        "embedded_content_digest": document["content_digest"],
        "file_sha256": file_sha256(path),
        "path": str(path),
        "path_id": path_id,
        "role": role,
        "schema_version": document["schema_version"],
    }


def extract_tle_lines(text: str, catalog_number: int) -> tuple[str, str, str]:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    prefix = f"1 {catalog_number:05d}"
    matches = [index for index, line in enumerate(lines) if line.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"expected one TLE record for {catalog_number}, found {len(matches)}")
    index = matches[0]
    if index == 0 or index + 1 >= len(lines):
        raise ValueError("selected TLE record is incomplete")
    name = lines[index - 1]
    if name.startswith("0 "):
        name = name[2:]
    return name, lines[index], lines[index + 1]


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected_manifest = {
        "session_id": SESSION_ID,
        "run_id": RUN_ID,
        "input_manifest_digest": INPUT_MANIFEST_DIGEST,
        "pipeline_release_id": PIPELINE_RELEASE_ID,
    }
    for key, expected in expected_manifest.items():
        if manifest.get(key) != expected:
            raise ValueError(f"manifest {key} changed: {manifest.get(key)!r}")

    source_files: list[dict[str, Any]] = []
    paths: list[dict[str, Any]] = []
    validation_paths: list[dict[str, Any]] = []
    support_starts: list[float] = []
    support_ends: list[float] = []

    for path_number, spec in enumerate(PATH_SPECS):
        scope_dir = STANDARD_ROOT / spec["scope_key"]
        bank_path = scope_dir / "standard.dealiased-trajectory-bank.v4.json"
        segment_path = scope_dir / "standard.pilot-doppler-segments.v1.json"
        bank = json.loads(bank_path.read_text(encoding="utf-8"))
        segments = json.loads(segment_path.read_text(encoding="utf-8"))

        if bank["schema_version"] != 4 or segments["schema_version"] != 1:
            raise ValueError(f"unexpected source schema for {spec['path_id']}")
        if segments["dealiased_bank_digest"] != bank["content_digest"]:
            raise ValueError(f"pilot/dealiased digest mismatch for {spec['path_id']}")

        matching_branches = [
            branch for branch in bank["branches"] if branch["branch_id"] == spec["branch_id"]
        ]
        if len(matching_branches) != 1:
            raise ValueError(
                f"expected one selected branch for {spec['path_id']}, found {len(matching_branches)}"
            )
        branch = matching_branches[0]
        model = branch["model"]

        observations_by_id = {
            observation["observation_id"]: observation for observation in bank["observations"]
        }
        if len(observations_by_id) != len(bank["observations"]):
            raise ValueError(f"duplicate persisted observation id for {spec['path_id']}")
        if len(set(branch["observation_ids"])) != len(branch["observation_ids"]):
            raise ValueError(f"duplicate selected branch observation id for {spec['path_id']}")
        try:
            selected_observations = [
                observations_by_id[observation_id]
                for observation_id in branch["observation_ids"]
            ]
        except KeyError as error:
            raise ValueError(f"selected branch observation is absent for {spec['path_id']}") from error

        delta_s = (int(spec["stream_start_ns"]) - STREAM_0_START_NS) / 1e9
        scale = REFERENCE_RF_HZ / float(spec["rf_hz"])
        reference_time_on_path_s = REFERENCE_TIME_FROM_STREAM_0_S - delta_s
        source_model_at_reference_hz = model_value(model, reference_time_on_path_s)

        observation_rows = []
        source_residuals = []
        normalized_residuals = []
        for observation in selected_observations:
            local_time_s = float(observation["time_s"])
            component_cfo_hz = float(observation["component_cfo_hz"])
            x_s = local_time_s + delta_s
            y_hz = (component_cfo_hz - source_model_at_reference_hz) * scale
            normalized_model_hz = (
                model_value(model, local_time_s) - source_model_at_reference_hz
            ) * scale
            source_residuals.append(component_cfo_hz - model_value(model, local_time_s))
            normalized_residuals.append(y_hz - normalized_model_hz)
            observation_rows.append([rounded(x_s, 9), rounded(y_hz, 6)])
        observation_rows.sort(key=lambda row: (row[0], row[1]))

        source_residual_array = np.asarray(source_residuals, dtype=np.float64)
        normalized_residual_array = np.asarray(normalized_residuals, dtype=np.float64)
        source_rms = rms(source_residual_array)
        source_max = float(np.max(np.abs(source_residual_array)))
        if not math.isclose(source_rms, float(model["residual_rms_hz"]), abs_tol=1e-9):
            raise ValueError(f"persisted model RMS does not reproduce for {spec['path_id']}")
        if not math.isclose(source_max, float(model["residual_max_hz"]), abs_tol=1e-9):
            raise ValueError(f"persisted model max residual does not reproduce for {spec['path_id']}")
        if not math.isclose(rms(normalized_residual_array), source_rms * scale, abs_tol=1e-9):
            raise ValueError(f"normalized residual scaling changed for {spec['path_id']}")

        line_start_x = float(branch["start_s"]) + delta_s
        line_end_x = float(branch["end_s"]) + delta_s
        line_start_y = (
            model_value(model, float(branch["start_s"])) - source_model_at_reference_hz
        ) * scale
        line_end_y = (
            model_value(model, float(branch["end_s"])) - source_model_at_reference_hz
        ) * scale
        centered_slope = float(model["coefficients_hz"][0]) * scale
        centered_value_at_reference = centered_slope * (
            REFERENCE_TIME_FROM_STREAM_0_S - REFERENCE_TIME_FROM_STREAM_0_S
        )

        selected_segments = [
            row for row in segments["segments"] if row["source_branch_id"] == spec["branch_id"]
        ]
        grouped_windows: dict[tuple[float, float], list[dict[str, Any]]] = defaultdict(list)
        for row in selected_segments:
            grouped_windows[(float(row["start_time_s"]), float(row["end_time_s"]))].append(row)

        pilot_windows = []
        for (start_s, end_s), rows in sorted(grouped_windows.items()):
            pilot_windows.append(
                [
                    rounded(start_s + delta_s, 9),
                    rounded(end_s + delta_s, 9),
                    len(rows),
                    sum(bool(row["qualified"]) for row in rows),
                    sum(bool(row["phase_lock_qualified"]) for row in rows),
                ]
            )

        pilot_rates = []
        for row in sorted(
            selected_segments,
            key=lambda item: (
                float(item["reference_time_s"]),
                int(item["segment_index"]),
                str(item["source_trajectory_id"]),
            ),
        ):
            if row["local_doppler_rate_hz_s"] is None:
                continue
            sigma = row["local_doppler_rate_sigma_hz_s"]
            pilot_rates.append(
                [
                    rounded(float(row["reference_time_s"]) + delta_s, 9),
                    rounded(float(row["local_doppler_rate_hz_s"]) * scale, 6),
                    None if sigma is None else rounded(float(sigma) * scale, 6),
                    bool(row["qualified"]),
                    bool(row["phase_lock_qualified"]),
                    int(row["segment_index"]),
                    str(row["source_trajectory_id"]),
                ]
            )

        support_starts.append(line_start_x)
        support_ends.append(line_end_x)
        source_files.extend(
            (
                source_file_record(bank_path, spec["path_id"], "dealiased_bank", bank),
                source_file_record(segment_path, spec["path_id"], "pilot_segments", segments),
            )
        )
        paths.append(
            {
                "branch": {
                    "branch_id": branch["branch_id"],
                    "component_id": branch["component_id"],
                    "observed_alias_indices": branch["observed_alias_indices"],
                    "seed_trajectory_id": branch["seed_trajectory_id"],
                },
                "centered_model": {
                    "line": [
                        [rounded(line_start_x, 9), rounded(line_start_y, 6)],
                        [rounded(line_end_x, 9), rounded(line_end_y, 6)],
                    ],
                    "line_columns": [
                        "time_from_stream_0_start_s",
                        "centered_cfo_at_reference_rf_hz",
                    ],
                    "slope_hz_s": centered_slope,
                    "value_at_common_reference_hz": centered_value_at_reference,
                },
                "normalization": {
                    "common_reference_time_from_stream_0_start_s": REFERENCE_TIME_FROM_STREAM_0_S,
                    "reference_time_on_path_s": reference_time_on_path_s,
                    "rf_scale_to_reference": scale,
                    "source_model_at_reference_hz": source_model_at_reference_hz,
                    "stream_start_delta_s": delta_s,
                },
                "observation_columns": [
                    "time_from_stream_0_start_s",
                    "centered_cfo_at_reference_rf_hz",
                ],
                "observations": observation_rows,
                "path": {
                    "path_id": spec["path_id"],
                    "path_number": path_number,
                    "radio_id": spec["radio_id"],
                    "receiver_id": spec["receiver_id"],
                    "rf_hz": spec["rf_hz"],
                    "scope_key": spec["scope_key"],
                    "stream_id": spec["stream_id"],
                    "stream_start_ns": spec["stream_start_ns"],
                    "stream_start_utc": utc_ns_text(int(spec["stream_start_ns"])),
                },
                "persisted_model": {
                    "algorithm_version": model["algorithm_version"],
                    "bic": model["bic"],
                    "coefficient_order": "highest_polynomial_power_first",
                    "coefficients_hz": model["coefficients_hz"],
                    "converged": model["converged"],
                    "end_s": model["end_s"],
                    "iteration_count": model["iteration_count"],
                    "mad_scale_hz": model["mad_scale_hz"],
                    "median_absolute_residual_hz": model["median_absolute_residual_hz"],
                    "model_id": model["model_id"],
                    "polynomial_degree": model["polynomial_degree"],
                    "reference_time_s": model["reference_time_s"],
                    "residual_max_hz": model["residual_max_hz"],
                    "residual_rms_hz": model["residual_rms_hz"],
                    "start_s": model["start_s"],
                },
                "pilot_rate_columns": [
                    "reference_time_from_stream_0_start_s",
                    "local_doppler_rate_at_reference_rf_hz_s",
                    "local_doppler_rate_sigma_at_reference_rf_hz_s",
                    "qualified",
                    "phase_lock_qualified",
                    "segment_index",
                    "source_trajectory_id",
                ],
                "pilot_rates": pilot_rates,
                "pilot_window_columns": [
                    "start_time_from_stream_0_start_s",
                    "end_time_from_stream_0_start_s",
                    "persisted_row_count",
                    "qualified_row_count",
                    "phase_lock_qualified_row_count",
                ],
                "pilot_windows": pilot_windows,
                "source_counts": {
                    "all_bank_branches": len(bank["branches"]),
                    "all_bank_observations": len(bank["observations"]),
                    "all_pilot_segments": len(segments["segments"]),
                    "selected_branch_observations": len(selected_observations),
                    "selected_branch_pilot_rate_rows": len(pilot_rates),
                    "selected_branch_pilot_segment_rows": len(selected_segments),
                    "selected_branch_unique_pilot_windows": len(pilot_windows),
                    "selected_pilot_phase_lock_rows": sum(
                        bool(row["phase_lock_qualified"]) for row in selected_segments
                    ),
                    "selected_pilot_qualified_rows": sum(
                        bool(row["qualified"]) for row in selected_segments
                    ),
                },
            }
        )
        validation_paths.append(
            {
                "branch_id": branch["branch_id"],
                "centered_model_value_at_reference_abs_hz": abs(centered_value_at_reference),
                "normalized_residual_rms_hz": rms(normalized_residual_array),
                "observation_count": len(selected_observations),
                "path_id": spec["path_id"],
                "persisted_minus_recomputed_max_residual_hz": float(model["residual_max_hz"])
                - source_max,
                "persisted_minus_recomputed_rms_hz": float(model["residual_rms_hz"])
                - source_rms,
            }
        )

    overlap_start = max(support_starts)
    overlap_end = min(support_ends)
    if overlap_end <= overlap_start:
        raise ValueError("selected branches do not share a common support interval")

    tle_text = TLE.read_text(encoding="utf-8")
    catalogue = parse_element_sets(tle_text)
    catalogue_matches = [
        index
        for index, catalog_number in enumerate(catalogue.satellite_numbers)
        if catalog_number == TLE_CATALOG_NUMBER
    ]
    if len(catalogue_matches) != 1:
        raise ValueError("NORAD 58610 is not unique in the causal catalogue")
    tle_index = catalogue_matches[0]
    tle_name, tle_line_1, tle_line_2 = extract_tle_lines(tle_text, TLE_CATALOG_NUMBER)
    if catalogue.names[tle_index] != tle_name:
        raise ValueError("parsed and raw TLE names disagree")

    tle_count = int(round((TLE_GRID_STOP_S - TLE_GRID_START_S) / TLE_GRID_STEP_S)) + 1
    tle_times = TLE_GRID_START_S + np.arange(tle_count, dtype=np.float64) * TLE_GRID_STEP_S
    tle_instants = tuple(
        STREAM_0_START_NS + int(round(float(time_s) * 1e9)) for time_s in tle_times
    )
    tle_grid = SamplingGrid(
        utc_ns=tle_instants,
        anchor_index=tle_count // 2,
        spacing_s=TLE_GRID_STEP_S,
    )
    observer = resolve_preset("spinnaker-sausalito")
    observed = observe_grid(
        propagate_grid(catalogue, tle_grid, indices=[tle_index]), observer, tle_grid
    )
    if not bool(observed.usable[0]):
        raise ValueError("NORAD 58610 propagation is not usable over the plotting grid")
    raw_doppler = np.asarray(
        doppler_shift_hz(REFERENCE_RF_HZ, observed.range_rate_km_s[0]), dtype=np.float64
    )
    elevation = np.asarray(observed.elevation_deg[0], dtype=np.float64)
    centered_doppler_reference = float(
        np.interp(REFERENCE_TIME_FROM_STREAM_0_S, tle_times, raw_doppler)
    )
    centered_doppler = raw_doppler - centered_doppler_reference
    doppler_rate = np.gradient(raw_doppler, TLE_GRID_STEP_S, edge_order=2)
    tle_samples = [
        [
            rounded(time_s, 9),
            rounded(cfo_hz, 6),
            rounded(rate_hz_s, 6),
            rounded(elevation_deg, 6),
        ]
        for time_s, cfo_hz, rate_hz_s, elevation_deg in zip(
            tle_times, centered_doppler, doppler_rate, elevation, strict=True
        )
    ]
    reference_index = int(
        round((REFERENCE_TIME_FROM_STREAM_0_S - TLE_GRID_START_S) / TLE_GRID_STEP_S)
    )
    if not math.isclose(
        float(tle_times[reference_index]), REFERENCE_TIME_FROM_STREAM_0_S, abs_tol=1e-12
    ):
        raise ValueError("TLE grid no longer contains the common reference time")

    tle_element_epoch_ns = catalogue.element_epoch_utc_ns()[tle_index]
    tle_reference_utc_ns = STREAM_0_START_NS + int(
        round(REFERENCE_TIME_FROM_STREAM_0_S * 1e9)
    )
    manifest_sha = file_sha256(MANIFEST)
    tle_sha = file_sha256(TLE)
    source_files.append(
        {
            "byte_size": MANIFEST.stat().st_size,
            "file_sha256": manifest_sha,
            "path": str(MANIFEST),
            "role": "analysis_manifest",
        }
    )
    source_files.append(
        {
            "byte_size": TLE.stat().st_size,
            "catalogue_object_count": len(catalogue),
            "file_sha256": tle_sha,
            "path": str(TLE),
            "role": "causal_tle_catalogue",
            "snapshot_collected_ns": TLE_SNAPSHOT_COLLECTED_NS,
            "snapshot_collected_utc": utc_ns_text(TLE_SNAPSHOT_COLLECTED_NS),
        }
    )

    total_observations = sum(
        path["source_counts"]["selected_branch_observations"] for path in paths
    )
    total_segment_rows = sum(
        path["source_counts"]["selected_branch_pilot_segment_rows"] for path in paths
    )
    total_unique_windows = sum(
        path["source_counts"]["selected_branch_unique_pilot_windows"] for path in paths
    )
    total_pilot_rates = sum(
        path["source_counts"]["selected_branch_pilot_rate_rows"] for path in paths
    )
    grid_steps = np.diff(tle_times)

    payload = {
        "axes": {
            "cfo_y": "CFO at 10,709,687,498 Hz, self-centered at t=56.25 s (Hz)",
            "elevation_y": "topocentric elevation (deg)",
            "rate_y": "Doppler rate at 10,709,687,498 Hz (Hz/s)",
            "time_x": "seconds from stream-0 first sample",
        },
        "caveats": [
            "All four persisted products are candidate-only; payload decoding and transmitter specificity are explicitly false.",
            "Each selected branch is independently centered on its own persisted linear model at the common absolute reference instant, so absolute CFO intercepts are intentionally removed.",
            "The stream-1 frequency and rates are scaled by reference_rf_hz / path_rf_hz, assuming first-order Doppler proportionality to carrier frequency.",
            "The stream alignment is best-effort observed and not phase coherent; the paired report gives 2,173,278 ns start-skew uncertainty.",
            "The TLE curve is predictive geometry, not proof that NORAD 58610 transmitted or was received; the reviewed Spinnaker site is not capture-bound GPS authority and prior evidence states 50 m site uncertainty.",
            "The TLE derivative is a numerical diagnostic from the exact-SGP4 25 ms grid (second-order edges, centered interior differences).",
            "Pilot windows group persisted rows with identical start/end times; pilot_rates retains every selected-branch row with a non-null local rate and its source trajectory id.",
            "Comparator values are supplied rate-RMS diagnostics in Hz/s, not probabilities or calibrated identity confidence; lower is better.",
        ],
        "comparators": {
            "columns": [
                "kind",
                "label",
                "catalog_number",
                "time_shift_s",
                "train_rate_rms_hz_s",
                "holdout_rate_rms_hz_s",
            ],
            "lower_is_better": True,
            "metric": "rate RMS diagnostic (Hz/s)",
            "rows": [
                ["actual", "NORAD 58610", 58610, 0, 10.37, 6.61],
                ["runner_up", "NORAD 62139", 62139, 0, 48.66, 47.54],
                ["wrong_time_control", "+60 s / NORAD 45217", 45217, 60, 5.72, 94.47],
                ["wrong_time_control", "+570 s / NORAD 62060", 62060, 570, 21.98, 19.50],
            ],
            "source": "constants supplied in the analysis context; not recomputed by this extractor",
        },
        "normalization": {
            "formula": {
                "model_at_reference_hz": "polyval(coefficients_hz, reference_time_on_path_s - persisted_model.reference_time_s)",
                "observation_x_s": "persisted time_s + stream_start_delta_s",
                "observation_y_hz": "(component_cfo_hz - model_at_reference_hz) * rf_scale_to_reference",
                "reference_time_on_path_s": "56.25 - stream_start_delta_s",
                "rf_scale_to_reference": "10709687498 / path_rf_hz",
                "tle_y_hz": "doppler_58610(time_s) - interp(doppler_58610, 56.25 s)",
            },
            "reference_rf_hz": REFERENCE_RF_HZ,
            "reference_time_from_stream_0_start_s": REFERENCE_TIME_FROM_STREAM_0_S,
            "reference_utc_ns": tle_reference_utc_ns,
            "reference_utc": utc_ns_text(tle_reference_utc_ns),
        },
        "overlap": {
            "definition": "intersection of the four selected persisted branch support intervals after stream-start alignment",
            "duration_s": rounded(overlap_end - overlap_start, 9),
            "end_time_from_stream_0_start_s": rounded(overlap_end, 9),
            "start_time_from_stream_0_start_s": rounded(overlap_start, 9),
            "union_end_time_from_stream_0_start_s": rounded(max(support_ends), 9),
            "union_start_time_from_stream_0_start_s": rounded(min(support_starts), 9),
        },
        "paths": paths,
        "provenance": {
            "capture": {
                "input_manifest_digest": INPUT_MANIFEST_DIGEST,
                "manifest_file_sha256": manifest_sha,
                "pipeline_release_id": PIPELINE_RELEASE_ID,
                "run_id": RUN_ID,
                "session_id": SESSION_ID,
                "stream_0": {
                    "first_sample_ns": STREAM_0_START_NS,
                    "first_sample_utc": utc_ns_text(STREAM_0_START_NS),
                    "rf_hz": STREAM_0_RF_HZ,
                },
                "stream_1": {
                    "first_sample_ns": STREAM_1_START_NS,
                    "first_sample_utc": utc_ns_text(STREAM_1_START_NS),
                    "rf_hz": STREAM_1_RF_HZ,
                },
            },
            "source_files": source_files,
            "software": {
                "numpy": np.__version__,
                "python": platform.python_version(),
                "sgp4": importlib.metadata.version("sgp4"),
                "sky_implementation": "leo.sky exact SGP4/topocentric observer pipeline",
            },
        },
        "schema": "four-path-centered-cfo-tle-visualization-data-v1",
        "tle": {
            "catalog_number": TLE_CATALOG_NUMBER,
            "center_raw_doppler_hz": centered_doppler_reference,
            "element_age_at_reference_s": (tle_reference_utc_ns - tle_element_epoch_ns) / 1e9,
            "element_epoch_ns": tle_element_epoch_ns,
            "element_epoch_utc": utc_ns_text(tle_element_epoch_ns),
            "element_lines": [tle_line_1, tle_line_2],
            "grid_end_time_from_stream_0_start_s": float(tle_times[-1]),
            "grid_start_time_from_stream_0_start_s": float(tle_times[0]),
            "grid_step_s": TLE_GRID_STEP_S,
            "name": tle_name,
            "observer": {
                "altitude_m": observer.altitude_m,
                "capture_bound": False,
                "latitude_deg": observer.latitude_deg,
                "longitude_deg": observer.longitude_deg,
                "preset": "spinnaker-sausalito",
            },
            "sample_columns": [
                "time_from_stream_0_start_s",
                "centered_doppler_hz",
                "doppler_rate_hz_s",
                "elevation_deg",
            ],
            "samples": tle_samples,
            "snapshot_collected_ns": TLE_SNAPSHOT_COLLECTED_NS,
            "snapshot_collected_utc": utc_ns_text(TLE_SNAPSHOT_COLLECTED_NS),
            "source_file_sha256": tle_sha,
            "source_path": str(TLE),
        },
        "validation": {
            "all_branch_observations_resolved": True,
            "all_pilot_bank_digests_match": True,
            "common_overlap_duration_s": rounded(overlap_end - overlap_start, 9),
            "comparator_row_count": 4,
            "maximum_tle_grid_step_error_s": float(
                np.max(np.abs(grid_steps - TLE_GRID_STEP_S))
            ),
            "paths": validation_paths,
            "selected_branch_observation_count": total_observations,
            "selected_branch_pilot_rate_row_count": total_pilot_rates,
            "selected_branch_pilot_segment_row_count": total_segment_rows,
            "selected_branch_unique_pilot_window_count": total_unique_windows,
            "tle_centered_value_at_reference_abs_hz": abs(
                float(centered_doppler[reference_index])
            ),
            "tle_elevation_range_deg": [
                float(np.min(elevation)),
                float(np.max(elevation)),
            ],
            "tle_propagation_usable": True,
            "tle_rate_range_hz_s": [
                float(np.min(doppler_rate)),
                float(np.max(doppler_rate)),
            ],
            "tle_sample_count": tle_count,
        },
    }

    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
