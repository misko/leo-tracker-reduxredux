"""Verify the one measured-prefix publication and join its after-seal positions."""

import json
from pathlib import Path
import subprocess

from prefix_transfer_0008_score import measured_delta, positions
from verified_window_transfer_0163 import ARMS, BASE, CASE, PROTOCOL, ROOT, controls, digest, lane_rows, observation_id, parse, read, verified_owner_rows, write


def score(root, *, destination=None):
    from clean_saved_0169_trial import output_seal
    from held_adaptive_0160_score import verified
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from unseen_saved_holdout_score import REFERENCE_PIN

    seal = root/"prediction-seal.json"
    destination = destination or root/"result.json"
    admission = read(root/"admission.json")
    if read(seal) != output_seal(root) or admission["protocol"] != digest(PROTOCOL):
        raise ValueError("The one-shot trial has not sealed its publication")
    overlap = parse(root/"verified-prefix-overlap.json", admission["producer_scope_sha256"])
    docs, _, _, lanes, _, original, _ = controls()
    source = docs["result.json"]
    clock = read(root/"routed/clock.json")
    if clock["exit_code"]:
        write(destination, dict(admission=admission, clock=clock, overlap=overlap, decision="failed", full_solves=0))
        return
    req = read(root/"request.json")
    baseline = docs["request.json"]
    compared = baseline.keys()-{"native_file", "native_sha256"}
    if (any(req[k] != baseline[k] for k in compared) or admission["sources"] != docs["admission.json"]["sources"]
            or req["native_sha256"] != overlap["native_sha256"][7:] or not overlap["exact_installed_parity"]):
        raise ValueError("Worker scope differs from the exact original combined settings")
    packet = parse(Path(req["native_file"]), req["native_sha256"])
    if packet["provenance"]["detector_sha256"] != admission["detector"]:
        raise ValueError("The experimental native recipe changed")
    before = {observation_id(req["session"], row): row for row in lanes.values()}
    replacement, _ = lane_rows(packet, req["issued"])
    after = {observation_id(req["session"], row): row for row in replacement.values()}
    if before.keys() != after.keys() or any(r != after[i] for i, r in before.items() if r["visit_index"] >= overlap["issued"]):
        raise ValueError("The supposedly untouched original detector suffix changed")
    result = verified(root/"routed/candidate", clock, "worker.json", req)
    receipt, terminal = result["worker"]["receipt"], result["terminal"]
    complete = receipt["decision"] == "complete"
    if (receipt["window_count"] != req["issued"] or receipt["counts"]["processed"] != req["admitted"]
            or receipt["region"] != read(Path(req["offer_file"])) or set(terminal["arms"]) != set(ARMS)
            or result["worker"]["detector"] != admission["detector"][7:]
            or (complete and (len(result["products"]["images"]) != 8 or not result["sample"]["complete"]
                or not result["sample"]["matched_c_grid"] or result["sample"]["evaluated_points"] != 179
                or not result["path"]["stages"]))
            or (not complete and (receipt["decision"] != "withheld" or result["products"]["images"]
                or any(arm["latlon"] is not None for arm in terminal["arms"].values())))):
        raise ValueError("Incomplete full grid, terminal or signed two-arm publication")
    rosters = (verified_owner_rows(result["rows"], result["science"]["owners"],
               {i for i, row in after.items() if row["candidates"]}, canonical_digest) if complete else {k:{} for k in ARMS})
    prefix = {i for i, row in before.items() if row["visit_index"] < overlap["issued"]}
    owner_delta = {arm: {
        k: measured_delta(original["routed"][arm], rosters[arm], ids) for k,ids in
        (("prefix", prefix), ("suffix", before.keys()-prefix), ("full", before.keys()))} for arm in ARMS}
    for arm in ARMS:
        for name in owner_delta[arm]:
            change = owner_delta[arm][name]
            change["changed_lanes"] = [dict(visit=before[i]["visit_index"], receiver=before[i]["receiver_id"],
                channel=before[i]["channel"], obs_id=i, old=original["routed"][arm].get(i), new=rosters[arm].get(i))
                for i in change.pop("changed_ids")]
    truth = subprocess.check_output(["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), "show",
                                     "2d0ad2dfd:reports/2026_11_21_ds30_full/reference-audit.json"])
    from hashlib import sha256

    if sha256(truth).hexdigest() != REFERENCE_PIN:
        raise ValueError("The original authority-defined position reference changed")
    site, = (row["reference"] for row in json.loads(truth)["cases"] if row["dataset_label"] == CASE
             and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    position = [site["latitude_deg"], site["longitude_deg"]]
    descriptions = {"hybrid": positions(terminal["arms"], position)}
    for key in ("installed", "routed"):
        descriptions[key] = positions(source["jobs"][key]["publication"]["terminal"]["arms"], position)
    all_owned = {}
    for mode, location, model in (("installed", BASE/"installed/candidate", source["jobs"]["installed"]["publication"]["science"]["receipt"]),
        ("routed", BASE/"routed/candidate", source["jobs"]["routed"]["publication"]["science"]["receipt"]),
        ("hybrid", root/"routed/candidate", receipt)):
        record = FastStandardAnalysisStore(location).detail(model["run_id"])
        all_owned[mode] = {arm: record["arms"].get(arm, {}).get("residual_rms_hz") for arm in ARMS}
    prior_pub = source["jobs"]["routed"]["publication"]
    route, = read(root/"routed/risk-route.json")["solves"]
    image_digest = result["products"]["images"]
    relative_owner_order = {
        arm: [row for row in result["rows"].get(arm, []) if row[0] in original["routed"][arm]]
        == [row for row in prior_pub["selected_rows"][arm] if row[0] in rosters[arm]] for arm in ARMS
    }
    report = dict(admission=admission, prediction_sha256=digest(seal), clock=clock,
          prior_clock=source["jobs"]["routed"]["clock"], overlap=overlap, decision=receipt["decision"],
          terminal=terminal, geography=descriptions, all_owned_rf_rms_hz=all_owned, owner_delta=owner_delta,
          common_owner_order_and_values_match=relative_owner_order,
          digests=result["science"]["scientific_digests"], previous_digests=prior_pub["science"]["scientific_digests"],
          worker=result["worker"], prior_worker=prior_pub["worker"], scientific_pins=admission["sources"],
          images=image_digest, matching_images={name: canonical_digest(prior_pub["figures"][name]) == canonical_digest(value)
                                                for name,value in image_digest.items()},
          same_image_dimensions={name: tuple(prior_pub["figures"][name]["size"]) == tuple(value["size"])
                                 for name,value in image_digest.items()},
          grid=read(root/"routed/combined-grid.json"), prior_grid=read(BASE/"routed/combined-grid.json"),
          route=dict(choice=route["choice"], nomination=route.get("nomination_handoff"),
                     attempts=[{k:item.get(k) for k in ("decision", "named_survivor_fit", "exterior")} for item in route["lean_attempts"]]),
          scope="measured pre-held sensitivity on original continuation suffix", new_waveforms=0, full_solves=1,
          reference_sha256=REFERENCE_PIN)
    write(destination, report)
