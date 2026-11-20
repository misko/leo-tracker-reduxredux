import json

import pytest

from tools.pipeline_eval.qualification.pruned_finish_audit import ARMS, counts


def _encoded(value):
    if isinstance(value, dict):
        return ["map", [[key, _encoded(item)] for key, item in value.items()]]
    if isinstance(value, list):
        return ["list", [_encoded(item) for item in value]]
    if isinstance(value, float):
        return ["float", value.hex()]
    return value


def _checkpoint_rows(norads):
    def family(norad, score, points, tracks, arms=ARMS):
        return dict(
            norad=norad, rank_score=score, points=points, tracks=tracks, arms=dict.fromkeys(arms)
        )

    ranking = [
        family(1, 1.5, 25, 2),
        family(2, 1.4, 60, 1, ("c0",)),
        family(3, 0.8, 30, 2),
        family(4, 0.7, 40, 3, ("fitted_c",)),
        family(5, 0.5, 71, 2),
        family(6, 0.1, 32, 2, ("c0",)),
    ]

    def target(names, screen_pass):
        return dict(
            folds=[dict(name=name) for name in names],
            summaries=[
                dict(
                    policy="72h_30s",
                    arms={arm: dict(folds=dict.fromkeys(names)) for arm in ARMS},
                    screen_pass=screen_pass,
                )
            ],
        )

    return {
        "reassociation_trigger": dict(
            status="reassociation_targets_ranked", ranking=ranking, targets=norads
        ),
        "reassociation_screen": dict(
            status="reassociation_candidates_screened",
            admission=dict(status="screened", targets=norads, admitted=[]),
        ),
        "additional_recovery": dict(
            status="additional_recovery_prepared",
            families=[{}, {}],
            inventory=dict(eligible_targets=2),
        ),
        "residual_screen": dict(
            status="additional_candidates_screened",
            screen=dict(
                targets=[
                    target(["full", "20261031", "94721", "4081"], True),
                    target(["full"], False),
                ]
            ),
        ),
        "replay": dict(
            pre_recovery={},
            recovery=dict(
                status="no_qualified_new_family",
                eligible_proposals=0,
                excluded=[dict(reason="exact joint-family compute cap")],
            ),
        ),
    }


def test_counts_distinguish_family_arms_rank_cap_and_residual_fold_support():
    raw = json.dumps(_encoded(_checkpoint_rows([3, 4])), separators=(",", ":")).encode()
    result = counts(raw)
    assert result["observed_families"] == 6
    assert result["support_eligible_families"] == 4
    assert result["original_arm_omissions"] == 9
    assert result["support_eligible_arm_omissions"] == 6
    assert result["rank_eligible_before_cap"] == 3
    assert result["rank_eligible_after_cap"] == 2
    assert result["residual_held_fold_counts"] == {0: 1, 3: 1}
    assert result["residual_scored_all_folds"] == dict.fromkeys(ARMS, 1)
    assert result["residual_screen_pass"] == result["residual_fold_eligible_targets"] == 1
    assert result["residual_pruned_fit_eligible_targets"] == 0
    assert result["residual_proposal_exclusions"] == {"exact joint-family compute cap": 1}


def test_counts_reject_an_archive_with_inconsistent_rank_cap():
    raw = json.dumps(_encoded(_checkpoint_rows([3, 4, 5])), separators=(",", ":")).encode()
    with pytest.raises(ValueError, match="top-two gate"):
        counts(raw)
