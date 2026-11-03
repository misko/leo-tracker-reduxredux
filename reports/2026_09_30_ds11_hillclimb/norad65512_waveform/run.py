#!/usr/bin/env python3
"""Bounded extraction and known-pilot measurement for the frozen 111-row plan."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
BULK = Path("/srv/bulk/leo")
PLAN = HERE / "manifest.json"
INVENTORY = HERE / "local/extraction.json"
MEASUREMENTS = HERE / "local/measurements.json"
EXCERPTS = HERE / "local/excerpts"
ATTEMPTS = HERE / "attempts"
THREAD_ENV = {
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_plan() -> tuple[dict, str]:
    plan = json.loads(PLAN.read_text())
    if (
        plan["schema"] != "ds11-norad65512-waveform-plan/v1"
        or plan["denominator"] != 111
        or len(plan["rows"]) != 111
        or [row["ordinal"] for row in plan["rows"]] != list(range(111))
    ):
        raise ValueError("invalid frozen waveform plan")
    for name, expected in plan["sources"].items():
        path = Path(name)
        if not path.is_absolute() or digest(path) != expected:
            raise ValueError(f"source digest mismatch: {name}")
    return plan, digest(PLAN)


def owner() -> tuple[int, int]:
    stat = PLAN.stat()
    return stat.st_uid, stat.st_gid


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    os.chown(temporary, *owner())
    os.replace(temporary, path)


def initial_extraction(plan: dict, plan_sha256: str) -> dict:
    return {
        "schema": "ds11-norad65512-waveform-extraction/v1",
        "plan_path": str(PLAN),
        "plan_sha256": plan_sha256,
        "denominator": 111,
        "rows": [
            {
                "ordinal": row["ordinal"],
                "track_id": row["track_id"],
                "observation_index": row["observation_index"],
                "visit": row["visit"],
                "status": "pending",
            }
            for row in plan["rows"]
        ],
    }


def load_or_initialize_extraction(plan: dict, plan_sha256: str) -> dict:
    if not INVENTORY.exists():
        value = initial_extraction(plan, plan_sha256)
        atomic_json(INVENTORY, value)
        return value
    value = json.loads(INVENTORY.read_text())
    expected = initial_extraction(plan, plan_sha256)
    if (
        value.get("schema") != expected["schema"]
        or value.get("plan_sha256") != plan_sha256
        or value.get("denominator") != 111
        or len(value.get("rows", [])) != 111
    ):
        raise ValueError("extraction checkpoint does not bind the frozen plan")
    for got, wanted in zip(value["rows"], expected["rows"], strict=True):
        for key in ("ordinal", "track_id", "observation_index", "visit"):
            if got.get(key) != wanted[key]:
                raise ValueError("extraction checkpoint row identity changed")
    return value


def terminalize_interrupted(value: dict, *, stage: str, exhaust_pending: bool) -> None:
    for row in value["rows"]:
        if row["status"] == stage:
            row.update(status="failed", reason=f"{stage}_process_interrupted")
        elif exhaust_pending and row["status"] == "pending":
            row.update(status="not_attempted", reason=f"{stage}_process_budget_exhausted")


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def run_process(stage: str, limit_s: int, sequence: int, plan_sha256: str) -> dict:
    ATTEMPTS.mkdir(parents=True, exist_ok=True)
    receipt_path = ATTEMPTS / f"{stage}-{sequence:02d}.receipt.json"
    if receipt_path.exists():
        raise FileExistsError(receipt_path)
    command = [sys.executable, str(HERE / "run.py"), f"{stage}-worker"]
    environment = dict(os.environ, **THREAD_ENV, DS11_WAVEFORM_WORKER="1")
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=limit_s,
            check=False,
        )
        exit_code = completed.returncode
        stdout, stderr = completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as error:
        timed_out = True
        exit_code = 124
        stdout, stderr = _text(error.stdout), _text(error.stderr)
    receipt = {
        "schema": "ds11-norad65512-waveform-process-receipt/v1",
        "stage": stage,
        "sequence": sequence,
        "command": command,
        "plan_sha256": plan_sha256,
        "limit_s": limit_s,
        "elapsed_s": time.monotonic() - started,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout": stdout,
        "stderr": stderr,
    }
    atomic_json(receipt_path, receipt)
    return receipt


def extract_controller() -> None:
    plan, plan_sha256 = load_plan()
    value = load_or_initialize_extraction(plan, plan_sha256)
    terminalize_interrupted(value, stage="reading", exhaust_pending=False)
    atomic_json(INVENTORY, value)
    prior = sorted(ATTEMPTS.glob("extract-*.receipt.json")) if ATTEMPTS.exists() else []
    while any(row["status"] == "pending" for row in value["rows"]) and len(prior) < 3:
        receipt = run_process("extract", 120, len(prior) + 1, plan_sha256)
        value = load_or_initialize_extraction(plan, plan_sha256)
        terminalize_interrupted(value, stage="reading", exhaust_pending=False)
        atomic_json(INVENTORY, value)
        prior.append(ATTEMPTS / f"extract-{len(prior) + 1:02d}.receipt.json")
        if receipt["exit_code"] not in (0, 124):
            for row in value["rows"]:
                if row["status"] == "pending":
                    row.update(
                        status="not_attempted", reason="extraction_process_failed"
                    )
            break
    exhausted = len(prior) >= 3 or not any(row["status"] == "pending" for row in value["rows"])
    terminalize_interrupted(value, stage="reading", exhaust_pending=exhausted)
    atomic_json(INVENTORY, value)
    print(json.dumps(status_counts(value["rows"]), sort_keys=True))


def _normalized(value) -> dict:
    return json.loads(json.dumps(dataclasses.asdict(value), allow_nan=False))


def validate_row_metadata(row: dict, track_freeze: dict, matched, probe, candidate) -> None:
    visits = [point.visit_index for point in matched]
    times = [point.support_center_utc_ns for point in matched]
    position = row["observation_index"]
    point = matched[position]
    if (
        visits != track_freeze["visits"]
        or times[position] != row["support_center_utc_ns"]
        or point.receiver_id != row["receiver_id"]
        or point.visit_index != row["visit"]
        or point.channel != row["channel"]
        or point.probe_index != row["probe_index"]
        or point.candidate_rank != row["candidate_rank"]
        or probe.actual_rf_hz != row["actual_rf_hz"]
        or probe.probe_start_ms != row["probe_start_ms"]
        or probe.edge != row["edge"]
        or _normalized(candidate) != row["candidate"]
        or not track_freeze["training_mask"][position]
    ):
        raise ValueError("frozen row no longer matches public tracking metadata")


def extract_worker() -> None:
    if os.environ.get("DS11_WAVEFORM_WORKER") != "1":
        raise PermissionError("extract-worker is controller-only")
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    plan, plan_sha256 = load_plan()
    value = load_or_initialize_extraction(plan, plan_sha256)
    terminalize_interrupted(value, stage="reading", exhaust_pending=False)
    atomic_json(INVENTORY, value)
    metadata = ScannerTrackingInputStore(BULK)
    try:
        raw = metadata.load(plan["session_id"])
    finally:
        metadata.close()
    if (
        raw.input_manifest_sha256 != plan["capture"]["manifest_sha256"]
        or raw.analysis_manifest_sha256 != plan["analysis_manifest_sha256"]
        or raw.sample_rate_hz != 5_000_000
    ):
        raise ValueError("tracking metadata manifest mismatch")
    points_list = project_scanner_candidates(raw)
    points = {point.candidate_id: point for point in points_list}
    graph = reconstruct_persistent_hop_trajectories(
        points_list,
        config=PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6),
    )
    tracks = {track.tracklet_id: track for track in graph.tracklets}
    probes = {(probe.receiver_id, probe.visit_index, probe.probe_index): probe for probe in raw.probes}
    track_freezes = {track["track_id"]: track for track in plan["tracks"]}
    plan_rows = {row["ordinal"]: row for row in plan["rows"]}

    iq_store = AdaptiveHopIqStore(BULK, read_only=True)
    try:
        session = iq_store.inspect(plan["session_id"])
        if session.manifest_sha256 != plan["capture"]["manifest_sha256"]:
            raise ValueError("IQ recording manifest mismatch")
        with iq_store.reader(plan["session_id"], expected=session) as reader:
            for state in value["rows"]:
                if state["status"] != "pending":
                    continue
                state["status"] = "reading"
                atomic_json(INVENTORY, value)
                row = plan_rows[state["ordinal"]]
                output = EXCERPTS / f"{row['ordinal']:03d}.npy"
                try:
                    if output.exists():
                        raise FileExistsError("unbound excerpt output already exists")
                    track = tracks[row["track_id"]]
                    matched = [points[item.candidate_id] for item in track.points]
                    point = matched[row["observation_index"]]
                    probe = probes[point.receiver_id, point.visit_index, point.probe_index]
                    candidate = next(
                        item
                        for item in probe.candidates
                        if item.candidate_rank == point.candidate_rank
                    )
                    validate_row_metadata(
                        row, track_freezes[row["track_id"]], matched, probe, candidate
                    )
                    visit, samples = reader.read_visit_ci16(row["visit"])
                    begin = round(row["probe_start_ms"] * raw.sample_rate_hz / 1000)
                    count = round(raw.sample_rate_hz * 0.020)
                    stop = begin + count
                    if (
                        samples.ndim != 3
                        or samples.shape[2] != 2
                        or row["receiver_id"] >= samples.shape[1]
                        or stop > samples.shape[0]
                    ):
                        raise ValueError("visit cannot supply the frozen 20-ms receiver excerpt")
                    excerpt = samples[begin:stop, row["receiver_id"], :].copy()
                    if excerpt.shape != (100_000, 2) or excerpt.dtype != np.dtype("<i2"):
                        raise ValueError("unexpected excerpt shape or dtype")
                    output.parent.mkdir(parents=True, exist_ok=True)
                    np.save(output, excerpt, allow_pickle=False)
                    os.chown(output, *owner())
                    state.update(
                        status="ok",
                        path=str(output.resolve()),
                        sha256=digest(output),
                        array_sha256=hashlib.sha256(excerpt.tobytes()).hexdigest(),
                        shape=list(excerpt.shape),
                        dtype=excerpt.dtype.str,
                        visit_record=visit.model_dump(mode="json"),
                        recording_manifest_sha256=session.manifest_sha256,
                    )
                except Exception as error:
                    state.update(status="failed", reason=f"{type(error).__name__}: {error}")
                atomic_json(INVENTORY, value)
    finally:
        iq_store.close()
    print(json.dumps(status_counts(value["rows"]), sort_keys=True))


def load_waveform_helpers():
    waveform = ROOT / "reports/2026_09_29_training_waveform"
    header = ROOT / "reports/2026_09_27_ds7_header"
    sys.path.insert(0, str(waveform))
    sys.path.insert(0, str(header))
    from convention import remove_upconversion_phase
    from estimator import errors, fit
    from tcodes import demodulate, geometry, references

    return remove_upconversion_phase, errors, fit, demodulate, geometry, references


def arm_frequencies(frames: np.ndarray, fit_function) -> dict[str, float]:
    return {
        "cached": 0.0,
        "pilot_2_65": float(fit_function(frames, np.arange(64))),
        "pilot_22_221": float(fit_function(frames, np.arange(20, 220))),
    }


def canonical_correction(row: dict, residual_hz: float) -> dict:
    delta = float(residual_hz * 11.2e9 / row["actual_rf_hz"])
    return {
        "native_residual_hz": float(residual_hz),
        "canonical_delta_hz": delta,
        "corrected_measured_hz": float(row["measured_hz"] + delta),
        "additive_alias": row["additive_alias"],
    }


def measure_frames(frames: np.ndarray, row: dict, fit_function, error_function) -> dict:
    result = {}
    for name, frequency in arm_frequencies(frames, fit_function).items():
        result[name] = {
            **canonical_correction(row, frequency),
            "search_boundary": abs(frequency) >= 1499.999,
            "frame_nmse_symbols_222_301": [float(x) for x in error_function(frames, frequency)],
        }
    return result


def initial_measurements(plan: dict, plan_sha256: str, extraction: dict) -> dict:
    rows = []
    for state in extraction["rows"]:
        row = {
            key: state[key]
            for key in ("ordinal", "track_id", "observation_index", "visit")
        }
        if state["status"] == "ok":
            row["status"] = "pending"
        else:
            row.update(status="not_available", reason=f"extraction_{state['status']}: {state.get('reason', '')}")
        rows.append(row)
    return {
        "schema": "ds11-norad65512-waveform-measurements/v1",
        "plan_path": str(PLAN),
        "plan_sha256": plan_sha256,
        "extraction_path": str(INVENTORY),
        "extraction_sha256": digest(INVENTORY),
        "denominator": 111,
        "rows": rows,
    }


def load_or_initialize_measurements(plan: dict, plan_sha256: str, extraction: dict) -> dict:
    if not MEASUREMENTS.exists():
        value = initial_measurements(plan, plan_sha256, extraction)
        atomic_json(MEASUREMENTS, value)
        return value
    value = json.loads(MEASUREMENTS.read_text())
    if (
        value.get("schema") != "ds11-norad65512-waveform-measurements/v1"
        or value.get("plan_sha256") != plan_sha256
        or value.get("extraction_sha256") != digest(INVENTORY)
        or len(value.get("rows", [])) != 111
    ):
        raise ValueError("measurement checkpoint binding mismatch")
    return value


def measurement_controller() -> None:
    plan, plan_sha256 = load_plan()
    extraction = load_or_initialize_extraction(plan, plan_sha256)
    if any(row["status"] in ("pending", "reading") for row in extraction["rows"]):
        raise ValueError("extraction denominator is not terminal")
    value = load_or_initialize_measurements(plan, plan_sha256, extraction)
    terminalize_interrupted(value, stage="measuring", exhaust_pending=False)
    atomic_json(MEASUREMENTS, value)
    receipts = sorted(ATTEMPTS.glob("measure-*.receipt.json")) if ATTEMPTS.exists() else []
    if receipts:
        raise RuntimeError("the single measurement process was already attempted")
    run_process("measure", 180, 1, plan_sha256)
    value = json.loads(MEASUREMENTS.read_text())
    terminalize_interrupted(value, stage="measuring", exhaust_pending=True)
    atomic_json(MEASUREMENTS, value)
    print(json.dumps(status_counts(value["rows"]), sort_keys=True))


def measurement_worker() -> None:
    if os.environ.get("DS11_WAVEFORM_WORKER") != "1":
        raise PermissionError("measure-worker is controller-only")
    plan, plan_sha256 = load_plan()
    extraction = load_or_initialize_extraction(plan, plan_sha256)
    if any(row["status"] in ("pending", "reading") for row in extraction["rows"]):
        raise ValueError("extraction denominator is not terminal")
    value = load_or_initialize_measurements(plan, plan_sha256, extraction)
    terminalize_interrupted(value, stage="measuring", exhaust_pending=False)
    atomic_json(MEASUREMENTS, value)
    remove_phase, errors, fit, demodulate, geometry, references = load_waveform_helpers()
    plan_rows = {row["ordinal"]: row for row in plan["rows"]}
    extraction_rows = {row["ordinal"]: row for row in extraction["rows"]}
    for result in value["rows"]:
        if result["status"] != "pending":
            continue
        result["status"] = "measuring"
        atomic_json(MEASUREMENTS, value)
        row = plan_rows[result["ordinal"]]
        extracted = extraction_rows[result["ordinal"]]
        try:
            path = Path(extracted["path"])
            if digest(path) != extracted["sha256"]:
                raise ValueError("excerpt digest mismatch")
            iq = np.load(path, allow_pickle=False)
            if iq.shape != (100_000, 2) or iq.dtype != np.dtype("<i2"):
                raise ValueError("excerpt array shape or dtype changed")
            if hashlib.sha256(iq.tobytes()).hexdigest() != extracted["array_sha256"]:
                raise ValueError("excerpt content digest mismatch")
            samples = iq[:, 0].astype(float) + 1j * iq[:, 1]
            sample_rate = 5_000_000
            _, pilot_bins, center = geometry(row["edge"])
            _, _, pilot = references(row["edge"])
            candidate = row["candidate"]
            cached = candidate["fractional_tracking_cfo_hz"]
            epoch = candidate["integer_epoch_sample"] + candidate["fractional_epoch_offset_samples"]
            frequency = np.fft.fftfreq(1024, 1 / 240e6)
            keep = abs(frequency[pilot_bins] - center + cached) <= 0.45 * sample_rate
            pilot_bins = pilot_bins[keep]
            pilot = pilot[:, keep]
            if len(pilot_bins) < 2:
                raise ValueError("fewer than two in-band pilot carriers")
            frames = []
            for frame_index in range(8):
                frame_epoch = epoch + frame_index * sample_rate / 750
                start = max(0, int(frame_epoch) - round(sample_rate * 10e-6))
                stop = start + round(sample_rate * 0.00137)
                if stop > len(samples):
                    raise ValueError("20-ms excerpt cannot supply eight complete frames")
                symbols = demodulate(
                    samples[start:stop], sample_rate, frame_epoch - start, cached, center
                )[1:]
                if symbols.shape[0] < 300:
                    raise ValueError("demodulator returned fewer than 300 post-SSS symbols")
                frames.append(remove_phase(symbols[:300, pilot_bins] / pilot, center))
            frames = np.asarray(frames)
            result.update(
                status="ok",
                pilot_carriers=int(len(pilot_bins)),
                frames=int(len(frames)),
                arms=measure_frames(frames, row, fit, errors),
                symbol_numbering={
                    "pilot_2_65": [2, 65],
                    "pilot_22_221": [22, 221],
                    "gain_calibration": [22, 221],
                    "within_excerpt_held": [222, 301],
                },
            )
        except Exception as error:
            result.update(status="failed", reason=f"{type(error).__name__}: {error}")
        atomic_json(MEASUREMENTS, value)
    print(json.dumps(status_counts(value["rows"]), sort_keys=True))


def status_counts(rows: list[dict]) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        result[row["status"]] = result.get(row["status"], 0) + 1
    return result


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: run.py extract|extract-worker|measure|measure-worker")
    command = sys.argv[1]
    functions = {
        "extract": extract_controller,
        "extract-worker": extract_worker,
        "measure": measurement_controller,
        "measure-worker": measurement_worker,
    }
    if command not in functions:
        raise SystemExit(f"unknown command: {command}")
    functions[command]()


if __name__ == "__main__":
    main()
