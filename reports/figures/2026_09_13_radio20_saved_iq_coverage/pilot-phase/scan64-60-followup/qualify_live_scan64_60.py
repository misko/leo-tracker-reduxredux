"""Exact short-profile/binary qualification on the authorized .20 radio."""

import hashlib
from pathlib import Path
import sys

sys.path.insert(0, "/home/mouse9911/gits/plutosdr-fw-radio20-tracking/scripts")
import qualify_glrt_cpu_live20 as live

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("deployment receipt and output directory required")
    binary = live.EVIDENCE / "glrt-cpu-live-scan64-v1"
    if (
        hashlib.sha256(binary.read_bytes()).hexdigest()
        != "ede7d9bd6e60fb692c916d9f0707595d02d6f0a39066174c1aaf827616cfd456"
    ):
        raise SystemExit("unreviewed binary")
    deployment = Path(sys.argv[1])
    output = Path(sys.argv[2])
    sys.argv = [
        __file__,
        "--deployment",
        str(deployment),
        "--rate",
        "60000000",
        "--binary",
        str(binary),
        "--blocks",
        "1536",
        "--observer-spacing",
        "3",
        "--candidate-budget",
        "64",
        "--lo-hz",
        "1690312500",
        "--output",
        str(output),
    ]
    live.main()
