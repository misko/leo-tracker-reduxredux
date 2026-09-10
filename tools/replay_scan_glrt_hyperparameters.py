#!/usr/bin/env python3
"""Bounded offline raw-IQ GLRT sweep with fixed, non-orbital acquisition seeds."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from leo.analysis.starlink.fractional_epoch import fractional_take_bounds
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    conditioned_glrt64_score,
    conditioned_pilot_method_scores,
    refine_glrt64_epoch,
)
from leo.analysis.starlink.templates import FRAME_RATE_HZ, OFDM_SYMBOL_DURATION_S, StarlinkEdge
from leo.storage.persistent_hop import PersistentHopIqStore, PersistentHopStoredCi16Reader


def support_center(fs, epoch, fraction, duration_ms, symbols=64):
    left, right = fractional_take_bounds(fraction)
    local = np.arange(2, 2 + symbols)
    starts = np.rint(local * fs * OFDM_SYMBOL_DURATION_S)
    counts = np.rint((local + 1) * fs * OFDM_SYMBOL_DURATION_S) - starts
    centers = []
    for frame in range(int(duration_ms / 1000 * FRAME_RATE_HZ) + 2):
        pos = epoch + round(frame * fs / FRAME_RATE_HZ) + starts + fraction
        valid = (pos >= left) & (pos + counts - 1 < fs * duration_ms / 1000 - right)
        # The scorer stops before the first incomplete symbol block.
        if not np.all(valid):
            break
        centers.extend((pos + (counts - 1) / 2).tolist())
    if not centers:
        raise ValueError("empty GLRT support")
    return float(np.mean(centers))


def variants():
    return (
        [
            {"name": f"fft_{n}", "nfft": n, "ms": 20, "symbols": 64}
            for n in (128, 256, 512, 1024, 2048, 4096)
        ]
        + [{"name": f"window_{ms}ms", "nfft": 512, "ms": ms, "symbols": 64} for ms in (10, 40, 80)]
        + [{"name": "symbols_32", "nfft": 512, "ms": 20, "symbols": 32}]
    )


def select_tracks(root):
    docs = [json.loads(p.read_text()) for p in (root / "evidence").glob("scan*.json")]
    docs.sort(key=lambda d: d["inventory"]["reference_utc_ns"])
    selected = []
    for rate in (2500000, 5000000):
        available = [d for d in docs if d["inventory"]["sample_rate_hz"] == rate]
        for idx in np.linspace(0, len(available) - 1, 6).round().astype(int):
            doc = available[idx]
            track = max(doc["series"], key=lambda s: np.ptp(s["t_s"]))
            selected.append(
                {
                    "session_id": doc["inventory"]["session_id"],
                    "reference_utc_ns": doc["inventory"]["reference_utc_ns"],
                    "sample_rate_hz": rate,
                    "track": track,
                }
            )
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--refine-timing", action="store_true")
    parser.add_argument("--refresh-times", action="store_true")
    args = parser.parse_args()
    root = args.output
    selected = select_tracks(root)
    configs = variants()
    namespace = "raw-replay"
    if args.refine_timing:
        configs = [
            c
            for c in configs
            if c["name"]
            in ("fft_512", "fft_1024", "fft_4096", "window_10ms", "window_40ms", "window_80ms")
        ]
        namespace = "raw-replay-refined"
    plan = {
        "selection": (
            "six evenly spaced scans in time per sample rate; longest primary lane per scan"
        ),
        "acquisition_seeds": "frozen published integer epoch, fractional offset, and acquired CFO",
        "variants": configs,
        "refine_timing_per_variant": args.refine_timing,
        "tracks": [
            {k: v for k, v in s.items() if k != "track"}
            | {"tracklet_id": s["track"]["tracklet_id"], "span_s": float(np.ptp(s["track"]["t_s"]))}
            for s in selected
        ],
    }
    (root / f"{namespace}-plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    store = PersistentHopIqStore.open_read_only(Path("/srv/bulk/leo"))
    start = time.monotonic()
    for j, selection in enumerate(selected):
        sid = selection["session_id"]
        path = root / namespace / f"{sid}.json"
        if path.exists():
            if args.refresh_times:
                document = json.loads(path.read_text())
                config_by_name = {c["name"]: c for c in configs}
                for row in document["results"]:
                    if "y_hz" not in row:
                        continue
                    original = selection["track"]["observations"][row["index"]]["persisted"]
                    config = config_by_name[row["profile"]]
                    fraction = row.get(
                        "epoch_offset_samples", original["fractional_epoch_offset_samples"]
                    )
                    center = support_center(
                        selection["sample_rate_hz"],
                        original["integer_epoch_sample"],
                        fraction,
                        config["ms"],
                        config["symbols"],
                    )
                    row.setdefault("previous_projected_t_s", row["t_s"])
                    row["t_s"] = (
                        original["integer_session_sample"]
                        - original["integer_epoch_sample"]
                        + center
                    ) / selection["sample_rate_hz"]
                document["time_support"] = (
                    "center of complete scored symbol blocks in device-counter time"
                )
                path.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")
            print(f"cached {sid}", flush=True)
            continue
        cap = store.inspect(sid)
        reader = PersistentHopStoredCi16Reader(store, cap)
        fs = selection["sample_rate_hz"]
        track = selection["track"]
        starts = {}
        cursor = 0
        for visit in cap.manifest.receipt.visits:
            starts[visit.visit_index] = cursor
            cursor += visit.valid_sample_count
        outputs = []
        for index, obs in enumerate(track["observations"]):
            original = obs["persisted"]
            epoch = original["integer_epoch_sample"]
            fraction = original["fractional_epoch_offset_samples"]
            acquired = original["acquired_cfo_hz"]
            # Published V2 configuration has one 20-ms probe at visit start.
            if obs["probe_index"] != 0:
                raise ValueError("replay requires the declared one-probe visit schedule")
            source = starts[obs["visit_index"]]
            raw = reader.read_valid_ci16(source, fs * 80 // 1000)
            column = reader.receiver_ids.index(obs["receiver_id"])
            iq = raw[:, column, 0].astype(float) + 1j * raw[:, column, 1].astype(float)
            scale = 11.2e9 / obs["actual_rf_hz"]
            for config in configs:
                iq_window = iq[: fs * config["ms"] // 1000]
                before = time.perf_counter()
                kwargs = dict(
                    epoch_sample=epoch,
                    acquired_cfo_hz=acquired,
                    edge=StarlinkEdge(track["edge"]),
                    glrt_size=config["nfft"],
                    fractional_epoch_offset_samples=fraction,
                )
                variant_fraction = fraction
                if args.refine_timing:
                    refined = refine_glrt64_epoch(
                        iq_window,
                        fs,
                        integer_epoch_sample=epoch,
                        acquired_cfo_hz=acquired,
                        edge=track["edge"],
                        glrt_size=config["nfft"],
                    )
                    variant_fraction = refined.fractional_epoch_offset_samples
                    if variant_fraction is None:
                        outputs.append(
                            {
                                "profile": config["name"],
                                "index": index,
                                "status": "unbracketed",
                                "candidate_id": obs["candidate_id"],
                            }
                        )
                        continue
                    # The refinement has already evaluated the continuous score.
                    from types import SimpleNamespace

                    score = SimpleNamespace(
                        tracking_cfo_hz=refined.fractional_tracking_cfo_hz,
                        margin=refined.fractional_margin,
                    )
                elif config["symbols"] == 64:
                    score = conditioned_glrt64_score(iq_window, fs, **kwargs)
                else:
                    scores = conditioned_pilot_method_scores(
                        iq_window,
                        fs,
                        **kwargs,
                        symbolwise_exact=0,
                        symbolwise_control=0,
                        qam_accuracy=None,
                    )
                    score = next(s for s in scores if s.method == PilotMethod.GLRT32)
                elapsed = time.perf_counter() - before
                center = support_center(
                    fs, epoch, variant_fraction, config["ms"], config["symbols"]
                )
                baseline_error = score.tracking_cfo_hz - obs["measured_cfo_hz"]
                if config["name"] == "fft_512" and (
                    abs(baseline_error) > 1e-5 or abs(score.margin - obs["margin"]) > 1e-8
                ):
                    raise ValueError(
                        f"raw replay disagrees with published baseline: {baseline_error}"
                    )
                outputs.append(
                    {
                        "profile": config["name"],
                        "index": index,
                        "candidate_id": obs["candidate_id"],
                        "t_s": (original["integer_session_sample"] - epoch + center) / fs,
                        "y_hz": track["y_hz"][index] + baseline_error * scale,
                        "margin": score.margin,
                        "runtime_s": elapsed,
                        "epoch_offset_samples": variant_fraction,
                        "frequency_delta_hz": baseline_error * scale,
                    }
                )
        document = {
            **{k: v for k, v in selection.items() if k != "track"},
            "tracklet_id": track["tracklet_id"],
            "channel": track["channel"],
            "edge": track["edge"],
            "receiver": track["receiver"],
            "manifest_sha256": cap.manifest_sha256,
            "results": outputs,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")
        print(
            f"raw replay {j + 1}/{len(selected)}: {sid}, {len(track['t_s'])} probes, "
            f"{time.monotonic() - start:.1f}s cumulative",
            flush=True,
        )


if __name__ == "__main__":
    main()
