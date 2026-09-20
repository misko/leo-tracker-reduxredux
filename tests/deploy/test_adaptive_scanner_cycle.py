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


def test_cycle_always_selects_dual_rx_2p5m() -> None:
    expected = ("adaptive-dual-rx-2p5m-300s-360s-v1", "2500000")
    assert _selection(1_201) == expected
    assert _selection(1_801) == expected
    assert _selection(2_401) == expected


def test_cycle_uses_upcoming_boundary_before_the_slot_starts() -> None:
    expected = ("adaptive-dual-rx-2p5m-300s-360s-v1", "2500000")
    assert _selection(1_799) == expected
    assert _selection(1_800) == expected
