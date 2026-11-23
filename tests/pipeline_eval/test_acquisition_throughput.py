from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from acquisition_throughput import gates, minimum_rate


def test_unsplit_run_stays_charged_and_two_throughputs_differ():
    cases = [dict(stages=[8, 2, 0], compressed_MB=20)] * 2 + [dict(stages=[0, 0, 6], compressed_MB=200)]
    assert gates(cases, 10., .5) == (.3, 12/26)
    assert abs(minimum_rate(cases, .5, 0) - 5.) < 1e-10
    assert abs(minimum_rate(cases, .5, 1) - 8.) < 1e-10
    assert minimum_rate(cases[-1:], .5, 0) is None
