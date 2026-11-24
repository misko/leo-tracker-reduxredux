"""Read sealed native, ownership and position receipts for two saved member-mask cases."""

import argparse
from collections import Counter, defaultdict
import gzip
from hashlib import sha256
import json
from math import dist, isfinite
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
from three_quarter_members import ARMS, HERE, checked, digest, read, write  # noqa: E402
from tools.pipeline_eval.scoring import distance_km  # noqa: E402


STAGE = Path("/dev/shm")
BUNDLES = {
    "three-quarter-members": "a211ba6c9c5bbd89500772325517281b2430db2cbc02c14198260edcd6dbcc2a",
    "three-quarter-challenge": "a9cdde3dda925166871f6acb0eb36893e7b4970061834ad99d1e6508f8b65b6f",
}
OLD_0086 = "0649beae4cda8663b43e3faabf245131c097b335dded181439575f854bf590c5"
OUTCOMES = ("deleted_unowned", "deleted_owned", "unowned_both", "same_satellite",
            "newly_assigned", "unassigned_after", "switched_satellite")


def source_bundle(name):
    return json.loads(gzip.decompress(checked(HERE / "measurements" / f"{name}.json.gz", BUNDLES[name])))


def snapshot(bundle, name):
    return bundle[name]["document"]


def signed_visits(members):
    """Use published member boundaries, including short tails and segment resets."""
    visits = {}
    for ordinal, member in enumerate(members):
        start, stop = member["first_visit"], member["stop_visit"]
        if (member["ordinal"] != ordinal or start != len(visits)
                or stop - start != member["window_count"] or not 0 < stop - start <= 64
                or member["observed_index_sha256"] != member["index_sha256"]
                or not member["manifest_sha256"] or (member["omit"] and stop - start != 64)):
            raise ValueError("Invalid signed member roster")
        segment = Path(member["segment_manifest"]).parent.name.rsplit("-segment-", 1)[-1]
        visits.update((visit, (segment, member["omit"])) for visit in range(start, stop))
    return visits


def native_locations(ordinary, sampled, members, authority):
    visits = signed_visits(members)
    old, new = ordinary["source"], sampled["source"]
    sampling = sampled["provenance"]["research_sampling"]
    omitted = [visit for visit, (_, omit) in visits.items() if omit]
    if (len(visits) != authority["window_count"] or sampling["members_sha256"] != digest(members)
            or sampling["skipped_acquisition_windows"] != omitted or sampling["receiver_slots"] != [0, 1]
            or old["session_id"] != new["session_id"] or new["session_id"] != authority["session_id"]
            or any(source["raw_recording_authority_digest"] != authority["raw_authority_sha256"]
                   or source["input_manifest_sha256"] != authority["inventory_sha256"] for source in (old, new))
            or any(ordinary[key] != sampled[key] for key in ("clock_anchor", "delivery_clocks"))
            or new["probes"] != [p for p in old["probes"] if not visits[p["visit_index"]][1]]):
        raise ValueError("Saved mask changed retained native factors or the signed acquisition identity")
    locations = {}
    for probe in old["probes"]:
        if not probe["candidates"]:
            continue
        key = f"{old['session_id']}:{probe['receiver_id']}:{probe['valid_start_counter']}"
        oid = "sha256:" + sha256(key.encode()).hexdigest()
        if oid in locations or len(probe["candidates"]) != 1:
            raise ValueError("The independent native lane is ambiguous")
        locations[oid] = visits[probe["visit_index"]]
    return visits, locations


def ownership(evidence, arm):
    rows = evidence["owner_rows"][arm]
    result = {oid: sat for oid, sat, _role in rows}
    detail = evidence["detail"]["arms"][arm]
    if len(result) != len(rows) or digest(result) != detail["owner_sha256"] or len(result) != detail["associated_points"]:
        raise ValueError("Owner rows differ from the sealed publication")
    return result


