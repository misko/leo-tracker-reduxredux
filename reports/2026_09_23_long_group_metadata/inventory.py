"""Metadata-only older-recording inventory for long random-group feasibility."""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.request import urlopen

from leo.storage.adaptive_hop import AdaptiveHopIqStore

OUT = Path(__file__).resolve().parent
CUTOFF = datetime(2026, 9, 23, 16, 35, 28, tzinfo=UTC)
END = CUTOFF
START = END - timedelta(hours=72)


def excluded():
    root = OUT.parent
    random_manifest = json.loads(
        (root / "2026_09_23_position_random_group_split/manifest.json").read_text()
    )
    ids = {sid for part in random_manifest["partitions"].values() for sid in part["session_ids"]}
    dataset = json.loads(
        (root / "2026_09_23_position_train_val_test/dataset/manifest.json").read_text()
    )
    ids |= {sid for part in dataset["partitions"].values() for sid in part.get("session_ids", [])}
    return ids


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--stdout-only", action="store_true")
    args = args.parse_args()
    blocked = excluded()
    start_ns = int(START.timestamp() * 1e9)
    end_ns = int(END.timestamp() * 1e9)
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        candidates = [
            (stamp, sid)
            for stamp, sid in store.publication_index()
            if start_ns <= stamp < end_ns and sid not in blocked
        ]
    finally:
        store.close()
    candidates = sorted(set(candidates))
    pre_cap = len(candidates)
    remainder = max(0, pre_cap - 200)
    candidates = candidates[:200]

    def one(item):
        _, sid = item
        try:
            with urlopen(
                f"http://127.0.0.1:8090/api/v3/scanner/adaptive-sessions/{sid}", timeout=5
            ) as r:
                c = json.load(r)["capture"]
            stamp = datetime.fromisoformat(c["captured_at"]).astimezone(UTC)
            if not START <= stamp < END:
                return {"session_id": sid, "state": "outside_capture_window"}
            return {
                "session_id": sid,
                "captured_at": c["captured_at"],
                "sample_rate_hz": c["sample_rate_hz"],
                "nominal_duration_s": c.get("nominal_duration_seconds"),
            }
        except Exception as e:
            return {"session_id": sid, "state": "unavailable", "reason": type(e).__name__}

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(one, candidates))
    rows.sort(key=lambda x: (x.get("captured_at", ""), x["session_id"]))
    groups = {}
    for row in rows:
        if "captured_at" not in row:
            continue
        stamp = datetime.fromisoformat(row["captured_at"]).astimezone(UTC)
        base = stamp.replace(hour=(stamp.hour // 8) * 8, minute=0, second=0, microsecond=0)
        groups.setdefault(base.isoformat(), []).append(row)
    blocks = [
        {
            "utc_8h_start": k,
            "scan_count": len(v),
            "at_least_40_nominal_300s_scans": sum(x.get("nominal_duration_s") == 300 for x in v)
            >= 40,
            "session_ids": [x["session_id"] for x in v],
            "max_inter_capture_gap_s": max(
                [
                    (b - a).total_seconds()
                    for a, b in zip(
                        [datetime.fromisoformat(x["captured_at"]).astimezone(UTC) for x in v],
                        [datetime.fromisoformat(x["captured_at"]).astimezone(UTC) for x in v][1:],
                        strict=False,
                    )
                ],
                default=None,
            ),
        }
        for k, v in groups.items()
    ]
    result = {
        "metadata_only": True,
        "worker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "position_or_track_outcomes_opened": False,
        "window_start": START.isoformat(),
        "window_end_exclusive": END.isoformat(),
        "prospective_cutoff_exclusive": CUTOFF.isoformat(),
        "excluded_randomized_and_quarantine_ids_count": len(blocked),
        "candidate_count_before_request_cap": pre_cap,
        "request_cap": 200,
        "uninspected_remainder_count": remainder,
        "api_timeout_s": 5,
        "api_workers": 4,
        "scans": rows,
        "utc_8h_groups": blocks,
    }
    if not args.stdout_only:
        (OUT / "inventory.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
