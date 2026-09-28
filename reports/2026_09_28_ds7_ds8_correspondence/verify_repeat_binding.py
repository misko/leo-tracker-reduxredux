"""Verify decoded acquisition solutions belong to independently labelled tracks."""

import dataclasses
import json
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).parent / "local"


def main():
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    groups = defaultdict(list)
    for name in ("repeat-0", "repeat-1", "repeat-3", "repeat-4", "repeat-5"):
        inventory = json.loads((OUT / name / "inventory.json").read_text())
        label = json.loads((OUT / name / "labels.json").read_text())[0]
        groups[label["session_id"]].append((name, inventory, label))
    source = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    rows = []
    for sid, group in groups.items():
        raw = source.load(sid)
        points = project_scanner_candidates(raw)
        graph = reconstruct_persistent_hop_trajectories(
            points, config=PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6)
        )
        for name, inventory, label in group:
            assert raw.input_manifest_sha256 == inventory["manifest_sha256"]
            track = next(t for t in graph.tracklets if t.tracklet_id == label["track_id"])
            ids = {p.candidate_id for p in track.points}
            members = {
                (p.visit_index, p.receiver_id, p.probe_index, p.candidate_rank)
                for p in points
                if p.candidate_id in ids
            }
            e = next(
                e for e in inventory["exports"] if e["probe"]["receiver_id"] == label["receiver_id"]
            )
            matches = []
            for p in raw.probes:
                pd = {k: v for k, v in dataclasses.asdict(p).items() if k != "candidates"}
                if pd != e["probe"]:
                    continue
                for c in p.candidates:
                    if (
                        p.visit_index,
                        p.receiver_id,
                        p.probe_index,
                        c.candidate_rank,
                    ) not in members:
                        continue
                    observed = {k: v for k, v in e["candidate"].items() if k != "candidate_rank"}
                    bound = {
                        k: v for k, v in dataclasses.asdict(c).items() if k != "candidate_rank"
                    }
                    if observed == bound:
                        matches.append(c.candidate_rank)
            assert matches, f"Decoded acquisition not bound to labelled track: {name}"
            rows.append(
                dict(
                    group=name,
                    session_id=sid,
                    track_id=label["track_id"],
                    receiver_id=label["receiver_id"],
                    visit=e["probe"]["visit_index"],
                    decoded_candidate_rank=e["candidate"]["candidate_rank"],
                    identical_track_candidate_ranks=matches,
                    analysis_manifest_sha256=raw.analysis_manifest_sha256,
                )
            )
            print(name, "verified", flush=True)
    source.close()
    (OUT / "repeat-binding-verification.json").write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
