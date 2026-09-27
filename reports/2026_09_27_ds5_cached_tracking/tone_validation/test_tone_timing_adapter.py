from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_timing_adapter as adapter


def test_actual_timing_helper_measures_call_and_returns_result():
    result, times = adapter.original.evaluation.raw_runner.timed(lambda: 17)
    assert result == 17
    assert set(times) == {'process_cpu_ms','wall_ms'}
    assert all(value >= 0 for value in times.values())
