from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def local(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("quadrature_local_repair")


@pytest.mark.parametrize("predictive", [False, True])
def test_native_profile_checks_original_rf_points_and_visibility(local, predictive):
    from leo.analysis.research.retained_track_likelihood import PERIOD

    times = np.arange(30.)
    raw = np.array([np.full(30, PERIOD + 7.), np.full(30, 7.), times * 100.])
    elevations = np.ones_like(raw)
    elevations[1, 13] = -0.01
    profiles = local.scores(raw, elevations, times, predictive=predictive)
    assert profiles[0]["compatible"] and profiles[0]["alias"] == -1
    assert not profiles[1]["compatible"]  # A single original interior point is below the horizon.
    assert not profiles[2]["compatible"]


def test_alias_and_owner_must_agree_in_both_calibration_arms(local):
    def row(alias, cost, compatible=True):
        return dict(alias=alias, cost=cost, compatible=compatible)

    labels = [11, 27, 40, 44, 52]
    zero = [row(1, 0.), row(0, 2.), row(-1, 4.), row(-1, 3.), row(0, 0., False)]
    fitted = [row(0, 0.), row(0, 8.), row(-1, 3.), row(-1, 4.), row(0, 0.)]
    chosen, available = local.common_nomination(labels, {"c0": zero, "fitted_c": fitted})
    assert chosen == dict(label=40, alias=-1, cost=4.)
    assert [row["label"] for row in available] == [27, 40, 44]


def test_optimistic_cap_charges_predictive_loss_when_curved_family_disappears(local):
    scan = SimpleNamespace(tracks=[dict(receiver=1, channel=1), dict(receiver=2, channel=1),
                                   dict(receiver=1, channel=1), dict(receiver=2, channel=1)])
    base = SimpleNamespace(rows=[dict(component="failed", candidate_index=10), dict(component="healthy", candidate_index=20)],
                           members=[0, 1], slices=[slice(0, 12), slice(12, 27)])
    entries = [dict(track_index=2, component="orphan", candidate_index=10, points=8),
               dict(track_index=3, component="linear", candidate_index=20, points=9)]
    keep = np.ones(27, bool)
    start = local.losses(scan, base, keep, entries, {"failed"}, set(), {})
    assert start == dict(tracks=(4, 2), curved=(27, 12), predictive=(17, 8))
    assert not local.small_rejection(start)
    kept = {"failed": dict(label=20, norad=2020, alias=1), "orphan": dict(label=20, norad=2020, alias=0)}
    assert local.losses(scan, base, keep, entries, {"failed"}, {"orphan"}, kept) == dict(
        tracks=(4, 0), curved=(27, 0), predictive=(17, 0))
