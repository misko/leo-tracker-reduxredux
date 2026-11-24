from copy import deepcopy

import pytest

from leo.analysis.position_grid import sample_position_grid
from reports.ALGO08.v3.three_quarter_challenge_score import complete_grid, gate


def test_grid_uses_configured_clipping_and_deduplication():
    endpoints = {"c0": (12.0, 12.0), "fitted_c": (12.0, 12.0)}
    valid = sample_position_grid(lambda *_: 1., endpoints, clock=lambda: 0.)
    assert complete_grid(valid) == len(valid["points"]) < 179
    broken = deepcopy(valid)
    broken["points"][0] = broken["points"][1]
    with pytest.raises(ValueError, match="configured location"):
        complete_grid(broken)


def test_geographic_change_is_signed_and_both_arms_keep_common_support():
    prior = {arm: [["a", 2, "conditional"], ["b", 3, "conditional"]] for arm in ("c0", "fitted_c")}
    installed = dict(c0=1.0, fitted_c=1.6)
    assert gate(installed, dict(c0=1.25, fitted_c=.3), prior, prior)[0]
    assert not gate(installed, dict(c0=1.251, fitted_c=.3), prior, prior)[0]
    lack = dict(prior, c0=[["a", 2, "conditional"], ["b", 2, "conditional"]])
    assert not gate(installed, dict(c0=1.25, fitted_c=.3), prior, lack)[0]
