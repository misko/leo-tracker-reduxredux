import pytest

from reports.ALGO08.v3.history_risk_figure import load_rows


def test_plot_displays_charged_time_and_keeps_the_sign_of_position_error():
    rows = {case: (original, charged, errors) for case, original, charged, errors in load_rows()}
    assert rows["DS30-0160"][1] == pytest.approx(10.886, abs=0.001)
    assert rows["DS30-0160"][2] == {"c0": 0, "fitted_c": 0}
    assert rows["DS30-0374"][2] == pytest.approx({"c0": 4.178, "fitted_c": -6.664}, abs=0.001)
