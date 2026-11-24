import pytest

from reports.ALGO08.v3.exact_solver_0008 import raw_budget


@pytest.fixture
def original_acquisition():
    return dict(acquire_cpu_s=31.0, acquire_wall_s=60.0, dense_compressed_MB=8100.0)


def test_dense_budget_keeps_original_wait_and_cpu_boundaries_separate(original_acquisition):
    result = raw_budget(dict(cpu_s=25.0, elapsed_s=26.0), original_acquisition)
    assert result["optimistic_no_overlap_cpu_s"] == 56.0
    assert result["historical_input_wait_sum_elapsed_s"] == 86.0
    assert result["original_exposed_wait_s"] == 29.0
    assert result["minimum_verified_acquisition_MBps"] == pytest.approx(8100/(113.021/2-26))


def test_dense_budget_reports_no_throughput_target_when_publication_uses_the_whole_budget(original_acquisition):
    result = raw_budget(dict(cpu_s=59.0, elapsed_s=60.0), original_acquisition)
    assert result["remaining_acquire_elapsed_s"] < 0
    assert result["minimum_verified_acquisition_MBps"] is None
