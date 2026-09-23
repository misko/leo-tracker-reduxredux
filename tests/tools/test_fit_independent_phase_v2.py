import copy

import pytest

from tools.research.fit_independent_phase_v2 import acquisition_only_rows


def test_acquisition_only_branch_is_forced_without_consulting_scores():
    row = {
        "observation": {"acquired_cfo_hz": 10.0},
        "selected_seed_index": 2,
        "branches": [
            {"seed_cfo_hz": 10.0, "calibration_even_margin": -1.0},
            {"seed_cfo_hz": 20.0, "calibration_even_margin": 999.0},
        ],
    }
    result = acquisition_only_rows([copy.deepcopy(row)])
    assert result[0]["selected_seed_index"] == 0


def test_acquisition_only_branch_fails_closed_on_seed_mismatch():
    row = {
        "observation": {"acquired_cfo_hz": 10.0},
        "selected_seed_index": 0,
        "branches": [{"seed_cfo_hz": 11.0}],
    }
    with pytest.raises(ValueError, match="branch zero"):
        acquisition_only_rows([row])
