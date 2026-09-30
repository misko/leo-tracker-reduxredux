"""Resumable read-only pilot-selected excerpt census; no message/FEC claims."""

import argparse
import dataclasses
import hashlib
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent
ROOT = BASE.parents[1]
OUT = BASE / "local"
sys.path.insert(0, str(ROOT / "reports/2026_09_28_ds7_ds8_correspondence"))
sys.path.insert(0, str(ROOT / "starlink_firmware/apk_fw_v1/reports/2026_09_28_sequence_semantics"))
from firmware_seed_search import SEED  # noqa: E402
from native_rate_decode import recover  # noqa: E402
from phase_model import codebook  # noqa: E402
from tcodes import bit_word, fit_code, score_code, slots  # noqa: E402


def observation_key(rx, visit, seconds, frequency):
    return rx, visit, round(seconds * 1e9), round(frequency, 3)


def word_candidate(z, bins, frame):
    """One fixed tail window, fit even symbols and validate odd; no window search."""
    symbols = np.arange(194, 258)
    mapping = slots(bins, symbols)
    values = z[symbols - 2]
    code, _, count = fit_code(values[::2], mapping[::2])
    peer, _, peer_count = fit_code(values[1::2], mapping[1::2])
    full = bool(np.all(count > 0) and np.all(peer_count > 0))
    score = score_code(values[1::2], mapping[1::2], code)
    rng = np.random.default_rng(713 + frame)
    control = max(score_code(values[1::2], mapping[1::2], rng.permutation(code)) for _ in range(99))
    accepted = full and np.array_equal(code, peer) and score > 0.25 and score > control
    word = bit_word(code)
    lookup = codebook(list(map(int, SEED)))
    return dict(
        frame=frame,
        word=word,
        odd_word=bit_word(peer),
        full_coverage=full,
        score=score,
        shuffle_max=control,
        accepted=bool(accepted),
        known_phase=lookup.index(word) if accepted and word in lookup else None,
    )


