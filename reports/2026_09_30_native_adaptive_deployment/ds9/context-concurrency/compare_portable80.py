#!/usr/bin/env python3
"""Compare detector replay science fields while excluding diagnostic timing."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def calls(path: Path) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for line in path.read_text().splitlines():
        document = json.loads(line)
        if "result" not in document:
            continue
        result = document["result"]
        for key in (
            "call_cpu_ms",
            "call_wall_ms",
            "detector_cpu_ms",
            "peak_rss_kib_before",
            "peak_rss_kib_after",
            "thermal_available_before",
            "thermal_millidegrees_before",
            "thermal_available_after",
            "thermal_millidegrees_after",
            "profile_enabled",
            "profile",
        ):
            result.pop(key, None)
        for row in result["rows"]:
            row.pop("timings_ms", None)
        results.append(result)
    return results


def digest(value: object) -> str:
    blob = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    summary: dict[str, object] = {
        "schema": "org.leo.native-adaptive-detector-context-parity/v1",
        "case_count": 80,
        "comparisons": {},
        "artifacts": {},
    }
    passed = True
    for mode in ("ordinary", "fractional"):
        old = calls(args.directory / f"old-{mode}.jsonl")
        new = calls(args.directory / f"new-{mode}.jsonl")
        exact = old == new and len(old) == len(new) == 80
        passed &= exact
        summary["comparisons"][mode] = {
            "old_calls": len(old),
            "new_calls": len(new),
            "non_timing_exact": exact,
            "old_projection_sha256": digest(old),
            "new_projection_sha256": digest(new),
        }
    for name in (
        "old-ordinary.jsonl",
        "old-fractional.jsonl",
        "new-ordinary.jsonl",
        "new-fractional.jsonl",
    ):
        summary["artifacts"][name] = hashlib.sha256(
            (args.directory / name).read_bytes()
        ).hexdigest()
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
