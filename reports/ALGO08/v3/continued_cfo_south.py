"""Reconstruct the continued-CFO South payload from the signed saved views."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time


ARCHIVED = Path("/dev/shm/leo-v3-south-cfo-route-02")
PUBLISHED = "cee62c62dddca08dc2e256791c28febd76da38d27a300e36c07e34a836a0c25f"
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


def sealed_json(output, document):
    with output.open("x") as out:
        json.dump(document, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")
    return sha256(output.read_bytes()).hexdigest()


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
    return sealed_json(output, document)


def publication(folder, receipt, clock, authority, native, old_media):
    from empty_bootstrap import checked
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from raw_cfo_north_trial import native_file
    from tools.pipeline_eval.qualification.paired_publication import evidence

    checked(native_file(folder), native[7:])
    checked(folder / "fast-scan-inputs" / (authority["session"] + ".json"), authority["inventory"][7:])
    verified = evidence(folder, receipt, clock["started_unix_ns"], read_only=True)
    media = artifacts(folder, receipt)
    storage = FastStandardAnalysisStore(folder)
    run = receipt["run_id"]
    if (clock["exit_code"] or receipt["decision"] != "complete"
            or receipt["session_id"] != authority["session"] or receipt["window_count"] != authority["measurements"]["issued"]
            or verified["raw_authority"] != authority["raw_authority"] or storage.detail(run)["input_sha256"] != native
            or canonical_digest(media) != canonical_digest(old_media)):
        raise ValueError("The archived offer terminal or media has changed")
    grid, path = storage.position_grid(run), storage.position_path(run)
    position = media["images"]["position"]["sha256"]
    if (not grid["complete"] or not grid["matched_c_grid"] or not path["stages"]
            or not len(grid["points"]) == grid["evaluated_points"] == grid["planned_points"] > 0
            or any(item["binding"]["position_png_sha256"] != position for item in (grid, path))):
        raise ValueError("Incomplete original two-arm evidence or mismatched position PNG")
    return verified, media, grid["evaluated_points"]


def score(route_file, route_pin, output):
    route = staged_json(route_file, route_pin)
    if not route["identical_payload"] or route["continued_probe_sha256"] != route["archive_probe_sha256"]:
        raise ValueError("Archived scores require exact ordered inference measurements")

    from leo.contracts.algo08_region import Algo08Region
    from raw_cfo_north_score import owner_summary
    from south_cfo_route import MODES, NAMED
    from south_cfo_route_score import NAMED_SCORED, NAMED_SCORED_PIN
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    chosen = staged_json(ARCHIVED / "result.json", PUBLISHED)
    named = staged_json(NAMED_SCORED, NAMED_SCORED_PIN)
    truth = named["truth"]
    if (not chosen["verified"] or not named["verified"] or truth != chosen["truth"]
            or chosen["binding"]["archive"]["snapshots_sha256"] != route["archive"]
            or chosen["seal"]["native_sha256"] != route["archived_native"]
            or chosen["chosen"]["pre_refinement_probes_sha256"] != chosen["seal"]["comparison"]["original_probe_sha256"]):
        raise ValueError("Original result, original named and route seal disagree")
    native = staged_json(chosen["seal"]["packet"], route["archived_native"][7:])
    amended = {tuple(row[:2]) for row in chosen["retained_cfo_edits"]}
    labels, edits = set(), set()
    for lane in native["source"]["probes"]:
        if lane["candidates"]:
            text = f"{route['session']}:{lane['receiver_id']}:{lane['valid_start_counter']}"
            identifier = "sha256:" + sha256(text.encode()).hexdigest()
            labels.add(identifier)
            if (lane["visit_index"], lane["receiver_id"]) in amended:
                edits.add(identifier)
    if len(labels) != route["measurements"]["archived"] or len(edits) != len(amended):
        raise ValueError("Archived owner evidence has an ambiguous original observation or edit")
    comparisons = {}
    for mode in MODES:
        original, control = chosen["cases"][mode], named["cases"][mode]
        folder, control_folder = ARCHIVED / mode, NAMED_SCORED.parent / mode
        receipt, control_receipt = original["receipt"], control["worker"]["receipt"]
        offer = Algo08Region.parse(staged_json(chosen["binding"]["offers"][mode], route["offers"][mode][7:])).document()
        if not receipt["region"] == control_receipt["region"] == control["offer"] == offer:
            raise ValueError("Original offers differ between published arms")
        if mode == "near-omitted":
            saved = json.loads((folder / "saved-south-cfo-route.json").read_bytes())
            if (saved["receipt"] != receipt or saved["native_sha256"] != route["archived_native"]
                    or saved["handoffs"] != 1 or not saved["staged_inventory"] or saved["waveform_calls"]):
                raise ValueError("The mirror did not use exactly one byte-identical saved handoff")
        verified, media, points = publication(folder, receipt, original["clock"], route, route["archived_native"], original["media"])
        control_verified, control_media, control_points = publication(control_folder, control_receipt,
            control["external_clock"], route, "sha256:" + NAMED[1], control["media"])
        trial = json.loads((folder / "joint-research-receipt.json").read_bytes())
        arms = {}
        for arm in ("c0", "fitted_c"):
            owners = owner_summary(trial["selected_rows"][arm], labels, edits)
            current, prior = verified["arms"][arm], control_verified["arms"][arm]
            error, prior_error = (distance_km(truth, row["latlon"]) for row in (current, prior))
            if (owners != original["owners"][arm] or owners["bound_sha256"] != verified["owners"][arm]
                    or control_verified["owners"][arm] != control["named_owner_digests"][arm]
                    or error != original["arms"][arm]["error_km"] or prior_error != original["named"][arm]["error_km"]
                    or current["latlon"] != original["arms"][arm]["latlon"] or prior["latlon"] != original["named"][arm]["latlon"]
                    or current["rf_rms_hz"] != original["arms"][arm]["rf_rms_hz"]
                    or prior["rf_rms_hz"] != original["named"][arm]["rf_rms_hz"]):
                raise ValueError("Archive alias changed original arm estimates, RF error or owners")
            arms[arm] = dict(error_km=error, rf_rms_hz=current["rf_rms_hz"], owners=owners,
                named_error_km=prior_error, named_rf_rms_hz=prior["rf_rms_hz"],
                named_owner_count=sum(control["selected_roles"][arm].values()),
                named_owner_sha256=control_verified["owners"][arm],
                delta_from_named_km=error-prior_error)
        truth_face = face_clearance_km(receipt["region"], truth)
        if abs(truth_face - (.1 if mode == "containing" else -.1)) > .001:
            raise ValueError("The scored original offer no longer brackets the signed boundary")
        comparisons[mode] = dict(status=original["status"], named_status=original["named_status"],
            truth_face_km=truth_face, arms=arms, media=media, named_media=control_media,
            grid_points=points, named_grid_points=control_points,
            terminal_sha256=receipt["terminal_sha256"], named_terminal_sha256=control_receipt["terminal_sha256"])
    return sealed_json(output, dict(pre_score_route_sha256=route_pin, route=route,
        archived_result_sha256=PUBLISHED, named_result_sha256=NAMED_SCORED_PIN, offers=comparisons,
        solver_invocations=0, waveform_reads=0, new_detector_publication=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--score-sealed", nargs=2, metavar=("ROUTE", "SHA256"))
    args = parser.parse_args()
    print(replay(args.output) if args.score_sealed is None else score(*args.score_sealed, args.output))
