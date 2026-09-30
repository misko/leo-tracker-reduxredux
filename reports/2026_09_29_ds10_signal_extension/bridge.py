"""Bridge production IDs through public default reconstruction and full point sequences."""

import json
import sys
import time
from collections import defaultdict
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from extend import MINT, OUT, PRIOR, sha, write  # noqa: E402


def signature(receiver, channel, rf, visits, times, frequencies):
    return (receiver, channel, rf, tuple(visits), tuple(round(t * 1e9) for t in times),
            tuple(round(y, 6) for y in frequencies))


def bridge(c):
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    path = OUT / "bridges" / (c["unit"] + ".json")
    if path.exists():
        return json.loads(path.read_text())
    root = MINT if c["dataset"] == "DS10" else BASE.parent / "2026_09_28_ds9_post_ds8"
    evidence_path = root / "analysis" / (c["session"] + ".json")
    evidence = json.loads(evidence_path.read_text())
    product = evidence["tracking"]["product"]
    assert product["analysis_manifest_sha256"] == c["analysis_manifest"]
    assert product["input_manifest_sha256"] == c["capture_manifest"]
    archived = {t["tracklet_id"]: t for t in product["tracklets"]}
    source = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        raw = source.load(c["session"])
        assert raw.input_manifest_sha256 == c["capture_manifest"]
        assert raw.analysis_manifest_sha256 == c["analysis_manifest"]
        points = project_scanner_candidates(raw)
        by_id = {p.candidate_id: p for p in points}
        graph = reconstruct_persistent_hop_trajectories(
            points, config=PersistentHopTrajectoryConfig()
        )
        available = defaultdict(list)
        for track in graph.tracklets:
            if track.tracklet_id not in archived:
                continue
            pts = [by_id[p.candidate_id] for p in track.points]
            times = [(p.support_center_utc_ns - c["start_utc_ns"]) / 1e9 for p in pts]
            key = signature(pts[0].receiver_id, pts[0].channel, pts[0].actual_rf_hz,
                            [p.visit_index for p in pts], times,
                            [p.normalized_dealiased_cfo_hz for p in track.points])
            available[key].append(dict(
                production_track_id=track.tracklet_id,
                candidate_ids=[p.candidate_id for p in track.points],
            ))
        mappings = []
        for track in c["tracks"]:
            key = signature(track["receiver_id"], track["channel"], track["rf_hz"],
                            track["visits"], track["times_s"], track["measured_hz"])
            matches = available.get(key, [])
            if len(matches) == 1:
                mappings.append(dict(census_track_id=track["track_id"], **matches[0]))
        result = dict(
            unit=c["unit"], session=c["session"], dataset=c["dataset"], mappings=mappings,
            census_tracks=len(c["tracks"]), archived_tracks=len(archived),
            reproduced_archived_tracks=sum(t.tracklet_id in archived for t in graph.tracklets),
            source_sha256=sha(evidence_path), method_sha256=sha(Path(__file__)),
            config_digest=graph.config_digest,
            policy="Exact archived production ID reproduced by public default reconstruction; "
            "all visits, nanosecond support-center times and microhertz normalized CFO "
            "sequences match uniquely. No nearest-time or nearest-frequency label join.",
        )
        write(path, result)
        return result
    finally:
        source.close()


def main():
    associations = json.loads((OUT / "associations.json").read_text())["rows"]
    by_id = defaultdict(set)
    for r in associations:
        by_id[r["norad_id"]].add(r["session"])
    repeated = {i for i, ss in by_id.items() if len(ss) > 1}
    sessions = {r["session"] for r in associations if r["norad_id"] in repeated
                or r["tier"] == "control_supported_candidate"}
    old = [c for c in json.loads((PRIOR / "local/census.json").read_text())["captures"]
           if c["dataset"] == "DS9" and c["session"] in sessions]
    members = json.loads((MINT / "manifest.json").read_text())["captures"]
    targets = {c["unit"] for c in old} | {
        f"DS10-F{i:03d}" for i, r in enumerate(members, 1)
        if r["sample_rate_hz"] >= 5_000_000 and r["session_id"] in sessions
    }
    write(OUT / "bridge-plan.json", dict(
        targets=sorted(targets),
        selection="Orbit labels selected before reading correlations: every cross-session "
        "repeated archived ID or control-supported candidate, in >=5MS/s recordings.",
    ))
    print("Target recordings", len(targets), flush=True)
    pending, done = {}, set()
    with ProcessPoolExecutor(max_workers=4) as pool:
        while done != targets:
            available = old + [json.loads(p.read_text()) for p in
                               sorted((OUT / "captures").glob("DS10-*.json"))]
            for c in available:
                unit = c["unit"]
                if unit not in targets or unit in done or unit in pending.values():
                    continue
                if len(pending) >= 4:
                    break
                pending[pool.submit(bridge, c)] = unit
            if not pending:
                time.sleep(2)
                continue
            ready, _ = wait(pending, timeout=2, return_when=FIRST_COMPLETED)
            for f in ready:
                unit = pending.pop(f)
                result = f.result()
                done.add(unit)
                print(unit, len(result["mappings"]), "bound /", result["census_tracks"],
                      "reproduced", result["reproduced_archived_tracks"], flush=True)


if __name__ == "__main__":
    main()
