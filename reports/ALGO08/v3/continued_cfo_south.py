"""Reconstruct the continued-CFO South payload from the signed saved views."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time


ARCHIVED = Path("/dev/shm/leo-v3-south-cfo-route-02")
PINS = {
    "request": "44963383f603983d543c4122b0ec055049a157bc817b82e8aff9d9da6be66f70",
    "unrefined": "a10693d167757124a036cfcd63e90966760e52b755f4bb834605ccaf74426d2e",
    "receiver_seal": "539dc5c87d69b7d00387e647ac879f01eb46ee1deab2d6f9f1a39f9ab41af422",
    "refined_bootstrap": "a9c1cd78961ea0cdc57263ba9f444f970e8f8ea977995153cd8f77c9b93a3ad4",
}


def projection(original, refined, route):
    from anchor_exposure import bind, enroll
    from anchor_holds import history_rows
    from continued_cfo import ContinuedChanges, lane_key
    from held_cycle_refined import CFO
    from south_cfo_route import audit_selected

    bind(original, refined)
    rows, measured = (native["source"]["probes"] for native in (original, refined))
    events = list(enroll(original))
    gate = ContinuedChanges()
    pending = [gate.consider(row, event[4] == "short")
               for row, event in zip(rows, events, strict=True)]
    historical = history_rows(rows)
    if gate.projected_history(rows) != historical:
        raise ValueError("The online gate differs from independent unrefined history replay")
    archived = audit_selected(original, dict(source=dict(probes=historical)), refined, route)
    selected, costs, consumed = [], {radio: Counter() for radio in (0, 1)}, []
    for base, after, event, paid in zip(rows, measured, events, pending, strict=True):
        original_positive, refined_positive = bool(base["candidates"]), bool(after["candidates"])
        if paid and not refined_positive:
            raise ValueError("A paid lane is missing its genuine original refinement")
        if paid:
            consumed.append(lane_key(base))
        chosen = base if route["route"] == "unfiltered" and not paid else after
        edited = (refined_positive and base["candidates"][0][CFO] != after["candidates"][0][CFO])
        if route["route"] == "history" and edited and not paid:
            raise ValueError("The history publication contains an unpaid edit")
        costs[base["receiver_id"]].update(opportunities=1, measured_positives=int(original_positive),
            short_positives=int(event[4] == "short" and original_positive), paid=int(paid),
            selected=int(bool(chosen["candidates"])), archived_selected_edits=int(edited),
            retained_edits=int(edited and paid))
        selected.append(chosen)
    if consumed != gate.paid:
        raise ValueError("The synthetic substitution order differs from the live admission")
    return selected, archived, costs


def staged_json(path, pin):
    from empty_bootstrap import checked

    resolved = Path(path).resolve(strict=True)
    if not any(resolved.is_relative_to(prefix) for prefix in (Path("/dev/shm"), Path("/tmp"))):
        raise ValueError("Only pre-existing staged JSON is eligible")
    return json.loads(checked(resolved, pin))


def replay(output):
    from anchor_cycle_route import select_route
    from empty_bootstrap import bind_native, checked
    from full_short_run import RECIPE_SHA
    from leo.contracts.digests import canonical_digest

    request = staged_json(ARCHIVED / "binding.json", PINS["request"])
    original = staged_json(request["packets"]["unfiltered"]["file"], PINS["unrefined"])
    session, inventory = request["session"], request["inventory"]
    bind_native(original, session, inventory, RECIPE_SHA, expected="sha256:" + PINS["unrefined"])
    start = process_time(), perf_counter()
    choice = select_route(original)
    select_clock = dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])
    seal = staged_json(ARCHIVED / "raw-packet-seal.json", PINS["receiver_seal"])
    raw = staged_json(ARCHIVED / "containing/unified-short-bootstrap.json", PINS["refined_bootstrap"])
    refined = staged_json(seal["packet"], seal["native_sha256"][7:])
    measured_route = raw["held_anchor_route"]
    probes = original["source"]["probes"]
    bind_native(refined, session, inventory, seal["detector_sha256"][7:], expected=seal["native_sha256"])
    if (seal["bootstrap_sha256"] != PINS["refined_bootstrap"]
            or raw["native_sha256"] != seal["native_sha256"]
            or measured_route["selected_native_sha256"] != seal["native_sha256"]
            or measured_route["selected_recipe_sha256"] != seal["detector_sha256"]
            or canonical_digest(raw["receiver_recipe"]) != seal["detector_sha256"]
            or canonical_digest(choice) != canonical_digest(measured_route["choice"])
            or canonical_digest(probes) != measured_route["pre_refinement_probes_sha256"]
            or original["source"]["raw_recording_authority_digest"] != request["authority"]
            or original["clock_anchor"]["before"]["realtime_ns"] != request["cutoff_utc_ns"]
            or raw["causal_cutoff_utc_ns"] != request["cutoff_utc_ns"]
            or original["provenance"]["processed_windows"] != request["issued"]
            or raw["raw_acquisitions"] != 1 or raw["verified_handoffs"] != 1):
        raise ValueError("Archived South receiver and newly decided route do not bind the same acquisition")
    start = process_time(), perf_counter()
    selected, audited, radio = projection(original, refined, choice)
    projection_clock = dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])
    refinement = raw["receiver_audit"]["native"]["cfo_refinement"]
    for receiver, counts in radio.items():
        lanes = [lane["counts"] for lane in refinement["lanes"] if lane["receiver_id"] == receiver]
        counts["all_paid"] = sum(lane["attempted"] for lane in lanes)
        counts["all_edits"] = sum(lane["changed"] for lane in lanes)
        counts["avoided"] = counts["all_paid"] - counts["paid"]
        if counts["all_paid"] != counts["short_positives"]:
            raise ValueError("The archived native receiver did not pay every original short positive")
    if (audited != seal["comparison"] or sum(c["all_paid"] for c in radio.values()) != measured_route["refinement_attempts"]
            or sum(c["all_edits"] for c in radio.values()) != measured_route["changed"]):
        raise ValueError("The original receiver counters or sealed archive projection do not match")
    offer_pins = {mode: "sha256:" + pin for mode, pin in request["offer_sha256"].items()}
    for mode, pin in offer_pins.items():
        checked(Path(request["offers"][mode]), pin[7:])
    document = dict(pins=PINS, raw_authority=request["authority"], session=session, inventory=inventory,
        archive=request["archive"]["snapshots_sha256"], cutoff_utc_ns=request["cutoff_utc_ns"], offers=offer_pins,
        archived_native=seal["native_sha256"], archive_probe_sha256=audited["retained_probe_sha256"],
        continued_probe_sha256=canonical_digest(selected), identical_payload=selected == refined["source"]["probes"],
        choice=choice, radio=radio, select_clock=select_clock, replay_projection_clock=projection_clock,
        actual_historical_all_paid=dict(cpu_ns=refinement["cpu_ns"], wall_ns=refinement["wall_ns"]),
        measurements=dict(issued=request["issued"], original=audited["measured"], archived=audited["selected"]),
        solver_invocations=0, waveform_reads=0, resolved_data_source="authenticated saved South simulation")
    with output.open("x") as out:
        json.dump(document, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")
    return sha256(output.read_bytes()).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(replay(parser.parse_args().output))
