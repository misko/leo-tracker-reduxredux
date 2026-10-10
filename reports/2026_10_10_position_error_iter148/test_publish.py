import pytest
from publish import publish


def test_unsealed_report_creates_nothing(tmp_path):
    with pytest.raises(ValueError, match="terminal"):
        publish(dict(both_terminal=False), tmp_path)
    assert not list(tmp_path.iterdir())


def test_all_failure_regions_and_missing_endpoints_retained(tmp_path):
    branch = dict(
        regions=[
            dict(
                name="retained-" + str(i),
                calibration_status="unavailable",
                calibration_available=False,
                failure_reason="AssertionError",
                finals={},
            )
            for i in range(3)
        ],
        arms={arm: dict(status="no-selected-endpoint") for arm in ("fitted-c", "zero-c")},
    )
    result = dict(
        both_terminal=True,
        branches={b: branch for b in ("native", "zero")},
        slices={
            b: dict(completed=1, claimed=1, known_elapsed_s=1.0, unfinished_claims=0)
            for b in ("native", "zero")
        },
    )
    publish(result, tmp_path)
    text = (tmp_path / "RESULTS.md").read_text()
    for i in range(3):
        assert text.count("retained-" + str(i)) == 2
    assert text.count("no-selected-endpoint | unavailable | unavailable | not reached") == 4
    assert (tmp_path / "comparison.png").is_file()
