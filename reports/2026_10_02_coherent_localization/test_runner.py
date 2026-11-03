import numpy as np
import pytest
from run import converged_best, require_success


def test_failed_lower_objective_cannot_win():
    failed = {"success": False, "objective": 1.0, "message": "budget exhausted"}
    successful = {"success": True, "objective": 2.0, "message": "converged"}
    assert converged_best([failed, successful]) is successful
    with pytest.raises(RuntimeError):
        require_success(failed)


def test_nonfinite_or_all_failed_fits_rejected():
    invalid = {"success": True, "objective": np.nan, "message": "invalid objective"}
    with pytest.raises(RuntimeError):
        converged_best([invalid])
    with pytest.raises(RuntimeError):
        require_success(invalid)
