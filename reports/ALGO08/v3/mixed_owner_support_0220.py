"""Join archived mixed-packet ownership and curved gates without scientific inference."""

from collections import Counter
from hashlib import sha256
from pathlib import Path
import argparse
import json

from pre_screen_owner_readout import ARMS, CASES, HERE, RELEASE, checked, document, owner_map, signature


CASE = "DS30-0220"
GATE_PIN = "6eb9e46220096e695eaddfb5b4b0a673d8a28d13035e7caf8a26b9fc5f7df995"
SOURCES = {
    "src/leo/analysis/localization_v3/acceptance.py":
        "d4a3c3d8331c9e24d678d3c271139fbb8da62356b66274f93042774c89196353",
    "src/leo/analysis/localization_v3/conservative_recovery.py":
        "9d5047f873a22790c4f0818877b09270ee91a0761a9a3d7204c8a849639ee656",
    "src/leo/analysis/localization_v3/predictive_linear.py":
        "1c1930b8fc71b6fafd43fa744661a785b7d243b74b1ab39ab1f59d8fe800dcc6",
}


def masks(trace):
    before, after = {}, {}
    for row in trace["tracks"]:
        ids = row["observation_ids"]
        if row["role"] != "conditional" or len(ids) != len(set(ids)) or len(ids) != row["points"]:
            raise ValueError("Gate row does not bind unique curved membership")
        value = row["norad"], row["role"]
        if before.keys() & set(ids):
            raise ValueError("Gate owner overlaps another original component")
        before.update(dict.fromkeys(ids, value))
        if row["compatible"]:
            after.update(dict.fromkeys(ids, value))
    return before, after


def compare(installed, charted, first, second, removed_curved, predictive_labels, failed_at_finish):
    first_in, first_out = masks(first)
    second_in, second_out = masks(second)
    removed = set(removed_curved)
    removed_ids = {oid for row in second["tracks"] if row["component"] in removed
                   for oid in row["observation_ids"]}
    remaining = {oid: owner for oid, owner in second_out.items() if oid not in removed_ids}
    if (not removed_ids <= second_out.keys()
            or remaining != {oid: owner for oid, owner in charted.items() if owner[1] == "conditional"}
            or not removed <= set(failed_at_finish)):
        raise ValueError("Finished curved ownership differs from the archived mask")
    missing = {oid: owner for oid, owner in installed.items() if oid not in charted}
    conditional = {oid: owner for oid, owner in missing.items() if owner[1] == "conditional"}
    predictive = {oid: owner for oid, owner in missing.items() if owner[1] == "predictive"}
    entered_families = {n for n, _ in second_in.values()}
    surviving_families = {n for n, _ in second_out.values()}
    selected_predictive_families = {n for _, n, _ in predictive_labels}
    if selected_predictive_families - surviving_families:
        raise ValueError("Selected predictive family has no surviving curved seed")
    curves = []
    for row in second["tracks"]:
        value = row["norad"], row["role"]
        joined = [oid for oid in row["observation_ids"] if conditional.get(oid) == value]
        if not joined:
            continue
        lost_at = "second_screen" if not row["compatible"] else "paired_finish_and_repair"
        curves.append(dict(component=row["component"], norad=row["norad"], matched=len(joined),
                           owner_ids_sha256=signature(joined), lost_at=lost_at,
                           family_survives_second=row["norad"] in surviving_families,
                           original_gate_tests=row["actual_tests"],
                           family_support_groups=row["family_support_groups"]))
    return dict(installed_only=len(missing), conditional=len(conditional), predictive=len(predictive),
                exact_conditional={key: sum(roster.get(oid) == owner for oid, owner in conditional.items())
                                   for key, roster in {"cold": first_in, "first_screen": first_out,
                                                        "signed_salvage": second_in,
                                                        "second_screen": second_out,
                                                        "paired_repair": remaining}.items()},
                conditional_curves=curves,
                predictive_missing_families=dict(Counter(n for n, _ in predictive.values())),
                predictive_ids_present_in_curved_tapes=len(predictive.keys() & (first_in.keys() | second_in.keys())),
                predictive_missing_ids_sha256=signature(sorted(predictive)),
                predictive_blocked_by_family_drop=sum(n in entered_families - surviving_families
                                                      for n, _ in predictive.values()),
                predictive_same_family_label_count=sum(n in selected_predictive_families
                                                       for n, _ in predictive.values()),
                predictive_selected_components=len(predictive_labels))


def evaluate(witness):
    pins = CASES[CASE]
    for path, pin in SOURCES.items():
        checked(RELEASE / path, pin)
    checked(HERE / "blind_joint_finish.py", "7d8d5a65ceb0e11150e28d0dbbddeabb7741ef1408ded6272500e4f0e012c708")
    original = document(witness, pins["charted"])
    crossover = document(HERE / "measurements/field-receiver-solver-cross-0220.json.gz", pins["crossover"])
    gate = document(HERE / "measurements/second-curve-gate.json.gz", GATE_PIN)[CASE]
    evidence, admission, alternate = original["evidence"], crossover["admission"], crossover["score"]
    tape, detail = gate["masks"], evidence["detail"]
    native = "sha256:" + pins["native"]
    if (not native == detail["input_sha256"] == admission["native_sha256"] == gate["stage"]["native_sha256"]
            or detail["raw_authority"] != admission["original_raw"]
            or detail["region"] != alternate["named_mixed"]["region"]
            or gate["ready"]["archive_sha256"] != admission["archive_sha256"]
            or gate["ready"]["offer_sha256"] != admission["offer_sha256"]
            or gate["ready"]["compatible_solver_sources"] != original["source_sha256"]
            or alternate["new_owners"] != crossover["worker"]["ordered_owners"]
            or crossover["worker"]["verified_handoffs"] != 1 or crossover["clock"]["exit_code"] or gate["clock"]["exit"]):
        raise ValueError("The recorded ownership does not bind the same mixed evidence and offer")
    attempt, = original["ports"]["history_risk"]["lean_attempts"]
    support, repair = attempt["support"], attempt["repair"]
    if (repair["status"] != "complete"
            or sorted(support["second_curved_rejections"]) != sorted(r["component"] for r in tape["after_salvage"]["tracks"]
                                                                   if not r["compatible"])):
        raise ValueError("The tape differs from the original recorded second drop")
    arms = {arm: compare(owner_map(alternate["new_owners"][arm], alternate["new_owner_maps"][arm]),
                         owner_map(evidence["owner_rows"][arm], evidence["owner_maps"][arm]),
                         tape["first"], tape["after_salvage"], repair["removed_curved"],
                         support["predictive_labels"], attempt["finish"][arm]["failed_curved"])
            for arm in ARMS}
    return dict(case=CASE, inputs=pins | dict(gates=GATE_PIN, causal=admission["archive_sha256"],
                region=admission["offer_sha256"]), source_sha256=SOURCES,
                evaluator_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), arms=arms,
                original_paired_repair_predictive_counts=repair["rejection_counts"]["predictive"],
                original_isolated_fit_calls=attempt["provisional_salvage"]["fit_calls"],
                installed_pre_final_owner_rows_available=False, rejected_predictive_member_rows_available=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("charted_witness", type=Path)
    print(json.dumps(evaluate(parser.parse_args().charted_witness), sort_keys=True, indent=2, allow_nan=False))
