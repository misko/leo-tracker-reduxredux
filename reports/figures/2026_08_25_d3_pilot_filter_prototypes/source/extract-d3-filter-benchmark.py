from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL
from leo.contracts.states import StarlinkEdge
from leo.storage import PinnedLocalRoot, RecordingStore


ROOT = Path(
    "/home/mouse9911/.codex/visualizations/2026/08/22/"
    "01a02af8-cec4-7703-a883-75760f132c40"
)
SOURCE = ROOT / "radio1-rx1-phase-lock-100ms-scan.json"
OUTPUT = Path("/tmp/d3-radio1-rx1-filter-benchmark.npz")
SUMMARY = Path("/tmp/d3-radio1-rx1-filter-benchmark-summary.json")
SESSION = "cap-20260824T192531-491832825b97"
STREAM = "stream-1"
RECEIVER = 1
WINDOW_SAMPLES = 250_000
SAMPLE_RATE_HZ = 2_500_000.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def load_corrected_module():
    path = Path(
        "/home/mouse9911/gits/leo-tracker-reduxredux/"
        "src/leo/analysis/qam/pilot_pnt_kalman.py"
    )
    spec = importlib.util.spec_from_file_location("leo_filter_benchmark_pnt", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load corrected PNT Kalman module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, path


def complex_receiver(values: np.ndarray) -> np.ndarray:
    return (
        values[:, 0, 0].astype(np.float64)
        + 1j * values[:, 0, 1].astype(np.float64)
    ) / 32_768.0


def phase_rms(result) -> float | None:
    supported = [frame for frame in result.frames if frame.measurement_supported]
    if not supported:
        return None
    return math.sqrt(
        sum(frame.phase_innovation_modulo_pi_rad**2 for frame in supported)
        / len(supported)
    )


def main() -> None:
    started = time.monotonic()
    pnt, pnt_path = load_corrected_module()
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    arrays: dict[str, list[float | int | bool]] = {
        key: []
        for key in (
            "window_index",
            "window_center_time_s",
            "window_raw_disjoint",
            "frame_index",
            "frame_start_sample",
            "absolute_time_s",
            "measurement_supported",
            "exact_coherence",
            "control_coherence",
            "coherence_margin",
            "absolute_cfo_measurement_hz",
            "measurement_sigma_hz",
            "frequency_innovation_hz",
            "tracked_absolute_cfo_hz",
            "tracked_rate_hz_s",
            "tracked_frequency_sigma_hz",
            "tracked_rate_sigma_hz_s",
            "phase_innovation_rad",
            "phase_sigma_rad",
            "phase_update",
            "frequency_update",
            "timing_update",
            "reacquired",
        )
    }
    exact_windows = []
    rolled_windows = []
    store = RecordingStore.open_pinned(PinnedLocalRoot(Path("/srv/bulk/leo")))
    try:
        reader = store.reader(store.inspect(SESSION), STREAM, verify=True)
        for index, source_row in enumerate(source["results"]):
            seed = source_row["seed"]
            start = int(seed["sample_start"])
            count = min(WINDOW_SAMPLES, reader.sample_count - start)
            values = complex_receiver(reader.read(start, count, receiver_ids=(RECEIVER,)))
            common = {
                "epoch_sample": int(seed["epoch_sample"]),
                "initial_absolute_cfo_hz": float(seed["tracking_cfo_hz"]),
                "edge": StarlinkEdge.UPPER,
            }
            exact = pnt.analyze_contiguous_pilot_pnt_kalman_v2(
                values, reader.sample_rate_hz, **common
            )
            rolled = pnt.analyze_contiguous_pilot_pnt_kalman_v2(
                values,
                reader.sample_rate_hz,
                **common,
                expected_symbol_roll=CONTROL_SYMBOL_ROLL,
            )
            exact_windows.append(
                {
                    "window_index": index,
                    "center_time_s": float(seed["center_time_s"]),
                    "qualified": bool(exact.phase_lock_qualified),
                    "supported": int(exact.supported_frame_count),
                    "phase_updates": int(exact.phase_update_count),
                    "reacquisitions": int(exact.reacquisition_count),
                    "phase_rms_rad": phase_rms(exact),
                }
            )
            rolled_windows.append(
                {
                    "window_index": index,
                    "center_time_s": float(seed["center_time_s"]),
                    "qualified": bool(rolled.phase_lock_qualified),
                    "supported": int(rolled.supported_frame_count),
                    "phase_updates": int(rolled.phase_update_count),
                    "reacquisitions": int(rolled.reacquisition_count),
                    "phase_rms_rad": phase_rms(rolled),
                }
            )
            for frame in exact.frames:
                values_by_key = {
                    "window_index": index,
                    "window_center_time_s": float(seed["center_time_s"]),
                    "window_raw_disjoint": bool(index % 2 == 0),
                    "frame_index": int(frame.frame_index),
                    "frame_start_sample": start + int(frame.frame_start_sample),
                    "absolute_time_s": start / SAMPLE_RATE_HZ + float(frame.time_s),
                    "measurement_supported": bool(frame.measurement_supported),
                    "exact_coherence": float(frame.exact_coherence),
                    "control_coherence": float(frame.control_coherence),
                    "coherence_margin": float(frame.coherence_margin),
                    "absolute_cfo_measurement_hz": float(
                        frame.absolute_cfo_measurement_hz
                    ),
                    "measurement_sigma_hz": max(float(frame.frequency_sigma_hz), 1.0),
                    "frequency_innovation_hz": float(frame.frequency_innovation_hz),
                    "tracked_absolute_cfo_hz": float(frame.tracked_absolute_cfo_hz),
                    "tracked_rate_hz_s": float(frame.tracked_doppler_rate_hz_s),
                    "tracked_frequency_sigma_hz": float(frame.frequency_sigma_hz),
                    "tracked_rate_sigma_hz_s": float(frame.doppler_rate_sigma_hz_s),
                    "phase_innovation_rad": float(frame.phase_innovation_modulo_pi_rad),
                    "phase_sigma_rad": float(frame.phase_sigma_rad),
                    "phase_update": bool(frame.phase_update_applied),
                    "frequency_update": bool(frame.frequency_update_applied),
                    "timing_update": bool(frame.timing_update_applied),
                    "reacquired": bool(frame.reacquired),
                }
                for key, value in values_by_key.items():
                    arrays[key].append(value)
            if (index + 1) % 50 == 0:
                print(f"{index + 1}/{len(source['results'])}", flush=True)
    finally:
        store.close()

    np.savez_compressed(
        OUTPUT,
        **{
            key: np.asarray(
                values,
                dtype=(
                    bool
                    if key
                    in {
                        "window_raw_disjoint",
                        "measurement_supported",
                        "phase_update",
                        "frequency_update",
                        "timing_update",
                        "reacquired",
                    }
                    else int
                    if key in {"window_index", "frame_index", "frame_start_sample"}
                    else float
                ),
            )
            for key, values in arrays.items()
        },
    )
    summary = {
        "schema": "org.leo.research.d3-filter-benchmark-source/v1",
        "session_id": SESSION,
        "stream_id": STREAM,
        "receiver_id": RECEIVER,
        "selection": source["selection"],
        "window_count": len(exact_windows),
        "raw_disjoint_window_count": sum(index % 2 == 0 for index in range(len(exact_windows))),
        "frame_count": len(arrays["frame_index"]),
        "source_path": str(SOURCE),
        "source_sha256": sha256(SOURCE),
        "pnt_source_path": str(pnt_path),
        "pnt_source_sha256": sha256(pnt_path),
        "output_path": str(OUTPUT),
        "exact": {
            "qualified_count": sum(row["qualified"] for row in exact_windows),
            "supported_frames": sum(row["supported"] for row in exact_windows),
        },
        "rolled": {
            "qualified_count": sum(row["qualified"] for row in rolled_windows),
            "supported_frames": sum(row["supported"] for row in rolled_windows),
        },
        "exact_windows": exact_windows,
        "rolled_windows": rolled_windows,
        "runtime_s": time.monotonic() - started,
    }
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("exact", "rolled", "runtime_s")}, indent=2))
    print(OUTPUT)
    print(SUMMARY)


if __name__ == "__main__":
    main()
