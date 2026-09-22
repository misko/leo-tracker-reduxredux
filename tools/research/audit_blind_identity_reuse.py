"""Count frozen conditional identity support; no new association or truth input."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def summarize(tracks, receivers, threshold):
    """Threshold is descriptive only; counts are not verified satellite identities."""
    if not 0 < threshold <= 1:
        raise ValueError("threshold must be in (0, 1]")
    support = defaultdict(list)
    seen = set()
    for track in tracks:
        key = (track["session_id"], track["episode_id"])
        if key in seen:
            raise ValueError("duplicate track")
        seen.add(key)
        candidates = track["candidates"]
        if len({c["norad"] for c in candidates}) != len(candidates):
            raise ValueError("duplicate candidate")
        for candidate in candidates:
            if candidate["weight"] >= threshold:
                support[candidate["norad"]].append((*key, receivers[key]))
    return {
        "threshold": threshold,
        "candidate_count": len(support),
        "supported_track_count": len({row[:2] for rows in support.values() for row in rows}),
        "repeated_across_tracks": sum(len(rows) > 1 for rows in support.values()),
        "repeated_across_scans": sum(len({r[0] for r in rows}) > 1 for rows in support.values()),
        "repeated_across_receivers": sum(
            len({r[2] for r in rows}) > 1 for rows in support.values()
        ),
    }


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def audit(refinement, evidence):
    result = json.loads(refinement.read_text())
    if result.get("position_truth_used") is not False or not result.get("complete"):
        raise ValueError("completed blind refinement required")
    receivers, bindings = {}, {}
    for session in result["sessions"]:
        if Path(session).name != session:
            raise ValueError("unsafe session name")
        path = evidence / "evidence" / (session + ".json")
        bindings[session] = digest(path)
        if bindings[session] != result["provenance"][session]["rf_digest"]:
            raise ValueError("RF evidence digest mismatch")
        doc = json.loads(path.read_text())
        for source in doc["series"]:
            key = (session, source["tracklet_id"])
            if key in receivers:
                raise ValueError("duplicate source")
            receivers[key] = source["receiver_id"]
    return {
        "schema": "blind-identity-reuse-diagnostic-v1",
        "refinement_digest": digest(refinement),
        "evidence_digests": bindings,
        "source_digest": digest(Path(__file__)),
        "truth_used": False,
        "scope": "frozen retained candidate weights; uncalibrated and incomplete support",
        "tracks": len(result["tracks"]),
        "null_mass_sum": sum(t["null_weight"] for t in result["tracks"]),
        "omitted_mass_sum": sum(t["omitted_identity_weight"] for t in result["tracks"]),
        "thresholds": [summarize(result["tracks"], receivers, t) for t in (0.1, 0.5, 0.9)],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refinement", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.refinement, args.evidence)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