def classify(locations, ordinary, sampled):
    if not (ordinary.keys() | sampled.keys()) <= locations.keys():
        raise ValueError("Published owner is absent from original selected native lanes")
    totals = Counter(dict.fromkeys(OUTCOMES, 0))
    segments, satellites, transitions = defaultdict(Counter), defaultdict(Counter), Counter()
    for oid, (segment, omitted) in locations.items():
        before, after = ordinary.get(oid), sampled.get(oid)
        if omitted:
            if after is not None:
                raise ValueError("Sampled publication owns an omitted native lane")
            change = "deleted_unowned" if before is None else "deleted_owned"
        elif before == after:
            change = "unowned_both" if before is None else "same_satellite"
        elif before is None:
            change = "newly_assigned"
        elif after is None:
            change = "unassigned_after"
        else:
            change = "switched_satellite"
            transitions[(before, after)] += 1
        totals[change] += 1
        segments[segment][change] += 1
        if before is not None:
            satellites[before]["ordinary"] += 1
            satellites[before]["switched_out" if change == "switched_satellite" else change] += 1
        if after is not None:
            satellites[after]["sampled"] += 1
            if change in ("newly_assigned", "switched_satellite"):
                satellites[after]["switched_in" if before is not None else change] += 1
    return dict(totals=totals, by_segment=dict(segments), by_satellite={str(k): v for k, v in satellites.items()},
                transitions=[dict(before=before, after=after, count=n)
                             for (before, after), n in sorted(transitions.items())])


def objective_summary(grid, path, terminal, detail):
    points = {(p["east_km"], p["north_km"]): p for p in grid["points"]}
    stage, = path["stages"]
    if (not grid["complete"] or not grid["matched_c_grid"] or grid["planned_points"] != len(points)
            or grid["evaluated_points"] != len(grid["points"]) or len(grid["points"]) != len(points)
            or grid["region_center"] != path["region_center"]):
        raise ValueError("Incomplete paired grid or inconsistent sealed path")
    result = {}
    for arm in ARMS:
        endpoint = grid["endpoints"][arm]
        point = points[tuple(endpoint)]
        replay_delta = grid["endpoint_objective_replay"][arm]
        trace = stage["arms"][arm]
        rounds = trace["rounds"]
        if (not trace["history_available"] or endpoint != trace["endpoint"] or endpoint != rounds[-1]["endpoint"]
                or point["latlon"] != grid["endpoint_latlon"][arm] or point["latlon"] != terminal["arms"][arm]["latlon"]
                or point["latlon"] != detail[arm]["endpoint_latlon"] or point["failures"]
                or not isfinite(replay_delta) or abs(replay_delta) > 1e-4 or not isfinite(point["scores"][arm])):
            raise ValueError("Sealed grid, optimization path and terminal endpoint disagree")
        result[arm] = dict(endpoint_latlon=point["latlon"], endpoint_east_north_km=endpoint,
                           path_first_recorded_east_north_km=rounds[0]["points"][0],
                           path_round_endpoints_east_north_km=[r["endpoint"] for r in rounds],
                           endpoint_objective=point["scores"][arm], replay_minus_saved_objective=replay_delta,
                           terminal_rf_rms_hz=terminal["arms"][arm]["rf_rms_hz"],
                           all_owned_rf_rms_hz=detail[arm]["residual_rms_hz"],
                           tracks=detail[arm]["tracks"], satellites=detail[arm]["satellites"])
    return result


