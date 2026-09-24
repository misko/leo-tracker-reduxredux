#!/usr/bin/env python3
"""Record authoritative tracking readiness for the exact frozen DS2 plan."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
API = "http://127.0.0.1:8090/api/v1/scanner/tracking"


def status(session_id: str) -> dict[str, Any]:
    try:
        with urlopen(f"{API}/{session_id}", timeout=20) as response:  # noqa: S310
            value = json.load(response)
        product = value.get("product")
        return {
            "session_id": session_id,
            "status": "available",
            "state": value.get("state"),
            "phase": value.get("phase"),
            "failure_summary": value.get("failure_summary"),
            "tracking": None
            if not isinstance(product, dict)
            else {
                "schema_version": product.get("schema_version"),
                "analysis_id": product.get("analysis_id"),
                "input_manifest_sha256": product.get("input_manifest_sha256"),
                "analysis_manifest_sha256": product.get("analysis_manifest_sha256"),
                "configuration_digest": product.get("configuration_digest"),
                "tracklet_count": len(product.get("tracklets", [])),
                "tle_candidate_count": len(product.get("tle_candidates", [])),
                "review_count": product.get("review_count"),
                "artifact_count": len(product.get("artifacts", [])),
            },
        }
    except Exception as error:
        return {"session_id": session_id, "status": "unavailable", "reason": type(error).__name__}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=HERE / "plan.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    sessions = [item["session_id"] for item in plan["actions"]]
    if len(sessions) != 20 or len(set(sessions)) != 20:
        raise ValueError("status snapshot requires the exact 20-session frozen DS2 plan")
    rows = [status(session_id) for session_id in sessions]
    counts: dict[str, int] = {}
    for row in rows:
        key = row.get("state", row["status"])
        counts[key] = counts.get(key, 0) + 1
    output = {
        "schema": "ds2-frozen-backfill-status/v1",
        "observed_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_plan_sha256": "sha256:" + hashlib.sha256(args.plan.read_bytes()).hexdigest(),
        "counts": counts,
        "sessions": rows,
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    main()
