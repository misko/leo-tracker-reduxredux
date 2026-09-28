#!/usr/bin/env python3
"""Wave 7 group8-07 preparation controller; dispatch only through LAUNCH.md."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller_common import main  # noqa: E402

SESSIONS = [
    "scan-fw-d3738157be6646a0",
    "scan-fw-a3dd7fad107c19e9",
    "scan-fw-a267faf8e5ca613c",
    "scan-fw-53b81eb605a1bb4f",
    "scan-fw-7bfaf984bc20419f",
    "scan-fw-a177aad6836951de",
    "scan-fw-f930a8e995aa139c",
    "scan-fw-5556fac26647c0e0",
]

if __name__ == "__main__":
    main(SESSIONS, "group07")
