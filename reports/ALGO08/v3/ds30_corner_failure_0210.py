"""Compare the first two sealed DS30 installed corner failures and candidate fixes."""

import argparse
from hashlib import sha256
import json
from math import fsum, isclose, isfinite
import os
from pathlib import Path
import re
from statistics import median
import sys

from ds30_0397_orbit_support_audit import (
    ARMS, BUILD, LIVE, OLD_CORNER, OUTSIDE, PAIR, PAYLOAD, PROJECTOR, REFERENCE, REPAIRED_CORNER,
    REQUEST, SPARSE, TRACE, VARIANTS, WITNESS, checked, denied, digest, document, encoded, git_blob,
    left_extension,
)


CAMPAIGN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
PINS = {
    "DS30-0210": dict(pair="7796938b0cd47a04ed183f3fc56f6a5075929f20c851272f904c6a75a295acdd",
                      request="b1b039ec56a0e5118cf200f232f0f78db2eb6558d98d014699524b8394fa98c0",
                      acquisition="c8edf7d4b91b24891e1c9eacf9b7fe761183301c7223df74ad5d5e298bfb478b",
                      witness="b635fb2a525c49aaffdee178289b6d189764bdce85d4f443acea022df8926c7f",
                      bootstrap="92c57a607eff6117f32552854b9dea5e34f2ef4959d1e0998fcc2babde7ba1b5"),
    "DS30-0397": dict(pair=PAIR, request=REQUEST, acquisition=LIVE, witness=WITNESS,
                      bootstrap="91a790fa0532194e22acf6087a67820cafc5cee4237d937c901ab17ce255b4ce"),
}
FRAMES = re.compile(r'^  File "[^"\n]+/([^/"\n]+)", line (\d+), in ([^\n]+)$', re.M)
CHAIN = (("v5_core.py", "40", "ranked_initial_nodes"),
         ("discovery.py", "313", "explore"), ("scan.py", "216", "association"),
         ("scan.py", "207", "predictions"), ("algo08_sparse_rank_projection.py", "69", "shifted"),
         ("orbit_projector.py", "66", "prepare"))
NORMAL_SCOPE = "raw_launcher_through_exit_plus_common_publication_verification"


def corner_trace(trace):
    """Require the original strict projector rejection and the failed class-patch retry."""
    pieces = trace.strip().split("During handling of the above exception, another exception occurred:")
    if len(pieces) != 2:
        raise ValueError("Expected exactly the initial and retry exceptions")
    paths = []
    for block in pieces:
        frames = FRAMES.findall(block)
        rank = frames.index(CHAIN[0]) if CHAIN[0] in frames else len(frames)
        observed = [f for f in frames[rank:] if f in CHAIN]
        if tuple(observed) != CHAIN or frames[-1] != CHAIN[-1] or not block.rstrip().endswith("ValueError: " + OUTSIDE):
            raise ValueError("The installed failure is not the expected sparse corner interpolation")
        paths.append(frames)
    retry = ("v5_orbit_domain.py", "159", "explore")
    if retry in paths[0] or retry not in paths[1]:
        raise ValueError("Expected only the second attempt to run the installed support wrapper")
    return dict(stage="receiver-smooth corner exploration during initial rank", exception=OUTSIDE,
                both_attempts_same_terminal_frames=True, retry_reached_original_sparse_instance=True,
                missing_numeric_query=True, trace_sha256=digest(trace.encode()), stack_paths=paths)


def support_disposition(observed, corners, spans, terminal_policy):
    if corners != 4 or spans["original_restart"]:
        raise ValueError("Expected one ordinary corner ranking without a whole-solver retry")
    projections = observed["corner_projections_extended"]
    if projections:
        if (terminal_policy != "orbit_support" or not observed["added_knots_s"]
                or not observed["sgp4_calls"] or not observed["new_state_count"]
                or observed["sgp4_state_count"] < observed["new_state_count"]):
            raise ValueError("Live phase-support counters disagree with the successful terminal")
        return "causal_extension_used"
    if (terminal_policy != "stock" or observed["added_knots_s"]
            or any(observed[key] for key in ("sgp4_calls", "new_state_count", "sgp4_state_count",
                                             "max_augmented_bank_bytes", "support_wall_s"))):
        raise ValueError("Unextended nominal support must have zero live extension counters")
    return "original_nominal_support_used"


