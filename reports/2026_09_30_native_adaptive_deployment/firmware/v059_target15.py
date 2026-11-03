#!/usr/bin/env python3
"""Bind the reviewed v0.59 PPU deployment adapter to radio 192.168.1.15."""

from __future__ import annotations

import sys
from pathlib import Path


RETAINED_TOOLS = Path(
    "/home/mouse9911/release-evidence/dual-rx-counter-fix-v059/tools"
)
sys.path.insert(0, str(RETAINED_TOOLS))

import v059_deploy as deploy  # noqa: E402


deploy.LAN_SERIAL = "104000b29905000e17000800065934759d"
deploy.LAN_HOST = "192.168.1.15"
deploy.LAN_BASELINE = "v0.54-plutoplus-spf-counter-utc-v1-rc1"


if __name__ == "__main__":
    raise SystemExit(deploy.main())
