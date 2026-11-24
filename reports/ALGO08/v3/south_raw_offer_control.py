"""Compare original South samples under two operator offers with one receiver."""

import gzip
from hashlib import sha256
import json
from pathlib import Path

from combined_raw_south import HERE, SOUTH, SOUTH_RESULT


CONTROL = HERE / "measurements/combined-raw-south.json.gz"
CONTROL_SHA = "ce1d12d43bc2769fbfc53aa66c810d0a71237ffc4d4950a78e1d2210f1fd5911"
PROTOCOL = HERE / "south-raw-offer-protocol.md"
MODE = "near-omitted"


def containing():
    data = gzip.decompress(CONTROL.read_bytes())
    if sha256(data).hexdigest() != CONTROL_SHA:
        raise ValueError("Containing result digest changed")
    return json.loads(data)


def offer_only(control, command, inside, outside):
    expected = list(control)
    for flag in ("--region", "--output"):
        if control.count(flag) != 1 or command.count(flag) != 1:
            raise ValueError("Expected one operator offer and one output")
        i = control.index(flag) + 1
        if flag == "--region" and (control[i] != inside or command[i] != outside or inside == outside):
            raise ValueError("Expected the original signed containing and omitted offers")
        if flag == "--output" and control[i] == command[i]:
            raise ValueError("A paired run requires a fresh output")
        expected[i] = command[i]
    if command != expected:
        raise ValueError("The executing pipeline differs between offers")


def preflight(binding):
    base = containing()
    offers = binding["request"]["offers"]
    offer_only(base["binding"]["command"], binding["command"], offers["containing"], offers[MODE])
    if base["binding"]["request"] != binding["request"] or base["binding"]["producer"] != binding["producer"]:
        raise ValueError("Input inventory, offer pair or causal producer changed")
    return dict(result_sha256=CONTROL_SHA, protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest())


def score_omitted(root, output=None):
    from aperture_trial import read, write
    from empty_bootstrap import bind_native, checked
    from joint_publication import artifacts
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from raw_cfo_north_trial import native_file
    from south_cfo_route import admissible
    from tools.pipeline_eval.qualification.paired_publication import evidence
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    binding, clock = read(root / "binding.json"), read(root / "clock.json")
    if preflight(binding) != binding["paired_control"] or clock["exit_code"]:
        raise ValueError("Original-input pair or process exit failed")
    caches = {key: read(root / f"cache-{key}.json") for key in ("before", "after")}
    if not all(admissible(cache) for cache in caches.values()):
        raise ValueError("Original input residency changed")
    base, folder = containing(), root / MODE
    request = binding["request"]
    raw = read(folder / "unified-short-bootstrap.json")
    research = read(folder / "joint-research-receipt.json")
    receipt = raw["receipt"]
    packet = json.loads(checked(native_file(folder), raw["native_sha256"][7:]))
    bind_native(packet, request["session"], request["inventory"], raw["detector_recipe_sha256"][7:],
                expected=raw["native_sha256"])
    offer = Algo08Region.parse(json.loads(checked(Path(request["offers"][MODE]), request["offer_sha256"][MODE]))).document()
    if (raw["raw_acquisitions"] != 1 or raw["verified_handoffs"] != 1 or raw["causal_cutoff_utc_ns"] != request["cutoff_utc_ns"]
            or packet["source"]["raw_recording_authority_digest"] != request["authority"] or receipt != research["receipt"]
            or receipt["region"] != offer or receipt["window_count"] != request["issued"]):
        raise ValueError("Acquisition, handoff or published search region failed verification")
    probes = canonical_digest(packet["source"]["probes"])
    one = evidence(folder, receipt, clock["started_unix_ns"], read_only=True)
    media = artifacts(folder, receipt)
    store = FastStandardAnalysisStore(folder)
    grid = store.position_grid(receipt["run_id"])
    path = store.position_path(receipt["run_id"])
    if receipt["decision"] == "complete":
        png = media["images"]["position"]["sha256"]
        if (not grid["complete"] or not grid["matched_c_grid"] or grid["evaluated_points"] != grid["planned_points"]
                or any(doc["binding"]["position_png_sha256"] != png for doc in (grid, path))):
            raise ValueError("Incomplete matched calibration grids or position PNG binding")
    elif grid is not None or path is not None:
        raise ValueError("Withheld product has unexpected position sidecars")
    historical = json.loads(checked(SOUTH / "result.json", SOUTH_RESULT))
    previous = historical["cases"][MODE]
    clearance = face_clearance_km(offer, historical["truth"])
    if previous["receipt"]["region"] != offer or clearance != previous["truth_face_km"] or clearance >= 0:
        raise ValueError("Historical truth must be outside the authenticated operator offer")
    arms = {name: dict(row, error_km=distance_km(historical["truth"], row["latlon"]) if row["latlon"] else None,
                       shift_km=distance_km(base["current"]["arms"][name]["latlon"], row["latlon"]) if row["latlon"] else None,
                       face_km=face_clearance_km(offer, row["latlon"]) if row["latlon"] else None)
            for name, row in one["arms"].items()}
    write(output or root / "result.json", dict(binding=binding, clock=clock, caches=caches, decision=receipt["decision"],
          reason=one.get("reason"), receipt=receipt, authority=request["authority"], detector=raw["detector_recipe_sha256"],
          probes=probes, same_probes=probes == base["current"]["probes"], native_sha256=raw["native_sha256"],
          same_detector=raw["detector_recipe_sha256"] == base["acquisition_selection"]["selected_recipe_sha256"],
          owners=one["owners"], same_owners=one["owners"] == base["current"]["owners"], arms=arms,
          inside=base["current"]["arms"], inside_error_km=base["error_km"], inside_clock=base["clock"],
          truth_face_km=previous["truth_face_km"], historical_named=previous["named"], historical_all_paid=previous["arms"],
          historical_status=previous["status"], historical_named_status=previous["named_status"],
          phases=raw["phases"], early=research["early_regional"], route=research["route_details"], media=media,
          grid_points=grid["evaluated_points"] if grid else None, verified_png_reads=raw.get("verified_png_reads"),
          orbit=read(root / "orbits-indexed.json") if (root / "orbits-indexed.json").exists() else None,
          rank=read(root / "catalogue-block-rank.json") if (root / "catalogue-block-rank.json").exists() else None))