def charged_clock(result, process):
    failed = result["outcome"] == "solver_failed"
    validates = result["validation"]
    if (result["process"] != process or process["timed_out"] or process["exit_code"] != int(failed)
            or result["timing_scope"] != ("raw_launch_to_exit" if failed else NORMAL_SCOPE)
            or any(not isclose(result[key], process[key]+(0 if failed else validates[key]),
                               rel_tol=0., abs_tol=1e-7) for key in ("elapsed_s", "cpu_s"))):
        raise ValueError("Published wall or CPU clock differs from its charged verifier boundary")
    return dict(outcome=result["outcome"], scope=result["timing_scope"], process=process,
                verifier=validates, verifier_charged=not failed,
                charged_wall_s=result["elapsed_s"], charged_cpu_s=result["cpu_s"])


def scientific_products(pub, witness, result, authority, reference):
    from tools.pipeline_eval.scoring import distance_km

    evidence = result["evidence"]
    receipt = evidence["receipt"]
    run_id = receipt["run_id"]
    suite = pub / "fast-scan-standard-v2" / run_id / "final-error-v7"
    terminal_sha = receipt["terminal_sha256"]
    terminal = document(pub/"fast-scan-automatic-work"/run_id/"terminal.json", terminal_sha)
    manifest = document(suite/"manifest.json")
    if (terminal["decision"] != "ok" or terminal["arms"] != evidence["arms"]
            or terminal["native_sha256"] != result["native_sha256"]
            or manifest["terminal_sha256"] != terminal_sha or manifest["input_sha256"] != terminal["native_sha256"]
            or manifest["region"] != receipt["region"] or manifest["orbit_policy"] != terminal["orbit_policy"]
            or witness["solver_recipe"]["archive_sha256"] != authority["archive_sha256"]):
        raise ValueError("The terminal, region and product provenance do not match the actual run")
    images = witness["evidence"]["images"]
    verified = {f["name"]: f for f in result["figures"]}
    if (len(verified) != 8 or set(verified) != set(images) or manifest["artifacts"] != evidence["artifacts"]
            or {f["name"]: f["sha256"] for f in manifest["artifacts"]} != {k:f["sha256"] for k,f in verified.items()}
            or any(verified[k]["sha256"] != image["sha256"] or verified[k]["size"] != image["size"]
                   or verified[k]["rgba_sha256"] != "sha256:"+image["rgba_sha256"] for k,image in images.items())):
        raise ValueError("Expected exact agreement with every original independently decoded PNG receipt")

    owners = {}
    for arm in ARMS:
        rows = witness["evidence"]["owner_rows"][arm]
        mapped = {row[0]: row[1] for row in rows}
        if len(mapped) != len(rows):
            raise ValueError("Duplicate original selected owner")
        owners[arm] = digest(encoded(mapped))
    if owners != evidence["owners"]:
        raise ValueError("Actual ordered owner rows do not match their sealed maps")
    binding = dict(terminal_sha256=terminal_sha, owner_sha256=owners, input_sha256=result["native_sha256"],
                   position_png_sha256=verified["position"]["sha256"])
    products = {}
    for tag in ("grid", "path"):
        envelope = document(suite/f"position-{tag}.json")
        value = envelope["document"]
        numerics = {k:v for k,v in value.items() if k not in ("binding", "elapsed_seconds")}
        if (digest(encoded(value)) != envelope["sha256"] or any(value["binding"][k] != v for k,v in binding.items())
                or digest(encoded(numerics)) != evidence["scientific_digests"][tag]):
            raise ValueError("Grid or path lost its terminal, owner, image or numerical binding")
        products[tag] = value
    grid = products["grid"]
    if (not grid["matched_c_grid"] or not grid["complete"]
            or not len(grid["points"]) == grid["planned_points"] == grid["evaluated_points"] == 179
            or any(not isfinite(p["scores"][arm]) for p in grid["points"] for arm in ARMS)):
        raise ValueError("Expected complete shared 179-site grid for both calibrations")

    arms = {}
    for arm in ARMS:
        loc = terminal["arms"][arm]["latlon"]
        details = manifest["arms"][arm]
        if (loc != details["endpoint_latlon"] or loc != grid["endpoint_latlon"][arm]
                or grid["endpoint_objective_replay"][arm] != 0 or owners[arm] != details["owner_sha256"]):
            raise ValueError("Original endpoint, replay or owners changed")
        arms[arm] = dict(latlon=loc, error_km=distance_km(loc, reference),
                         conditional_rf_rms_hz=terminal["arms"][arm]["rf_rms_hz"],
                         all_owner_rf_rms_hz=details["residual_rms_hz"], owners=details["associated_points"],
                         grid_minimum_index=min(range(179), key=lambda i: grid["points"][i]["scores"][arm]))
    return dict(arms=arms, between_arm_km=distance_km(*(arms[a]["latlon"] for a in ARMS)),
                reference=reference, region=receipt["region"], terminal_sha256=terminal_sha,
                orbit_policy=terminal["orbit_policy"], figures=verified, numerical_digests=evidence["scientific_digests"],
                exact_endpoints_and_owner_bindings=True, grid_points=len(grid["points"]),
                same_ordered_owners=witness["evidence"]["owner_rows"]["c0"] == witness["evidence"]["owner_rows"]["fitted_c"])


