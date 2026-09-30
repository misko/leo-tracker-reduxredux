"""Recover two pilot-selected candidates from identical existing DS7 excerpts."""

import argparse
import dataclasses
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

BASE = Path(__file__).resolve().parent
OUT = BASE / "local/simultaneous"
sys.path.insert(0, str(BASE))
from long_track_excerpts import recover, temporal_choices  # noqa: E402


def selected_job(pair):
    if pair is None:
        return "DS7-F069", (7, 17), OUT
    jobs = [("DS7-F020", (28, 34)), ("DS7-F035", (33, 39)),
            ("DS7-F042", (22, 27)), ("DS7-F042", (46, 51))]
    if pair not in range(len(jobs)):
        raise ValueError("Only the four inventoried 5-MS/s opportunities are authorized here")
    unit, indices = jobs[pair]
    return unit, indices, BASE / f"local/simultaneous5/pair-{pair}"


def main():
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", type=int, choices=range(4))
    args = parser.parse_args()
    unit, indices, output = selected_job(args.pair)
    output.mkdir(parents=True, exist_ok=True)
    receipt = output / "recovery.json"
    if receipt.exists():
        raise SystemExit("Existing result retained")
    census_path = BASE.parent / "2026_09_29_ds10_signal_extension/local/census.json"
    census = json.loads(census_path.read_text())
    capture = next(c for c in census["captures"] if c["unit"] == unit)
    metadata_path = BASE / "local/rows.json"
    rows = json.loads(metadata_path.read_text())
    seeds = [next(r for r in rows if r["id"] == f"{unit}-T{i:04d}") for i in indices]
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
        matched = []
        for seed in seeds:
            archived = next(t for t in capture["tracks"] if t["track_id"] == seed["track_id"])
            ps = [by_id[p.candidate_id] for p in tracks[seed["track_id"]].points]
            assert [p.visit_index for p in ps] == archived["visits"]
            assert all(abs((p.support_center_utc_ns - capture["start_utc_ns"]) / 1e9 - t)
                       < 1e-9 for p, t in zip(ps, archived["times_s"], strict=True))
            assert len({p.visit_index for p in ps}) == len(ps)
            matched.append({p.visit_index: p for p in ps})
        common = sorted(matched[0].keys() & matched[1].keys())
        choices = []
        for visit in common:
            a, b = [m[visit] for m in matched]
            assert (a.receiver_id, a.probe_index) == (b.receiver_id, b.probe_index)
            choices.append(SimpleNamespace(visit_index=visit, candidate_rank=0,
                support_center_utc_ns=min(a.support_center_utc_ns, b.support_center_utc_ns),
                margin=min(a.margin, b.margin)))
        selected = temporal_choices(choices)
        with (
            store.reader(capture["session"]) as reader,
            tempfile.TemporaryDirectory(dir=output) as td,
        ):
            for part, choice in enumerate(selected):
                _, values = reader.read_visit_ci16(choice.visit_index)
                for seed, mapping in zip(seeds, matched, strict=True):
                    point = mapping[choice.visit_index]
                    probe = probes[point.receiver_id, point.visit_index, point.probe_index]
                    candidate = next(c for c in probe.candidates
                                     if c.candidate_rank == point.candidate_rank)
                    start = round(probe.probe_start_ms * capture["rate"] / 1000)
                    excerpt = values[start:start + round(.020 * capture["rate"]),
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
                    path = output / f"{seed['id']}-part{part}.npz"
                    np.savez_compressed(path, bins=bins, z=z, metadata=json.dumps(meta))
                    results.append(dict(id=seed["id"], part=part, track_id=seed["track_id"],
                                        visit=point.visit_index,
                                        time_ns=point.support_center_utc_ns,
                                        source=source, qualified=qualified, artifact=str(path),
                                        artifact_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
                    print(seed["id"], part, point.visit_index,
                          "qualified", len(qualified), flush=True)
    finally:
        inputs.close()
        store.close()
    receipt.write_text(json.dumps(dict(rows=results, common_visits=common,
        census_sha256=hashlib.sha256(census_path.read_bytes()).hexdigest(),
        metadata_sha256=hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()), indent=2) + "\n")


if __name__ == "__main__":
    main()