def cold_forensics(witness, ordinary_endpoint, lost_satellites):
    audit = witness["ports"]["history_risk"]
    attempt, = audit["lean_attempts"]
    rank, cold, support = audit["two_centre_rank"], attempt["cold"], attempt["support"]
    if rank.get("fallback") or audit["nomination_handoff"].get("ordinary_fallbacks"):
        raise ValueError("The recorded speculative rank and completed candidate ranks are incomparable")
    finalists = []
    prefix = {p["branch"]: p for p in cold["prefix"]}
    completed = {p["branch"]: p for p in cold["completed"]}
    for branch, signature in enumerate(rank["finalist_signatures"], 1):
        start, end = prefix[branch], completed[branch]
        counts = Counter(row[2] for row in signature)
        if cold["scores"][branch-1] != end["score"] or set(end["labels"]) != {row[1] for row in signature}:
            raise ValueError("The recorded finalist assignments and completed cold fits disagree")
        finalists.append(dict(branch=branch, tracks=len(signature), satellites=len(counts),
                              lost_satellite_tracks={str(sat): counts[sat] for sat in sorted(lost_satellites)},
                              prefix_evaluations=start["evaluations"], prefix_east_north_km=start["parameters"],
                              prefix_to_ordinary_c0_km=dist(start["parameters"], ordinary_endpoint),
                              completed_east_north_km=end["point"], completed_to_ordinary_c0_km=dist(end["point"], ordinary_endpoint),
                              completed_score=end["score"]))
    selected = cold["branch"]
    if completed[selected]["point"] != cold["east_north_km"]:
        raise ValueError("Selected candidate does not match its completed cold fit")
    traces = [dict(component=component, norad=sat, alias=alias, cold_rejected=component in support["cold_rejected_tracks"],
                   second_curved_rejected=component in support["second_curved_rejections"])
              for component, _index, sat, alias in rank["finalist_signatures"][selected-1] if sat in lost_satellites]
    return dict(ranked_nodes=rank["ranked_nodes"], routing=cold["routing"], selected=selected, finalists=finalists,
                selected_lost_satellite_tracks=traces, initial_paired_finish_passed=attempt["pair_passes"],
                repair_status=attempt.get("repair", {}).get("status"))


def publication(directory, seal, native_pin):
    def sealed(name):
        path, = directory.rglob(name)
        key = str(path.relative_to(directory.parent))
        # The earlier 0086 seal pins its scientific sidecars via the witness itself.
        return read(path, seal[key] if directory.name == "candidate" or name == "exact-named-raw-witness.json" else None)

    witness = sealed("exact-named-raw-witness.json")
    terminal = sealed("terminal.json")
    evidence = witness["evidence"]
    if terminal["decision"] != "ok" or terminal["native_sha256"] != native_pin:
        raise ValueError("Publication does not bind the matched native packet")
    sides = {}
    for kind in ("grid", "path"):
        sidecar = sealed(f"position-{kind}.json")
        if digest(sidecar["document"]) != sidecar["sha256"] or sidecar["sha256"] != evidence["sidecars"][kind]:
            raise ValueError("Grid or path changed since witness sealing")
        sides[kind] = sidecar["document"]
    return witness, objective_summary(sides["grid"], sides["path"], terminal, evidence["detail"]["arms"])


