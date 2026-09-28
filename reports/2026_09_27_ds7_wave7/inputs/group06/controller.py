#!/usr/bin/env python3
"""Wave 7 group8-06 preparation controller; dispatch only through LAUNCH.md."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller_common import main  # noqa: E402

SESSIONS = [
    "scan-fw-eed84e063170a6dd",
    "scan-fw-02511088637aaaea",
    "scan-fw-5b05d8a7826a6255",
    "scan-fw-4b7be407428889a5",
    "scan-fw-46e1a8825e3451ac",
    "scan-fw-642071d813c16e17",
    "scan-fw-2905ecb9b5c0e2e3",
    "scan-fw-49205c424bbbefdc",
]

if __name__ == "__main__":
    main(SESSIONS, "group06")
