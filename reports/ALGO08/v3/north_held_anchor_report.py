"""Verify and seal the completed North raw pair before scoring the public site."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from aperture_trial import read, write
from dense_full_short_raw import checked
from north_held_anchor_pair import HERE, NORTH, ORDER, WINDOWS, admission, assignments, publication_evidence, require_resident
from north_interlaced_raw import TRUTH_SHA


STOCK_PACKET = "sha256:1e35f931202a67e122526aaf394192582f46989e3fd89cf9690cb84a4b9b5c17"


def compare_candidate(directory, receipt, evidence, assignment, archived):
    from leo.contracts.digests import canonical_digest

    route_file = directory.with_name(directory.name + "-held-anchor-route.json")
    route = read(route_file)
    bootstrap_file = directory / "unified-short-bootstrap.json"
    bootstrap = read(bootstrap_file)
    solve_file = directory / "joint-research-receipt.json"
    solve = read(solve_file)
    archived_route = archived["receipt"]
    for key in ("choice", "settings", "selector_sources", "history_sources", "adapter_sha256",
                "raw_recording_authority", "input_inventory", "session", "original_native_sha256",
                "original_recipe_sha256", "selected_native_sha256", "selected_recipe_sha256"):
        if route[key] != archived_route[key]:
            raise ValueError(f"The original-input held route differs from its archived control at {key}")
    native = evidence["native"]
    source = native["source"]
    effective = route["selected_recipe_sha256"]
    receiver = bootstrap["receiver_audit"]
    if (
        bootstrap["receipt"] != receipt or solve["receipt"] != receipt
        or bootstrap["requested_offer_sha256"] != assignment["region_sha256"]
        or bootstrap["archive_root"] != assignment["archive"]["root"]
        or bootstrap["causal_cutoff_utc_ns"] != evidence["cutoff_utc_ns"]
        or bootstrap["raw_acquisitions"] != 1 or bootstrap["verified_handoffs"] != 1
        or receiver["issued"] != WINDOWS or receiver["input_manifest"] != assignment["inventory"]
        or receiver["recording_authority"] != assignment["stock"]["raw_authority"]
        or ("sha256:" + receiver["detector_pin"]) != route["original_recipe_sha256"]
        or bootstrap["route"] != "optimized_installed_graph" or solve["input"] != "raw recording"
        or not solve["solve"] or solve["saved_handoff_manifest"] is not None
        or canonical_digest(solve["evidence"]["images"]) != canonical_digest(evidence["figures"])
        or bootstrap["held_anchor_route"] != route or not bootstrap["one_pass_web_png"]["enabled"]
        or bootstrap["native_sha256"] != route["selected_native_sha256"]
        or evidence["native_sha256"] != route["selected_native_sha256"]
        or bootstrap["detector_recipe_sha256"] != effective or native["provenance"]["detector_sha256"] != effective
        or canonical_digest(route["selected_recipe"]) != effective
        or source["analysis_manifest_sha256"] != canonical_digest([
            "cancellation", source["raw_recording_authority_digest"], effective.removeprefix("sha256:"), source["probes"],
        ])
        or sum(bool(row["candidates"]) for row in source["probes"]) != archived["factors"]
    ):
        raise ValueError("The active solve does not bind one original acquisition and the selected packet")
    (native_file,) = (directory / "fast-scan-automatic-work").glob("*/detections.json")
    if route_file.stat().st_mtime_ns > native_file.stat().st_mtime_ns:
        raise ValueError("Held route was sealed after starting the selected solve")
    return dict(
        sidecars={path.name: sha256(path.read_bytes()).hexdigest() for path in (route_file, bootstrap_file, solve_file)},
        selected_route=route["choice"], selected_native_sha256=route["selected_native_sha256"],
        original_native_sha256=route["original_native_sha256"], original_factors=receiver["selected"],
        selected_factors=archived["factors"], phases=bootstrap["phases"],
        acquisition=receiver["acquire"], native=receiver["native"], prefetch=bootstrap["prefetch"],
        raw_acquisitions=bootstrap["raw_acquisitions"], verified_handoffs=bootstrap["verified_handoffs"],
        selected_publications=1, solve_route=solve["route"], selected_roles=solve["selected_roles"],
        graph=bootstrap["exact_graph_reuse"], layout=bootstrap["one_pass_web_png"],
    )


def compare_stock(receipt, evidence, archived):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.paired_publication import V3_IDENTITY

    native = evidence["native"]
    detector = V3_IDENTITY["detector_sha256"]
    source = native["source"]
    if (
        evidence["native_sha256"] != STOCK_PACKET
        or receipt["terminal_sha256"] != archived["receipt"]["terminal_sha256"]
        or native["provenance"]["detector_sha256"] != "sha256:" + detector
        or source["analysis_manifest_sha256"] != canonical_digest([
            "cancellation", source["raw_recording_authority_digest"], detector, source["probes"],
        ])
        or any(evidence["verified"][field] != archived[field]
               for field in ("arms", "owners", "scientific_digests", "artifacts"))
    ):
        raise ValueError("The named v3 replay does not match its original signed publication")


def seal(directory):
    binding_path = directory / "binding.json"
    binding = read(binding_path)
    assignment = binding["assignment"]
    pair, _ = assignments()
    controls = admission()
    if binding["controls"] != controls:
        raise ValueError("Archived parity bound at launch differs")
    results = {}
    for arm in ORDER:
        output = directory / arm
        clock = read(directory / f"{arm}-clock.json")
        cache = read(directory / f"{arm}-cache.json")
        require_resident(cache)
        if clock["exit_code"]:
            raise ValueError(f"The sealed {arm} launch failed")
        stdout = output.with_suffix(".stdout")
        receipt = json.loads(stdout.read_text().splitlines()[-1])
        fresh = publication_evidence(output, receipt, clock, assignment)
        if arm == "stock":
            compare_stock(receipt, fresh, pair["runs"]["candidate"])
            details = None
        else:
            details = compare_candidate(output, receipt, fresh, assignment, controls["north"])
        del fresh["native"]
        if not fresh["detector_ready_s"] <= fresh["verified"]["terminal_file_s"] <= clock["elapsed_s"]:
            raise ValueError("Timed publication order changed")
        results[arm] = dict(clock=clock, cache=cache, details=details, **fresh)
        results[arm]["effective_mb_s"] = assignment["compressed_bytes"] / (1e6 * fresh["detector_ready_s"])
    stock, candidate = (results[arm] for arm in ORDER)
    if any(stock[field] != candidate[field] for field in ("opportunity_sha256", "cutoff_utc_ns")):
        raise ValueError("Matched raw support or causal cutoff differs between treatments")
    if any(stock["figures"][name]["size"] != image["size"] for name, image in candidate["figures"].items()):
        raise ValueError("The selected route altered native PNG dimensions")
    write(directory / "sealed.json", dict(binding_sha256=sha256(binding_path.read_bytes()).hexdigest(),
                                            report_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                                            results=results))


def score(directory):
    from tools.pipeline_eval.scoring import distance_km

    sealed_path = directory / "sealed.json"
    sealed = read(sealed_path)
    key = read(checked(HERE.parent / "regional-release/scoring-key.json", TRUTH_SHA))
    (truth,) = {tuple(row["truth"]) for row in key["answers"].values() if row["recording"] == NORTH}
    outcomes = {
        arm: {name: dict(error_km=distance_km(truth, tuple(values["latlon"])), rf_rms_hz=values["rf_rms_hz"],
                         position=values["latlon"])
              for name, values in data["verified"]["arms"].items()}
        for arm, data in sealed["results"].items()
    }
    write(directory / "score.json", dict(recording=NORTH, assessment="previously scored public simulation",
                                          sealed_sha256=sha256(sealed_path.read_bytes()).hexdigest(),
                                          scoring_key_sha256=TRUTH_SHA, outcomes=outcomes))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--score", action="store_true")
    args = parser.parse_args()
    (score if args.score else seal)(args.directory)
