from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np


def module():
    path = Path(__file__).parent / "leave_one_scan_out.py"
    spec = importlib.util.spec_from_file_location("i12lootest", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_slice_removes_one_whole_session_and_its_weight():
    m = module()
    support = SimpleNamespace(
        measured=np.arange(4),
        nominal=np.arange(4),
        sensitivity_hz_s=np.arange(4),
        age_h=np.arange(4),
        source=np.asarray(["1", "1", "2", "2"], dtype=object),
        track=np.asarray(["scan-a:t", "scan-a:t", "scan-b:u", "scan-b:u"], dtype=object),
        weights={"scan-a:t": 2, "scan-b:u": 2},
        associations=[
            {"session_id": "scan-a"},
            {"session_id": "scan-b"},
        ],
    )
    result = m.sliced(support, "scan-a")
    assert result.measured.tolist() == [2, 3]
    assert result.weights == {"scan-b:u": 2}
    assert result.associations == [{"session_id": "scan-b"}]
