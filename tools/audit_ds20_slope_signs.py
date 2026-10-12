"""Summarize orbit-blind qualified slopes by edge without inferring identities."""

import json
from pathlib import Path

import numpy as np
from band_calibrated_merge_study import REPORT
from continuous_merge_study import sha, write

from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.contracts.scanner_tracking import TrackingCandidate, TrackingInput, TrackingProbe
from leo.scanner.persistent_hop import Feature103DualRxTimingV3, PersistentHopUtcTimingAuthorityV1


def main():
    base = Path("/srv/bulk/leo-dev/leo-track-merge-study/reports/2026_10_12_continuous_track_merge")
    membership_path = base / "membership.json"
    members = json.loads(membership_path.read_bytes())["members"]
    rows = []
    for member in members:
        if member["dataset"] != "DS20":
            continue
        case = base / "local/DS20" / member["session_id"]
        source_path = case / "source.json"
        d = json.loads(source_path.read_bytes())
        timing_type = {1: PersistentHopUtcTimingAuthorityV1, 3: Feature103DualRxTimingV3}[
            d["timing"]["schema_version"]
        ]
        d["timing"] = timing_type.model_validate(d["timing"])
        d["probes"] = tuple(
            TrackingProbe(
                **{**p, "candidates": tuple(TrackingCandidate(**c) for c in p["candidates"])}
            )
            for p in d["probes"]
        )
        source = TrackingInput(**d)
        prepared = json.loads((case / "baseline.json").read_bytes())
        candidates = {c.candidate_id: c for c in project_scanner_candidates(source)}
        trajectory = reconstruct_persistent_hop_trajectories(
            tuple(candidates[i] for i in prepared["candidate_ids"])
        )
        selected = []
        for t in trajectory.tracklets:
            span = (t.end_utc_ns - t.start_utc_ns) / 1e9
            if len(t.points) < 15 or span < 15:
                continue
            selected.append(
                {
                    "lane": t.lane_key,
                    "slope_hz_s": t.normalized_rate_hz_per_s,
                    "points": len(t.points),
                    "span_s": span,
                    "linear_rms_hz": t.residual_rms_hz,
                }
            )
        rows.append(
            {
                "session_id": member["session_id"],
                "source_sha256": sha(source_path),
                "tracks": selected,
            }
        )
    aggregates = []
    for edge in ("lower", "upper"):
        tracks = [t for r in rows for t in r["tracks"] if t["lane"][1] == edge]
        slopes = np.array([t["slope_hz_s"] for t in tracks])
        aggregates.append(
            {
                "edge": edge,
                "qualified_tracks": len(tracks),
                "positive_above_200": int(np.sum(slopes > 200)),
                "negative_below_minus_200": int(np.sum(slopes < -200)),
                "median_slope_hz_s": float(np.median(slopes)),
            }
        )
    write(
        REPORT / "edge-slope-sign-audit.json",
        {
            "membership_sha256": sha(membership_path),
            "script_sha256": sha(Path(__file__)),
            "aggregates": aggregates,
            "rows": rows,
            "scope": (
                "Qualified orbit-blind straight segments normalized to 11.2 GHz; "
                "data diagnostics only, no true satellite identities or calibration proof"
            ),
        },
    )
    print(json.dumps(aggregates, indent=2))


if __name__ == "__main__":
    main()
