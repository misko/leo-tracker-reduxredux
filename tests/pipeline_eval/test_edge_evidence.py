import numpy as np
import pytest

from tools.pipeline_eval.qualification import edge_evidence_trial, screening_figures
from tools.pipeline_eval.scoring import ARMS
from tools.pipeline_eval.variants import edge_evidence


def test_single_face_continuation_shares_tangent_and_symmetric_physical_steps():
    tile = dict(center=[35.0, 110.0], width_km=25.0)
    stock = dict(
        arms={
            "c0": dict(latlon=[35 + 12 / 111, 110.0]),
            "fitted_c": dict(latlon=[35 + 12.5 / 111, 110.0]),
        }
    )
    inward, face, outward = edge_evidence.normal_hypotheses(stock, tile)
    assert np.allclose(face, [0.0, 12.5])
    assert np.allclose(inward, [0.0, 11.0])
    assert np.allclose(outward, [0.0, 14.0])
    stock["arms"]["c0"]["latlon"][0] = 35 - 12.5 / 111
    assert edge_evidence.normal_hypotheses(stock, tile) is None


def test_shared_timestamps_stay_together_in_the_held_orbit_block():
    t = np.r_[np.repeat(np.arange(18), 2), np.arange(5)]
    family = np.r_[np.ones(36), np.full(5, 9)]
    train, held, owners = edge_evidence.split(t, family, np.ones(t.size, bool))
    assert len(owners) == 1
    assert np.array_equal(np.unique(t[held]), np.arange(6, 12))
    assert held.sum() == 12
    assert np.all(train[-5:])
    assert not np.any(train & held)


@pytest.mark.parametrize(
    ("difference", "state"),
    [
        ([1, 1.1, 0.9, 1], "inside"),
        ([-1, -1.1, -0.9, -1], "outside"),
        ([1, -1.1, 0.9, -1], "weak"),
        ([1, 1, 1], "insufficient"),
    ],
)
def test_orbit_contrast_requires_direction_consistency_and_support(difference, state):
    fit = np.column_stack(
        [np.ones(len(difference)) * 2, np.ones(len(difference)) * 2, np.asarray(difference) + 2]
    )
    assert edge_evidence.contrast(fit)["state"] == state


def test_transfer_cards_keep_fresh_sites_and_measured_parity_separate():
    cards = {c.id: c for c in screening_figures.charts(evidence=edge_evidence_trial.REPORT)}
    for scope, count in (("fresh", 8), ("roof", 1)):
        card = cards[f"compact-held-face-{scope}"]
        assert len(card.cases) == count
        for arm in ARMS:
            for key in ("candidate", "stock"):
                assert len([r for r in card.page(arm).rows if r.series == key]) == count
