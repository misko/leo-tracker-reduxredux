#!/usr/bin/env python3
"""Wave 9 group8-10 preparation controller; dispatch only through LAUNCH.md."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller_common import main  # noqa: E402

SESSIONS = [
    "scan-fw-28e2dd779ecf4874",
    "scan-fw-e55291a0c748eccd",
    "scan-fw-9e2df39a87ca02d5",
    "scan-fw-cefd970b797cdcee",
    "scan-fw-e559e007fe5a9dcd",
    "scan-fw-90329b2d033fac49",
    "scan-fw-2eec81109f3b02cd",
    "scan-fw-ac5bf361fa79f8d5",
]

if __name__ == "__main__":
    main(SESSIONS, "group10")