def process_capture(capture, frames):
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    start = time.monotonic()
    folder = OUT / "decoded" / capture["unit"]
    folder.mkdir(parents=True, exist_ok=True)
    receipt = folder / "results.json"
    binding = hashlib.sha256(
        json.dumps(
            dict(
                capture=capture,
                frames=frames,
                script_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            ),
            sort_keys=True,
        ).encode()
    ).hexdigest()
    if receipt.exists():
        previous = json.loads(receipt.read_text())
        if previous["binding"] == binding:
            return dict(unit=capture["unit"], reused=True, seconds=0, statuses=previous["statuses"])
    inputs = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    rows = []
    try:
        raw = inputs.load(capture["session"])
        assert raw.input_manifest_sha256 == capture["capture_manifest"]
        assert raw.analysis_manifest_sha256 == capture["analysis_manifest"]
        points = project_scanner_candidates(raw)
        graph = reconstruct_persistent_hop_trajectories(
            points, config=PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6)
        )
        by_track = {t.tracklet_id: t for t in graph.tracklets}
        by_candidate = {p.candidate_id: p for p in points}
        probes = {(p.receiver_id, p.visit_index, p.probe_index): p for p in raw.probes}
        jobs = []
        for ti, track in enumerate(capture["tracks"]):
            reconstructed = by_track.get(track["track_id"])
            matches = (
                [by_candidate[p.candidate_id] for p in reconstructed.points]
                if reconstructed is not None
                else []
            )
            bound = bool(matches) and [p.visit_index for p in matches] == track["visits"]
            if bound:
                bound = all(
                    abs((p.support_center_utc_ns - capture["start_utc_ns"]) / 1e9 - t) < 1e-9
                    for p, t in zip(matches, track["times_s"], strict=True)
                )
            info = dict(
                index=ti,
                track_id=track["track_id"],
                receiver=track["receiver_id"],
                channel=track["channel"],
                span_s=track["span_s"],
                track_observations=len(track["visits"]),
                exact_track_binding=bound,
            )
            if not bound:
                rows.append(dict(**info, status="track_binding_failed"))
                continue
            point = max(matches, key=lambda p: (p.margin, -p.visit_index, -p.candidate_rank))
            probe = probes[point.receiver_id, point.visit_index, point.probe_index]
            candidate = next(
                c for c in probe.candidates if c.candidate_rank == point.candidate_rank
            )
            info.update(
                visit=point.visit_index,
                probe=dataclasses.asdict(probe),
                candidate=dataclasses.asdict(candidate),
                edge=probe.edge,
                actual_rf_hz=probe.actual_rf_hz,
                selection_margin=point.margin,
                candidate_id=point.candidate_id,
            )
            info["probe"].pop("candidates")
            jobs.append((point.visit_index, info, probe, candidate))
        with (
            store.reader(capture["session"]) as reader,
            tempfile.TemporaryDirectory(dir=folder) as temp,
        ):
            current_visit, values = None, None
            for visit_index, info, probe, _candidate in sorted(
                jobs, key=lambda j: (j[0], j[1]["index"])
            ):
                try:
                    if current_visit != visit_index:
                        visit, values = reader.read_visit_ci16(visit_index)
                        current_visit = visit_index
                    begin = round(probe.probe_start_ms * capture["rate"] / 1000)
                    # Retain the bounded frame prefix from this 20ms acquisition probe.
                    excerpt = values[
                        begin : begin + round(capture["rate"] * 0.020), probe.receiver_id, :
                    ].copy()
                    np.save(Path(temp) / "stream.npy", excerpt)
                    row = dict(
                        name="stream",
                        sample_rate_hz=capture["rate"],
                        probe=info["probe"],
                        candidate=info["candidate"],
                        excerpt_sha256=hashlib.sha256(excerpt.tobytes()).hexdigest(),
                    )
                    bins, z, meta = recover(row, Path(temp), frames, all_supported_bins=True)
                    pilots = meta["pilot_bins"]
                    data = ~np.isin(bins, pilots)
                    qualified = [
                        f
                        for f in meta["evaluation_frames"]
                        if meta["diagnostics"][f]["held_pilot_coherence"] > 0.5
                    ]
                    words = [word_candidate(z[f][:, data], bins[data], f) for f in qualified]
                    artifact = folder / f"track-{info['index']:04d}.npz"
                    np.savez_compressed(
                        artifact,
                        bins=bins,
                        z=z.astype(np.complex64),
                        metadata=json.dumps(meta),
                        hard_real_signs=np.packbits(z.real >= 0, axis=None),
                    )
                    info.update(
                        status="qualified" if len(qualified) >= 2 else "insufficient_pilots",
                        qualified_frames=qualified,
                        words=words,
                        receiver_metadata=meta,
                        excerpt_sha256=row["excerpt_sha256"],
                        artifact=str(artifact),
                        artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
                        shape=list(z.shape),
                    )
                except Exception as exc:
                    info.update(status="decode_error", error=f"{type(exc).__name__}: {exc}")
                rows.append(info)
    finally:
        inputs.close()
        store.close()
    from collections import Counter

    result = dict(
        binding=binding,
        unit=capture["unit"],
        frames_requested=frames,
        elapsed_seconds=time.monotonic() - start,
        rows=sorted(rows, key=lambda r: r["index"]),
        statuses=dict(Counter(r["status"] for r in rows)),
    )
    receipt.write_text(json.dumps(result, indent=2) + "\n")
    return dict(
        unit=capture["unit"], seconds=result["elapsed_seconds"], statuses=result["statuses"]
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--frames", type=int, default=4)
    args = parser.parse_args()
    captures = json.loads((OUT / "census.json").read_text())["captures"][: args.limit]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        pending = {pool.submit(process_capture, c, args.frames): c for c in captures}
        for future in as_completed(pending):
            try:
                result = future.result()
            except Exception as exc:
                result = dict(unit=pending[future]["unit"], error=f"{type(exc).__name__}: {exc}")
            print(json.dumps(result), flush=True)


if __name__ == "__main__":
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    main()
