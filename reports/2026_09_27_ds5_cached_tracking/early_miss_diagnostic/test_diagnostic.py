from pathlib import Path
from types import SimpleNamespace
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_diagnostic import failures


def test_margin_and_status_failures_are_distinct_and_jointly_reported():
    point = SimpleNamespace(status=2, supported=True, valid_bounds=True,
                            support_frames=15, fractional_complete=True, margin=.024)
    assert failures(point) == ['status', 'margin']
    point.margin = .025
    assert failures(point) == ['status']
    point.status = 0
    assert failures(point) == []
    assert failures(None) == ['no_observation']
