#!/usr/bin/env python3
"""Fresh standard-server GLRT replay over every saved adaptive-hop visit."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np

SESSION = "scan-fw-f363c7f29141d0b1"
MANIFEST = "sha256:b74c950fb172433dab804ddd14b46a3f4c6c1d2e85a09855b0bfdff5da78e015"
RATE = 2_500_000
DWELL_MS = 120
PROBE_MS = 20
PROBE_STRIDE_MS = 120
GATE = 0.025
FALLBACK_ANCHORS = tuple(range(2, 302, 14))
EXPECTED_VISITS = 2215


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bytes_sha256(values: np.ndarray) -> str:
    return hashlib.sha256(memoryview(values).cast("B")).hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def event_sha256(event) -> str:
    return canonical_sha256(event.model_dump(mode="json"))


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fchmod(stream.fileno(), 0o644)
        os.fsync(stream.fileno())
    temporary.replace(path)


def derive_geometry(event, capture):
    from leo.analysis.starlink.pilot_search_geometry import compile_pilot_search_geometry
    from leo.analysis.starlink.templates import edge_frequencies_hz
    from leo.contracts.starlink_frequency import starlink_edge_rf_center_frequency_hz

    offsets = edge_frequencies_hz(event.target.edge)
    pilot_if_hz = (
        starlink_edge_rf_center_frequency_hz(event.target.channel, event.target.edge)
        - capture.lnb_lo_hz
    )
    center_hz = float(pilot_if_hz - event.actual_lo_frequency_hz)
    half_usable_hz = min(capture.sample_rate_hz, capture.bandwidth_hz) / 2.0
    observable_hz = min(
        center_hz + float(offsets.min()) + half_usable_hz,
        half_usable_hz - center_hz - float(offsets.max()),
    )
    if not math.isfinite(observable_hz) or observable_hz <= 0:
        raise ValueError("selected pilot template is not completely observable")
    half_width_hz = min(800_000.0, observable_hz)
    calibrations = tuple(
        compile_pilot_search_geometry(
            receiver_id=receiver,
            starlink_channel=event.target.channel,
            edge=event.target.edge,
            tuned_center_frequency_hz=event.actual_lo_frequency_hz,
            sample_rate_hz=capture.sample_rate_hz,
            rf_bandwidth_hz=capture.bandwidth_hz,
            residual_cfo_min_hz=-half_width_hz,
            residual_cfo_max_hz=half_width_hz,
            lnb_lo_hz=capture.lnb_lo_hz,
        ).frequency_reference
        for receiver in capture.receiver_ids
    )
    if any(item.center_hz != center_hz for item in calibrations):
        raise ValueError("receiver geometry center mismatch")
    return pilot_if_hz, center_hz, half_width_hz, calibrations


def candidates(analysis) -> dict[str, list[dict]]:
    output: dict[str, list[dict]] = {}
    for probe in analysis.probes:
        rows = []
        for candidate in probe.candidates:
            rows.append(
                {
                    "receiver_id": probe.receiver_id,
                    "probe_index": probe.probe_index,
                    "rank": candidate.candidate_rank,
                    "epoch": candidate.epoch_sample,
                    "acquired_cfo_hz": candidate.acquired_cfo_hz,
                    "residual_cfo_hz": candidate.residual_cfo_hz,
                    "tracking_cfo_hz": candidate.tracking_cfo_hz,
                    "exact_score": candidate.exact_score,
                    "control_score": candidate.control_score,
                    "margin": candidate.margin,
                    "fractional_status": candidate.fractional_epoch_status,
                    "fractional_offset_samples": candidate.fractional_epoch_offset_samples,
                    "fractional_residual_cfo_hz": candidate.fractional_residual_cfo_hz,
                    "fractional_tracking_cfo_hz": candidate.fractional_tracking_cfo_hz,
                    "fractional_exact_score": candidate.fractional_exact_score,
                    "fractional_control_score": candidate.fractional_control_score,
                    "fractional_margin": candidate.fractional_margin,
                    "passed_fractional_margin_gate": (
                        candidate.fractional_margin is not None
                        and candidate.fractional_margin >= GATE
                    ),
                }
            )
        output[str(probe.receiver_id)] = rows
    return output


@dataclass(frozen=True)
class Batch:
    visits: tuple[int, ...]
    output_dir: str
    bulk_root: str
    task_digest: str


def run_batch(batch: Batch) -> list[dict]:
    from leo.scanner.detector import Glrt64SearchGeometry, analyze_glrt64_dwell
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    store = AdaptiveHopIqStore(batch.bulk_root, read_only=True)
    session = store.inspect(SESSION)
    if session.manifest_sha256 != MANIFEST:
        raise ValueError("recording manifest changed")
    capture = session.manifest.receipt.plan.geometry
    timing = session.manifest.timing
    if (
        capture.sample_rate_hz != RATE
        or tuple(capture.receiver_ids) != (0, 1)
        or not timing.qualified
        or timing.sample_rate_hz != RATE
    ):
        raise ValueError("saved source geometry/timing is outside the replay contract")
    configuration = SimpleNamespace(
        dwell_samples=RATE * DWELL_MS // 1000,
        probe_samples=RATE * PROBE_MS // 1000,
        probe_stride_ms=PROBE_STRIDE_MS,
        probe_stride_samples=RATE * PROBE_STRIDE_MS // 1000,
        scheduled_probe_count=1,
        sample_rate_hz=RATE,
        receiver_ids=(0, 1),
        probe_ms=PROBE_MS,
        glrt64_margin_gate=GATE,
        maximum_acquisition_candidates=8,
    )
    results = []
    with store.reader(SESSION, expected=session) as reader:
        for visit_index in batch.visits:
            path = Path(batch.output_dir) / "visits" / f"visit-{visit_index:06d}.json"
            started = time.monotonic()
            cpu_started = time.process_time()
            visit, values = reader.read_visit_ci16(visit_index)
            event = visit.event
            if (
                event.visit_index != visit_index
                or values.dtype != np.dtype("<i2")
                or values.shape != (RATE * DWELL_MS // 1000, 2, 2)
                or not values.flags.c_contiguous
            ):
                raise ValueError(f"visit {visit_index} source shape/identity changed")
            raw_hash = bytes_sha256(values)
            read_wall = time.monotonic() - started
            pilot_if_hz, center_hz, half_width_hz, calibrations = derive_geometry(event, capture)
            samples = np.empty(values.shape[:2], dtype=np.complex64)
            samples.real = values[:, :, 0]
            samples.imag = values[:, :, 1]
            samples.setflags(write=False)
            analysis_started = time.monotonic()
            analysis_cpu_started = time.process_time()
            analysis = analyze_glrt64_dwell(
                samples,
                configuration,
                edge=event.target.edge,
                search_geometry=Glrt64SearchGeometry(
                    receiver_calibrations=calibrations,
                    residual_cfo_min_hz=-half_width_hz,
                    residual_cfo_max_hz=half_width_hz,
                    fallback_anchor_symbols=FALLBACK_ANCHORS,
                ),
            )
            analysis_wall = time.monotonic() - analysis_started
            analysis_cpu = time.process_time() - analysis_cpu_started
            delta = event.valid_start_counter - timing.session_start_device_sample_counter
            utc_delta_ns = delta * 1_000_000_000 // RATE
            result = {
                "schema": "org.leo.standard-server-full-scan-visit/v1",
                "status": "pass",
                "task_digest": batch.task_digest,
                "visit": visit_index,
                "source": {
                    "session_id": SESSION,
                    "recording_manifest_sha256": session.manifest_sha256,
                    "recording_event_sha256": event_sha256(event),
                    "raw_sha256": raw_hash,
                    "raw_bytes": int(values.nbytes),
                    "event": event.model_dump(mode="json"),
                    "valid_start_utc_estimate_ns": (
                        timing.first_sample_estimate_utc_ns + utc_delta_ns
                    ),
                    "valid_start_utc_earliest_ns": (
                        timing.first_sample_earliest_utc_ns + utc_delta_ns
                    ),
                    "valid_start_utc_latest_ns": (
                        timing.first_sample_latest_utc_ns + utc_delta_ns
                    ),
                },
                "geometry": {
                    "sample_rate_hz": RATE,
                    "bandwidth_hz": capture.bandwidth_hz,
                    "probe_ms": PROBE_MS,
                    "probe_stride_ms": PROBE_STRIDE_MS,
                    "scheduled_probe_count_per_receiver": 1,
                    "pilot_if_hz": pilot_if_hz,
                    "receiver_center_hz": [center_hz, center_hz],
                    "residual_cfo_min_hz": -half_width_hz,
                    "residual_cfo_max_hz": half_width_hz,
                    "fallback_anchor_symbols": list(FALLBACK_ANCHORS),
                },
                "candidates": candidates(analysis),
                "server_analysis": asdict(analysis),
                "timing_s": {
                    "raw_read_and_hash_wall": read_wall,
                    "detector_wall": analysis_wall,
                    "detector_process_cpu": analysis_cpu,
                    "whole_visit_wall": time.monotonic() - started,
                    "whole_visit_process_cpu": time.process_time() - cpu_started,
                },
            }
            atomic_json(path, result)
            results.append(
                {
                    "visit": visit_index,
                    "path": str(path),
                    "raw_sha256": raw_hash,
                    "event_sha256": result["source"]["recording_event_sha256"],
                    "detector_wall": analysis_wall,
                    "detector_process_cpu": analysis_cpu,
                    "candidates": sum(len(row) for row in result["candidates"].values()),
                    "passing": sum(
                        candidate["passed_fractional_margin_gate"]
                        for row in result["candidates"].values()
                        for candidate in row
                    ),
                }
            )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bulk-root", default="/srv/bulk/leo")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--batch-size", type=int, choices=range(1, 33), default=8)
    parser.add_argument("--maximum-visits", type=int, default=EXPECTED_VISITS)
    args = parser.parse_args()
    if not 1 <= args.maximum_visits <= EXPECTED_VISITS:
        raise ValueError("maximum visits lies outside 1..2215")
    here = Path(__file__).resolve().parent
    reference = Path("/var/tmp/leo-arm-realtime-publication")
    if subprocess.check_output(
        ["git", "-C", str(reference), "status", "--porcelain", "--untracked-files=no"],
        text=True,
    ):
        raise ValueError("standard server reference checkout has tracked modifications")
    sources = (
        "src/leo/analysis/starlink/acquisition.py",
        "src/leo/analysis/starlink/pilot_search_geometry.py",
        "src/leo/analysis/starlink/templates.py",
        "src/leo/contracts/starlink_frequency.py",
        "src/leo/scanner/detector.py",
        "src/leo/scanner/adaptive_hop_analysis.py",
        "src/leo/storage/adaptive_hop.py",
    )
    dependencies = {
        "harness_sha256": sha256(Path(__file__).resolve()),
        "session_id": SESSION,
        "recording_manifest_sha256": MANIFEST,
        "bulk_store": args.bulk_root,
        "bulk_store_read_only": True,
        "reference_git_head": subprocess.check_output(
            ["git", "-C", str(reference), "rev-parse", "HEAD"], text=True
        ).strip(),
        "reference_tracked_checkout_clean": True,
        "reference_source_sha256": {name: sha256(reference / name) for name in sources},
        "schedule": {
            "sample_rate_hz": RATE,
            "dwell_ms": DWELL_MS,
            "probe_ms": PROBE_MS,
            "probe_stride_ms": PROBE_STRIDE_MS,
            "margin_gate": GATE,
            "maximum_candidates": 8,
            "fallback_anchor_symbols": list(FALLBACK_ANCHORS),
        },
    }
    task_digest = canonical_sha256(dependencies)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "visits").mkdir(exist_ok=True)
    visits = tuple(range(args.maximum_visits))
    batches = [
        Batch(
            visits=visits[offset : offset + args.batch_size],
            output_dir=str(args.output_dir),
            bulk_root=args.bulk_root,
            task_digest=task_digest,
        )
        for offset in range(0, len(visits), args.batch_size)
    ]
    started = time.monotonic()
    completed = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(run_batch, batch) for batch in batches]
        for future in as_completed(futures):
            completed.extend(future.result())
            if len(completed) % 64 < args.batch_size:
                print(
                    json.dumps(
                        {
                            "kind": "progress",
                            "completed": len(completed),
                            "visits": len(visits),
                            "elapsed_s": time.monotonic() - started,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
    completed.sort(key=lambda item: item["visit"])
    if [item["visit"] for item in completed] != list(visits):
        raise ValueError("fresh server replay did not complete every requested visit")
    inventory = []
    with (args.output_dir / "server-visits.jsonl").open("w") as stream:
        for item in completed:
            receipt = json.loads(Path(item["path"]).read_text())
            json.dump(receipt, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            source = receipt["source"]
            event = source["event"]
            inventory.append(
                {
                    "visit": item["visit"],
                    "channel": event["target"]["channel"],
                    "edge": event["target"]["edge"],
                    "valid_start_counter": event["valid_start_counter"],
                    "valid_end_counter_exclusive": event["valid_end_counter_exclusive"],
                    "valid_start_utc_estimate_ns": source["valid_start_utc_estimate_ns"],
                    "recording_event_sha256": item["event_sha256"],
                    "raw_sha256": item["raw_sha256"],
                    "raw_bytes": source["raw_bytes"],
                }
            )
    atomic_json(args.output_dir / "inventory.json", inventory)
    summary = {
        "schema": "org.leo.standard-server-full-scan-summary/v1",
        "status": "pass",
        "fresh_processing": True,
        "visits": len(completed),
        "receiver_windows": len(completed) * 2,
        "candidates": sum(item["candidates"] for item in completed),
        "passing_candidates": sum(item["passing"] for item in completed),
        "channels": sorted({item["channel"] for item in inventory}),
        "edges": sorted({item["edge"] for item in inventory}),
        "task_digest": task_digest,
        "dependencies": dependencies,
        "workers": args.workers,
        "batch_size": args.batch_size,
        "timing_s": {
            "wall": time.monotonic() - started,
            "summed_detector_wall": sum(item["detector_wall"] for item in completed),
            "summed_detector_process_cpu": sum(
                item["detector_process_cpu"] for item in completed
            ),
        },
    }
    atomic_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
