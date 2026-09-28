#!/usr/bin/env python3
"""Wave 8 group8-09 preparation controller; dispatch only through LAUNCH.md."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller_common import main  # noqa: E402

SESSIONS = [
    "scan-fw-4aa194987d208183",
    "scan-fw-35b0a85ef3a724a8",
    "scan-fw-fc8ddf94792f5fb1",
    "scan-fw-b8ce372354655c6f",
    "scan-fw-0da0bd80eeec99cf",
    "scan-fw-b54fb2b735148a71",
    "scan-fw-49c4b2440c4da135",
    "scan-fw-62858ecc5303eb78",
]

if __name__ == "__main__":
    main(SESSIONS, "group09")
