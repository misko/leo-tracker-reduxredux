from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

HERE = (
    Path(__file__).resolve().parents[2]
    / "reports"
    / "2026_09_26_scan_fw_32a202b6e55630ec_phase_replay"
    / "sync-spectral"
)
SPEC = importlib.util.spec_from_file_location("scan_sss_template", HERE / "sss_template.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_sss_published_encoding_and_edges() -> None:
    assert len(MODULE.SSS_HEX) == 510
    assert MODULE.sss_phase_states().shape == (1020,)
    assert MODULE.sss_edge_symbols("lower").shape == (8,)
    assert MODULE.sss_edge_symbols("upper").shape == (8,)
    np.testing.assert_array_equal(MODULE.sss_phase_states((2, 3, 1021)), [3, 0, 2])
    # Frozen parity values from leo-tracker's decode.sss_phase_states oracle.
    np.testing.assert_array_equal(
        MODULE.sss_phase_states(tuple(range(488, 496))), [3, 1, 0, 1, 3, 0, 3, 2]
    )
    np.testing.assert_array_equal(
        MODULE.sss_phase_states(tuple(range(528, 536))), [0, 0, 0, 2, 1, 1, 2, 0]
    )


def test_sss_rejects_invalid_index_and_edge() -> None:
    with pytest.raises(ValueError):
        MODULE.sss_phase_states((1,))
    with pytest.raises(ValueError):
        MODULE.sss_edge_symbols("middle")
