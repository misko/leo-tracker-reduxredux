from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_distance_and_reference_guard():
    p = Path(__file__).parent / "evaluate_iteration5_postseal.py"
    s = importlib.util.spec_from_file_location("i5e", p)
    m = importlib.util.module_from_spec(s)
    sys.modules[s.name] = m
    s.loader.exec_module(m)
    assert m.distance(m.REF, m.REF) == 0
    assert m.bad({"reference": 1})
    assert not m.bad({"x": 1})
