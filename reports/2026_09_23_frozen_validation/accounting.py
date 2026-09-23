"""Count frozen support without reading frequency values or position outcomes."""

import json
import math
from pathlib import Path

from export import CACHE, HERE, digest


def main():
    frozen = json.loads((HERE / "freeze.json").read_text())
    bindings = {
        r["session_id"]: r for r in json.loads((HERE / "cache_receipts.json").read_text())["rows"]
    }
    groups = []
    for group in frozen["groups"]:
        scans = []
        for sid in group["session_ids"]:
            path = CACHE / sid / "cache_receipt.json"
            assert digest(path) == bindings[sid]["receipt"]
            evidence = json.loads(path.read_text())["prepared_evidence"]
            tracks = [t for t in evidence["tracks"] if max(t["times_s"]) - min(t["times_s"]) >= 3.0]
            scans.append(
                {
                    "session_id": sid,
                    "start_utc_ns": evidence["start_utc_ns"],
                    "tracks": len(tracks),
                    "observations": sum(len(t["times_s"]) for t in tracks),
                    "training_rows": sum(sum(t["training_mask"]) for t in tracks),
                    "occupied_track_seconds": sum(
                        len({math.floor(v) for v in t["times_s"]}) for t in tracks
                    ),
                }
            )
        for count in (1, 6, 16, len(scans)):
            active = scans[:count]
            groups.append(
                {
                    "group": group["utc_8h_start"],
                    "scan_count": count,
                    "start_span_seconds": (active[-1]["start_utc_ns"] - active[0]["start_utc_ns"])
                    / 1e9,
                    **{
                        key: sum(s[key] for s in active)
                        for key in (
                            "tracks",
                            "observations",
                            "training_rows",
                            "occupied_track_seconds",
                        )
                    },
                }
            )
    result = {
        "views": groups,
        "bindings": {
            "tool": digest(Path(__file__)),
            "freeze": digest(HERE / "freeze.json"),
            "receipts": digest(HERE / "cache_receipts.json"),
        },
        "notes": (
            "Counts are correlated evidence, not independent satellites or independent IQ samples. "
            "Start span excludes the final capture duration."
        ),
    }
    (HERE / "accounting.json").write_text(json.dumps(result, indent=2) + "\n")
    for row in groups:
        print(row)


if __name__ == "__main__":
    main()
