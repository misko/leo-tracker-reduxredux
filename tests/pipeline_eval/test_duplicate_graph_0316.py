from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from duplicate_graph_0316 import validate_pair


def test_reference_region_and_detector_are_required_for_comparison():
    worker = dict(no_waveform=True, handoffs=1, native_sha256="original")
    trace = dict(receipt=dict(region={"width_km": 25}, tle_records=22))
    clock, counts = dict(exit_code=0), dict(calls=16, skipped=0)
    validate_pair(clock, counts, worker, worker, trace, trace)
    with pytest.raises(ValueError):
        validate_pair(clock, counts, worker, dict(worker, native_sha256="other"), trace, trace)
    with pytest.raises(ValueError):
        validate_pair(clock, counts, worker, worker, trace, {"receipt": dict(trace["receipt"], region={"width_km": 20})})
