"""Protect the distinction between held rows and target-excluded training."""

import pytest

from opposite_radio_profile_preflight import DEPENDENCIES, excluded_dependencies, inspect_case


def test_held_linear_exclusion_does_not_clear_target_overlap():
    memberships = {stage: ["unrelated"] for stage in DEPENDENCIES}
    memberships["position_geometry"].append("target")
    leakage = excluded_dependencies(memberships, ["target"], ["linear"])
    assert leakage["position_geometry"] == {"target_curved": 1, "held_linear": 0}
    assert all(row["held_linear"] == 0 for row in leakage.values())


def test_both_exclusions_apply_to_every_stage():
    memberships = {stage: ["unrelated"] for stage in DEPENDENCIES}
    assert all(row == {"target_curved": 0, "held_linear": 0}
               for row in excluded_dependencies(memberships, ["target"], ["linear"]).values())
    memberships.pop("noise_calibration")
    with pytest.raises(ValueError, match="Missing"):
        excluded_dependencies(memberships, ["target"], ["linear"])
    memberships["noise_calibration"] = ["unrelated"]
    with pytest.raises(ValueError, match="distinct"):
        excluded_dependencies(memberships, ["same"], ["same"])


def test_later_predictive_checkpoint_cannot_supply_excluded_state():
    pins = {"native": "native", "charted": "witness"}
    target = dict(curved_points=8, seed_span=[5, 15], seed_radio=2, components=["target"])
    opportunities = {oid: dict(rf=1, start=start, lane=[radio, 5]) for oid, radio, start in
                     (("target", 2, 5), ("rival", 1, 10), ("rx1", 1, 20), ("rx2", 2, 20))}
    plan = dict(candidate_tape_sha256="tape", families={"1": target}, graph=None, opportunities=opportunities)
    tape = [{"norad": 1, "component": "target", "observation_ids": ["target"]},
            {"norad": 2, "component": "rival", "observation_ids": ["rival"]}]
    trace = dict(stage=dict(native_sha256="sha256:native", masks={"after_salvage": "tape"}, finishing_fits=0),
                 ready=dict(archive_sha256="archive", offer_sha256="offer", compatible_solver_sources={},
                            resident_archive={}), clock=dict(exit=0, wall_s=9, cpu_s=8),
                 masks={"after_salvage": {"tracks": tape}})
    fit = {"arms": {"c0": {"predictive": {"track": {"ids": ["held"]}}}}}
    witness = dict(evidence={"detail": {"input_sha256": "sha256:native"}}, solver_recipe={"archive_sha256": "archive"},
                   source_sha256={}, ports={"history_risk": {"lean_final_fit": fit}})

    result = inspect_case(plan, trace, witness, pins)
    assert result["curved_target_points"] == 8
    assert result["archived_later_pair_operands"]["c0"]["predictive_points"] == 1
    assert not result["target_excluded_geometry_bound"]
    assert result["direct_linear_terms_in_second_curved_posterior"] == 0
    assert result["measured_independent_profile_bound_s"] is None
    assert result["same_rf_candidate_only_support"][1] == dict(
        stereo_positive_counter_pairs_outside_span=1, opposite_curved_comparison_overlap={"rival": 1})

    witness["solver_recipe"]["archive_sha256"] = "different archive"
    with pytest.raises(ValueError, match="Unqualified"):
        inspect_case(plan, trace, witness, pins)
