"""Audit a fixed accepted-support-repair trigger on sealed field receipts."""

import argparse
from collections import defaultdict
import gzip
from hashlib import sha256
import json
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from statistics import median


ARMS = ("c0", "fitted_c")
LIMIT_M = 250.0
HERE = Path(__file__).resolve().parent
SEAL = "sha256:1b88b5875c04f7c935a156f1414131ce4d665c48ea3774a8da4f08e2530aed60"
REFERENCE = "sha256:c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
PACKAGED_0220 = "sha256:cbc1ae11c9a40f9d667bd45966d3dffc40b6c3b8d94a15fcdf9cbe38018a2455"
CROSSOVERS = {
    "DS30-0049": ("ds30-0049-saved-crossover.json.gz",
                  "sha256:76ffa1841268d1f9dd8348a3549c8927655653abdcc804697b6a36f00aebf8ce"),
    "DS30-0086": ("field-receiver-solver-cross-0086.json.gz",
                  "sha256:e98fac35839b13c3b002cc1ba53ce50111cb53f86e6bb735ca1985c1b89a6da9"),
    "DS30-0220": ("score.json", "sha256:45253ba9c06057eb98d344b908cfd3ce5fa415958d7b91df9431cd66d6df874d"),
}


def evidence(path, expected=None):
    body = path.read_bytes()
    digest = "sha256:" + sha256(body).hexdigest()
    if expected is not None and digest != expected:
        raise ValueError(f"Sealed evidence changed: {path.name}")
    return body, digest


def read(path, expected=None):
    body, digest = evidence(path, expected)
    return json.loads(gzip.decompress(body) if path.suffix == ".gz" else body), digest


def accepted_repair(attempt):
    repair = attempt.get("repair") or {}
    count = repair.get("attempted_refits")
    return (attempt.get("decision") == "complete" and repair.get("status") == "complete"
            and type(count) is int and count > 0)


def branch(witness, outcome):
    if witness.get("raw_route") == "authenticated_installed_graph_ineligible" and outcome == "withheld":
        return False, None
    risk = (witness.get("ports") or {}).get("history_risk") or {}
    attempts = risk.get("lean_attempts")
    if (risk.get("choice", {}).get("route") != "lean" or not isinstance(attempts, list) or len(attempts) != 1
            or attempts[0].get("decision") not in ("complete", "fallback")):
        return None, None
    return accepted_repair(attempts[0]), attempts[0]


def distance_m(left, right):
    x, y = map(radians, left)
    u, v = map(radians, right)
    chord = sin((x-u)/2)**2 + cos(x)*cos(u)*sin((y-v)/2)**2
    return 12_742_017.6 * asin(sqrt(min(1.0, chord)))


def degradation(errors):
    return dict(any_positive=any(x > 0 for x in errors.values()), over_250m=any(x > LIMIT_M for x in errors.values()))


def timings(fields, clock_scope):
    return dict(scope=clock_scope, elapsed_s=fields.get("elapsed_s", fields.get("wall_s")), cpu_s=fields["cpu_s"])


def sum_clocks(rows):
    return {key: sum(row[key] for row in rows) for key in ("elapsed_s", "cpu_s")}


