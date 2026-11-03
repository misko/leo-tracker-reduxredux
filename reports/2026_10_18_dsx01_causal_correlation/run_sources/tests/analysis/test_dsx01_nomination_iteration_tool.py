"""Nomination updates must not smuggle noise gates or linear votes into fitting."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def tool():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        yield importlib.import_module("iterate_dsx01_position_nominations")
    finally:
        sys.path.remove(path)


def test_lowest_cost_nominee_can_fail_structure_gate_without_changing_membership(tool):
    scan = SimpleNamespace(curved=[0], tracks=[dict(key="curve")], norads=np.array([100, 200]))
    row = dict(component="curve", active_curvature=True, candidate_index=0, points=35)
    terms = dict(
        rms=[150, 140],
        bias=[0, 10],
        cost=[30, 25],
        parts=[1, 2],
        split_at=[-1, 17],
        passing=[True, False],
    )
    result = tool.nomination_rows(scan, [row], {0: dict(j=1, terms=terms)})[0]
    assert result["candidate_norad"] == 200
    assert result["split_at"] == 17
    assert not result["compatible"]
    assert result["points"] == 35


def test_linear_rows_cannot_enter_calibration_refresh(tool):
    scan = SimpleNamespace(curved=[], tracks=[], norads=np.array([]))
    with pytest.raises(ValueError, match="linear"):
        tool.nomination_rows(scan, [dict(active_curvature=False)], {})
