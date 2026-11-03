#!/usr/bin/env python3
import hashlib
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REFERENCE = ROOT / "ds9/receiver-authority-ablation-v1/wideband-research/retention-audit-v1/visit-0301.jsonl"
CANDIDATE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "visit-0301-host.jsonl"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def scientific(value):
    if isinstance(value, list):
        return [scientific(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if (
            key == "timings_ms"
            or key.endswith("_cpu_ms")
            or key.endswith("_wall_ms")
            or key.startswith("write_cpu_ms")
            or key.startswith("write_wall_ms")
            or key == "peak_rss_kib"
            or key.startswith("peak_rss_kib_")
        ):
            continue
        result[key] = scientific(item)
    return result


reference = load(REFERENCE)
candidate = load(CANDIDATE)
equal = scientific(reference) == scientific(candidate)
output = {
    "schema": "leo-corrected-wideband-nextup-comparison/v1",
    "status": "pass" if equal else "fail",
    "scope": "DS9 visit 301; exact equality after removing timing and RSS diagnostics",
    "reference_sha256": sha(REFERENCE),
    "candidate_sha256": sha(CANDIDATE),
    "non_timing_equal": equal,
}
print(json.dumps(output, indent=2, sort_keys=True))
raise SystemExit(0 if equal else 1)
