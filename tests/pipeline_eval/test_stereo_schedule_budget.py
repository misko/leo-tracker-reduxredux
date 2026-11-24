from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from stereo_schedule_budget import data


def test_conditional_dense_model_charges_all_other_work_and_preserves_exit_status():
    cases, result = data()
    assert set(cases) == {"DS30-0008", "DS30-0016"}
    assert result["saved_process_exit_code"] == 1
    assert result["allowable_extra_s"] == pytest.approx(result["warm_named_half_s"] - result["zero_wait_model_s"])
    assert result["required_compressed_MB_s"] == pytest.approx(262.97, abs=.01)
