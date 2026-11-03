#!/usr/bin/env python3
"""Verify C1 byte/counter parity over the frozen 80-dwell panel."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--binary", required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--fixtures", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    cases = json.loads(a.manifest.read_text())["cases"]
    checks = []
    for case in cases:
        path = a.fixtures / case["raw_file"]
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == case["raw_sha256"]
        rate, first = case["rate_hz"], case["sample_start_counter"]
        width = rate // 50
        expected = f"0\t{first}\t{width}\t{hashlib.sha256(raw[: width * 8]).hexdigest()}\n"
        for chunk in (1, 7919, 270001, 900000):
            result = subprocess.run(
                [
                    a.binary,
                    str(path),
                    str(rate),
                    "2",
                    str(first),
                    str(case["sample_end_counter"]),
                    str(case["visit_index"]),
                    str(chunk),
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            assert result.stdout == expected, (case["raw_file"], chunk)
        checks.append(dict(raw_sha256=case["raw_sha256"], window_sha256=expected.split()[-1]))
    a.output.write_text(
        json.dumps(
            dict(
                status="pass",
                cases=len(cases),
                chunk_samples=[1, 7919, 270001, 900000],
                checks=checks,
                scope="C1 existing 120ms dual-RX DS9 dwells, first20ms, four delivery chunkings",
            ),
            indent=2,
        )
        + "\n"
    )
    print(f"{len(cases)} DS9 dwells x 4 chunkings: pass")


if __name__ == "__main__":
    main()
