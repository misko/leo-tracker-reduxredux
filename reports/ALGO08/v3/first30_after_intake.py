"""Reconcile downstream clocks and disjoint saved sensitivities on 30 DS30 pairs."""

from collections import Counter
import gzip
import json
from math import fsum, isclose
from pathlib import Path
import sys

from .field_fallback_budget import METRICS, clock, route_times
from .field_speed_reachability import BUILD, STOCK, checked, gates, reconcile
from .first24_slot_transfer import donors, project


HERE = Path(__file__).resolve().parent / "measurements"
EXPORT = "2994fe3bd068dc661fb7c4a6f9667e370218acae226106f7dd0b05636d71f8c5"
SEAL = "84fc1193f55485f66a20b703fc52540fb8c94301937769759e4ed07a75b3af92"
NATIVE = "6edf7f54ff0689eb27712cad780d7539a9fa8dc7f95c3d7dd379641580225eeb"
VETO = "4b3efdaf6970e8107260b12e9a6f6abe06fd0179ed96bf96942029699c41a2d3"
FIRST24 = "16297e515c2944148b3e591958b5f2023bba93ef4ed05e1ea70280072622c4e8"
PRE_EVIDENCE = ("cold", "initial_gate", "salvage", "predictive", "finish", "repair_prepare", "repair_fit", "expansion")


def remainder(total, *phases):
    delta = total - fsum(phases)
    if delta < -1e-6:
        raise ValueError("Stage clocks exceed their enclosing measured boundary")
    return max(0., delta)


def partition(row, original, raw, witness):
    """Each of the three dictionaries is internally disjoint and nested as named."""
    outer, solver, proposal = {}, {}, {}
    route = route_times(witness, row["decision"])
    lean = ((witness["ports"] or {}).get("history_risk") or {}).get("lean_attempts", [])
    attempt = lean[0] if lean else {}
    timing = witness.get("timing") or {}
    history = (witness["ports"] or {}).get("history", {})
    phases = raw["phases"]

    def callback(name, metric):
        return fsum(item[metric.removesuffix("_s")+"_ns"] for item in history.get(name, ()))/1e9

    for metric in METRICS:
        def stage(name):
            return clock(phases[name])[metric]

        def substage(name):
            return fsum(clock(record)[metric] for record in timing.get(name, ()))

        def attempt_stage(name):
            return clock(attempt[f"{name}_clocks"])[metric] if f"{name}_clocks" in attempt else 0.

        ready, assets = stage("receiver_ready_from_entry"), stage("asset_and_inventory_checks")
        acquire, selection = stage("authenticated_raw_acquisition"), stage("held_anchor_route_selection")
        decision, solve = stage("decision_and_publication"), substage("solve")
        analyze, render = substage("analyze"), substage("render")
        # The installed source checks are inside receiver readiness. Render and solve are inside analyze.
        remainder(ready, stage("installed_source_checks"))
        check = original["validation"][metric]
        if not isclose(original["process"][metric] + check, original[metric], abs_tol=1e-6, rel_tol=0.):
            raise ValueError("Independent readback is outside the charged child")
        outer[metric] = dict(receiver_ready=ready, assets_and_inventory=assets, held_selection=selection,
                             solve=solve, render=render, other_analyze=remainder(analyze, solve, render),
                             decision_outside_analyze=remainder(decision, analyze), independent_verify=check,
                             remaining_child=remainder(original["process"][metric], ready, assets, acquire, selection, decision))
        prepare, infer = callback("prepare", metric), callback("infer", metric)
        pre, signed, exterior, evidence = (attempt_stage(n) for n in
                                           ("candidate_pre_evidence", "signed_total", "exterior", "standard_evidence"))
        rejected, fallback = (route[n][metric] for n in ("rejected", "fallback"))
        solver[metric] = dict(preparation=prepare, accepted_proposal=remainder(pre, rejected), rejected_proposal=rejected,
                              signed_finish=signed, exterior=exterior, accepted_standard_evidence=evidence,
                              ordinary_fallback=fallback, inference_remainder=remainder(infer, pre, signed, exterior, evidence, fallback),
                              other_solve=remainder(solve, prepare, infer))
        proposal[metric] = {n: attempt_stage(n) for n in PRE_EVIDENCE}
        proposal[metric]["unassigned"] = remainder(pre, *proposal[metric].values())
    return dict(outer=outer, solver=solver, proposal=proposal, route=route["route"], reason=route.get("reason"),
                render_ports=(witness["ports"] or {}).get("cairo_layout"),
                png_ports=(witness["ports"] or {}).get("png"),
                rank=[{k: r[k] for k in ("nodes", "elapsed_ns", "cpu_ns")} for r in (witness["ports"] or {}).get("rank", ())],
                grid=(witness["ports"] or {}).get("grid"),
                nomination=(witness["ports"] or {}).get("history_risk", {}).get("nomination_handoff"),
                repair_refit=attempt.get("repair_fit_clocks"))