def case_audit(directory, pin, reference):
    pair = document(directory/"pair.json", pin["pair"])
    req = document(directory/"input.json", pin["request"])
    authority = document(directory/"authority.json", pair["authority_sha256"])
    bases = {k: directory/k/"attempt-000001" for k in ("installed", "successor")}
    original, candidate = [document(bases[k]/"result.json", pair["attempt_result_sha256"][k]) for k in bases]
    if (not pair["verified_pair"] or not pair["chronological"] or pair["generation"] != 1
            or not authority == req["authority"] == original["raw_identity"] == candidate["raw_identity"]
            or any(r["authority_sha256"] != pair["authority_sha256"] for r in (original, candidate))
            or original["outcome"] != "solver_failed" or candidate["outcome"] != "complete"
            or original["native_sha256"] == candidate["native_sha256"] or not original["reached_solver"]
            or original.get("figures") is not None or original["evidence"]["artifacts"] or original["evidence"]["owners"]
            or original["evidence"]["arms"] != {arm:dict(latlon=None, rf_rms_hz=None) for arm in ARMS}
            or list((bases["installed"]/"publication").glob("fast-scan-automatic-work/*/terminal.json"))):
        raise ValueError("Expected original no-fix failure and genuine candidate publication on the same capture")
    trace = checked((bases["installed"]/"stderr.log").read_bytes(), TRACE).decode()
    if trace != original["evidence"]["failure_observation"]["stderr"]:
        raise ValueError("Installed stderr is detached from the failed attempt")
    exception = corner_trace(trace)
    pub = bases["successor"]/"publication"
    witness = document(pub/"exact-named-raw-witness.json", pin["witness"])
    live = document(pub/"legacy-original-acquisition.json", pin["acquisition"])
    boot = document(pub/"unified-short-bootstrap.json", pin["bootstrap"])
    marker = document(pub/"algo08v3-successor-release.json")
    risk = witness["ports"]["history_risk"]
    choice = risk["choice"]
    lean, = risk["lean_attempts"]
    rank, = witness["ports"]["rank"]
    seed = risk["two_centre_rank"]
    receiver = boot["receiver_audit"]
    counts = candidate["evidence"]["receipt"]["counts"]
    if (marker["build_sha256"] != "sha256:"+BUILD or marker["receipt"] != candidate["evidence"]["receipt"]
            or marker["authority_sha256"] != pair["authority_sha256"] or boot["raw_acquisitions"] != 1
            or boot["native_sha256"] != candidate["native_sha256"] or boot["verified_handoffs"] != 1
            or receiver["recording_authority"] != live["finished_raw_authority"]
            or receiver["recording_authority"] != authority["raw_authority_sha256"]
            or receiver["input_manifest"] != authority["inventory_sha256"]
            or receiver["issued"] != authority["window_count"] or sum(receiver["native"]["native_calls"].values()) != 2*counts["processed"]
            or counts != original["evidence"]["receipt"]["counts"]
            or counts["processed"]+counts["invalid_capture"] != receiver["issued"]
            or choice["census"]["cutoff_utc_ns"] != authority["causal_cutoff_utc_ns"]
            or choice["route"] != "lean" or choice["reason"] != "healthy_samples"
            or risk["inference_calls"] != 1 or lean["decision"] != "complete" or lean.get("fallback_clocks")
            or seed["paid_centres"] != 2 or seed["distinct_finalists"] != 3 or seed.get("ordinary_retry")):
        raise ValueError("Original receiver, charted route or paid centre evidence does not bind the pair")

    product = scientific_products(pub, witness, candidate, authority, reference)
    acceleration = live["acceleration"]["solver"]
    support, = acceleration["in_flight"]
    disposition = support_disposition(support, rank["inputs"]["other_projections"], acceleration, product["orbit_policy"])
    extension = left_extension(support["added_knots_s"], 300) if support["added_knots_s"] else None
    png = witness["ports"]["png"]
    if not png["verified"] == png["reused"] == acceleration["png_native"]["native"] == 8 or png["fallbacks"]:
        raise ValueError("Original application and native PNG check counts differ")
    methods = {k: charged_clock(r, document(bases[k]/"process.json")) for k,r in zip(bases,(original,candidate),strict=True)}
    return dict(clocks=methods, authority=pair["authority_sha256"], attempt_sha256=pair["attempt_result_sha256"],
                raw_authority=authority["raw_authority_sha256"], native_sha256=dict(installed=original["native_sha256"],
                    successor=candidate["native_sha256"]), same_lease=pair["same_lease"], actual_order=pair["actual_order"],
                cutoff_utc_ns=choice["census"]["cutoff_utc_ns"], origin_utc_ns=choice["census"]["origin_utc_ns"],
                exception=exception, support=support, support_disposition=disposition, derived_extension=extension,
                rank=dict(clock={k:rank[k] for k in ("cpu_ns", "elapsed_ns")}, corners=rank["inputs"]["other_projections"],
                          lean=choice["route"], reason=choice["reason"], inferences=risk["inference_calls"],
                          centres=seed["paid_centres"], fixed_order_nodes=rank["nodes"], curved=seed["original_curved"],
                          catalogue=seed["catalogue_rows"]), raw_visits=receiver["issued"], admitted=counts["processed"],
                signed_successor_factors=receiver["selected"], verified_png_port=png, product=product)


