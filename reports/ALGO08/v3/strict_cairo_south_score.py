"""Verify the sealed South strict replay and compare its complete products and clocks."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from reports.ALGO08.v3.strict_cairo_south import HERE, PRIOR, archived, read_json, seal


ARMS = ("c0", "fitted_c")
OMITTED_PIN = "2e0f9c3bb1a2cbe837dd4ebc139667c8869ab2d3d45173075f498e6a6901bf07"
NAMED_ROWS_PIN = "25a311334c51296e81176c23fe7609b78b1262c7a600da2e5a2a6eed0d029195"


def opportunities(native):
    return [{key: value for key, value in probe.items() if key != "candidates"} for probe in native["source"]["probes"]]


def prices(named, child, ready, common, conversion, historical_wall):
    metrics = (("elapsed_s", "wall_ns"), ("cpu_s", "cpu_ns"))
    out = {}
    for metric, field in metrics:
        paid = conversion[field]/1e9
        prepared = child[metric]+ready[metric]
        first = prepared+paid
        full = prepared+common[metric]
        out[metric] = dict(named=named[metric], replay=child[metric], ready=ready[metric], conversion=paid,
                           prepared=prepared, first_use=first, common=common[metric], prepared_plus_common=full,
                           first_use_plus_common=full+paid, prepared_speedup=named[metric]/prepared,
                           first_use_speedup=named[metric]/first, prepared_common_speedup=named[metric]/full)
    out["elapsed_s"]["historical_named"] = historical_wall
    out["elapsed_s"]["historical_prepared_speedup"] = historical_wall/out["elapsed_s"]["prepared"]
    return out


def score(root):
    from aperture_trial import write
    from eight_ms_held_score import owner_differences
    from eight_ms_south_transfer import KEY_SHA, NAMED_RECEIPT, NAMED_RECEIPT_SHA
    from empty_bootstrap import bind_native, checked
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from north_held_anchor_pair import publication_evidence
    from raw_0016_best_score import position_sides
    from reports.ALGO08.v3.history_risk_0016_cairo import active_renderer
    from south_strict_transfer import figures, named_reference, omission_join
    from strict_history_raw_trial import packed_integrity
    from tools.pipeline_eval.qualification import paired_publication as pair
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    prediction = root/"prediction-seal.json"
    if read_json(prediction) != seal(root):
        raise ValueError("South candidate changed after the clocked prediction")
    admission, measured = (read_json(root/name) for name in ("admission.json", "candidate-clock.json"))
    prior, conversion = (archived(name) for name in ("result.json", "conversion.json"))
    request, stock_clock = admission["request"], archived("named/clock.json")
    clocks = prices(stock_clock, measured, admission["candidate_ready"], admission["common_setup"],
                    conversion["total_including_compiler_and_verification"], prior["historical_named_clock_s"])
    if measured["exit_code"]:
        raise ValueError(f"The only enrolled child exited {measured['exit_code']}: {measured['stderr_tail']}")

    older_root, older_named, region = named_reference(request)
    named_out = PRIOR/"named/stock"
    named_receipt = archived("named/stock.stdout")
    pair.verify_v3_publication(named_out, named_receipt)
    assignment = dict(session=request["session"], inventory=request["inventory"], offered_region=region, stock=older_named)
    named = publication_evidence(named_out, named_receipt, stock_clock, assignment)
    historical = artifacts(older_root/"candidate", older_named["receipt"])
    if (named["native_sha256"] != request["packets"]["named"]["native_sha256"] or named["grid_points"] != 137
            or named["cutoff_utc_ns"] != request["cutoff_utc_ns"] or figures(named["figures"]) != figures(historical["images"])
            or any(named["verified"][key] != older_named[key] for key in ("arms", "owners", "scientific_digests"))):
        raise ValueError("The fresh installed v3 control differs from the historical named control")
    named_roles = json.loads(checked(NAMED_RECEIPT/"result.json", NAMED_RECEIPT_SHA))["cases"]["containing"]
    old_trace = json.loads(checked(NAMED_RECEIPT/"containing/joint-research-receipt.json", NAMED_ROWS_PIN))
    named_rows = old_trace["selected_rows"]
    if (old_trace["receipt"]["region"] != region or any(
            canonical_digest({uid: sat for uid, sat, _ in named_rows[arm]}) != named["verified"]["owners"][arm]
            or canonical_digest(named_rows[arm]) != named_roles["ordered_owner_sha256"][arm] for arm in ARMS)):
        raise ValueError("The archived ordered named rows do not match the official owner-map digests")
    named_sides = position_sides(FastStandardAnalysisStore(named_out), named_receipt, dict(images=named["figures"]), 137)

    out = root/"candidate"
    raw, witness = (read_json(out/name) for name in ("unified-short-bootstrap.json", "exact-named-raw-witness.json"))
    native = read_json(native_packet(out))
    bind_native(native, request["session"], request["inventory"], raw["detector_recipe_sha256"][7:],
                expected=prior["candidate"]["native_sha256"])
    source = native["source"]
    receipt, recipe, ports = raw["receipt"], witness["solver_recipe"], witness["ports"]
    candidate = pair.evidence(out, receipt, measured["started_unix_ns"], read_only=True)
    packed = packed_integrity(raw["packed_ci16_input"], conversion)
    check_counts = all(receipt[key] == named_receipt[key] for key in ("counts", "window_count", "session_id", "decision", "region"))
    if (not check_counts or receipt["decision"] != "complete" or candidate["raw_authority"] != request["authority"]
            or source["raw_recording_authority_digest"] != request["authority"]
            or opportunities(native) != opportunities(named["native"]) or len(source["probes"]) != 2*request["issued"]
            or raw["clock_anchor"] != named["native"]["clock_anchor"] or raw["causal_cutoff_utc_ns"] != request["cutoff_utc_ns"]
            or raw["archive_root"] != request["archive"]["root"] or recipe["archive_sha256"] != request["archive"]["snapshots_sha256"]
            or raw["requested_offer_sha256"] != request["offer_sha256"]["containing"] or raw["raw_acquisitions"] != 1
            or raw["verified_handoffs"] != 1 or raw["scientific_imports_before"] or raw["stock_launcher_sha256"] != pair.V3_LAUNCHER_SHA
            or raw["frozen_specification"] != pair.V3_IDENTITY["frozen_specification"]
            or raw["native_sha256"] != prior["candidate"]["native_sha256"]
            or raw["route"] != witness["raw_route"] or raw["route"] != "history_risk_installed"
            or not recipe["history_risk"]["requested"] or recipe["orbit_index"] != "cold" or not active_renderer(ports)
            or packed["apertures"] != raw["receiver_audit"]["native"]["visits"]
            or read_json(root/"packed-after.json")["cached_pages"] != admission["packed_before"]["cached_pages"]):
        raise ValueError("The fresh result must match original South support and use the actual strict history and Cairo route")

    media = artifacts(out, receipt)
    store = FastStandardAnalysisStore(out)
    sidecars = position_sides(store, receipt, media, 137)
    inner = witness["evidence"]
    owners = inner["owner_rows"]
    if (inner["grid"] != sidecars["grid_points"] or inner["detail"]["terminal_sha256"] != receipt["terminal_sha256"]
            or figures(media["images"]) != figures(inner["images"])
            or any(media[name] != inner["sidecars"][name] for name in ("path", "grid"))
            or any(canonical_digest({uid: sat for uid, sat, _ in owners[arm]}) != candidate["owners"][arm] for arm in ARMS)):
        raise ValueError("Independent reopened products differ from the clocked published evidence")

    key = json.loads(checked(HERE.parent/"regional-release/scoring-key.json", KEY_SHA))
    truth, = {tuple(row["truth"]) for row in key["answers"].values() if row["recording"] == Path(request["recording"]).name}
    clearance = face_clearance_km(region, truth)
    if clearance <= 0:
        raise ValueError("The authorized containing offer does not contain the held reference")
    geographic = {label: {arm: dict(point, horizontal_error_km=distance_km(truth, point["latlon"]))
                          for arm, point in publication["arms"].items()}
                  for label, publication in (("named", named["verified"]), ("candidate", candidate))}
    omission = omission_join(request, dict(native_sha256=raw["native_sha256"], receiver_recipe_sha256=raw["detector_recipe_sha256"]))
    exact_omission = json.loads(gzip.decompress(checked(HERE/"measurements/exact-named-south-omitted.json.gz", OMITTED_PIN)))
    omission_terminal = exact_omission["terminal"]["value"]
    omission_score = exact_omission["documents"]["result.json"]["value"]
    if (omission_terminal["native_sha256"] != raw["native_sha256"] or omission_terminal["region"] != omission["offer"]
            or omission_terminal["decision"] != "ok" or omission["scoring"]["geography"] != "false_fix"
            or any(omission_score[field] != "false_fix" for field in ("candidate_status", "named_status"))):
        raise ValueError("Prior omitted-route evidence must bind the same signed detector and false fix")
    reference = prior["candidate"]
    prior_overlap = dict(armlocations_and_rf=geographic["candidate"] == prior["both_arms"]["candidate"],
                         ordered_owners=canonical_digest(owners) == reference["owners_sha256"],
                         native=raw["native_sha256"] == reference["native_sha256"], previous_layout=reference["layout"],
                         wall=reference["clock"]["elapsed_s"])
    named_native = named.pop("native")
    comparison = {name: dict(bytes_equal=media["images"][name]["sha256"] == stock["sha256"],
                             pixels_equal=media["images"][name]["rgba_sha256"] == stock["rgba_sha256"],
                             dimensions_equal=tuple(media["images"][name]["size"]) == tuple(stock["size"]))
                  for name, stock in named["figures"].items()}
    write(root/"result.json", dict(qualified=True, simulation_only=True, no_new_named=True, no_new_omitted=True,
          prediction_seal_sha256=sha256(prediction.read_bytes()).hexdigest(), admission=admission,
          clocks=clocks, measured_candidate=measured, measured_named=stock_clock,
          containing=dict(geographic=geographic, truth_clearance_km=clearance, truth_source_sha256=KEY_SHA),
          packed=packed, conversion_phases={name: conversion[name] for name in ("counts", "compiler", "independent_check", "total_including_compiler_and_verification")},
          factors={label: sum(len(row["candidates"]) for row in packet["source"]["probes"]) for label, packet in
                   (("candidate", native), ("named", named_native))},
          media_comparison=comparison,
          ordered_owner_rows=dict(candidate=owners, named=named_rows),
          owner_changes={arm: owner_differences(named_rows[arm], owners[arm]) for arm in ARMS},
          named=dict(named, sidecars=named_sides),
          candidate=dict(science=candidate, media=media, sidecars=sidecars, recipe=recipe, ports=ports,
                         selector=raw["held_anchor_route"]["choice"], phases=raw["phases"], native=raw["native_sha256"],
                         native_recipe=raw["receiver_recipe"], solver_timing=witness["timing"], source_sha256=witness["source_sha256"]),
          prior_strict_adaptive=prior_overlap,
          previous_omission=dict(packet=omission["native_sha256"], score_sha256=OMITTED_PIN, result=omission["scoring"],
                                 exact_named_control={name: omission_score[name] for name in ("candidate_status", "named_status",
                                     "candidate_geometry", "measured", "truth_face_inward_km")}, replayed=False)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    score(parser.parse_args().root)