def enrolled(snapshot, campaign):
    book = json.loads(gzip.decompress(checked(HERE/"first30-empty-call-roof.json.gz", NATIVE)))
    seal = json.loads(checked(snapshot/"rows-with-relocations-seal.json", SEAL))
    rows = {(x["case"], x["algorithm"]): x for x in map(json.loads, checked(snapshot/"rows-with-relocations.jsonl", EXPORT).splitlines())}
    if book["rows_sha256"] != EXPORT or seal["combined_sha256"] != "sha256:"+EXPORT or len(book["cases"]) != 30:
        raise ValueError("Expected the fixed first 30 verified field pairs")
    result = []
    for case in book["cases"]:
        stock, candidate = (rows[case["case"], k] for k in ("installed", "successor"))
        if (any(not r["verified_pair"] or not r["acquisition_verified"] for r in (stock, candidate))
                or stock["build_sha256"] != "sha256:"+STOCK or candidate["build_sha256"] != "sha256:"+BUILD
                or candidate["attempt_result_sha256"] != case["candidate_join_sha256"]):
            raise ValueError("Paid arm identity differs from the first-30 native ledger")
        detail = reconcile(campaign, stock, candidate)
        root = (campaign/candidate["attempt"]).parent
        paid = json.loads(checked(root/"result.json", detail["pins"]["result"]))
        raw = json.loads(checked(root/"publication/unified-short-bootstrap.json", detail["pins"]["raw"]))
        witness = json.loads(checked(root/"publication/exact-named-raw-witness.json", detail["pins"]["scientific"]))
        authority = witness["evidence"]["detail"]
        if (authority["terminal_sha256"] != candidate["terminal_sha256"] or authority["input_sha256"] != case["native_sha256"]
                or paid["native_sha256"] != case["native_sha256"] or detail["acquisition_s"] != case["acquisition"]["elapsed_s"]):
            raise ValueError("Non-receiver stage must belong to the actual selected science")
        parts = partition(detail, paid, raw, witness)
        result.append(dict(detail, phases=parts, actual_child_wall_s=paid["process"]["elapsed_s"],
                           installed_result=stock["attempt_result_sha256"]))
    return result


def summarize(rows, slot_donors):
    observed = gates(rows, [0.]*len(rows))
    oracle_names = ("rejected_proposal", "ordinary_fallback")
    post_cost = lambda r, n: r["phases"]["solver"]["elapsed_s"][n]
    rejected = [post_cost(row, oracle_names[0]) for row in rows]
    both = [fsum(post_cost(row, n) for n in oracle_names) for row in rows]
    veto = [row["phases"]["repair_refit"]["elapsed_s"] if reject else 0. for row, reject in zip(rows, rejected, strict=True)]
    bands = {}
    for key, donor in slot_donors.items():
        transfer = [project(row, donor) for row in rows]
        for clock_name in ("producer_cpu_if_wall", "acquisition_wall", "prefix_exit_wall"):
            intake = [t[clock_name] for t in transfer]
            bands[f"{key}/{clock_name}"] = {
                label: gates(rows, [a+b for a, b in zip(intake, y, strict=True)])
                for label, y in (("keep", [0.]*len(rows)), ("veto_upper", veto),
                                 ("free_failed_proposal", rejected), ("free_both", both))
            }
    case_0147, case_0073 = (next(r for r in rows if r["case"] == name) for name in ("DS30-0147", "DS30-0073"))
    audited_veto = json.loads(checked(HERE/"repair-veto-transfer-0073.json", VETO))
    if (not audited_veto["frozen_veto_on_repaired_c0"] or not audited_veto["control_veto_on_repaired_c0"]
            or audited_veto["pins"]["successor_result"] != case_0073["pins"]["result"].removeprefix("sha256:")
            or audited_veto["pins"]["witness"] != case_0073["pins"]["scientific"]
            or audited_veto["fit_budget"]["control_upper_bound"] != case_0147["phases"]["repair_refit"]
            or audited_veto["fit_budget"]["whole_refit_upper_bound"] != case_0073["phases"]["repair_refit"]):
        raise ValueError("The held original does not match the frozen first-arm veto transfer")
    return dict(observed=observed, bands=bands, veto_upper_s=fsum(veto), both_calls_upper_s=fsum(both),
                rejected_upper_s=fsum(rejected), routes=dict(Counter(r["phases"]["route"] for r in rows)),
                totals={layer: {metric: {k: fsum(r["phases"][layer][metric][k] for r in rows)
                                        for k in rows[0]["phases"][layer][metric]}
                                for metric in METRICS} for layer in ("outer", "solver", "proposal")})


def run(snapshot, campaign):
    rows = enrolled(snapshot, campaign.resolve(strict=True))
    old = json.loads(checked(HERE/"first24-slot-transfer.json", FIRST24))
    prefix = {r["case"] for r in old["rows"]}
    slot_donors = donors()
    projected_prefix = {r["case"]: project(r, slot_donors["0049_slots_first"]) for r in rows if r["case"] in prefix}
    previous = old["transfers"]["0049_slots_first"]["per_case"]
    if len(projected_prefix) != 24 or projected_prefix != previous:
        raise ValueError("First 24 signed slot budgets did not reproduce")
    return dict(inputs=dict(export=EXPORT, seal=SEAL, native=NATIVE, veto=VETO, prior_slots=FIRST24),
                cases=rows, **summarize(rows, slot_donors))


if __name__ == "__main__":
    print(json.dumps(run(Path(sys.argv[1]), Path(sys.argv[2])), sort_keys=True, allow_nan=False))
