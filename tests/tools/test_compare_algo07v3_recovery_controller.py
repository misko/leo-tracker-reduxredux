from copy import deepcopy

import pytest
from compare_algo07v3_recovery_controller import compare

from leo.contracts.fast_graph_position_v2 import RF_CHECKS


def fixture():
    target = dict(track_id="t0", observation_ids=["n0"])
    selected = dict(kind="new_family", arms={"c0": dict(added_points=1)})
    vote = dict(status="conditionally_supported_identity")
    reference = dict(
        predictive_annotation=dict(result=dict(track_id="t0")),
        predictive_inclusion=dict(
            annotation=vote, shared_family=False, retry=None, selected=selected
        ),
    )
    evidence = dict(
        selected_targets=[target],
        publication_support={},
        eligible_targets=1,
        inventory=dict(summary=[]),
    )
    prefix = dict(recovery_inventory=evidence)
    decision = dict(
        decision="ALGO03_single",
        selected=selected,
        attempts=[
            dict(
                track_id="t0", points=1, annotation=vote, shared_family=False, status="RF_qualified"
            )
        ],
        stages=[
            dict(name="target-0-" + s, status="complete")
            for s in ("annotation", "inclusion", "audit")
        ],
        source_support={},
        inventory_summary=[],
        eligible_tracks=1,
        selected_track_ids=["t0"],
        no_GPS_selection=True,
        causal_only=True,
        matched_c_arms=True,
        rf_checks={k: True for k in RF_CHECKS},
    )
    return dict(prefix, predictive_recovery=decision), prefix, [reference]


def test_controller_comparison_does_not_accept_only_matching_endpoint():
    candidate, prefix, references = fixture()
    assert compare(candidate, prefix, references)["exact"]
    candidate["predictive_recovery"]["attempts"][0]["status"] = "RF_rejected"
    with pytest.raises(ValueError, match="Controller scientific"):
        compare(candidate, prefix, references)


def test_controller_comparison_requires_every_target_and_unchanged_prefix():
    candidate, prefix, references = fixture()
    with pytest.raises(ValueError, match="Every selected target"):
        compare(candidate, prefix, [])
    changed = deepcopy(candidate)
    changed["recovery_inventory"]["eligible_targets"] = 2
    with pytest.raises(ValueError, match="Preceding prefix"):
        compare(changed, prefix, references)
