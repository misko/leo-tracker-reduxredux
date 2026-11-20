import json

import numpy as np

from tools.pipeline_eval.qualification import bridge_support_eval
from tools.pipeline_eval.variants.bridge_support import pick_candidate, support


def test_owner_change_requires_a_valid_strict_held_win():
    labels = np.array([3, 2, 1])
    costs = np.array([8.0, 3.0, 8.0])
    assert pick_candidate(labels, costs, [True, False, True], 1, True) == 2
    assert pick_candidate(labels, costs, [True, True, True], 1, True) == 1
    assert pick_candidate(labels, costs, [True, True, True], 4, True) is None


def test_whole_track_readmission_uses_passing_candidates_only():
    labels, costs = np.array([3, 1]), np.array([8.0, 3.0])
    assert pick_candidate(labels, costs, [True, False], 1, False) == 0
    assert pick_candidate(labels, costs, [False, False], 1, False) is None


def test_new_holdouts_have_no_prior_bridge_or_development_ids():
    eligible = bridge_support_eval.frozen_inputs()
    chosen = bridge_support_eval.holdouts(reversed(tuple(eligible)))
    assert chosen == bridge_support_eval.COHORTS["confirmation"]
    assert not set(chosen) & bridge_support_eval.EXCLUDE


def test_final_support_serializes_only_retained_curved_rows():
    gates = {
        "tracks": [
            dict(component="keep", norad=np.int64(3), points=np.int64(15), compatible=True),
            dict(component="removed", norad=5, points=10, compatible=False),
        ]
    }
    arms = {arm: dict(gates=gates, predictive_points=np.int64(7)) for arm in ("c0", "fitted_c")}
    rendered = json.loads(json.dumps(support(arms)))
    expected = dict(curved=[dict(component="keep", norad=3, points=15)], predictive_points=7)
    assert rendered == {"c0": expected, "fitted_c": expected}
