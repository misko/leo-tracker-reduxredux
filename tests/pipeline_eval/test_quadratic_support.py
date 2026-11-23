from importlib import import_module
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def support(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("quadratic_support")


def test_separates_waveform_loss_and_effective_alias_change(support):
    a = dict(norad=1, role="conditional", effective_alias=2)
    b = dict(norad=1, role="predictive", effective_alias=1)
    full = dict(A=a, B=a, C=a, D=a)
    sparse = dict(A=b, C=b)
    original = {key: dict(visit=i, signal=(1, 0, -400)) for i, key in enumerate(full)}
    sparse_rows = {key: dict(value) for key, value in original.items()}
    sparse_rows["C"]["signal"] = (1, 0, 800)
    sparse_rows["D"]["signal"] = None
    exact, common, audit = support.incidence(full, sparse, original, sparse_rows, {0, 2, 3})
    assert exact == common == {"A"}
    assert audit["unpaid"] == audit["paid_no_signal"] == audit["paid_changed_peak"] == 1
    assert audit["changed_norad"] == 0
    assert audit["changed_role"] == audit["changed_effective_alias"] == 1


def test_projected_information_declines_when_timing_is_free(support):
    clock = np.array([0., 1., 2., 1.])
    other = np.array([1., 0., 0., 1.])
    design = np.c_[clock, other, clock]
    fixed = support.projected(design, excluded=(2,))
    free = support.projected(design, free=(2,))
    assert np.linalg.eigvalsh(fixed)[0] > 0.
    assert np.linalg.eigvalsh(free)[0] == pytest.approx(0.)
    assert support.validation_fold(9)[0].sum() == 6
    keep, held = support.validation_fold(9)
    assert not np.any(keep & held) and np.all(keep | held)
    assert keep[0] and keep[-1] and held.sum() == 3


def test_nominations_use_two_strictly_previous_anchors_on_the_same_lane(support):
    timeline = {}
    for oid, slot, receiver in (("A", 0, 1), ("B", 3, 1), ("F", 4, 0), ("C", 5, 1), ("D", 9, 1)):
        timeline[oid] = dict(visit=slot, time_s=slot, receiver=receiver, channel=6, rf_hz=12e9)
    sparse = {"A": {"norad": 7}, "B": {"norad": 7}}
    truth = {"C": {"norad": 7}, "F": {"norad": 7}}
    queries = support.proposals(sparse, timeline, {0, 3})
    assert queries == {"C": {7: ["A", "B"]}}
    assert sum(row["past_anchor_supported"] for row in
               support.acquisition_ceiling(truth, sparse, timeline, {0, 3})) == 1
