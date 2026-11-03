import numpy as np
import pytest
from association_timing_compatibility import timing_summary


def test_shared_shift_not_counted_as_individual_error():
    result=timing_summary([1,2,3],[8,8,8],[1,1,2,3])
    assert result['common_timing_s']==8
    assert result['relative_timing_rms_s']==0
    assert result['relative_over3s_windows']==0


def test_counts_and_zero_sum_center_are_per_satellite():
    result=timing_summary([1,2],[4,-4],[1,1,1,2])
    assert result['common_timing_s']==0
    assert result['relative_over3s_windows']==4
    assert result['relative_over3s_satellites']==2
    assert result['nominal_relative_prior_nll']==16
    with pytest.raises(ValueError):timing_summary([1,2],[4,-4],[3])