def audit(campaign):
    old = checked((PAYLOAD/VARIANTS/"v5_orbit_domain.py").read_bytes(), OLD_CORNER)
    repaired = checked(git_blob("de7873faa", VARIANTS/"v5_orbit_domain.py"), REPAIRED_CORNER)
    sparse = checked((PAYLOAD/VARIANTS/"algo08_sparse_rank_projection.py").read_bytes(), SPARSE)
    checked((PAYLOAD/VARIANTS/"orbit_projector.py").read_bytes(), PROJECTOR)
    build = document(campaign/"frozen-build/build.json", BUILD)
    if (b'patch.object(scan.ScanLikelihood, "shifted", shifted)' not in old
            or b'patch.object(context, "shifted", shifted)' not in repaired
            or b'patch.object(scan, "shifted", shifted)' not in sparse
            or build["sources"][str(VARIANTS/"v5_orbit_domain.py")] != REPAIRED_CORNER):
        raise ValueError("The failed class retry and frozen instance repair differ from the published source")
    refs = json.loads(checked(git_blob("2d0ad2dfd", "reports/2026_11_21_ds30_full/reference-audit.json"), REFERENCE))
    sites = {r["dataset_label"]: [r["reference"][k] for k in ("latitude_deg", "longitude_deg")]
             for r in refs["cases"] if r["dataset_label"] in PINS and r["authority_eligible"] and r["sealed_metadata_digests_verified"]}
    cases = {case:case_audit(campaign/"cases"/case, pin, sites[case]) for case,pin in PINS.items()}
    if cases["DS30-0210"]["support_disposition"] == cases["DS30-0397"]["support_disposition"]:
        raise ValueError("Expected distinguishable live extension paths")
    pair_clocks = [c["clocks"] for c in cases.values()]
    totals = {role: fsum(clocks[role]["charged_wall_s"] for clocks in pair_clocks) for role in ("installed", "successor")}
    return dict(cases=cases, same_installed_trace_bytes=True, original_paid_wall_s=totals,
                respective_outcome_summed_wall_ratio=totals["successor"]/totals["installed"],
                respective_outcome_median_wall_ratio=median(r["successor"]["charged_wall_s"]/r["installed"]["charged_wall_s"]
                                                            for r in pair_clocks),
                new_solver_runs=0, waveform_reads=0, ephemeris_reads=0, png_payload_reads=0)


if __name__ == "__main__":
    def metadata_only(event, args):
        denied(event, args)
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0]))
            if path.suffix in (".tle", ".png") or path.name.endswith((".tle.gz", ".ci16")):
                raise ValueError("Only retained metadata is admitted")

    sys.addaudithook(metadata_only)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path, nargs="?", default=CAMPAIGN)
    print(json.dumps(audit(parser.parse_args().campaign), indent=2, sort_keys=True, allow_nan=False))
