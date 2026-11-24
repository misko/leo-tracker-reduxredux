"""Freeze deferred nominations and then grade distinct support on the sealed tapes."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path

from deferred_family_nomination import nominate, track_key


CAMPAIGN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124/cases")
CUSTODIAN = Path("/srv/postgres-nvme/leo-ds30-research-worktrees/pre-screen-owner-trace/reports/ALGO08/v3")
CHARTED = Path("/tmp/leo-v3-integrated-original-batch")
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
SEAL = "6eb9e46220096e695eaddfb5b4b0a673d8a28d13035e7caf8a26b9fc5f7df995"
SOURCE_SEAL = "8fa3872d7db96babacad8a5f2d12dfa449caa136"
SOURCES = {
    "second_curve_gate_trace.py": "395b8227825d6702ca0aaad69ccd82c3dc2aa4491d70942ba2b453105a47e666",
    "second_curve_gate_trial.py": "c9ccd01d2647c3422ec2ece46ad4273c2eebc93806a1ce56fd1e6781a9651c3d",
    "second_curve_gate_grade.py": "b8aaa49852f9e211ae8d203486aefe8bd1c5efddd8f666e744abe12c7f7145be",
}
CHARTED_SOURCES = {
    "reports/ALGO08/v3/blind_joint_finish.py": "7d8d5a65ceb0e11150e28d0dbbddeabb7741ef1408ded6272500e4f0e012c708",
    "reports/ALGO08/v3/isolated_salvage.py": "868bc79aa30e4548bd7979a79e458117583f4941cc374a8343568dc0a767d771",
    "reports/ALGO08/v3/fragment_gate_cross.py": "a0a19352c3aecb845c8b291f033126f8c1f670c4e3d285d2e5d757ccd6306da0",
    "reports/ALGO08/v3/provisional_salvage.py": "69dc94c6645f4b97cb6cadf79d7d0fc57a54138fc30cec176a4b5ab4729517af",
}
RELEASE_SOURCES = {
    "src/leo/analysis/localization_v3/conservative_recovery.py": "9d5047f873a22790c4f0818877b09270ee91a0761a9a3d7204c8a849639ee656",
    "src/leo/analysis/localization_v3/acceptance.py": "d4a3c3d8331c9e24d678d3c271139fbb8da62356b66274f93042774c89196353",
    "src/leo/analysis/research/polynomial_satellite_diagnostics.py": "8bf7d7935b74bba728d437d2652af636e5532be74d798ed4f56c6641be7352c5",
    "src/leo/analysis/localization_v3/tracks.py": "db44a947666c2dd7946534f69bf6af72ced63c8af553bb1b089c0fba3d5b7b6f",
}
CASES = {
    "DS30-0220": {
        "stage": "09866aab40a2a083c99c22763382400e3f09e4819dd525f7dc70989a0b1f115f",
        "after_salvage": "6e2d1e2a663de2f936297884f7a7524883d21ebf7a59b8545ac1ba8164f3838b",
        "charted": "b8be7fef63a425d3fd15de1ca206f6ec40be65b96afa8d114fb0e8808c8a36eb",
        "installed_score": "45253ba9c06057eb98d344b908cfd3ce5fa415958d7b91df9431cd66d6df874d",
    },
    "DS30-0086": {
        "stage": "41d1d808bfe657375581bb5083f7b42e4069fca54e9acb945cd54825ee31fa60",
        "after_salvage": "80cf9bdba526c0fab14ada5c27ea9fddffc0ac1492a41915ead2c32a58603c80",
        "charted": "5d775bbb9ff01ca9943c8001ed316cd2d65925da8348368452ddd8c0855ae084",
        "installed_score": "71b42b5c21f1f117981d18462f8fc4ccc883039e4cfdb9b2ed661380098a4bfd",
    },
}
ARMS = ("c0", "fitted_c")


def checked(path, pin):
    body = path.read_bytes()
    if sha256(body).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"Sealed source or replay metadata changed at {path}")
    return body


def document(path, pin):
    body = checked(path, pin)
    return json.loads(gzip.decompress(body) if path.suffix == ".gz" else body)


def signature(value):
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def snapshot(tape):
    inputs, outputs = {}, {}
    for row in tape["tracks"]:
        for oid in row["observation_ids"]:
            if oid in inputs:
                raise ValueError("Repeated original second-gate observation")
            inputs[oid] = row["norad"], row["role"]
            if row["compatible"]:
                outputs[oid] = inputs[oid]
    return dict(input=signature(inputs), output=signature(outputs), n_input=len(inputs), n_output=len(outputs))


def charted(case):
    path = CAMPAIGN / case / "successor/attempt-000001/publication/exact-named-raw-witness.json"
    return document(path, CASES[case]["charted"])


def certified_profile_slope(tape, attempt):
    """Link the original isolation `sole_failure` receipt to its same active rows."""
    isolation = attempt["provisional_salvage"]
    selected = {row["component"]: row["selected"] for row in attempt["support"]["salvage"]}
    eligible = set(isolation["eligible"])
    certified = set()
    for row in tape["tracks"]:
        if row["component"] not in eligible:
            continue
        salvage = selected.get(row["component"])
        if (salvage is None or (salvage["candidate_index"], salvage["norad"], salvage["points"])
                != (row["candidate_index"], row["norad"], row["points"])):
            raise ValueError("Isolated slope eligibility does not bind the salvaged interval")
        certified.add(track_key(row))
    if len(certified) != len(eligible):
        raise ValueError("Some isolated slope candidates disappeared from the exact second tape")
    return frozenset(certified)


def prior_hypotheses(deferred, attempt):
    if deferred is None:
        return None
    rows = [*deferred["survivors"], deferred["peer"]]
    selected, alternatives = {}, {}
    by_name = {item["component"]: item for item in attempt["support"]["salvage"]}
    for row in rows:
        name = row["component"]
        family = (row["candidate_index"], row["norad"])
        prior = by_name.get(name, {})
        item = prior.get("selected")
        if item is not None and (item["candidate_index"], item["norad"], item["points"]) == (*family, row["points"]):
            selected[name] = {key: item[key] for key in ("alias", "start_index", "stop_index", "points", "phase_s")}
        alternatives[name] = [{key: item[key] for key in ("alias", "start_index", "stop_index", "points")}
                              for item in prior.get("alternatives", ())
                              if (item["candidate_index"], item["norad"]) == family]
    provisional = attempt["provisional_salvage"]
    names = {row["component"] for row in rows}
    predictive = [label for label in attempt["support"]["predictive_labels"]
                  if label[0] in names or any(label[1] == row["norad"] for row in rows)]
    return dict(ordinary_selected_same_intervals=selected, ordinary_same_family_alternatives=alternatives,
                isolated_eligible=provisional["eligible"], isolated_status=provisional["status"],
                isolated_fit_calls=provisional["fit_calls"], isolated_reason=provisional.get("reason"),
                signed_history_status=attempt["signed"]["status"], predictive_labels=predictive,
                new_discrete_hypotheses=int(len(selected) != len(rows)))


def predict():
    for root, pins in ((CUSTODIAN, SOURCES), (CHARTED, CHARTED_SOURCES), (RELEASE, RELEASE_SOURCES)):
        for name, pin in pins.items():
            checked(root / name, pin)
    graded = document(CUSTODIAN / "measurements/second-curve-gate.json.gz", SEAL)
    rows = {}
    for case, pins in CASES.items():
        root = Path(f"/dev/shm/leo-v3-second-gate-{case[-4:]}-run01/run")
        stage = document(root / "stage-result.json", pins["stage"])
        tape = document(root / "after_salvage.json", pins["after_salvage"])
        sealed = graded[case]
        official = charted(case)
        attempt, = official["ports"]["history_risk"]["lean_attempts"]
        ready = sealed["ready"]
        rejected = sorted(row["component"] for row in tape["tracks"] if not row["compatible"])
        if (stage != sealed["stage"] or tape != sealed["masks"]["after_salvage"] or sealed["clock"]["exit"]
                or stage["masks"]["after_salvage"] != pins["after_salvage"] or stage["case"] != case
                or any(stage[key] for key in ("acquisition", "finishing_fits", "rendered"))
                or ready["native_sha256"] != stage["native_sha256"]
                or stage["native_sha256"] != official["evidence"]["detail"]["input_sha256"]
                or ready["compatible_solver_sources"] != official["source_sha256"]
                or snapshot(tape) != ready["expected_stage_masks"]["after_salvage"]
                or rejected != sorted(attempt["support"]["second_curved_rejections"])):
            raise ValueError("The observed second gate and original charted salvage diverged")
        tape_only = nominate(tape)
        certified = certified_profile_slope(tape, attempt)
        outcome = nominate(tape, certified_profile_slope=certified)
        novelty = prior_hypotheses(outcome["deferred"], attempt)
        rows[case] = dict(original_stage_sha256=pins["stage"], original_tape_sha256=pins["after_salvage"],
                          native_sha256=stage["native_sha256"], ordered_support=snapshot(tape),
                          tape_only_status=tape_only["status"], confirmed_profile_slope=[key[0] for key in sorted(certified)],
                          outcome=outcome, prior=novelty, independent_future_evidence_verified=False,
                          advance=False)
    return dict(custodian_commit=SOURCE_SEAL, custodian_seal_sha256=SEAL, original_clock_scope="saved second gate only",
                nomination_source_sha256=sha256(Path(nominate.__code__.co_filename).read_bytes()).hexdigest(),
                original_gates_changed=False, new_numeric_calls=0, rows=rows)


def owners(rows, owner_sha):
    found = {oid: (norad, role) for oid, norad, role in rows}
    if len(found) != len(rows) or signature({oid: norad for oid, (norad, _) in found.items()}) != owner_sha:
        raise ValueError("Published owner identity did not reproduce")
    return found


def support_coverage(rows, current, installed):
    counts = Counter()
    for row in rows:
        wanted = row["norad"], row["role"]
        for oid in row["observation_ids"]:
            if oid in current:
                counts["already_owned"] += 1
                continue
            target = installed.get(oid)
            if target is None:
                counts["extra_relative_to_installed"] += 1
            elif target == wanted:
                counts["matched_missing_installed"] += 1
            else:
                counts["wrong_satellite_or_role"] += 1
    return {key: counts[key] for key in ("matched_missing_installed", "wrong_satellite_or_role",
                                         "extra_relative_to_installed", "already_owned")}


def evaluate(prediction_path, pin):
    prediction = document(prediction_path, pin)
    rows = {}
    for case, predicted in prediction["rows"].items():
        expected = CASES[case]
        result = document(Path(f"/dev/shm/leo-v3-field-receiver-solver-cross-{case[-4:]}-01/score.json"),
                          expected["installed_score"])
        current = charted(case)["evidence"]
        if (result["grid"]["binding"]["input_sha256"] != predicted["native_sha256"]
                or result["named_mixed"]["region"] != current["detail"]["region"] or result["clock"]["exit_code"]):
            raise ValueError("Installed crossover owners come from a different native packet or offer")
        deferred = predicted["outcome"]["deferred"]
        arms = {}
        for arm in ARMS:
            old = owners(current["owner_rows"][arm], current["owner_maps"][arm])
            installed = owners(result["new_owners"][arm], result["new_owner_maps"][arm])
            missing = set(installed) - set(old)
            direct = support_coverage(deferred["survivors"] if deferred else (), old, installed)
            peer = support_coverage([deferred["peer"]] if deferred else (), old, installed)
            both = {key: direct[key] + peer[key] for key in direct}
            arms[arm] = dict(installed_only=len(missing),
                             installed_only_conditional=sum(installed[oid][1] == "conditional" for oid in missing),
                             direct_closure=direct, failed_peer=peer, joint_unattainable_upper_bound=both,
                             joint_fraction_of_all_missing=both["matched_missing_installed"] / len(missing) if missing else None,
                             currently_adopted=0)
        rows[case] = dict(installed_score_sha256=expected["installed_score"], arms=arms, advance=predicted["advance"])
    return dict(prediction_sha256=pin, new_numeric_calls=0, rows=rows)


if __name__ == "__main__":
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--prediction", type=Path)
    command.add_argument("--pin")
    args = command.parse_args()
    answer = predict() if args.prediction is None else evaluate(args.prediction, args.pin)
    print(json.dumps(answer, sort_keys=True, indent=2, allow_nan=False))
