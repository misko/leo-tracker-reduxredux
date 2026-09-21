"""Export all non-overlapping leading RF tracklets for a frozen scan inventory.

Read-only source access. This removes the research export's longest-per-lane and
14-observation/7-second cuts, not the RF reconstruction's own detection gates.
No catalogue comparison or known receiver coordinate participates.
"""

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path


def validate_unique_series(series):
    seen = set()
    for row in series:
        ids = row["candidate_ids"]
        if len(ids) != len(set(ids)) or seen.intersection(ids):
            raise ValueError("RF observations repeated across tracklets")
        if not len(ids) == len(row["t_s"]) == len(row["y_hz"]):
            raise ValueError("observation arrays disagree")
        seen.update(ids)
    return len(seen)


def export_one(task):
    from leo.analysis.persistent_hop_trajectory import (
        persistent_hop_tracklet_graph,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    path, root, destination = task
    original = json.loads(path.read_text())
    sid = original["inventory"]["session_id"]
    store = ScannerTrackingInputStore(root)
    try:
        source = store.load(sid)
        if (
            source.input_manifest_sha256 != original["inventory"]["capture_digest"]
            or source.analysis_manifest_sha256 != original["inventory"]["analysis_digest"]
        ):
            return {"session_id": sid, "status": "source-digest-changed"}
        trajectory = reconstruct_persistent_hop_trajectories(project_scanner_candidates(source))
        hypothesis = trajectory.hypotheses[0]
        by_id = {track.tracklet_id: track for track in trajectory.tracklets}
        start = original["inventory"]["reference_utc_ns"]
        series = []
        for tid in hypothesis.tracklet_ids:
            track = by_id[tid]
            rows = sorted(
                persistent_hop_tracklet_graph(hypothesis, tid).observations,
                key=lambda row: row.support_center_utc_ns,
            )
            series.append(
                dict(
                    tracklet_id=tid,
                    channel=track.lane_key[0],
                    edge=track.lane_key[1].value,
                    actual_rf_hz=11.2e9,
                    t_s=[(r.support_center_utc_ns - start) / 1e9 for r in rows],
                    y_hz=[r.measured_cfo_hz for r in rows],
                    candidate_ids=[r.observation_id for r in rows],
                )
            )
        count = validate_unique_series(series)
        doc = dict(
            inventory={**original["inventory"], "selection": "all-leading-RF-tracklets"},
            series=series,
            episodes=[
                dict(episode_id=s["tracklet_id"], members=[s["tracklet_id"]], channel=s["channel"])
                for s in series
            ],
        )
        (destination / path.name).write_text(json.dumps(doc, indent=2) + "\n")
        old_ids = {i for s in original["series"] for i in s["candidate_ids"]}
        new_ids = {i for s in series for i in s["candidate_ids"]}
        return dict(
            session_id=sid,
            status="exported",
            old_tracklets=len(original["series"]),
            new_tracklets=len(series),
            old_observations=len(old_ids),
            new_observations=count,
            old_observations_missing=len(old_ids - new_ids),
            below_previous_gate=sum(
                len(s["t_s"]) < 14 or max(s["t_s"]) - min(s["t_s"]) < 7 for s in series
            ),
        )
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    destination = args.output / "evidence"
    destination.mkdir()
    paths = sorted((args.evidence / "evidence").glob("*.json"))
    for path in (args.evidence / "evidence").glob("*.tle"):
        (destination / path.name).write_bytes(path.read_bytes())
    tasks = [(path, args.root, destination) for path in paths]
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(export_one, tasks):
            rows.append(result)
            if len(rows) % 20 == 0:
                print(len(rows), "/", len(paths), flush=True)
    (args.output / "audit.json").write_text(json.dumps(rows, indent=2) + "\n")
    print("complete", len(rows), flush=True)


if __name__ == "__main__":
    main()
