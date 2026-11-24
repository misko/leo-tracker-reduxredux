"""Measure one live 20/8 ms North publication with the exact history-risk opt-in."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from time import perf_counter, process_time


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
CONTROL = HERE/"measurements/exact-named-raw.json.gz"
CONTROL_PIN = "e654af8ddfc9c9bf0b479f722003e984a35ca47eab8a94c4540bee57f0dc6b86"
SOURCES = (Path(__file__).name, "history-risk-raw-protocol.md", "exact_named_raw.py", "exact_named_route.py",
           "named_history_once.py", "unified_short_bootstrap.py")
PREBUILT_FLAGS = ("--portable-orbit-index", "--portable-orbit-index-sha256", "--portable-orbit-producer-sha256")


def prior_controls():
    from empty_bootstrap import checked
    from exact_named_raw_transfer import RAW_PACKET
    from raw_cfo_north_trial import STOCK_PACKET

    rows = json.loads(gzip.decompress(checked(CONTROL, CONTROL_PIN)))["north"]
    job = rows["binding.json"]["value"]
    result = rows["verified-result.json"]["value"]
    for side, pin in (("named", STOCK_PACKET), ("candidate", RAW_PACKET)):
        report, clock = result["runs"][side], result["clocks"][side]
        if (report["native_sha256"] != pin or report["status"] != "complete" or clock["exit_code"]
                or len(report["evidence"]["images"]) != 8 or report["evidence"]["grid"] != 137
                or clock != rows[f"{side}-clock.json"]["value"]
                or len(report["timings"]["solve"]) != 1):
            raise ValueError("Expected a complete matched, verified through-exit North control")
    if rows["candidate/unified-short-bootstrap.json"]["value"]["verified_handoffs"] != 1:
        raise ValueError("The previous exact control must bind the original one-traversal recipe")
    return rows, job, result


def without_prebuilt(options):
    """Keep the original recording and recipe, with a fresh exact catalogue index."""
    pairs = zip(options[::2], options[1::2], strict=True)
    return [item for key, value in pairs if key not in PREBUILT_FLAGS for item in (key, value)]


def launch(root):
    start = process_time(), perf_counter()
    from eight_ms_south_transfer import environment_for
    from empty_bootstrap import clock
    from exact_named_raw import RISK_SOURCES, write
    from exact_named_raw_transfer import referenced_binding
    from portable_orbit_index_trial import local_launcher_tools

    local_launcher_tools()
    from short_raw_diagnostic import measure

    old_root, observe_cache, _, job = referenced_binding(root)
    _, previous, _ = prior_controls()
    if job["request"] != previous["request"] or job["machine"] != previous["machine"]:
        raise ValueError("Original North authority, input, offered region or CPU configuration changed")
    regular = dict(zip(previous["candidate_args"][::2], previous["candidate_args"][1::2], strict=True))
    live = dict(zip(job["candidate_args"][::2], job["candidate_args"][1::2], strict=True))
    if regular | {"--output": live["--output"]} != live:
        raise ValueError("The comparison must use the matched original acquisition and numerical request")
    root.mkdir()
    (root/"tmp").mkdir()
    shutil.copytree(old_root/"fonts", root/"fonts")
    command = ["/usr/bin/timeout", "--kill-after=2s", "75s", sys.executable, "-IB", str(HERE/"exact_named_raw.py"),
               *without_prebuilt(job["candidate_args"]), "--history-risk-route"]
    cache_before = observe_cache()
    sources = {name: sha256((HERE/name).read_bytes()).hexdigest() for name in (*SOURCES, *RISK_SOURCES)}
    write(root/"binding.json", dict(request=job["request"], machine=job["machine"], control_receipt_sha256=CONTROL_PIN,
                                   command=command, cache_before=cache_before, sources=sources,
                                   index="cold-original-archive", setup=clock(start)))
    result = measure(command, environment_for(root), root/"candidate")
    write(root/"clock.json", result)
    write(root/"cache-after.json", observe_cache())
    if result["exit_code"]:
        raise RuntimeError(result["stderr_tail"])


def score(root):
    from eight_ms_held_score import geographic_reference, owner_differences
    from empty_bootstrap import load_runtime
    from exact_named_raw import ARM_NAMES, write
    from exact_named_raw_transfer import RAW_PACKET, authenticate_packet, read

    load_runtime()
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval import qualification
    from tools.pipeline_eval.scoring import distance_km

    qualification.__path__.append(str(HERE.parents[2]/"tools/pipeline_eval/qualification"))
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km

    controls, _, reference = prior_controls()
    binding, clock, after = (read(root/name) for name in ("binding.json", "clock.json", "cache-after.json"))
    output = root/"candidate"
    witness, raw = (read(output/name) for name in ("exact-named-raw-witness.json", "unified-short-bootstrap.json"))
    ports, evidence = witness["ports"], witness["evidence"]
    history, risk = ports["history"], ports["history_risk"]
    choice = risk["choice"]
    req = binding["request"]
    authenticate_packet(output, req, RAW_PACKET, raw["detector_recipe_sha256"][7:])
    old_raw = controls["candidate/unified-short-bootstrap.json"]["value"]
    native_fields = ("native_sha256", "detector_recipe_sha256", "receiver_recipe", "causal_cutoff_utc_ns",
                     "requested_offer_sha256", "archive_root", "raw_acquisitions", "verified_handoffs")
    if (clock["exit_code"] or raw["receipt"]["decision"] != "complete"
            or raw["raw_acquisitions"] != 1 or raw["verified_handoffs"] != 1 or raw["scientific_imports_before"]
            or raw["route"] != "history_risk_installed" or witness["solver_recipe"]["orbit_index"] != "cold"
            or any(raw[key] != old_raw[key] for key in native_fields) or ports["portable"].get("transfers")
            or history["solves"] != 1 or len(history["prepare"]) != 1 or len(history["infer"]) != 1
            or risk["inference_calls"] != 1 or choice["census"]["cutoff_utc_ns"] != req["cutoff_utc_ns"]
            or not risk["boundary_checks"] or any(not row["terminal_only"] for row in risk["boundary_checks"])
            or evidence["grid"] != 137 or len(evidence["images"]) != 8
            or {key: after[key]["cached_pages"] for key in after}
               != {key: value["cached_pages"] for key, value in binding["cache_before"].items()}):
        raise ValueError("The true raw route or standard publication did not satisfy its frozen scope")
    if choice["route"] == "lean" and not risk["lean_attempts"]:
        raise ValueError("The selected lean route never executed")
    terminal_path, = output.glob("fast-scan-automatic-work/*/terminal.json")
    terminal = read(terminal_path)
    offer = Algo08Region.parse(read(Path(req["inside_offer"]))).document()
    if (raw["receipt"]["terminal_sha256"] != canonical_digest(terminal) or terminal["region"] != offer
            or evidence["detail"]["region"] != offer or terminal["native_sha256"] != RAW_PACKET
            or set(terminal["arms"]) != set(ARM_NAMES)):
        raise ValueError("Expected the original unaltered region and both calibrated terminal arms")
    truth, reference_sha = geographic_reference("north")
    clearance = face_clearance_km(offer, truth)
    if clearance <= 0:
        raise ValueError("This prospective raw offer must contain the scoring reference")
    arms = {arm: dict(position=value["latlon"], rf_rms_hz=value["rf_rms_hz"],
                     error_km=distance_km(truth, value["latlon"]),
                     plot_residual_rms_hz=evidence["detail"]["arms"][arm]["residual_rms_hz"])
            for arm, value in terminal["arms"].items()}
    comparison = {}
    for key, side in (("named", "named/named-raw-witness.json"), ("exact", "candidate/exact-named-raw-witness.json")):
        control = controls[side]["value"]["evidence"]
        label = "named" if key == "named" else "candidate"
        old = reference["runs"][label]
        comparison[key] = dict(clock=reference["clocks"][label], arms=old["arms"], native=old["native_sha256"],
             same_terminal=control["detail"]["terminal_sha256"] == evidence["detail"]["terminal_sha256"],
             owners={arm: owner_differences(control["owner_rows"][arm], evidence["owner_rows"][arm]) for arm in ARM_NAMES},
             same_ordered_owners=control["owner_rows"] == evidence["owner_rows"],
             same_grids_and_paths=control["sidecars"] == evidence["sidecars"],
             encoded_and_decoded_images_equal=sum(row == control["images"][name] for name, row in evidence["images"].items()))
    write(root/"verified-result.json", dict(clock=clock, setup=binding["setup"], signed_native=RAW_PACKET, arms=arms,
        region=offer, clearance_km=clearance, reference_sha256=reference_sha, controls=comparison, witness=witness,
        raw_phases=raw["phases"], receiver=raw["receiver_audit"], route=risk, raw_archive_index=binding["index"],
        optional_prefit_exterior_probe=False, actual_exterior_calls=history["exterior_proof"],
        paid_omission=False, binding_sha256=sha256((root/"binding.json").read_bytes()).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "score"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    {"launch": launch, "score": score}[args.action](args.root)
