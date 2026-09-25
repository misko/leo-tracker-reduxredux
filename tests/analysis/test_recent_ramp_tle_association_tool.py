from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np

from leo.operations.tle_archive import TleSnapshotRef


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "associate_recent_raw_doppler_starlink.py"
    spec = importlib.util.spec_from_file_location("recent_ramp_tle_association_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _snapshot(time_ns: int, suffix: str) -> TleSnapshotRef:
    return TleSnapshotRef(
        collected_utc_ns=time_ns,
        provider="space-track",
        sha256=suffix * 64,
        byte_size=100,
        path=Path(f"/{time_ns}-{suffix * 64}.tle"),
    )


def test_causal_snapshot_triplet_never_uses_future_snapshot_as_primary() -> None:
    tool = _tool()
    snapshots = (_snapshot(100, "a"), _snapshot(200, "b"), _snapshot(300, "c"))

    previous, primary, following = tool.causal_snapshot_triplet(snapshots, 250)

    assert previous == snapshots[0]
    assert primary == snapshots[1]
    assert following == snapshots[2]


def test_doppler_rate_bank_recovers_linear_frequency_change() -> None:
    tool = _tool()
    time_s = np.arange(0.0, 2.0, 0.125)
    expected_rate_hz_s = -3_250.0
    # Invert the first-order Doppler formula to create the requested shift.
    shift_hz = 100_000.0 + expected_rate_hz_s * time_s
    range_rate = -shift_hz * tool.doppler_shift_hz.__globals__["SPEED_OF_LIGHT_KM_S"] / 10e9
    observed = type("Observed", (), {"range_rate_km_s": range_rate[None, :]})()

    recovered = tool._doppler_rate_bank(observed, time_s, 10e9)

    assert np.allclose(recovered, expected_rate_hz_s, atol=1e-8)
