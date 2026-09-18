#!/usr/bin/env python3
"""Replay candidate-only PSS timing on a frozen multi-rate scanner cohort."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from leo.analysis.standard.native_pss import starlink_pss_channel_reference_hz
from leo.analysis.starlink.pss_bandwidth import PssCaptureBand, acquire_pss_band
from leo.analysis.starlink.pss_tracker import PssTracker, observations_from_search
from leo.storage.adaptive_hop import AdaptiveHopIqStore

SERIAL = "104000bac4950008230026001b440a003a"
BANK = tuple(float(v) for v in range(-1_200_000, 1_200_001, 200_000))
SALT = "sixteen-hour-multirate-pss-v1"


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as stream:
        if rows:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


def select(indexes: list[int], manifest_sha256: str) -> int:
    return min(
        indexes,
        key=lambda i: hashlib.sha256(f"{SALT}:{manifest_sha256}:{i}".encode()).digest(),
    )


def timing_metrics(windows: list[object], rate: float) -> dict[str, float | int | None]:
    if len(windows) < 8:
        return {
            "timing_windows": len(windows),
            "linear_fit_rms_ns": None,
            "alternating_validation_rms_ns": None,
        }
    phase = np.asarray([w.frame_phase_samples / rate for w in windows])
    phase = np.unwrap(phase * 2 * np.pi * 750) / (2 * np.pi * 750)
    times = np.asarray([w.frame_index / 750 for w in windows])
    times -= times.mean()
    fitted = np.polyval(np.polyfit(times, phase, 1), times)
    validation = np.polyval(np.polyfit(times[::2], phase[::2], 1), times[1::2])
    return {
        "timing_windows": len(windows),
        "linear_fit_rms_ns": float(np.sqrt(np.mean((phase - fitted) ** 2)) * 1e9),
        "alternating_validation_rms_ns": float(
            np.sqrt(np.mean((phase[1::2] - validation) ** 2)) * 1e9
        ),
    }


def session_job(job: dict) -> dict:
    store = AdaptiveHopIqStore(Path(job["bulk_root"]), read_only=True)
    try:
        session = store.inspect(job["session_id"])
        receipt = session.manifest.receipt
        geometry = receipt.plan.geometry
        if (
            session.manifest_sha256 != job["manifest_sha256"]
            or receipt.radio_serial != SERIAL
            or geometry.receiver_ids != (0,)
            or receipt.plan.classification_receiver != 0
            or geometry.sample_rate_hz != job["sample_rate_hz"]
        ):
            raise ValueError("frozen RX0 source binding differs")
        by_target: dict[int, list[int]] = {}
        for visit in receipt.visits:
            by_target.setdefault(visit.event.target_index, []).append(visit.event.visit_index)
        selected = {select(indexes, session.manifest_sha256) for indexes in by_target.values()}
        track_selected = set()
        for indexes in by_target.values():
            late = [
                index for index in indexes
                if (
                    receipt.visits[index].event.valid_start_counter
                    - receipt.terminal.first_counter
                ) / geometry.sample_rate_hz >= 120
            ]
            track_selected.update(late[:6])
        rows, tracking = [], []
        trackers: dict[int, PssTracker] = {}
        with store.reader(session.session_id, expected=session) as reader:
            for index in sorted(selected | track_selected):
                visit, raw = reader.read_visit_ci16(index)
                event = visit.event
                actual_center = event.actual_lo_frequency_hz + event.actual_if_offset_hz
                reference = starlink_pss_channel_reference_hz(event.target.channel, event.target.edge)
                iq = (raw[:, 0, 0] + 1j * raw[:, 0, 1]).astype("complex64")
                start = event.valid_start_counter - receipt.terminal.first_counter
                half_band = min(geometry.bandwidth_hz, geometry.sample_rate_hz) / 2
                band = PssCaptureBand(
                    geometry.sample_rate_hz,
                    actual_center - reference,
                    -half_band,
                    half_band,
                )
                result = acquire_pss_band(
                    iq,
                    band,
                    device_sample_start=start,
                    continuity_segment_index=index,
                    frequency_offsets_hz=BANK,
                )
                observations = observations_from_search(result)
                qualified = [
                    (candidate.robust_z, hypothesis, candidate)
                    for hypothesis in result.hypotheses
                    for candidate in hypothesis.qualified_candidates
                ]
                candidates = [
                    candidate
                    for hypothesis in result.hypotheses
                    for candidate in hypothesis.candidates
                ]
                metric = {
                    "timing_windows": 0,
                    "linear_fit_rms_ns": None,
                    "alternating_validation_rms_ns": None,
                }
                best_cfo = best_phase = best_z = None
                if qualified:
                    best_z, hypothesis, candidate = max(qualified, key=lambda item: item[0])
                    best_cfo = candidate.frequency_offset_hz
                    best_phase = candidate.frame_phase_samples / geometry.sample_rate_hz * 1e9
                    metric = timing_metrics(
                        [
                            window
                            for window in hypothesis.windows
                            if window.candidate_index == candidate.candidate_index
                        ],
                        geometry.sample_rate_hz,
                    )
                chunk = session.manifest.chunks[index // 8]
                rows.append(
                    {
                        "session_id": session.session_id,
                        "capture_start_utc": job["capture_start_utc"],
                        "sample_rate_hz": geometry.sample_rate_hz,
                        "visit_index": index,
                        "target_index": event.target_index,
                        "channel": event.target.channel,
                        "edge": str(event.target.edge),
                        "source_manifest_sha256": session.manifest_sha256,
                        "chunk_sha256": chunk.compressed_sha256,
                        "source_start_counter": event.valid_start_counter,
                        "source_end_counter": visit.valid_end_counter_exclusive,
                        "nominal_overlap_hz": (
                            band.overlap_hz(0)[1] - band.overlap_hz(0)[0]
                            if band.overlap_hz(0) else 0
                        ),
                        "comparison_selected": index in selected,
                        "tracking_selected": index in track_selected,
                        "candidate_count": len(candidates),
                        "qualified_mode_count": len(qualified),
                        "pss_candidate": bool(qualified),
                        "maximum_robust_z": max((c.robust_z for c in candidates), default=None),
                        "best_robust_z": best_z,
                        "best_cfo_hz": best_cfo,
                        "best_frame_phase_ns": best_phase,
                        **metric,
                    }
                )
                if index in track_selected:
                    key = f"{session.session_id}:{receipt.stream_generation}:rx0:{event.target_index}"
                    tracker = trackers.setdefault(event.target_index, PssTracker(key))
                    time_s = (start + len(iq) / 2) / geometry.sample_rate_hz
                    estimate = tracker.update(key, time_s, observations)
                    tracking.append(
                        {
                            "session_id": session.session_id,
                            "sample_rate_hz": geometry.sample_rate_hz,
                            "visit_index": index,
                            "target_index": event.target_index,
                            "state": estimate.state,
                            "reason": estimate.reason,
                            "accepted_observations": estimate.accepted_observations,
                            "timing_sigma_ns": (
                                estimate.timing_sigma_s * 1e9
                                if estimate.timing_sigma_s is not None else None
                            ),
                            "cfo_sigma_hz": estimate.cfo_sigma_hz,
                        }
                    )
        return {"session_id": session.session_id, "rows": rows, "tracking": tracking}
    finally:
        store.close()


def aggregate(output: Path, expected_sessions: int) -> dict:
    documents = [json.loads(path.read_text()) for path in sorted(output.glob("session-*.json"))]
    if len(documents) != expected_sessions:
        raise ValueError(f"expected {expected_sessions} session products, found {len(documents)}")
    all_rows = [row for document in documents for row in document["rows"]]
    rows = [row for row in all_rows if row["comparison_selected"]]
    tracking = [row for document in documents for row in document["tracking"]]
    write_csv(output / "pss-visits.csv", rows)
    write_csv(output / "pss-tracking.csv", tracking)
    session_rows = []
    for document in documents:
        group = [row for row in document["rows"] if row["comparison_selected"]]
        track_group = document["tracking"]
        timed = [r for r in group if r["alternating_validation_rms_ns"] is not None]
        session_rows.append(
            {
                "session_id": document["session_id"],
                "capture_start_utc": group[0]["capture_start_utc"],
                "sample_rate_hz": group[0]["sample_rate_hz"],
                "selected_visits": len(group),
                "candidate_visits": sum(r["pss_candidate"] for r in group),
                "timed_visits": len(timed),
                "tracking_updates": sum(row["state"] == "tracking" for row in track_group),
                "targets_reaching_tracking": len({
                    row["target_index"] for row in track_group if row["state"] == "tracking"
                }),
                "median_alternating_validation_rms_ns": (
                    float(np.median([r["alternating_validation_rms_ns"] for r in timed]))
                    if timed else None
                ),
            }
        )
    write_csv(output / "pss-sessions.csv", session_rows)
    by_rate = {}
    for rate in (10_000_000, 15_000_000, 20_000_000):
        group = [r for r in rows if r["sample_rate_hz"] == rate]
        timed = [r for r in group if r["alternating_validation_rms_ns"] is not None]
        values = [r["alternating_validation_rms_ns"] for r in timed]
        by_rate[str(rate)] = {
            "sessions": len({r["session_id"] for r in group}),
            "selected_visits": len(group),
            "candidate_visits": sum(r["pss_candidate"] for r in group),
            "candidate_visit_percent": 100 * sum(r["pss_candidate"] for r in group) / len(group),
            "timed_visits": len(timed),
            "median_alternating_validation_rms_ns": float(np.median(values)) if values else None,
            "p10_p90_alternating_validation_rms_ns": (
                [float(np.percentile(values, 10)), float(np.percentile(values, 90))]
                if values else [None, None]
            ),
            "tracking_updates": sum(
                row["state"] == "tracking" for row in tracking
                if row["sample_rate_hz"] == rate
            ),
            "sessions_reaching_tracking": len({
                row["session_id"] for row in tracking
                if row["sample_rate_hz"] == rate and row["state"] == "tracking"
            }),
        }
    summary = {
        "protocol": {
            "selection": "minimum sha256(salt:manifest_digest:visit_index) per present target",
            "salt": SALT,
            "frequency_bank_hz": BANK,
            "candidate_only": True,
            "receiver_response": "ideal rectangular; analogue response uncalibrated",
            "timing_metric": "alternating-frame linear prediction RMS on strongest qualified mode",
            "tracking_selection": "first six retained visits per present target at or after 120 seconds",
        },
        "sessions": expected_sessions,
        "by_sample_rate_hz": by_rate,
    }
    (output / "pss-summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    labels = ["10", "15", "20"]
    rates = (10_000_000, 15_000_000, 20_000_000)
    values = [
        [r["alternating_validation_rms_ns"] for r in rows if r["sample_rate_hz"] == rate and r["alternating_validation_rms_ns"] is not None]
        for rate in rates
    ]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].bar(labels, [by_rate[str(r)]["candidate_visit_percent"] for r in rates])
    axes[0].set_ylim(0, 100)
    axes[0].set_xlabel("Native capture rate (MS/s)")
    axes[0].set_ylabel("Selected visits with qualified candidate (%)")
    axes[0].set_title("Candidate availability; not verified PSS")
    axes[1].boxplot(values, tick_labels=labels, showmeans=True)
    axes[1].set_yscale("log")
    axes[1].set_xlabel("Native capture rate (MS/s)")
    axes[1].set_ylabel("Alternating-frame prediction RMS (ns)")
    axes[1].set_title("Conditional timing repeatability")
    axes[1].grid(axis="y", alpha=0.25)
    fig.suptitle("Bandwidth-aware PSS replay across every sealed scanner recording")
    fig.tight_layout()
    fig.savefig(output / "pss-multirate-summary.png", dpi=180)
    plt.close(fig)

    ordered = sorted(session_rows, key=lambda row: row["capture_start_utc"])
    colors = {10_000_000: "#1676a3", 15_000_000: "#d28c28", 20_000_000: "#6b8e23"}
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    for rate in rates:
        points = [(i, row) for i, row in enumerate(ordered) if row["sample_rate_hz"] == rate]
        axes[0].scatter(
            [i for i, _ in points],
            [row["candidate_visits"] for _, row in points],
            label=f"{rate / 1e6:g} MS/s",
            color=colors[rate],
        )
        timed = [
            (i, row) for i, row in points
            if row["median_alternating_validation_rms_ns"] is not None
        ]
        axes[1].scatter(
            [i for i, _ in timed],
            [row["median_alternating_validation_rms_ns"] for _, row in timed],
            color=colors[rate],
        )
    axes[0].set_ylabel("Candidate-bearing selected visits")
    axes[0].set_title("Per-recording candidate availability (seven present targets selected)")
    axes[0].legend(ncol=3)
    axes[1].set_ylabel("Session median timing RMS (ns)")
    axes[1].set_xlabel("Recording in chronological order")
    axes[1].set_yscale("log")
    axes[1].set_title("Conditional alternating-frame timing repeatability")
    for axis in axes:
        axis.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output / "pss-recording-timeline.png", dpi=180)
    plt.close(fig)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=2)
    parser.add_argument("--aggregate-only", action="store_true")
    args = parser.parse_args()
    sessions = read_csv(args.input / "sessions.csv")
    args.output.mkdir(parents=True, exist_ok=True)
    if args.aggregate_only:
        aggregate(args.output, len(sessions))
        return
    sources = {
        row["session_id"]: row["declared_document_sha256"]
        for row in read_csv(args.input / "source-manifests.csv")
        if row["product"] == "capture"
    }
    jobs = [
        {
            "session_id": row["session_id"],
            "capture_start_utc": row["capture_start_utc"],
            "sample_rate_hz": int(row["sample_rate_hz"]),
            "manifest_sha256": sources[row["session_id"]],
            "bulk_root": str(args.bulk_root),
        }
        for row in sessions
    ]
    pending = [job for job in jobs if not (args.output / f"session-{job['session_id']}.json").exists()]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for completed, result in enumerate(pool.map(session_job, pending), 1):
            path = args.output / f"session-{result['session_id']}.json"
            path.write_text(json.dumps(result) + "\n")
            print(f"{completed}/{len(pending)} pending sessions complete", flush=True)
    aggregate(args.output, len(sessions))


if __name__ == "__main__":
    main()
