"""Confirm that only the ordered Graph node rewards change."""

import importlib
from pathlib import Path
import subprocess

import numpy as np
import pytest


@pytest.fixture
def trial(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "reports/ALGO08/v3"))
    result = importlib.import_module("discovery_margin")
    monkeypatch.setattr(result, "NATIVE_DIR", root / "tools/pipeline_eval/variants/experimental")
    return result


@pytest.mark.parametrize("margin,anchor,expected", [(.025, False, 0.), (.050, False, .5), (.1, False, .75), (.025, True, 1.)])
def test_frozen_normalized_reward(trial, margin, anchor, expected):
    assert trial.weight(margin, anchor) == expected


@pytest.mark.parametrize("margin", [float("nan"), float("inf"), .0249])
def test_only_confirmed_fractional_margin_is_eligible(trial, margin):
    with pytest.raises(ValueError, match="valid selected"):
        trial.weight(margin, False)


def test_native_chain_awards_both_start_nodes_and_one_new_target(trial, tmp_path):
    from leo.analysis import graph_tracklets
    from leo.analysis.polynomial_tracklets import TrackConfig
    from tools.pipeline_eval.variants.experimental.graph_path import pack

    source, library = tmp_path / "path.c", tmp_path / "path.so"
    source.write_text(trial.weighted_source())
    subprocess.run(["cc", "-std=c11", "-O2", "-fPIC", "-shared", "-ffp-contract=off", str(source), "-o", str(library)],
                   check=True, timeout=15)
    config = TrackConfig(min_points=3, min_span_s=2., max_gap_s=1., track_penalty=1.)
    time, values = np.arange(3.), np.zeros(3)
    neighbors = graph_tracklets._graph(time, values, config)
    native = trial.WeightedPath(library)
    paths = pack(time, neighbors)
    available, enabled = np.ones(3, dtype=bool), np.ones(2, dtype=bool)
    order, lift, edges, score = native.solve(paths, values, available, enabled, config, np.array([3., 2., 4.]))
    assert order.tolist() == [0, 1, 2] and lift.tolist() == [0., 0., 0.] and edges.tolist() == [0, 1]
    assert score.hex() == ((((3. + 2. - 1.) - .05) + 4.) - .05).hex()
    enabled[0] = False
    assert native.solve(paths, values, available, enabled, config, np.full(3, 9.))[0].size == 0
