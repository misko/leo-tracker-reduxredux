from importlib import import_module

import pytest

trial = import_module("reports.ALGO08.single-core-2x.screened_graph_transfer")


def test_reference_is_used_separately_for_each_returned_arm():
    arms = {"c0": {"latlon": [0, 0]}, "fitted_c": {"latlon": [0, 1]}}
    errors = trial.score(arms, [0, 0])
    assert errors["c0"] == 0
    assert 111 < errors["fitted_c"] < 112
    assert trial.score({}, [0, 0]) == {}
    with pytest.raises(ValueError):
        trial.score({"c0": arms["c0"]}, [0, 0])


def test_saved_withhold_preserves_reason_and_has_no_scientific_packet():
    result = {"status": "withheld", "reason": "exterior", "arms": {}}
    assert trial.compact(result) == result | {"science": {}}


def test_evidence_digest_ignores_duration_but_changes_with_grid_values():
    def evidence(point, seconds):
        result = {"evidence": {"position_grid": {"points": [point], "elapsed_seconds": seconds}}}
        compact = trial.compact(result)
        assert "evidence" not in compact
        return compact["science"]["position_grid"]

    assert evidence(1, 3) == evidence(1, 4)
    assert evidence(1, 3) != evidence(2, 3)
