#!/usr/bin/env python3
"""Verify and bind the recorded portable80 input inventory."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

SCHEDULES = (
    "lower-000.tsv",
    "lower-008.tsv",
    "lower-016.tsv",
    "lower-024.tsv",
    "lower-032.tsv",
    "lower-040.tsv",
    "upper-000.tsv",
    "upper-008.tsv",
    "upper-016.tsv",
    "upper-024.tsv",
    "upper-032.tsv",
)
TEMPLATES = (
    "lower-exact.c128",
    "lower-control.c128",
    "upper-exact.c128",
    "upper-control.c128",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: verify_panel_inventory.py FIXTURES SCHEDULES OUTPUT", file=sys.stderr)
        return 2
    fixtures = Path(sys.argv[1]).resolve(strict=True)
    schedules = Path(sys.argv[2]).resolve(strict=True)
    output = Path(sys.argv[3])
    rows: list[dict[str, object]] = []
    schedule_hashes: dict[str, str] = {}
    raw_names: set[str] = set()
    for schedule_name in SCHEDULES:
        schedule = schedules / schedule_name
        schedule_hashes[schedule_name] = sha256(schedule)
        with schedule.open(newline="", encoding="utf-8") as stream:
            for source_row, row in enumerate(csv.reader(stream, delimiter="\t"), 1):
                if len(row) != 8:
                    raise ValueError(f"{schedule}:{source_row}: expected 8 columns")
                if row[1:4] != ["2500000", "120", "120"]:
                    raise ValueError(f"{schedule}:{source_row}: unexpected rate/dwell/stride")
                raw_name = Path(row[6]).name
                if raw_name in raw_names:
                    raise ValueError(f"duplicate portable80 raw: {raw_name}")
                raw = fixtures / raw_name
                actual_hash = sha256(raw)
                if raw.suffix != ".ci16" or raw.stem != actual_hash:
                    raise ValueError(f"content-address mismatch: {raw}")
                metadata = json.loads(row[7])
                if metadata.get("raw_sha256") != actual_hash:
                    raise ValueError(f"metadata hash mismatch: {schedule}:{source_row}")
                raw_names.add(raw_name)
                rows.append(
                    {
                        "panel_index": len(rows),
                        "schedule": schedule_name,
                        "schedule_row": source_row,
                        "edge": schedule_name.split("-", 1)[0],
                        "raw": raw_name,
                        "sha256": actual_hash,
                        "size_bytes": raw.stat().st_size,
                    }
                )
    if len(rows) != 80 or len(raw_names) != 80:
        raise ValueError(f"expected 80 unique raws, got rows={len(rows)} unique={len(raw_names)}")
    document = {
        "schema": "leo.single-rx-portable80-inventory.v1",
        "verified": True,
        "row_count": len(rows),
        "unique_raw_count": len(raw_names),
        "sample_rate_hz": 2_500_000,
        "dwell_ms": 120,
        "stride_ms": 120,
        "templates": {
            name: {
                "sha256": sha256(fixtures / name),
                "size_bytes": (fixtures / name).stat().st_size,
            }
            for name in TEMPLATES
        },
        "schedules": schedule_hashes,
        "rows": rows,
    }
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
