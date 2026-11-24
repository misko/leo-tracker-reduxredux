from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
from orbit_rank_gates_figure import panels


def test_chart_keeps_the_two_distinct_through_exit_boundaries_and_controls():
    north, medium = panels()
    assert [north[1], medium[1]] == ["Original samples through exit", "Saved detections through exit"]
    assert [round(value, 3) for _, value in north[2]] == [16.761, 11.224, 11.051, 10.835]
    assert [round(value, 3) for _, value in medium[2]] == [18.140, 11.695, 11.083, 11.209]
