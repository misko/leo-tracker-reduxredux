"""Inspect whether the saved opposite-radio study can run without a new fit."""

from pathlib import Path
import argparse
import json

from mixed_owner_support_0220 import GATE_PIN
from pre_screen_owner_readout import CASES, HERE, RELEASE, checked, document


PLAN_PIN = "9d5b51d818e716ff0a42b31021bd5642e2a837f160f0d19f503cc288dd6393b8"
HISTORICAL_CHILD_CAP_S = 18
DEPENDENCIES = {
    "catalogue_and_curve_nomination", "noise_calibration", "phase_and_radio_nuisance", "position_geometry"
}
SOURCE_PINS = {
    "src/leo/application/localization_v3.py": "0642e5de4e765e89791f9ea827950a0e29fdad01f16d9f91e8f2e19b11e51cf6",
    "src/leo/analysis/localization_v3/noise.py": "9e5256d3814031936561b233e2913713c447b18be73d6ab4939813cb34e88d1b",
    "src/leo/analysis/localization_v3/acceptance.py": "d4a3c3d8331c9e24d678d3c271139fbb8da62356b66274f93042774c89196353",
    "src/leo/analysis/research/retained_track_likelihood.py": "73c24d054d5676c7d7051779a6960f8f692ce0d97bc23d292470aa01f6110bcf",
    "src/leo/analysis/research/polynomial_satellite_diagnostics.py": "8bf7d7935b74bba728d437d2652af636e5532be74d798ed4f56c6641be7352c5",
}
FINISH_PIN = "7d8d5a65ceb0e11150e28d0dbbddeabb7741ef1408ded6272500e4f0e012c708"


def excluded_dependencies(observation_ids_by_stage, target_curved, held_linear):
    """Require source-attested membership for both distinct exclusions."""
    if not DEPENDENCIES <= observation_ids_by_stage.keys():
        raise ValueError("Missing a source-attested training cohort")
    target, held = set(target_curved), set(held_linear)
    if not target or not held or target & held:
        raise ValueError("Target curves and held linear observations must be distinct nonempty sets")
    result = {}
    for stage in sorted(DEPENDENCIES):
        ids = set(observation_ids_by_stage[stage])
        result[stage] = dict(target_curved=len(target & ids), held_linear=len(held & ids))
    return result


def same_rf_support(opportunities, base, targets):
    """Count candidate-only comparison material without comparing any CFO."""
    tracks = {row["component"]: row["observation_ids"] for row in base}
    result = {}
    for norad, target in targets.items():
        lo, hi = target["seed_span"]
        radio = target["seed_radio"]
        frequencies = {opportunities[oid]["rf"] for name in target["components"] for oid in tracks[name]}
        by_radio = {1: set(), 2: set()}
        opposite_in_span = set()
        for oid, row in opportunities.items():
            rf, start, rx = row["rf"], row["start"], row["lane"][0]
            if rf not in frequencies:
                continue
            if lo <= start <= hi:
                if rx != radio:
                    opposite_in_span.add(oid)
            else:
                by_radio[rx].add((rf, start))
        other_curves = {name: len(opposite_in_span.intersection(ids)) for name, ids in tracks.items()}
        result[norad] = dict(stereo_positive_counter_pairs_outside_span=len(by_radio[1] & by_radio[2]),
                             opposite_curved_comparison_overlap={name: count for name, count in other_curves.items() if count})
    return result


def inspect_case(plan, trace, witness, pins):
    detail, risk = witness["evidence"]["detail"], witness["ports"]["history_risk"]
    if (trace["stage"]["native_sha256"] != detail["input_sha256"]
            or detail["input_sha256"] != "sha256:" + pins["native"]
            or trace["stage"]["masks"]["after_salvage"] != plan["candidate_tape_sha256"]
            or trace["ready"]["archive_sha256"] != witness["solver_recipe"]["archive_sha256"]
            or trace["ready"]["compatible_solver_sources"] != witness["source_sha256"]
            or trace["clock"]["exit"] or trace["stage"]["finishing_fits"]):
        raise ValueError("Unqualified exact signed checkpoint")
    base = trace["masks"]["after_salvage"]["tracks"]
    in_curved = {row["norad"] for row in base}
    targets = {int(norad): row for norad, row in plan["families"].items()}
    if not targets.keys() <= in_curved:
        raise ValueError("Candidate target was absent from original curved likelihood")
    training = risk["lean_final_fit"].get("arms", {})
    available_state = {arm: dict(predictive_points=sum(len(p["ids"]) for p in state["predictive"].values()),
                                 predictive_components=len(state["predictive"])) for arm, state in training.items()}
    return dict(native_sha256=pins["native"], witness_sha256=pins["charted"],
                archive_sha256=trace["ready"]["archive_sha256"], offer_sha256=trace["ready"]["offer_sha256"],
                historic_resident_archive=trace["ready"]["resident_archive"],
                checkpoint_wall_s=trace["clock"]["wall_s"], checkpoint_cpu_s=trace["clock"]["cpu_s"],
                curved_target_families=len(targets), curved_target_points=sum(row["curved_points"] for row in targets.values()),
                target_excluded_geometry_bound=False, target_excluded_receiver_noise_bound=False,
                direct_linear_terms_in_second_curved_posterior=0,
                held_data_independent_preparation_bound=False, exact_rejected_linear_table_available=plan["graph"] is not None,
                archived_later_pair_operands=available_state, measured_independent_profile_bound_s=None,
                same_rf_candidate_only_support=same_rf_support(plan["opportunities"], base, targets))


def preflight(candidate_plan, witnesses):
    checked(HERE / "blind_joint_finish.py", FINISH_PIN)
    for logical, pin in SOURCE_PINS.items():
        checked(RELEASE / logical, pin)
    nomination = document(candidate_plan, PLAN_PIN)
    tape = document(HERE / "measurements/second-curve-gate.json.gz", GATE_PIN)
    records = {case: inspect_case(nomination["cases"][case], tape[case], document(witness, pins["charted"]), pins)
               for (case, pins), witness in zip(CASES.items(), witnesses, strict=True)}
    return dict(disposition="refused_before_lease_missing_target_excluded_frozen_state_and_timing_bound",
                nomination_sha256=PLAN_PIN, gate_tape_sha256=GATE_PIN,
                source_sha256=SOURCE_PINS | {"blind_joint_finish.py": FINISH_PIN}, cases=records,
                historical_shared_child_cap_s=HISTORICAL_CHILD_CAP_S,
                sum_of_separate_contaminated_checkpoint_wall_s=sum(x["checkpoint_wall_s"] for x in records.values()),
                lease_attempts=0, graph_rebuilds=0, archive_bodies_read=0, observed_profiles=0, endpoint_values_used=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_plan", type=Path)
    parser.add_argument("charted_witnesses", nargs=2, type=Path, metavar=("CHARTED_0220", "CHARTED_0086"))
    args = parser.parse_args()
    print(json.dumps(preflight(args.candidate_plan, args.charted_witnesses), sort_keys=True, indent=2, allow_nan=False))
