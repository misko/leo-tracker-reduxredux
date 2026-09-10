#!/usr/bin/env python3
"""Bounded dense-probe replay of frozen visits for stride and probe-offset studies."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from replay_scan_glrt_hyperparameters import select_tracks, support_center

from leo.analysis.starlink.pilot_methods import conditioned_glrt64_scores, refine_glrt64_epoch
from leo.storage.persistent_hop import PersistentHopIqStore, PersistentHopStoredCi16Reader


def probe_starts(stride_ms: int, *, project_nonoverlap: bool = False) -> list[int]:
    if stride_ms < 10 or stride_ms > 120:
        raise ValueError("20-ms probes require a stride in 10..120 ms")
    starts = list(range(0, 101, stride_ms))
    if not project_nonoverlap:
        return starts
    retained = []
    next_start = -1
    for start in starts:
        if start >= next_start:
            retained.append(start)
            next_start = start + 20
    return retained


def shifted_epoch(epoch: int, start_ms: int, fs: int) -> int:
    start_sample = start_ms * fs // 1000
    advance = max(0, math.ceil((start_sample - epoch) / (fs / 750)))
    shifted = epoch + round(advance * fs / 750) - start_sample
    if shifted < 0 or shifted > math.ceil(fs / 750):
        raise ValueError("shifted epoch lies outside the first local frame")
    return shifted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timing-radius", type=int, choices=(2, 8), default=2)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    selected = select_tracks(args.source)
    plan = {
        "source_study": str(args.source.resolve()),
        "window_ms": 20,
        "grid_points": 512,
        "raw_start_ms": list(range(0, 101, 10)),
        "stride_ms": [120, 60, 40, 20, 10],
        "seed_policy": (
            "First-probe acquisition seed propagated by the known frame period; "
            "fractional timing refitted independently in each probe. "
            "No orbit/track-fit predictions consumed."
        ),
        "timing_radius_samples": args.timing_radius,
        "sessions": [s["session_id"] for s in selected],
    }
    (args.output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    store = PersistentHopIqStore.open_read_only(Path("/srv/bulk/leo"))
    for choice in selected:
        sid = choice["session_id"]
        dest = args.output / "raw" / f"{sid}.json"
        if dest.exists():
            print(f"cached {sid}", flush=True)
            continue
        before = time.monotonic()
        capture = store.inspect(sid)
        reader = PersistentHopStoredCi16Reader(store, capture)
        fs = choice["sample_rate_hz"]
        track = choice["track"]
        starts, cursor = {}, 0
        for visit in capture.manifest.receipt.visits:
            starts[visit.visit_index] = cursor
            cursor += visit.valid_sample_count
        output = []
        for visit_index, obs in enumerate(track["observations"]):
            original = obs["persisted"]
            raw = reader.read_valid_ci16(starts[obs["visit_index"]], fs * 120 // 1000)
            column = reader.receiver_ids.index(obs["receiver_id"])
            iq = raw[:, column, 0].astype(float) + 1j * raw[:, column, 1].astype(float)
            for start_ms in range(0, 101, 10):
                epoch = shifted_epoch(original["integer_epoch_sample"], start_ms, fs)
                sample_start = start_ms * fs // 1000
                probe = iq[sample_start : sample_start + fs * 20 // 1000]
                start = time.perf_counter()
                selected_offset = 0
                if args.timing_radius > 2 and start_ms > 0:
                    offsets = list(range(-args.timing_radius, args.timing_radius + 1))
                    epochs = [(epoch + offset) % round(fs / 750) for offset in offsets]
                    scores = conditioned_glrt64_scores(
                        probe,
                        fs,
                        epoch_samples=epochs,
                        acquired_cfo_hz=[original["acquired_cfo_hz"]] * len(epochs),
                        edge=track["edge"],
                        glrt_size=512,
                    )
                    best = max(range(len(scores)), key=lambda i: scores[i].exact_score)
                    selected_offset = offsets[best]
                    epoch = epochs[best]
                refined = refine_glrt64_epoch(
                    probe,
                    fs,
                    integer_epoch_sample=epoch,
                    acquired_cfo_hz=original["acquired_cfo_hz"],
                    edge=track["edge"],
                    glrt_size=512,
                )
                row = {
                    "visit_index": visit_index,
                    "capture_visit_index": obs["visit_index"],
                    "candidate_id": obs["candidate_id"],
                    "start_ms": start_ms,
                    "runtime_ms": 1000 * (time.perf_counter() - start),
                    "status": refined.status.value,
                    "selected_integer_offset_samples": selected_offset,
                    "timing_search_boundary": abs(selected_offset) == args.timing_radius,
                }
                fraction = refined.fractional_epoch_offset_samples
                if fraction is not None:
                    delta = refined.fractional_tracking_cfo_hz - obs["measured_cfo_hz"]
                    if start_ms == 0 and (
                        abs(delta) > 1e-5 or abs(refined.fractional_margin - obs["margin"]) > 1e-8
                    ):
                        raise ValueError("zero-offset replay disagrees with published baseline")
                    alias = 1 / 4.4e-6
                    delta -= round(delta / alias) * alias
                    center = support_center(fs, epoch, fraction, 20)
                    row.update(
                        t_s=(
                            original["integer_session_sample"]
                            - original["integer_epoch_sample"]
                            + sample_start
                            + center
                        )
                        / fs,
                        y_hz=track["y_hz"][visit_index] + delta * 11.2e9 / track["actual_rf_hz"],
                        margin=refined.fractional_margin,
                        fractional_epoch_samples=fraction,
                    )
                output.append(row)
        document = {
            "session_id": sid,
            "sample_rate_hz": fs,
            "tracklet_id": track["tracklet_id"],
            "manifest_sha256": capture.manifest_sha256,
            "input_visits": len(track["observations"]),
            "results": output,
        }
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")
        print(f"{sid}: {len(output)} probes in {time.monotonic() - before:.1f}s", flush=True)


if __name__ == "__main__":
    main()
