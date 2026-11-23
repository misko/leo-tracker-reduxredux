"""Graph reduction keeps interaction and discovery evidence distinct."""

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return importlib.import_module("eight_ms_graph_subset")


def test_reduction_can_keep_an_interacting_pair_without_claiming_global_minimum(trial):
    def matches(ids):
        return {1, 4} <= set(ids) or 7 in ids

    selected = trial.minimize(tuple(range(8)), matches)
    assert matches(selected)
    assert all(not matches(tuple(item for item in selected if item != dropped)) for dropped in selected)
    assert trial.minimize([0, 1, 2, 3, 4], matches) == (1, 4)


def test_original_lane_signature_distinguishes_membership_and_curvature(trial):
    old = {"a", "b", "c"}
    base = [(True, ["a", "b"]), (False, ["c"])]
    extra = [(False, ["c", "x"]), (True, ["b", "a"])]
    assert trial.signature(base, old) == trial.signature(extra, old)
    extra[0] = (True, ["c", "x"])
    assert trial.signature(base, old) != trial.signature(extra, old)


def test_path_discovery_can_change_via_unassigned_addition(trial):
    base = [dict(path=["a", "b"], proposals=[["a", "b"]])]
    modified = [dict(path=["a", "extra", "b"], proposals=[["a", "b"]])]
    found = trial.first_divergence(base, modified, {"extra"})
    assert found["path_index"] == 1
    assert found["added_in_path"] == ["extra"]
    assert found["added_in_polynomial"] == []


def test_current_predecessor_feature_handles_aliases_and_ignores_future(trial):
    def row(time, cfo):
        return dict(time_s=time, measured_cfo_hz=cfo)

    cfg = SimpleNamespace(max_gap_s=10., alias_spacing_hz=1000., max_slope_hz_s=20.)
    past = [row(1., -490), row(1., 0), row(-50., 499), row(3., 495)]
    assert trial.feature(row(2., 499), past, cfg) == dict(prior_rows=2, legal_predecessors=1, in_density_cap=False)
