from importlib import import_module
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def study(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("moment_preserving_cfo")


def test_removed_component_includes_the_actual_quadratic_track_moment(study):
    t = np.array([-2., -1., 0., 1., 2.])
    design = study.basis([(dict(degree=2, reference_time_s=0., time_scale_s=2.), t)])
    original = np.array([28_001., 27_600., 27_200., 26_810., 26_440.])
    previous = original + [18., 32., -40., 70., 95.]
    updated, proof = study.project(design, original, previous, 200.)
    delta = updated - original
    assert np.linalg.norm(delta) > 10.
    assert np.max(np.abs(np.array([t**p @ delta for p in range(3)]))) < 5e-11
    assert proof["after"] <= proof["tolerance"]


def test_released_join_enforces_value_and_slope_continuity(study):
    left = dict(degree=1, reference_time_s=-1., time_scale_s=1., join_time_s=0.)
    right = dict(degree=1, reference_time_s=2., time_scale_s=2., join_time_s=0.)
    t = np.array([-3., -2., -1., 1., 3., 5.])
    design = study.basis([(left, t[:3]), (right, t[3:])])
    assert design.shape == (6, 2)
    coefficients = np.linalg.lstsq(design, 12 + 17*t, rcond=None)[0]
    assert np.allclose(design @ coefficients, 12 + 17*t)
    with pytest.raises(ValueError, match="one authenticated C1 join"):
        study.basis([(left, t[:3]), (dict(right, join_time_s=1.), t[3:])])


def test_track_cap_is_one_common_scale_and_deficient_support_keeps_original(study):
    original = np.array([10_001., 10_002., 10_003.])
    previous = original + [100., -100., -100.]
    new, proof = study.project(np.ones((3, 1)), original, previous, 100.)
    assert proof["scale"] == pytest.approx(.75)
    assert new - original == pytest.approx([100., -50., -50.])
    assert np.max(np.abs(new - original)) <= 100.
    duplicate = np.ones((3, 2))
    saturated = np.eye(3)
    for design, status in [(duplicate, "insufficient_rank"), (saturated, "fully_in_span")]:
        new, proof = study.project(design, original, previous, 100.)
        assert new.tolist() == original.tolist()
        assert proof["status"] == status


def test_unassigned_proposal_stays_in_mask_and_anchor_stays_outside(study):
    slots = ["first", "anchor", "last", "unassigned"]
    data = dict(observations=[dict(observation_id=oid, time_s=i, measured_cfo_hz=1000.)
                              for i, oid in enumerate(slots)], graph_points=3,
                tracks=[dict(indices=[0, 1, 2], observation_ids=slots[:3], key="track",
                             pieces=[dict(indices=[0, 1, 2], degree=0, reference_time_s=1.,
                                          time_scale_s=1.)])])
    edits = {oid: dict(original_hz=1000., updated_hz=updated)
             for oid, updated in [("first", 1030.), ("last", 990.), ("unassigned", 1010.)]}
    values, proof = study.project_tracks(data, edits)
    assert values == {"first": 1020., "last": 980., "unassigned": 1000.}
    assert proof["original_edits"] == 3 and proof["surviving_edits"] == 2 and proof["unassigned_edits"] == 1
