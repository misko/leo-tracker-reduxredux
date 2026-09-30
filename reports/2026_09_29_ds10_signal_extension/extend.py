"""Add frozen DS10 to the earlier excerpt census without altering prior artifacts."""

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

BASE = Path(__file__).resolve().parent
PRIOR = BASE.parent / "2026_09_29_all_track_symbols"
MINT = BASE.parent / "2026_09_29_ds10_post_ds9/local"
OUT = BASE / "local"
sys.path.insert(0, str(PRIOR))


def sha(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def census_one(job):
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    index, member = job
    path = OUT / "captures" / f"DS10-F{index:03d}.json"
    if path.exists():
        saved = json.loads(path.read_text())
        assert saved["capture_manifest"] == member["manifest_sha256"]
        return saved
    evidence = MINT / "analysis" / (member["session_id"] + ".json")
    assert sha(evidence) == member["analysis_evidence_sha256"]
    product = json.loads(evidence.read_text())
    source = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        raw = source.load(member["session_id"])
        assert raw.input_manifest_sha256 == member["manifest_sha256"]
        assert raw.analysis_manifest_sha256 == product["glrt"]["metrics_manifest_sha256"]
        points = project_scanner_candidates(raw)
        by_id = {p.candidate_id: p for p in points}
        graph = reconstruct_persistent_hop_trajectories(
            points, config=PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6)
        )
        start = raw.capture_start_utc_ns
        tracks = []
        for track in graph.tracklets:
            pts = [by_id[p.candidate_id] for p in track.points]
            times = [(p.support_center_utc_ns - start) / 1e9 for p in pts]
            if max(times) - min(times) <= 3:
                continue
            tracks.append(dict(
                track_id=track.tracklet_id, times_s=times,
                measured_hz=[p.normalized_dealiased_cfo_hz for p in track.points],
                receiver_id=pts[0].receiver_id, channel=pts[0].channel,
                edge=pts[0].edge, rf_hz=pts[0].actual_rf_hz,
                visits=[p.visit_index for p in pts], span_s=max(times) - min(times),
            ))
        result = dict(
            unit=f"DS10-F{index:03d}", dataset="DS10", session=member["session_id"],
            rate=raw.sample_rate_hz, capture_manifest=raw.input_manifest_sha256,
            analysis_manifest=raw.analysis_manifest_sha256, start_utc_ns=start,
            mint_manifest_sha256=sha(MINT / "manifest.json"),
            analysis_evidence=str(evidence), analysis_evidence_sha256=sha(evidence),
            method_sha256=sha(Path(__file__)), tracks=tracks,
        )
        write(path, result)
        return result
    finally:
        source.close()


def decode_one(capture):
    import decode_tracks

    decode_tracks.OUT = OUT
    return decode_tracks.process_capture(capture, 4)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["census", "decode", "windows", "audit"])
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    if args.action == "census":
        manifest = json.loads((MINT / "manifest.json").read_text())
        jobs = [(i, r) for i, r in enumerate(manifest["captures"], 1)
                if r["sample_rate_hz"] >= 5_000_000]
        captures = []
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for f in as_completed([pool.submit(census_one, j) for j in jobs]):
                c = f.result()
                captures.append(c)
                print(c["unit"], len(c["tracks"]), "tracks", flush=True)
        prior = json.loads((PRIOR / "local/census.json").read_text())
        combined = prior["captures"] + sorted(captures, key=lambda c: c["unit"])
        assert len({c["session"] for c in combined}) == len(combined)
        write(OUT / "census.json", dict(
            captures=combined, tracks=sum(len(c["tracks"]) for c in combined),
            counts=dict(Counter(c["dataset"] for c in combined)),
            prior_census_sha256=sha(PRIOR / "local/census.json"),
            ds10_manifest_sha256=sha(MINT / "manifest.json"),
            policy=">=5MS/s, >3s, support>=6; four pilot-selected frames per track",
        ))
        # Reuse prior immutable receipts and symbol arrays without copying or decoding them.
        (OUT / "decoded").mkdir(exist_ok=True)
        for c in prior["captures"]:
            dest = OUT / "decoded" / c["unit"]
            if not dest.exists():
                dest.symlink_to(PRIOR / "local/decoded" / c["unit"], target_is_directory=True)
    elif args.action == "decode":
        captures = json.loads((OUT / "census.json").read_text())["captures"]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(decode_one, c) for c in captures if c["dataset"] == "DS10"]
            for f in as_completed(futures):
                print(json.dumps(f.result()), flush=True)
    elif args.action == "windows":
        import decode_windows

        decode_windows.OUT = OUT
        decode_windows.main()
    else:
        import audit

        audit.OUT = OUT
        audit.main()


if __name__ == "__main__":
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    main()
