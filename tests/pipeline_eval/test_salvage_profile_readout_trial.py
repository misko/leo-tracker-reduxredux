from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.research.retained_track_likelihood import PERIOD


@pytest.fixture(scope="module")
def trial():
    source = (Path(__file__).resolve().parents[2] / "reports/ALGO08/single-core-2x"
              / "salvage_profile_readout_trial.py")
    spec = spec_from_file_location(source.stem, source)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("order", ["C", "F"])
@pytest.mark.parametrize("correlated", [False, True])
def test_score_and_selected_fields_are_bit_exact_across_layouts(trial, order, correlated):
    rng = np.random.default_rng(31)
    y = rng.normal(42000, 100, 131)
    f = np.array(rng.normal(43000, 190, (17, len(y))), order=order)
    inverse = np.diag(rng.uniform(0.0002, 0.001, len(y)))
    if correlated:
        inverse += np.tril(rng.uniform(0.0, 0.00005, inverse.shape), -1)
    visible = np.ones(len(f), dtype=bool)
    visible[2] = False
    trial.compare(y, f, inverse, np.zeros(len(f)), visible)


def test_preserves_aligned_alias_and_phase_ties(trial):
    y = np.linspace(-90.0, 90.0, 29)
    f = y + np.array([-0.5 * PERIOD, -0.5 * PERIOD, 0.5 * PERIOD])[:, None]
    inverse = np.eye(len(y)) / 150.0
    fields = trial.score_rows(y, f, inverse)
    assert fields["cost"][0] == fields["cost"][1]
    visible = np.array([False, True, False])
    assert trial.winner(fields["cost"], np.zeros(3), visible) == 1
    trial.compare(y, f, inverse, np.zeros(3), visible)
