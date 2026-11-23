from importlib import import_module
from pathlib import Path

import pytest


def test_chart_requires_complete_disjoint_stage_clocks(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    stage_times = import_module("bounds_pair_figure").stage_times
    row = dict(detection_file_s=10, detection_to_terminal_s=20, terminal_to_exit_s=5, elapsed_s=35)
    assert stage_times(row) == [10, 20, 5]
    with pytest.raises(ValueError, match="full elapsed"):
        stage_times(row | {"detection_to_terminal_s": 30})
    with pytest.raises(ValueError, match="nonnegative"):
        stage_times(row | {"terminal_to_exit_s": -5})
