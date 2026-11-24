"""Check single-publication ambiguity coverage without recomputing an orbit."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isclose
from pathlib import Path
import re
import sys
from time import perf_counter, process_time


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from prefix_transfer_0419 import ARMS, checked, write

DENSE = Path("/tmp/leo-v3-0008-prefix-transfer-result05")
DENSE_SEAL = "014568015a902fc2cd85c874306caa00c3892db17f334e678eae43cf8e2ef95c"
WITNESS = Path("/tmp/leo-v3-0008-prefix-trace01.json")
WITNESS_PIN = "bdbf9d195914eacda9b6acf8e815e7d89a949c5c4ab8e1d2971ac714dd331398"
CONTROL = Path("/dev/shm/leo-v3-nomination-handoff-0316-01")
CONTROL_PIN = "f7bc212aaddb1c2bbafc5c01532ed0ffaeccf188fcb4284cc8244dbb07c15a5d"
LANE = re.compile(r"SCAN-RX([12])-CH([1-8])-")
MODES = ("full-20", "measured-prefix")
UNITS = ("cpu_s", "elapsed_s")
FIT_FIELDS = {"curves", "families", "fit", "likelihood_columns", "normalization", "orbital_mode_families",
              "original_noise", "original_previous_tle", "phase_labels", "predictive", "timing_origin_ns", "total_curve_slots"}
SALVAGE_FIELDS = {"alternatives", "candidate_count", "component", "selected", "supports_tested"}


def parse(path, pin):
    return json.loads(checked(path, pin))


def family_scope(curves):
    """Project the original confidence eligibility predicate onto published curves."""
    lanes, owners = defaultdict(set), {}
    for name, curve in curves.items():
        key = LANE.match(name)
        if key is None:
            raise ValueError("Missing the observed radio/channel")
        owner = curve["norad"]
        lanes[owner].add(key.groups())
        owners[name] = owner
    return {name for name, owner in owners.items() if len(lanes[owner]) >= 2
            and len({receiver for receiver, _ in lanes[owner]}) == 1}


def cold_clearance(cold, half_width):
    from cold_finalist_race import choose

    leader, decision, ranks = choose(cold["prefix"], half_width)
    if decision != cold["routing"] or ranks != cold.get("gaps", []):
        raise ValueError("The recorded nomination rule does not replay directly")
    return dict(decision=decision, leader=None if leader is None else leader+1, comparisons=ranks,
                minimum_gap_surplus=min((v["gap"]-v["required"] for v in ranks), default=None))


def paid_work(clock, solve, attempt):
    keys = ("cold_clocks", "candidate_pre_evidence_clocks", "signed_total_clocks", "exterior_clocks",
            "standard_evidence_clocks")
    inner = {key: attempt[key] for key in keys}
    after_cold_before_signed = {u: inner["candidate_pre_evidence_clocks"][u] - inner["cold_clocks"][u] for u in UNITS}
    post_solve_to_publication = {u: solve["publication_"+u] - solve["solve"][u] for u in UNITS}
    late = {u: inner["signed_total_clocks"][u] + inner["exterior_clocks"][u]
            + inner["standard_evidence_clocks"][u] + post_solve_to_publication[u] for u in UNITS}
    named = {u: sum(t[u] for t in attempt["named_survivor_fit"]["named_arm_clocks"].values()) for u in UNITS}
    repair = {u: sum(attempt.get(k, {}).get(u, 0.) for k in ("repair_prepare_clocks", "repair_fit_clocks")) for u in UNITS}
    starts = clock["started_unix_ns"]
    return dict(inner=inner, child={u: clock[u] for u in UNITS},
                child_started_utc=datetime.fromtimestamp(starts/1e9, timezone.utc).isoformat(),
                after_cold_before_signed=after_cold_before_signed, named_final_fits_within_signed=named,
                confidence_inside_proposal={u: sum(r["clocks"][u] for r in attempt["sensitive_confidence"]) for u in UNITS},
                post_solve_to_publication=post_solve_to_publication, after_proposal_through_publication_gross=late,
                observed_optional_proven_avoidable=dict(cpu_s=0., elapsed_s=0.),
                optional_rework=dict(named_fallback=attempt.get("fallback_clocks"), earlier_repair_prepare_and_fit=repair,
                                    postfit_repair=attempt.get("local_future_repair"),
                                    provisional_refits=attempt["provisional_salvage"]["fit_calls"]))


def single(root, seal, route_file, science_file, clock_file):
    clock, route, science = (parse(root/key, seal[key]) for key in (clock_file, route_file, science_file))
    attempt, = route["solves"][0]["lean_attempts"]
    route = route["solves"][0]
    receipt = science["receipt"]
    if clock["exit_code"] != 0 or receipt["decision"] != "complete" or attempt["decision"] != "complete":
        raise ValueError("The comparison needs one successful published lean attempt")
    paid = paid_work(clock, science, attempt)
    clearance = cold_clearance(attempt["cold"], receipt["region"]["width_km"]/2)
    supports = {row["component"]: row for row in attempt["support"].get("salvage", [])}
    if any(set(row) != SALVAGE_FIELDS for row in supports.values()):
        raise ValueError("A new salvage schema needs a new aligned-coverage audit")
    shortlists = {row["component"]: row["candidate_indices"] for row in attempt.get("salvage_shortlists", [])}
    outcome = {}
    for arm in ARMS:
        final = route["lean_final_fit"]["arms"][arm]
        if set(final) != FIT_FIELDS:
            raise ValueError("A new curve book schema needs a new held-evidence audit")
        curves = {name: row for name, row in final["curves"].items() if row["ids"]}
        known = family_scope(curves)
        conditional = {i for i, _, role in science["selected_rows"][arm] if role == "conditional"}
        if {i for row in curves.values() for i in row["ids"]} != conditional:
            raise ValueError("The trace is missing accepted conditional observations")
        listed = shortlists.keys() & curves.keys()
        observations = supports.keys() & curves.keys()
        geometry = next(iter(final["families"].values()))
        outcome[arm] = dict(curves=len(curves), conditional_observations=len(conditional),
            one_receiver_multichannel_curves=sorted(known), in_salvage_shortlist=sorted(listed),
            in_salvage_support_trials=sorted(observations),
            aligned_same_state_all_catalogue_scores=[], independent_held_group_scores=[],
            derived_input_fields=sorted(final), salvage_record_fields=sorted({k for r in supports.values() for k in r}),
            fit_curve_value_representation=next(iter(curves.values()))["clock_cfo_rf"],
            orbit_context_fields=sorted(geometry), saved_orbit_prediction_representation=geometry["causal_sky"])
    return dict(clock_scope=paid, existing_race=clearance, arms=outcome,
                saved_confidence_counts=[{k: v for k,v in row.items() if k != "clocks"}
                                         for row in attempt["sensitive_confidence"]])


def audit(output):
    started = process_time(), perf_counter()
    seals = parse(DENSE/"prediction-seal.json", DENSE_SEAL)
    scopes = {mode: single(DENSE, seals, f"{mode}/routed/risk-route.json",
                           f"{mode}/routed/candidate/joint-research-receipt.json", f"{mode}/clock.json") for mode in MODES}
    negative = parse(CONTROL/"result.json", CONTROL_PIN)
    scopes["archived_same_input_parity"] = single(CONTROL, negative["process_and_publication_sha256"],
             "risk-route.json", "candidate/joint-research-receipt.json", "clock.json")
    # Join the retrospective switch witness only after producing all single-run diagnostics.
    trace = parse(WITNESS, WITNESS_PIN)
    curves = {row["curve"]: row["count"] for row in trace["unchanged_curve_rows"]}
    reachable = {mode: {arm: {name: sorted(curves.keys() & set(view[name]))
                             for name in ("one_receiver_multichannel_curves", "in_salvage_shortlist",
                                          "in_salvage_support_trials", "aligned_same_state_all_catalogue_scores",
                                          "independent_held_group_scores")}
                        for arm, view in scopes[mode]["arms"].items()} for mode in MODES}
    write(output, dict(protocol=sha256((HERE/"0008-prefix-ambiguity-protocol.md").read_bytes()).hexdigest(),
                       seals=[DENSE_SEAL, WITNESS_PIN, CONTROL_PIN], scopes=scopes,
                       retrospective_join=dict(curves=len(curves), rows=sum(row["count"] for row in trace["unchanged_curve_rows"]),
                                               reachable=reachable, projected_one_receiver_rows={
                          mode: {arm: sum(curves[n] for n in view["one_receiver_multichannel_curves"])
                                 for arm, view in arms.items()} for mode, arms in reachable.items()}),
                       negative_parity=negative["parity"],
                       audit_clock=dict(cpu_s=process_time()-started[0], elapsed_s=perf_counter()-started[1]),
                       waveforms=0, new_orbit_states=0, new_inference_calls=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    audit(parser.parse_args().output)
