"""Bounded, reproducible PSS bandwidth and causal tracking replay on frozen IQ."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from leo.analysis.standard.native_pss import starlink_pss_channel_reference_hz
from leo.analysis.starlink.pss_bandwidth import PssCaptureBand, acquire_pss_band
from leo.analysis.starlink.pss_search import compile_pss_projection, project_pss_block
from leo.analysis.starlink.pss_tracker import PssTracker, observations_from_search
from leo.storage.adaptive_hop import AdaptiveHopIqStore

SERIAL = "104000bac4950008230026001b440a003a"
BANK = tuple(float(f) for f in range(-1_200_000, 1_200_001, 200_000))
SALT = "eight-hour-matched-pss-glrt-v1"
PROTOCOL = {
    "version": 1,
    "selection": "minimum sha256(salt:manifest_digest:visit_index) per session/target",
    "salt": SALT,
    "frequency_bank_hz": BANK,
    "bands": ["native10", "derived2p5"],
    "derived_filter": "existing ideal FFT projection; trim 64 output samples each end",
    "receiver_response": "ideal rectangular; hardware analogue response uncalibrated",
    "tracking_sessions": [0, 6, 12, 18, 24, 30, 36, 42, 46],
    "tracking_selection": "first six visits per target at/after 120 seconds",
    "z_gate": 6.0,
    "peak_to_median_gate": 1.15,
    "minimum_frame_support": 4,
    "candidate_only": True,
}


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as stream:
        if rows:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


def select(indexes: list[int], manifest_digest: str) -> int:
    return min(
        indexes, key=lambda i: hashlib.sha256(f"{SALT}:{manifest_digest}:{i}".encode()).digest()
    )


def session_job(job: dict) -> dict:
    store = AdaptiveHopIqStore(Path(job["bulk"]), read_only=True)
    rows, tracking, evidence = [], [], []
    try:
        session = store.inspect(job["session_id"])
        receipt = session.manifest.receipt
        g = receipt.plan.geometry
        if (
            session.manifest_sha256 != job["manifest_sha256"]
            or receipt.radio_serial != SERIAL
            or g.sample_rate_hz != 10_000_000
            or g.receiver_ids != (0,)
            or receipt.plan.classification_receiver != 0
        ):
            raise ValueError("frozen RX0 source binding differs")
        by_target = defaultdict(list)
        for visit in receipt.visits:
            by_target[visit.event.target_index].append(visit.event.visit_index)
        if set(by_target) != set(range(8)):
            raise ValueError("source does not cover all eight targets")
        selected = {select(v, session.manifest_sha256) for v in by_target.values()}
        track_indexes = set()
        if job["tracking"]:
            for indexes in by_target.values():
                late = [
                    i
                    for i in indexes
                    if (
                        receipt.visits[i].event.valid_start_counter - receipt.terminal.first_counter
                    )
                    / g.sample_rate_hz
                    >= 120
                ]
                if len(late) < 6:
                    raise ValueError("not enough retained visits for tracking protocol")
                track_indexes.update(late[:6])
        trackers = {}
        with store.reader(session.session_id, expected=session) as reader:
            for index in sorted(selected | track_indexes):
                visit, raw = reader.read_visit_ci16(index)
                event = visit.event
                actual_center = event.actual_lo_frequency_hz + event.actual_if_offset_hz
                reference = starlink_pss_channel_reference_hz(
                    event.target.channel, event.target.edge
                )
                iq = (raw[:, 0, 0] + 1j * raw[:, 0, 1]).astype("complex64")
                # Source-relative integer counter preserves retune gaps and avoids UTC float loss.
                start = event.valid_start_counter - receipt.terminal.first_counter
                projection = compile_pss_projection(
                    input_sample_rate_hz=g.sample_rate_hz,
                    input_center_frequency_hz=actual_center,
                    rf_bandwidth_hz=g.bandwidth_hz,
                    target_center_frequency_hz=actual_center,
                    channel_reference_hz=reference,
                )
                narrow = project_pss_block(
                    iq, projection, input_device_sample_start=start, continuity_segment_index=index
                )
                decision = receipt.host_decisions[index]
                if (
                    decision.visit_index != index
                    or decision.receiver_id != 0
                    or decision.valid_start_counter != event.valid_start_counter
                ):
                    raise ValueError("GLRT decision differs from retained visit")
                chunk = session.manifest.chunks[index // 8]
                for label, rate, values, origin in (
                    ("native10", 10_000_000, iq, start),
                    ("derived2p5", 2_500_000, narrow.samples, narrow.output_device_sample_start),
                ):
                    band = PssCaptureBand(rate, actual_center - reference, -rate / 2, rate / 2)
                    result = acquire_pss_band(
                        values,
                        band,
                        device_sample_start=origin,
                        continuity_segment_index=index,
                        frequency_offsets_hz=BANK,
                    )
                    observations = observations_from_search(result)
                    qualified = [c for h in result.hypotheses for c in h.qualified_candidates]
                    candidates = [c for h in result.hypotheses for c in h.candidates]
                    row = dict(
                        session_id=session.session_id,
                        capture_start_utc=job["capture_start_utc"],
                        visit_index=index,
                        target_index=event.target_index,
                        channel=event.target.channel,
                        edge=str(event.target.edge),
                        band=label,
                        comparison_selected=index in selected,
                        tracking_selected=index in track_indexes,
                        source_manifest_sha256=session.manifest_sha256,
                        chunk_sha256=chunk.compressed_sha256,
                        source_start_counter=event.valid_start_counter,
                        source_end_counter=visit.valid_end_counter_exclusive,
                        analysis_start_counter=origin,
                        analysis_sample_rate_hz=rate,
                        analysis_sample_count=len(values),
                        nominal_overlap_hz=band.overlap_hz(0)[1] - band.overlap_hz(0)[0],
                        glrt_outcome=decision.feedback_outcome,
                        glrt_cfo_hz=decision.numerics.cfo_hz if decision.numerics else None,
                        pss_detected=bool(qualified),
                        pss_qualified_modes=len(qualified),
                        pss_distinct_modes=len(observations),
                        pss_max_robust_z=max(c.robust_z for c in candidates),
                        pss_measured_windows=sum(len(h.windows) for h in result.hypotheses),
                    )
                    rows.append(row)
                    evidence.append(
                        dict(
                            visit_index=index,
                            band=label,
                            hypotheses=[
                                dict(
                                    cfo_hz=h.nominal_frequency_offset_hz,
                                    template_sha256=h.template_sha256,
                                    candidates=[asdict(c) for c in h.candidates],
                                    windows=[asdict(w) for w in h.windows],
                                )
                                for h in result.hypotheses
                            ],
                        )
                    )
                    if index in track_indexes:
                        key = (
                            f"{session.session_id}:{receipt.stream_generation}:"
                            f"rx0:{event.target_index}:{label}"
                        )
                        tracker = trackers.setdefault(key, PssTracker(key))
                        t = (origin + len(values) / 2) / rate
                        estimate = tracker.update(key, t, observations)
                        tracking.append(
                            dict(
                                session_id=session.session_id,
                                visit_index=index,
                                target_index=event.target_index,
                                band=label,
                                **asdict(estimate),
                            )
                        )
    finally:
        store.close()
    return dict(rows=rows, tracking=tracking, evidence=evidence)


def aggregate(output: Path) -> None:
    paths = sorted([*output.glob("session-*.json"), *output.glob("session-*.json.gz")])
    records = [
        json.loads(gzip.decompress(p.read_bytes()) if p.suffix == ".gz" else p.read_bytes())
        for p in paths
    ]
    if len(records) != 47:
        raise ValueError("cannot publish an incomplete 47-session replay")
    rows = [r for record in records for r in record["rows"]]
    tracks = [r for record in records for r in record["tracking"]]
    write_csv(output / "visits.csv", rows)
    write_csv(output / "tracking.csv", tracks)
    selected = [r for r in rows if r["comparison_selected"]]
    for band in PROTOCOL["bands"]:
        keys = [(r["session_id"], r["target_index"]) for r in selected if r["band"] == band]
        if len(keys) != 376 or len(set(keys)) != 376:
            raise ValueError("comparison must contain exactly eight unique targets per session")
    summary = dict(
        protocol=PROTOCOL,
        sessions=len(records),
        visits_per_band={},
        detected_per_band={},
        glrt_outcomes={},
        cross_tabs={},
        tracking_states={},
    )
    timing_rows = []
    for record in records:
        selected_keys = {
            (r["visit_index"], r["band"]) for r in record["rows"] if r["comparison_selected"]
        }
        for evidence in record["evidence"]:
            if (evidence["visit_index"], evidence["band"]) not in selected_keys:
                continue
            modes = [
                (c["robust_z"], h, c)
                for h in evidence["hypotheses"]
                for c in h["candidates"]
                if c["qualified"]
            ]
            if not modes:
                continue
            _, hypothesis, candidate = max(modes, key=lambda item: item[0])
            windows = [
                w
                for w in hypothesis["windows"]
                if w["candidate_index"] == candidate["candidate_index"]
            ]
            if len(windows) < 8:
                continue
            rate = 10_000_000 if evidence["band"] == "native10" else 2_500_000
            phase = np.asarray([w["frame_phase_samples"] / rate for w in windows])
            phase = np.unwrap(phase * 2 * np.pi * 750) / (2 * np.pi * 750)
            times = np.asarray([w["frame_index"] / 750 for w in windows])
            times -= times.mean()
            fitted = np.polyval(np.polyfit(times, phase, 1), times)
            validation = np.polyval(np.polyfit(times[::2], phase[::2], 1), times[1::2])
            timing_rows.append(
                dict(
                    session_id=record["rows"][0]["session_id"],
                    visit_index=evidence["visit_index"],
                    band=evidence["band"],
                    windows=len(windows),
                    linear_fit_rms_ns=float(np.sqrt(np.mean((phase - fitted) ** 2)) * 1e9),
                    alternating_validation_rms_ns=float(
                        np.sqrt(np.mean((phase[1::2] - validation) ** 2)) * 1e9
                    ),
                )
            )
    write_csv(output / "conditional-timing.csv", timing_rows)
    summary["conditional_timing"] = {
        band: {
            "visits": sum(r["band"] == band for r in timing_rows),
            "median_linear_fit_rms_ns": float(
                np.median([r["linear_fit_rms_ns"] for r in timing_rows if r["band"] == band])
            ),
            "median_alternating_validation_rms_ns": float(
                np.median(
                    [r["alternating_validation_rms_ns"] for r in timing_rows if r["band"] == band]
                )
            ),
        }
        for band in PROTOCOL["bands"]
    }
    for band in PROTOCOL["bands"]:
        group = [r for r in selected if r["band"] == band]
        summary["visits_per_band"][band] = len(group)
        summary["detected_per_band"][band] = sum(r["pss_detected"] for r in group)
        summary["glrt_outcomes"][band] = dict(Counter(r["glrt_outcome"] for r in group))
        summary["cross_tabs"][band] = dict(
            Counter(f"pss={r['pss_detected']},glrt={r['glrt_outcome']}" for r in group)
        )
        summary["tracking_states"][band] = dict(
            Counter(r["state"] for r in tracks if r["band"] == band)
        )
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    times = sorted({(r["capture_start_utc"], r["session_id"]) for r in selected})
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    for band in PROTOCOL["bands"]:
        axes[0].plot(
            range(len(times)),
            [
                sum(
                    r["pss_detected"]
                    for r in selected
                    if r["session_id"] == sid and r["band"] == band
                )
                * 12.5
                for _, sid in times
            ],
            ".-",
            label=band,
        )
        axes[1].plot(
            range(len(times)),
            [
                np.median(
                    [
                        r["pss_max_robust_z"]
                        for r in selected
                        if r["session_id"] == sid and r["band"] == band
                    ]
                )
                for _, sid in times
            ],
            ".-",
            label=band,
        )
    axes[0].plot(
        range(len(times)),
        [
            sum(
                r["glrt_outcome"] == "detected"
                for r in selected
                if r["session_id"] == sid and r["band"] == "native10"
            )
            * 12.5
            for _, sid in times
        ],
        ".--",
        label="online GLRT, same visits",
    )
    axes[0].set_ylabel("Selected visits passing (%)")
    axes[1].set_ylabel("Median maximum PSS robust z")
    axes[1].set_xlabel("Chronological session index (47 sessions, eight targets each)")
    axes[1].axhline(6, color="grey", linestyle="--")
    for ax in axes:
        ax.legend()
        ax.grid(alpha=0.25)
    fig.suptitle("Native 10 MS/s and derived 2.5 MS/s PSS: full CFO-bank acquisition")
    fig.tight_layout()
    fig.savefig(output / "bandwidth-comparison.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    bands = PROTOCOL["bands"]
    values = [
        [r["alternating_validation_rms_ns"] for r in timing_rows if r["band"] == band]
        for band in bands
    ]
    if all(values):
        ax.boxplot(values, tick_labels=bands, showmeans=True)
        ax.set_yscale("log")
    ax.set_ylabel("Alternating-frame linear prediction RMS (ns)")
    ax.set_title("Qualified-mode timing repeatability; conditional, unverified PSS")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output / "conditional-timing.png", dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--aggregate-only", action="store_true")
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("QNAP is read-only")
    if args.aggregate_only:
        aggregate(args.output)
        return
    sessions = read_csv(args.input / "sessions.csv")
    sources = {
        r["session_id"]: r["declared_document_sha256"]
        for r in read_csv(args.input / "source-manifests.csv")
        if r["product"] == "capture"
    }
    if len(sessions) != 47 or set(sources) != {r["session_id"] for r in sessions}:
        raise ValueError("expected frozen 47-session cohort")
    args.output.mkdir(parents=True, exist_ok=True)
    protocol = json.dumps(PROTOCOL, sort_keys=True)
    protocol_path = args.output / "protocol.json"
    if protocol_path.exists() and protocol_path.read_text() != protocol:
        raise ValueError("replay protocol changed")
    protocol_path.write_text(protocol)
    jobs = []
    for i, row in enumerate(sessions):
        path = args.output / f"session-{i:02d}.json"
        if path.exists():
            raise ValueError("output already contains replay; choose a fresh output directory")
        jobs.append(
            dict(
                session_id=row["session_id"],
                capture_start_utc=row["capture_start_utc"],
                manifest_sha256=sources[row["session_id"]],
                bulk=str(args.bulk_root),
                tracking=i in PROTOCOL["tracking_sessions"],
            )
        )
    with ProcessPoolExecutor(max_workers=2) as pool:
        for i, result in enumerate(pool.map(session_job, jobs)):
            (args.output / f"session-{i:02d}.json").write_text(json.dumps(result) + "\n")
            print(f"{i + 1}/47 sessions complete", flush=True)
    aggregate(args.output)


if __name__ == "__main__":
    main()
