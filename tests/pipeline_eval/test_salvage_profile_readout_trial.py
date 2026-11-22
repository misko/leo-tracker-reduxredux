from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.research.retained_track_likelihood import PERIOD, profile
from tools.pipeline_eval.variants.algo08_deferred_salvage_readout import (
    DeferredDiagnostic,
    ProfileRows,
)


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


def test_scalar_readout_reuses_the_winner_and_falls_back_for_a_full_array(trial):
    y = np.arange(13.0)
    f = np.arange(26.0).reshape(2, 13)
    inverse = np.eye(13)
    stock = profile(y, f, inverse)
    readings = []
    counts = dict(winning_rows=0, winning_readout_cpu_s=0.0,
                  full_array_requests=0, full_array_cpu_s=0.0)

    def fallback():
        readings.append("complete")
        return stock

    staged = ProfileRows(trial.score_rows(y, f, inverse), trial.winning_readout, fallback, counts)
    residual = DeferredDiagnostic(staged, "residual")
    rms = DeferredDiagnostic(staged, "rms")
    assert residual[1].tobytes() == stock["residual"][1].tobytes()
    assert rms[1].tobytes() == stock["rms"][1].tobytes()
    assert counts["winning_rows"] == 1
    assert readings == []
    np.testing.assert_array_equal(np.asarray(residual), stock["residual"])
    np.testing.assert_array_equal(rms[:], stock["rms"])
    assert readings == ["complete"]
    assert counts["full_array_requests"] == 1
