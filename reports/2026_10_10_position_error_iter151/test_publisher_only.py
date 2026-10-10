"""Publisher-only fixtures outside the frozen scientific closure."""

import copy

import pytest

from publish import publish


def fixture():
    endpoint = dict(status="selected", qualified=True, frequency=dict(posterior_rms_hz=10.0))
    rows = []
    for index in range(12):
        rows.append(dict(
            label=f"member-{index}", statuses=dict(search="complete", native="complete", zero="complete"),
            arms={arm: dict(native=copy.deepcopy(endpoint), zero=copy.deepcopy(endpoint), delta_km=-.1)
                  for arm in ("fitted-c", "zero-c")},
            phase_elapsed_s=dict(search=1.0, native=2.0, zero=3.0),
            regions={branch: [dict(name=f"retained-{j}", calibration_status="qualified",
                                  finals={arm: dict(qualified=1, attempts=2) for arm in ("fitted-c", "zero-c")})
                              for j in range(3)] for branch in ("native", "zero")},
            joint_stages={branch: {"B7": {"fitted-c": True, "zero-c": True}} for branch in ("native", "zero")},
            failure_reasons={},
        ))
    return dict(all_terminal=True, full_comparison_complete=True, rows=rows, aggregates={},
                progression=dict(passed=True, paired_fitted=12, mean_fitted_delta_km=-.1,
                                 worst_fitted_regression_km=-.1))


def test_pass_costs_and_qualification_visible_without_new_evaluation(tmp_path):
    summary = fixture()
    before = copy.deepcopy(summary)
    publish(summary, tmp_path, lambda *args: None)
    text = (tmp_path / "RESULTS.md").read_text()
    assert "screen: PASS" in text and "strictly improves" in text
    assert "1.000 | 2.000 | 3.000 | 6.000 | 0" in text
    assert "| member-0 | native | 2/2 | 0 | 3/3 | 0 | 6/12 | 2/2 |" in text
    assert summary == before


def test_missing_failure_and_unknown_cost_never_become_zero_attempts(tmp_path):
    summary = fixture()
    summary["full_comparison_complete"] = False
    summary["progression"].update(passed=False, paired_fitted=11)
    row = summary["rows"][0]
    row["statuses"]["zero"] = "budget-exhausted"
    row["failure_reasons"]["zero"] = "time | limit\nreached"
    row["phase_elapsed_s"]["zero"] = None
    row["regions"]["zero"] = [dict(name=f"retained-{j}", status="unavailable-in-terminal", finals=None) for j in range(3)]
    row["joint_stages"]["zero"] = {}
    for arm in row["arms"].values():
        arm["zero"] = dict(status="no-selected-endpoint")
        arm.pop("delta_km")
    publish(summary, tmp_path, lambda *args: None)
    text = (tmp_path / "RESULTS.md").read_text()
    assert "screen: FAIL" in text and "available pairs" in text
    assert "1.000 | 2.000 | unavailable | 3.000 | 1" in text
    assert "| member-0 | zero | 0/2 | 2 | unavailable | 3 | unavailable | unavailable |" in text
    assert "time &#124; limit<br>reached" in text


def test_unsealed_and_missing_progression_block_publication(tmp_path):
    summary = fixture()
    summary["all_terminal"] = False
    with pytest.raises(ValueError):
        publish(summary, tmp_path, lambda *args: None)
    summary["all_terminal"] = True
    summary.pop("progression")
    with pytest.raises(ValueError):
        publish(summary, tmp_path, lambda *args: None)
