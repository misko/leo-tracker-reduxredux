"""Read only saved timing authorities for the twelve training diagnostic scans."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPLIT = HERE.parent / "2026_09_23_position_random_group_split/manifest.json"
DRIFT = HERE.parent / "2026_09_23_receiver_drift_audit/receiver_drift.json"


def main():
    split = json.loads(SPLIT.read_text())
    # Match the diagnostic's first twelve available day-cache training IDs.
    index = set()
    for path in (HERE.parent / "2026_09_23_day_position_validation/replication").glob(
        "block_*/cache/cache_manifest.json"
    ):
        index.update(row["session_id"] for row in json.loads(path.read_text())["scans"])
    ids = [sid for sid in split["partitions"]["train"]["session_ids"] if sid in index][:12]
    program = """
import json,sys
from pathlib import Path
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
rows=[]
try:
    for sid in sys.argv[1:]:
        timing=store.load(sid).timing
        rows.append({'session_id':sid,'timing':timing.model_dump(mode='json')})
finally: store.close()
print(json.dumps(rows))
"""
    result = subprocess.run(
        ["sudo", "-n", "-u", "leo", sys.executable, "-c", program, *ids],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    rows = json.loads(result.stdout)
    output = {
        "scope": "training timing authorities only; no validation/test sources",
        "source_manifest_sha256": hashlib.sha256(SPLIT.read_bytes()).hexdigest(),
        "worker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "rows": rows,
    }
    (HERE / "training_timing.json").write_text(json.dumps(output, indent=2) + "\n")
    print(
        json.dumps(
            [
                {
                    "session_id": r["session_id"],
                    "bracket_ms": r["timing"]["first_sample_bracket_width_ns"] / 1e6,
                    "qualified": r["timing"]["qualified"],
                }
                for r in rows
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
