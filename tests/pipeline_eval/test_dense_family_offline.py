from importlib import import_module
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.research.retained_track_likelihood import PERIOD


@pytest.fixture
def study(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("dense_family_offline")


@pytest.mark.parametrize("presence", [0., .7])
def test_positive_density_and_empty_mass_are_jointly_normalized(study, presence):
    length = 8192
    rf = np.linspace(-PERIOD / 2, PERIOD / 2, length, endpoint=False)
    mean, sigma, clutter, signal = (np.full(length, value) for value in (20., 580., .33, presence))
    density = study.log_likelihood(np.ones(length, bool), rf, mean, sigma, clutter, signal)
    empty = study.log_likelihood(np.array([False]), rf[:1], mean[:1], sigma[:1], clutter[:1], signal[:1])
    assert np.exp(density).sum() * PERIOD / length + np.exp(empty[0]) == pytest.approx(1.)
    wrapped = study.log_likelihood(np.ones(length, bool), rf + PERIOD, mean, sigma, clutter, signal)
    assert np.allclose(density, wrapped)


def test_transfer_uses_training_pair_and_excludes_target_ambiguous_background(study):
    def row(track, *nominees):
        return dict(track=track, shortlist=[dict(norad=j, log_odds=s) for j, s in nominees])

    rows = [row("matched", (1, 20), (2, 10)), row("unsafe", (3, 25), (2, 5)),
            row("background", (5, 30)), row("tied", (4, 8), (6, 7))]
    pair, anchors, background = study.pair_for("DS30-0057", rows)
    assert pair == (1, 2)
    assert anchors == {"matched"}
    assert background == {"background": 5}