def qualify_crossover(case, document, installed, successor, reference, triggers):
    if case == "DS30-0049":
        cells = document["cells"]
        new, old = (cells[k] for k in ("installed-successor", "successor-successor"))
        if (document["waveform_reads"] != 0 or new["terminal_sha256"] != old["terminal_sha256"]
                or old["terminal_sha256"] != successor["evidence"]["receipt"]["terminal_sha256"]
                or new["native_sha256"] != old["native_sha256"] or old["native_sha256"] != successor["native_sha256"]
                or {new["decision"], old["decision"]} != {"complete"} or len(new["figures"]) != 8):
            raise ValueError("The measured 0049 mixed cells do not bind the field packet")
        target = {arm: new["arms"][arm]["latlon"] for arm in ARMS}
        costs = {name: timings(cell["clocks"], "matched_saved_child_to_exit")
                 for name, cell in (("installed_mixed", new), ("charted_mixed", old))}
        costs["saved_replacement_delta_s"] = {key: costs["installed_mixed"][key] - costs["charted_mixed"][key]
                                               for key in ("elapsed_s", "cpu_s")}
    else:
        score = document.get("score", document)
        grid, receipt = score["grid"], score["named_mixed"]
        binding = grid["binding"]
        if (score["case"] != case or score["scientific_cells"] != 4 or score["clock"]["exit_code"] != 0
                or not grid["complete"] or grid["evaluated_points"] != 179 or len(score["figures"]) != 8
                or receipt["decision"] != "complete" or binding["input_sha256"] != successor["native_sha256"]
                or score["path"]["binding"]["terminal_sha256"] != binding["terminal_sha256"]
                or receipt["terminal_sha256"] != binding["terminal_sha256"]):
            raise ValueError(f"The measured installed/mixed result is unbound: {case}")
        target = grid["endpoint_latlon"]
        costs = dict(installed_mixed=timings(score["clock"], "separate_shipped_saved_child_to_exit"))
    effects = {}
    for arm in ARMS:
        old, named = (r["evidence"]["arms"][arm]["latlon"] for r in (successor, installed))
        stock_error, old_error, new_error = [distance_m(reference, point) for point in (named, old, target[arm])]
        effects[arm] = dict(installed_full_error_m=stock_error, charted_mixed_error_m=old_error,
                            installed_mixed_error_m=new_error, mixed_solver_displacement_m=distance_m(old, target[arm]),
                            mixed_solver_error_delta_m=new_error-old_error,
                            switch_remaining_regression_m=new_error-stock_error,
                            rule_error_m=None if triggers is None else (new_error if triggers else old_error))
    return dict(trigger=triggers, arms=effects, costs=costs, native_sha256=successor["native_sha256"])


def case_inputs(capture, cohort):
    batches = defaultdict(dict)
    for row in cohort:
        if row["verified_pair"] is not True:
            continue
        key, method = row["case"], row["algorithm"]
        if method in batches[key] or method not in ("installed", "successor"):
            raise ValueError(f"Unexpected verified pair member: {key}")
        path = Path(row["attempt"])
        if path.is_absolute() or ".." in path.parts or path.name != "result.json":
            raise ValueError("Expected a sealed local result path")
        result, _ = read(capture / path, row["attempt_result_sha256"])
        receipt = result["evidence"]["receipt"]
        if (result["algorithm"] != method or row["outcome"] != receipt["decision"]
                or receipt.get("terminal_sha256") != row["terminal_sha256"]):
            raise ValueError(f"Field result disagrees with the sealed ledger: {key}")
        batches[key][method] = row, result, (capture / path).parent / "publication"
    if len(batches) != 27 or any(len(pair) != 2 for pair in batches.values()):
        raise ValueError("Expected exactly 27 verified field pairs")
    return batches


