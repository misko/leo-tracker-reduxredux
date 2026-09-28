#!/usr/bin/env python3
"""Wave 8 group8-08 preparation controller; dispatch only through LAUNCH.md."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller_common import main  # noqa: E402

SESSIONS = [
    "scan-fw-a2d5dadd1a63c960",
    "scan-fw-6f18b6eb990a8198",
    "scan-fw-35896b80c5b357ab",
    "scan-fw-be74914cdda63c5b",
    "scan-fw-4df05eefa93a1b1b",
    "scan-fw-dbf7972f30e74755",
    "scan-fw-30cb794dc996d187",
    "scan-fw-7c504d862c2326b4",
]

if __name__ == "__main__":
    main(SESSIONS, "group08")
