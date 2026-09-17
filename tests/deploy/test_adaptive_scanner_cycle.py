from __future__ import annotations

import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "deploy/scripts/run-adaptive-scanner-cycle"


def _selection(epoch: int) -> tuple[str, str]:
    result = subprocess.run(
        ("bash", str(SCRIPT)),
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "LEO_SCANNER_CYCLE_DRY_RUN": "1",
            "LEO_SCANNER_CYCLE_NOW_EPOCH": str(epoch),
        },
    )
    fields = dict(item.split("=", 1) for item in result.stdout.strip().split() if "=" in item)
    return fields["profile"], fields["rates"]


def test_cycle_selects_ten_then_two_wide_slots() -> None:
    # These values place the next slot at ordinals 3, 4 and 5.
    assert _selection(1_201) == ("adaptive-single-rx0-10m-300s-v1", "10000000")
    assert _selection(1_801) == (
        "adaptive-single-rx0-random-15m-20m-300s-v1",
        "15000000,20000000",
    )
    assert _selection(2_401) == (
        "adaptive-single-rx0-random-15m-20m-300s-v1",
        "15000000,20000000",
    )


def test_cycle_uses_upcoming_boundary_before_the_slot_starts() -> None:
    assert _selection(1_799) == ("adaptive-single-rx0-10m-300s-v1", "10000000")
    assert _selection(1_800) == ("adaptive-single-rx0-10m-300s-v1", "10000000")
