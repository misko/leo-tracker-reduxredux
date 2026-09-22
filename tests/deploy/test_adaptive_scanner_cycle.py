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


def test_cycle_selects_only_dual_rx_2p5m_or_10m_and_both_occur() -> None:
    allowed = {
        ("adaptive-dual-rx-2p5m-edge-random-300s-360s-v1", "2500000"),
        ("adaptive-dual-rx-10m-edge-random-300s-360s-v1", "10000000"),
    }
    selected = {_selection(slot * 360) for slot in range(100, 164)}
    assert selected == allowed


def test_cycle_selection_is_stable_within_a_durable_slot() -> None:
    assert _selection(1_441) == _selection(1_799)


def test_cycle_uses_upcoming_boundary_before_the_slot_starts() -> None:
    assert _selection(1_799) == _selection(1_800)
