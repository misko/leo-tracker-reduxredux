"""Verify the two sealed dense saved publications and score their prefix impact."""

import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from prefix_transfer_0008 import ARMS, ORDER, PROTOCOL, ROOT, checked, digest, inputs, lane_rows, observation_id, overlap, read, verified_owner_rows, write


OWNER_PIN = "9ab0632563cc2ceacd043569956ef7fa1dfb9e24f26de370df57b8a19681221f"
REFERENCE_PIN = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"


def tracked(spec, pin):
    command = ["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), "show", spec]
    body = subprocess.check_output(command)
    if sha256(body).hexdigest() != pin:
        raise ValueError("The archived owner or survey witness changed")
    return body


def measured_delta(before, after, subset):
    before, after = ({i: entry for i, entry in view.items() if i in subset} for view in (before, after))
    common = before.keys() & after.keys()
    return dict(before=len(before), after=len(after), shared=len(common), removed=len(before.keys()-after.keys()),
                added=len(after.keys()-before.keys()), changed_norad=sum(before[k][0] != after[k][0] for k in common),
                changed_role=sum(before[k][1] != after[k][1] for k in common),
                changed_ids=sorted((before.keys() ^ after.keys()) | {k for k in common if before[k] != after[k]}))


def positions(arms, siting):
    from tools.pipeline_eval.scoring import distance_km

    return {arm: (dict(horizontal_error_m=1000*distance_km(siting, data["latlon"]),
                       rf_rms_hz=data["rf_rms_hz"], latlon=data["latlon"]) if data["latlon"] else None)
            for arm, data in arms.items()}


def route_evidence(path):
    route, = read(path/"risk-route.json")["solves"]
    summary = route["choice"]
    return dict(route=summary["route"], reason=summary["reason"], infer_calls=route["inference_calls"],
                nomination=route.get("nomination_handoff", {}), exterior=route["exterior_handoff"],
                lean_attempts=[dict(decision=row["decision"], exterior=row.get("exterior"),
                                    named_survivor=row.get("named_survivor_fit", {}).get("status"))
                               for row in route["lean_attempts"]],
                orbit_recovery=read(path/"live-corner.json"), render=read(path/"render-usage.json"))


def score(root):
    from clean_saved_0169_trial import output_seal
    from held_adaptive_0160_score import verified
    from leo.contracts.digests import canonical_digest

    seal = root/"prediction-seal.json"
    admission = read(root/"admission.json")
    if read(seal) != output_seal(root) or admission["protocol"] != digest(PROTOCOL):
        raise ValueError("The saved pair must be sealed before joining positions")
    bundle = json.loads(checked(Path(admission["bundle"]), admission["bundle_sha256"]))
    req, _, packets, recipe, sources, _, _, historical = inputs(bundle)
    if admission["source_pins"] != sources or admission["recipe"] != recipe:
        raise ValueError("The original solver or measured splice changed")
    rosters, observations, trials = {}, {}, {}
    for mode in ORDER:
        folder = root/mode
        target = folder/"routed"
        packet = packets[mode]
        request = read(folder/"request.json")
        fields = req.keys() - {"native_file", "native_sha256"}
        if (any(request[k] != req[k] for k in fields) or request["native_sha256"] != canonical_digest(packet)[7:]
                or packet["provenance"]["detector_sha256"] != admission["receiver"][mode]):
            raise ValueError("A timed child has the wrong measurement packet or scientific context")
        timing = read(folder/"clock.json")
        if timing["exit_code"]:
            raise ValueError("Both paid workers must finish before scoring")
        run = verified(target/"candidate", timing, "worker.json", request)
        other = run["worker"]["receipt"]
        complete = other["decision"] == "complete"
        if (other["window_count"] != req["issued"] or other["counts"]["processed"] != req["admitted"]
                or other["region"] != read(Path(req["offer_file"])) or set(run["terminal"]["arms"]) != set(ARMS)
                or run["worker"]["detector"] != admission["receiver"][mode][7:]
                or (complete and (len(run["products"]["images"]) != 8 or not run["sample"]["complete"]
                    or not run["path"]["stages"] or set(run["rows"]) != set(ARMS)))
                or (not complete and (other["decision"] != "withheld" or run["products"]["images"]
                    or any(data["latlon"] is not None for data in run["terminal"]["arms"].values())))):
            raise ValueError("Found an incomplete or contradictory saved result")
        rows, _ = lane_rows(packet, req["issued"])
        observations[mode] = {observation_id(req["session"], row): row for row in rows.values()}
        allowed = {i for i, row in observations[mode].items() if row["candidates"]}
        rosters[mode] = verified_owner_rows(run["rows"], run["science"]["owners"], allowed, canonical_digest) if complete else {arm:{} for arm in ARMS}
        panel = run["terminal"]
        trials[mode] = dict(clock=timing, publication_elapsed_s=run["trace"]["publication_elapsed_s"],
                            publication_cpu_s=run["trace"]["publication_cpu_s"], solve=run["trace"]["solve"],
                            terminal=panel, region=other["region"], decision=other["decision"], figures=run["products"]["images"],
                            digests=run["science"]["scientific_digests"], selected_roles=run["trace"]["selected_roles"],
                            ordered_owner_sha256={arm: canonical_digest(run["rows"].get(arm, [])) for arm in ARMS},
                            grid_points=run["sample"]["evaluated_points"] if complete else None, route=route_evidence(target))
    named = historical["runs"]["candidate"]
    historical_stock = json.loads(gzip.decompress(tracked("HEAD:reports/ALGO08/v3/measurements/track-quadrature.json.gz", OWNER_PIN)))
    published = historical_stock["runs"]["DS30-0008"]["stock"]
    if (published["identity"]["native_sha256"] != canonical_digest(packets[ORDER[0]])
            or published["owners"] != named["owners"] or published["arms"] != named["arms"]):
        raise ValueError("The installed archived owner witness has different science")
    old = verified_owner_rows(published["selected_rows"], named["owners"],
                              {i for i,row in observations[ORDER[0]].items() if row["candidates"]}, canonical_digest)
    stock, mixed = (bundle["native"][mode] for mode in ("named", "first_use"))
    audit, _ = overlap(packets[ORDER[0]], stock, mixed, bundle["witness"],
                       dict(installed=old, routed=rosters[ORDER[0]]))
    all_ids = observations[ORDER[0]].keys()
    prefix_ids = {i for i, row in observations[ORDER[0]].items() if row["visit_index"] < 64}
    deltas = {arm: {scope: measured_delta(rosters[ORDER[0]][arm], rosters[ORDER[1]][arm], ids)
                   for scope, ids in (("prefix", prefix_ids), ("suffix", all_ids-prefix_ids), ("full", all_ids))}
              for arm in ARMS}
    for arm, scopes in deltas.items():
        for scope in scopes.values():
            scope["switched_lanes"] = [{k: observations[ORDER[0]][i][k] for k in ("visit_index", "receiver_id", "channel")} |
                                        dict(id=i, before=rosters[ORDER[0]][arm].get(i), after=rosters[ORDER[1]][arm].get(i))
                                        for i in scope.pop("changed_ids")]
    truth_body = tracked("2d0ad2dfd:reports/2026_11_21_ds30_full/reference-audit.json", REFERENCE_PIN)
    truth, = (row["reference"] for row in json.loads(truth_body)["cases"] if row["dataset_label"] == "DS30-0008"
              and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    siting = [truth["latitude_deg"], truth["longitude_deg"]]
    geography = {mode: positions(trials[mode]["terminal"]["arms"], siting) for mode in ORDER}
    geography["archived-installed-v3"] = positions(named["arms"], siting)
    write(root/"result.json", dict(scope="saved first-member development intervention", admission=admission,
          prediction_sha256=digest(seal), reference_sha256=REFERENCE_PIN, parent_owner_sha256=OWNER_PIN,
          trials=trials, prefix=audit, switched_rosters=deltas, geography=geography, waveform_reads=0))
