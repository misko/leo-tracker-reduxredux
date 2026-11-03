import json
from dataclasses import asdict, replace
from pathlib import Path

from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTrajectoryConfig,
    _lane_tracklets,
)
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.storage.scanner_tracking import ScannerTrackingStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

session_id = "scan-fw-4971402f107cf8e1"
root = Path("/srv/bulk/leo")
reader = ScannerTrackingInputStore(root)
try:
    source = reader.load(session_id)
finally:
    reader.close()
origin = source.timing.first_sample_estimate_utc_ns
candidates = tuple(
    candidate
    for candidate in project_scanner_candidates(source)
    if candidate.channel == 1 and candidate.receiver_id == 0
)
status = ScannerTrackingStore(root, read_only=True).analysis_status(session_id)
published = [
    track.model_dump(mode="json")
    for track in status.product.tracklets
    if track.channel == 1 and track.receiver_id == 0
]
for track in published:
    track["start_s"] = (track["start_utc_ns"] - origin) / 1e9
    track["end_s"] = (track["end_utc_ns"] - origin) / 1e9


def summarize(track):
    return {
        "id": track.tracklet_id,
        "start_s": (track.start_utc_ns - origin) / 1e9,
        "end_s": (track.end_utc_ns - origin) / 1e9,
        "support": len(track.points),
        "slope": track.normalized_rate_hz_per_s,
        "rms": track.residual_rms_hz,
        "weight": track.weighted_support,
        "point_ids": [point.candidate_id for point in track.points],
    }


result = {
    "session_id": session_id,
    "origin_utc_ns": origin,
    "input_digest": source.input_manifest_sha256,
    "analysis_digest": source.analysis_manifest_sha256,
    "published_tracks": published,
    "candidates": [asdict(candidate) for candidate in candidates],
    "replays": {},
}
for name, start, stop, limit in (
    ("baseline", 0, 300, 8),
    ("capacity16", 0, 300, 16),
    ("window", 170, 280, 8),
):
    selected = tuple(
        candidate
        for candidate in candidates
        if start <= (candidate.support_center_utc_ns - origin) / 1e9 <= stop
    )
    tracks = []
    for lane in sorted({candidate.lane_key for candidate in selected}):
        rows = tuple(candidate for candidate in selected if candidate.lane_key == lane)
        tracks.extend(
            _lane_tracklets(
                rows,
                replace(PersistentHopTrajectoryConfig(), maximum_tracks_per_lane=limit),
            )
        )
    result["replays"][name] = [summarize(track) for track in tracks]
    print(
        json.dumps(
            {
                "replay": name,
                "tracks": [
                    {key: value for key, value in summarize(track).items() if key != "point_ids"}
                    for track in tracks
                ],
            }
        ),
        flush=True,
    )
Path(__file__).with_name("evidence.json").write_text(json.dumps(result))
