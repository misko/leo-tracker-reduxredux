"""Bounded host/native support geometry comparison; server is a test oracle only."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--oracle-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("refusing to overwrite an existing evidence receipt")
    sys.path.insert(0, str(args.oracle_source))
    from leo.application.persistent_hop_trajectory import fractional_glrt64_support_geometry

    rows = []
    for rate in (2_500_000, 5_000_000, 7_500_000, 10_000_000):
        for epoch in (0, 100, round(rate / 750) - 1):
            for frac in (-2.0, -0.75, -0.25, 0.0, 0.25, 0.75, 2.0):
                expected = fractional_glrt64_support_geometry(
                    SimpleNamespace(
                        integer_epoch_sample=epoch, fractional_epoch_offset_samples=frac
                    ),
                    sample_rate_hz=rate,
                    probe_sample_count=rate // 50,
                )
                actual = json.loads(
                    subprocess.check_output(
                        [str(args.binary), str(rate), str(rate // 50), str(epoch), str(frac)],
                        text=True,
                    )
                )
                assert actual["first"] == expected.source_start_in_probe
                assert actual["end"] == expected.source_end_in_probe
                delta = abs(actual["center"] - expected.center_in_probe_samples)
                assert delta < 1e-9
                for key, reference in zip(
                    ("moment2", "moment3"), expected.factorial_support_moments_s[2:], strict=True
                ):
                    assert abs(actual[key] - reference) < 1e-18
                rows.append(
                    {"rate": rate, "epoch": epoch, "offset": frac, "center_error_samples": delta}
                )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "status": "pass",
                "scope": "C3 physical support geometry, not full observation identity projection",
                "binary_sha256": hashlib.sha256(args.binary.read_bytes()).hexdigest(),
                "oracle_source": str(args.oracle_source),
                "cases": rows,
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps({"status": "pass", "cases": len(rows), "output": str(args.output)}))


if __name__ == "__main__":
    main()
