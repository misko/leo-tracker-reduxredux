from copy import deepcopy

import pytest
from compare_algo07v3_residual_screen import compare_screen


def packet():
    winner = dict(norad=123, phase_s=2.0, rms_hz=100.0)
    arms = {
        a: dict(
            qualified=True,
            folds={s: dict(winner=deepcopy(winner), margin=12.0) for s in ("full", "1", "2", "3")},
        )
        for a in ("c0", "fitted_c")
    }
    return dict(
        catalogue_count=10,
        targets=[
            dict(
                source=dict(
                    fragment_id="source", receiver=1, channel=8, points=40, duration_s=30.0
                ),
                finalists=[123, 456],
                summaries=[dict(policy="72h_30s", arms=arms, screen_pass=True)],
            )
        ],
    )


def test_matched_screen_pass_is_not_credited_as_an_association():
    p = packet()
    result = compare_screen(p, deepcopy(p))
    assert result["passed_tracks"] == 1 and result["screen_pass_points"] == 40
    assert result["newly_associated_points"] == 0 and not result["full_pipeline_parity"]


@pytest.mark.parametrize("fault", ["score", "identity", "fold", "catalogue"])
def test_scientific_screen_changes_are_rejected(fault):
    p = packet()
    changed = deepcopy(p)
    fold = changed["targets"][0]["summaries"][0]["arms"]["c0"]["folds"]["1"]
    if fault == "score":
        fold["margin"] += 1e-9
    elif fault == "identity":
        fold["winner"]["norad"] += 1
    elif fault == "fold":
        del changed["targets"][0]["summaries"][0]["arms"]["c0"]["folds"]["1"]
    else:
        changed["catalogue_count"] += 1
    with pytest.raises(ValueError, match="Residual screen changed"):
        compare_screen(p, changed)


def test_same_malformed_pass_does_not_qualify():
    p = packet()
    del p["targets"][0]["summaries"][0]["arms"]["c0"]["folds"]["1"]
    with pytest.raises(ValueError, match="independent identity"):
        compare_screen(p, p)