def result(bundle, *, members_key, native_key, stage, original, sampled_root, ordinary_seal, sampled_seal,
           scope, scores, sampled_label, inspect_cold=False):
    signed = snapshot(bundle, members_key)
    projected = snapshot(bundle, native_key)
    authority, binds = scope["authority"], scope["scope"]
    old_pin = binds["historical_final_native_sha256"]
    new_pin = binds["proposed_native_sha256"]
    ordinary = read(stage / "native.json", old_pin)
    if digest(signed) != binds["members_sha256"] or digest(projected) != new_pin:
        raise ValueError("The published admission does not bind the signed spans and derived native")
    visits, locations = native_locations(ordinary, projected, signed, authority)
    ordinary_witness, prior_objective = publication(original, ordinary_seal, old_pin)
    sampled_witness, after_objective = publication(sampled_root, sampled_seal, new_pin)
    prior, after = ordinary_witness["evidence"], sampled_witness["evidence"]
    ordinary_owners = {arm: ownership(prior, arm) for arm in ARMS}
    sampled_owners = {arm: ownership(after, arm) for arm in ARMS}
    rows = {}
    for arm in ARMS:
        ordinary_science, sampled_science = prior_objective[arm], after_objective[arm]
        for archive, receipt in ((scores["successor"][arm], ordinary_science), (scores[sampled_label][arm], sampled_science)):
            if (archive.get("latlon", receipt["endpoint_latlon"]) != receipt["endpoint_latlon"]
                    or archive["rf_rms_hz"] != receipt["terminal_rf_rms_hz"]):
                raise ValueError("Terminal coordinates or RF scores disagree with the sealed field comparison")
        rows[arm] = dict(
            ownership=classify(locations, ordinary_owners[arm], sampled_owners[arm]),
            ordinary=ordinary_science, sampled=sampled_science,
            historical_horizontal_error_km={mode: scores[key][arm]["error_km"] for mode, key in
                                            (("installed", "installed"), ("ordinary", "successor"), ("sampled", sampled_label))},
            ordinary_to_sampled_endpoint_km=distance_km(ordinary_science["endpoint_latlon"], sampled_science["endpoint_latlon"]),
            first_recorded_path_points_separation_km=dist(ordinary_science["path_first_recorded_east_north_km"],
                                                         sampled_science["path_first_recorded_east_north_km"]),
        )
    record = dict(arms=rows, signed_visits=len(visits), omitted_visits=sum(omit for _, omit in visits.values()),
                  signed_member_plan_sha256=digest(signed), ordinary_native_sha256=old_pin, sampled_native_sha256=new_pin,
                  same_owners_between_calibration_arms={mode: owners[ARMS[0]] == owners[ARMS[1]]
                                                        for mode, owners in (("ordinary", ordinary_owners), ("sampled", sampled_owners))},
                  sidecars=dict(ordinary=prior["sidecars"], sampled=after["sidecars"]))
    if inspect_cold:
        lost = set(ordinary_owners["c0"].values()) - set(sampled_owners["c0"].values())
        endpoint = prior_objective["c0"]["endpoint_east_north_km"]
        record["cold_finalist_audit"] = {mode: cold_forensics(witness, endpoint, lost)
                                         for mode, witness in (("ordinary", ordinary_witness), ("sampled", sampled_witness))}
    return record


def collect():
    development, challenge = map(source_bundle, BUNDLES)
    stage = STAGE / "leo-v3-cfo-epoch-0086-saved01"
    original = stage / "ordinary"
    seal = read(stage / "prediction-seal.json", OLD_0086)
    old = seal["products"]["ordinary"]
    receipt = read(stage / old["receipt_file"], old["receipt_sha256"])
    development_result = result(
        development, members_key="DS30-0086-members.json", native_key="DS30-0086-native.json", stage=stage,
        original=original, sampled_root=STAGE / "leo-v3-three-quarter-0086-saved02/candidate",
        ordinary_seal={"ordinary/exact-named-raw-witness.json": receipt["witness_sha256"]},
        sampled_seal=snapshot(development, "prediction-seal.json"), scope=snapshot(development, "admission.json"),
        scores=snapshot(development, "leo-v3-three-quarter-0086-score01.json")["saved_science"], sampled_label="three_quarter")
    ordinary_seal = snapshot(challenge, "ordinary/prediction-seal.json")
    proof = snapshot(challenge, "ordinary_proof")
    if not proof["exact_scientific_control"] or proof["saved_seal_sha256"] != digest(ordinary_seal):
        raise ValueError("Ordinary DS30-0220 publication lacks exact scientific parity to the field predecessor")
    challenge_result = result(
        challenge, members_key="members", native_key="projected_native", stage=STAGE / "leo-v3-three-quarter-0220-stage01",
        original=STAGE / "leo-v3-three-quarter-0220-ordinary01/candidate", ordinary_seal=ordinary_seal,
        sampled_root=STAGE / "leo-v3-three-quarter-0220-sampled01/candidate",
        sampled_seal=snapshot(challenge, "sampled/prediction-seal.json"), scope=snapshot(challenge, "sampled/admission.json"),
        scores=snapshot(challenge, "result")["arms"], sampled_label="sampled", inspect_cold=True)
    return dict(bundle_sha256=BUNDLES, ordinary_0086_prediction_seal_sha256=OLD_0086,
                cases={"DS30-0086": development_result, "DS30-0220": challenge_result})


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    write(cli.parse_args().output, collect())
