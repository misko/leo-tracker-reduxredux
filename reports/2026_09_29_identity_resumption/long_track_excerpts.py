"""Six bounded offline excerpts along two exactly rebound DS10 trajectories."""

import dataclasses
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
PRIOR = BASE.parent / "2026_09_29_ds10_signal_extension/local"
OUT = BASE / "local/long-track"
sys.path.insert(0, str(BASE.parent / "2026_09_29_all_track_symbols"))
from decode_tracks import recover  # noqa: E402


def temporal_choices(points):
    times = np.array([p.support_center_utc_ns for p in points], dtype=np.int64)
    segment = np.minimum(2, ((times - times.min()) * 3 // (times.max() - times.min() + 1)))
    return [max((p for p, s in zip(points, segment, strict=True) if s == k),
                key=lambda p: (p.margin, -p.visit_index, -p.candidate_rank))
            for k in range(3) if np.any(segment == k)]


def main():
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    OUT.mkdir(exist_ok=True)
    receipt = OUT / "recovery.json"
    if receipt.exists():
        raise SystemExit("Existing result retained; inspect it before a new experiment")
    capture_path = PRIOR / "captures/DS10-F010.json"
    capture = json.loads(capture_path.read_text())
    seeds = json.loads((BASE / "local/rows.json").read_text())
    seeds = [next(r for r in seeds if r["id"] == name)
             for name in ("DS10-F010-T0031", "DS10-F010-T0040")]
    inputs = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    results = []
    try:
        raw = inputs.load(capture["session"])
        assert raw.input_manifest_sha256 == capture["capture_manifest"]
        assert raw.analysis_manifest_sha256 == capture["analysis_manifest"]
        points = project_scanner_candidates(raw)
        graph = reconstruct_persistent_hop_trajectories(
            points, config=PersistentHopTrajectoryConfig(minimum_span_s=3., minimum_support=6))
        by_id = {p.candidate_id: p for p in points}
        tracks = {t.tracklet_id: t for t in graph.tracklets}
        probes = {(p.receiver_id, p.visit_index, p.probe_index): p for p in raw.probes}
        with store.reader(capture["session"]) as reader, tempfile.TemporaryDirectory(dir=OUT) as td:
            for seed in seeds:
                track = next(t for t in capture["tracks"] if t["track_id"] == seed["track_id"])
                ps = [by_id[p.candidate_id] for p in tracks[seed["track_id"]].points]
                assert [p.visit_index for p in ps] == track["visits"]
                assert all(abs((p.support_center_utc_ns - capture["start_utc_ns"]) / 1e9 - t)
                           < 1e-9 for p, t in zip(ps, track["times_s"], strict=True))
                for part, point in enumerate(temporal_choices(ps)):
                    probe = probes[point.receiver_id, point.visit_index, point.probe_index]
                    candidate = next(c for c in probe.candidates
                                     if c.candidate_rank == point.candidate_rank)
                    _, values = reader.read_visit_ci16(point.visit_index)
                    begin = round(probe.probe_start_ms * capture["rate"] / 1000)
                    excerpt = values[begin:begin + round(.020 * capture["rate"]),
                                     probe.receiver_id, :].copy()
                    np.save(Path(td) / "stream.npy", excerpt)
                    p = dataclasses.asdict(probe)
                    p.pop("candidates")
                    source = dict(name="stream", sample_rate_hz=capture["rate"], probe=p,
                                  candidate=dataclasses.asdict(candidate),
                                  excerpt_sha256=hashlib.sha256(excerpt.tobytes()).hexdigest())
                    bins, z, meta = recover(source, Path(td), 15, all_supported_bins=True)
                    qualified = [f for f in meta["evaluation_frames"]
                                 if meta["diagnostics"][f]["held_pilot_coherence"] > .5]
                    path = OUT / f"{seed['id']}-part{part}.npz"
                    np.savez_compressed(path, bins=bins, z=z, metadata=json.dumps(meta))
                    results.append(dict(id=seed["id"], part=part, track_id=seed["track_id"],
                                        candidate_id=point.candidate_id, visit=point.visit_index,
                                        time_ns=point.support_center_utc_ns, source=source,
                                        qualified=qualified, artifact=str(path),
                                        artifact_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
                    print(seed["id"], part, point.visit_index, "qualified", len(qualified),
                          flush=True)
    finally:
        inputs.close()
        store.close()
    receipt.write_text(json.dumps(dict(rows=results,
        capture_sha256=hashlib.sha256(capture_path.read_bytes()).hexdigest(),
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()), indent=2) + "\n")


if __name__ == "__main__":
    main()
