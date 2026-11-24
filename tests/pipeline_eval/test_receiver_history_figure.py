from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from receiver_history_figure import results


def test_series_bind_both_calibrations_and_frequency_measurements():
    series = results()
    assert len(series) == 5
    baseline, grouped = series[1][1], series[-1][1]
    for arm in ("c0", "fitted_c"):
        assert grouped[arm]["error_m"] > baseline[arm]["error_m"] + 2500
        assert grouped[arm]["rf_rms_hz"] < baseline[arm]["rf_rms_hz"]