def evaluate(capture, enrolled, latest_score, reference_file):
    seal, _ = read(enrolled / "rows-with-relocations-seal.json", SEAL)
    corpus, _ = evidence(enrolled / "rows-with-relocations.jsonl", seal["combined_sha256"])
    enrolled_rows = [json.loads(line) for line in corpus.splitlines()]
    batches = case_inputs(capture, enrolled_rows)
    contexts = {}
    for case, pair in batches.items():
        successor, named, pub = pair["successor"]
        witness, digest = read(pub / "exact-named-raw-witness.json")
        observed = witness["evidence"]["detail"]
        if (observed["terminal_sha256"] != successor["terminal_sha256"] or observed["state"] != successor["outcome"]
                or observed["input_sha256"] != named["native_sha256"]):
            raise ValueError(f"Misbound successor witness: {case}")
        trigger, attempt = branch(witness, successor["outcome"])
        contexts[case] = (trigger, attempt, digest, witness.get("raw_route"))

    # The policy has been evaluated for every case before opening survey data.
    survey, _ = read(reference_file, REFERENCE)
    eligible = {r["dataset_label"]: (r["reference"]["latitude_deg"], r["reference"]["longitude_deg"])
                for r in survey["cases"] if r["authority_eligible"] and r["sealed_metadata_digests_verified"]}
    rows, measured = {}, {}
    for case, pair in batches.items():
        left, named, _ = pair["installed"]
        right, current, _ = pair["successor"]
        trigger, attempt, digest, route = contexts[case]
        site = eligible.get(case)
        outcome = {"installed": left["outcome"], "charted": right["outcome"]}
        errors = (None if site is None or set(outcome.values()) != {"complete"} else
                  {arm: {key: distance_m(site, src["arms"][arm]["latlon"])
                         for key, src in (("installed_full", left), ("charted_mixed", right))} for arm in ARMS})
        changes = (None if errors is None else {arm: values["charted_mixed"]-values["installed_full"]
                                                for arm, values in errors.items()})
        data = dict(assigned_rank=right["assigned_rank"], trigger=trigger, outcome=outcome, route=route,
                    witness_sha256=digest, ledger_result_sha256={key: r[0]["attempt_result_sha256"] for key, r in pair.items()},
                    errors_m=errors, error_delta_m=changes, regression=degradation(changes) if changes is not None else None,
                    decisions_differ=len(set(outcome.values())) != 1)
        if attempt is not None:
            repair = attempt.get("repair") or {}
            data.update(attempt_decision=attempt.get("decision"), repair_status=repair.get("status"),
                        attempted_refits=repair.get("attempted_refits"), first_pair_failed=attempt.get("pair_passes") is False)
            if repair.get("status") is not None:
                keys = ("repair_prepare_clocks", "repair_fit_clocks")
                clocks = [attempt[k] for k in keys if k in attempt]
                if clocks:
                    data["observed_repair_prepare_and_fit"] = sum_clocks(clocks)
        if case in CROSSOVERS:
            file, source = CROSSOVERS[case]
            path = HERE / "measurements" / file
            if case == "DS30-0220":
                path = latest_score
                source = PACKAGED_0220 if path.suffix == ".gz" else source
            proof, _ = read(path, source)
            case_measurement = qualify_crossover(case, proof, named, current, site, trigger)
            case_measurement["source_sha256"] = source
            case_measurement["costs"]["charted_mixed_raw"] = timings(right, right["timing_scope"])
            measured[case] = case_measurement
        if trigger is False:
            data["policy_disposition"] = "retain_observed_charted"
        elif case in measured and trigger:
            data["policy_disposition"] = "measured_released_mixed_fix"
        else:
            data["policy_disposition"] = "switch_or_trigger_unmeasured"
        rows[case] = data

    summary = dict(cases=len(rows), triggered=[c for c, row in rows.items() if row["trigger"] is True],
                   unknown_trigger=[c for c, row in rows.items() if row["trigger"] is None],
                   decision_disagreements=[c for c, row in rows.items() if row["decisions_differ"]],
                   common_fixes_scored=sum(row["errors_m"] is not None for row in rows.values()),
                   first_pair_failures=[c for c, row in rows.items() if row.get("first_pair_failed") is True])
    for key in ("any_positive", "over_250m"):
        group = [c for c, row in rows.items() if row["regression"] is not None and row["regression"][key]]
        summary[key] = dict(reached=[c for c in group if rows[c]["trigger"] is True],
                            missed=[c for c in group if rows[c]["trigger"] is False],
                            unknown=[c for c in group if rows[c]["trigger"] is None])
    clocks = [rows[c]["observed_repair_prepare_and_fit"] for c in summary["triggered"]
              if "observed_repair_prepare_and_fit" in rows[c]]
    summary["observed_repair_prepare_and_fit"] = dict(
        cases=len(clocks), total=sum_clocks(clocks),
        median={key: median(c[key] for c in clocks) for key in ("elapsed_s", "cpu_s")} if clocks else None,
    )
    return dict(ledger_sha256=seal["combined_sha256"], freeze_sha256=SEAL, reference_sha256=REFERENCE,
                candidate_reexecutions=0, cases=rows, crossovers=measured, summary=summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("latest_0220_score", type=Path)
    parser.add_argument("reference", type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.capture, args.ledger, args.latest_0220_score, args.reference),
                     sort_keys=True, indent=2, allow_nan=False))
