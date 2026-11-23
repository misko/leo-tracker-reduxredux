"""Verify a combined raw pair, including authentic packets preserved before a failure."""

import argparse
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))


CAVITY_ERROR = "cavity nomination failed: ValueError('nonempty observation mask matching full design required')"
CAVITY_SOURCES = {
    "position.py": "c3507e6ecaba0adf6d3677f56d8056afcccbcf90d6a561bca7a42b06b0daef9d",
    "family_cavity.py": "7a20ac84d4c245df95481d10425def01642cbf4d3f45f1f32b9188a78007b3ae",
    "signed_context.py": "b556b0b9526fb0b2aa1d0cecfedf25f9b652a12c42441ec9ef0d538ab34db49d",
    "event_position.py": "3a8c9bde7ddddc115fcb219f8588fd51188ef4081567d8e2fe91df8324418e9f",
    "history_position.py": "00e349de1a25ac62fb287f970a005737675b5f2e6d45273baa9c914e8a7918f0",
    "marginal.py": "c80ac51249578e8a2c6c6a13a04aaa22a168353b2c758155858106b91507b609",
}


def cavity_diagnosis(logs):
    from empty_bootstrap import PAYLOAD, RELEASE, checked
    from short_graph_guard import NAMED_ORDER_PINS

    if not all(log["clock"]["exit_code"] and log["clock"]["stderr_tail"].rstrip().endswith(CAVITY_ERROR)
               for log in logs.values()):
        return None
    for name, pin in CAVITY_SOURCES.items():
        checked(RELEASE/"src/leo/analysis/localization_v3"/name, pin)
    core = "tools/pipeline_eval/variants/v5_core.py"
    pin = NAMED_ORDER_PINS["payload/"+core]
    checked(PAYLOAD/core, pin)
    return dict(error=CAVITY_ERROR, inference="family exclusion exhausted the kept curved calibration rows",
                support="pinned source and both process errors", kept_curved_families=1,
                mask_shape_invariant="same scan, seed, track members and arm; slice assignment changes only mask values",
                sources=CAVITY_SOURCES | {core: pin}, counterfactual_decision=None)


def proofs(packets):
    import empty_bootstrap as staged

    staged.load_runtime()
    from short_graph_guard import prove

    return {name: prove(json.loads(path.read_bytes()), staged.RELEASE/"assets", use_time_support=True, use_curvature_extent=True)
            for name, path in packets.items()}


def stopped_after_acquisition(target, log, admission, detector, native_path):
    from empty_bootstrap import bind_native
    from leo.contracts.digests import canonical_digest
    from raw_0016_best_trial import sha
    from short_raw_diagnostic import require_warm

    require_warm(log["cache_before"])
    require_warm(log["cache_after"])
    blob = native_path.read_bytes()
    native = json.loads(blob)
    source, provenance = native["source"], native["provenance"]
    native_sha = canonical_digest(native)
    bind_native(native, admission["session"], admission["inventory"], detector, expected="sha256:"+sha(blob))
    inventory = target/"fast-scan-inputs"/(admission["session"]+".json")
    started = log["clock"]["started_unix_ns"]
    detection_time = (native_path.stat().st_mtime_ns - started)/1e9
    if (not log["clock"]["exit_code"] or source["raw_recording_authority_digest"] != admission["raw_authority"]
            or canonical_digest(json.loads(inventory.read_bytes())) != admission["inventory"]
            or provenance["processed_windows"] != admission["admitted"] or len(source["probes"]) != 2*admission["admitted"]
            or native["clock_anchor"]["before"]["realtime_ns"] != admission["cutoff_utc_ns"]
            or not 0 <= detection_time <= log["clock"]["elapsed_s"]):
        raise ValueError("Unproven receiver, processing extent or original physical authority")
    terminal = list(target.glob("fast-scan-automatic-work/*/terminal.json"))
    if terminal or any(target.rglob("*.png")) or (target/"fast-scan-standard-v2").exists():
        raise ValueError("A failed acquisition worker left partial standard results requiring separate validation")
    lanes = source["probes"]
    return dict(process=log, science=None, terminal_status="process_failed", figures={}, bootstrap=None,
                time_boundaries=dict(detections_file_s=detection_time, terminal_file_s=None, exit_s=log["clock"]["elapsed_s"]),
                native_sha256=native_sha, native_file_sha256=sha(blob),
                native_provenance=provenance, opportunities=canonical_digest([{k: v for k, v in row.items() if k != "candidates"} for row in lanes]),
                probes=len(lanes), factors=sum(len(row["candidates"]) for row in lanes), owner_counts={},
                factors_by_radio={str(radio): sum(len(row["candidates"]) for row in lanes if row["receiver_id"] == radio) for radio in (0, 1)})


def score(root, output):
    from aperture_trial import read, write
    from empty_bootstrap import RELEASE, checked
    from full_short_physical import environment
    from local_future_cli_trial import native_packet
    from raw_0016_best_score import ARMS, process_rows
    from raw_0016_best_trial import frozen_sources, sha
    from raw_band_pair import selection
    from raw_band_pair_score import paired_error_delta
    from raw_combined_band import BAND, BASE, CFO_FLAG, COMBINED_FLAGS, EXTRA_SOURCES, PROTOCOL_SHA, WRAPPER, receiver_configuration, sealed
    from short_raw_diagnostic import pairs
    from triage_bounds import calibration_comparison

    inputs = BAND.inputs
    order = inputs.workload.order
    witness = root/"prediction-seal.json"
    if read(witness) != sealed(root, order):
        raise ValueError("Raw evidence changed after the two process clocks")
    admission = read(root/"admission.json")
    receiver = receiver_configuration()
    if (admission["case"] != inputs.workload.id or admission["base"] != BASE
            or tuple(admission["order"]) != order or tuple(admission["route_flags"]) != COMBINED_FLAGS
            or admission["selection"] != selection(BAND, checkout=BASE, protocol_sha256=PROTOCOL_SHA)
            or admission["inventory"] != inputs.inventory or admission["archive"]["sha256"] != inputs.archive
            or admission["binding"] != inputs.workload.binding_sha or admission["cutoff_utc_ns"] != inputs.cutoff_ns
            or admission["issued"] != inputs.workload.windows or admission["admitted"] != inputs.admitted):
        raise ValueError("Raw case admission changed")
    if admission["receiver_configuration"] != receiver or admission["sources"] != frozen_sources(BASE, EXTRA_SOURCES):
        raise ValueError("Source or detector recipe differs from the frozen combined route")
    for name, pin in admission["library_sha256"].items():
        checked(root/(name+".so"), pin)
    logs = {name: read(root/f"{name}-clock.json") for name in order}
    if logs[order[0]]["clock"]["started_unix_ns"] >= logs[order[1]]["clock"]["started_unix_ns"]:
        raise ValueError("Timed process order changed")
    commands = {name: logs[name]["command"] for name in order}
    for argv in commands.values():
        common = {flag: argv[argv.index(flag)+1] for flag in ("--recording", "--region", "--archive")}
        if common != {"--recording": admission["recording"], "--region": str(root/"offer.json"), "--archive": str(root/"tle")}:
            raise ValueError("Timed recording, offer or causal archive differs from admission")
    candidate, stock = commands["candidate"], commands["stock"]
    if (stock[0] != str(pairs.NAMED_V3) or candidate[2] != str(WRAPPER) or not set(COMBINED_FLAGS) <= set(candidate)
            or candidate[candidate.index(CFO_FLAG)+1] != str(root/"cfo_refinement.so")):
        raise ValueError("Timed receiver configuration differs from the two enrolled CLI entries")
    packets = {name: native_packet(root/name) for name in order}
    eligible = tuple(name for name in order if logs[name]["clock"]["exit_code"] == 0)
    detector = receiver["detector_recipe_sha256"].removeprefix("sha256:")
    runs = process_rows(root, admission, inputs, modes=eligible, candidate_recipe=detector)
    detectors = {"candidate": detector, "stock": pairs.V3_IDENTITY["detector_sha256"]}
    for name in set(order)-runs.keys():
        runs[name] = stopped_after_acquisition(root/name, logs[name], admission, detectors[name], packets[name])
    if runs["stock"]["opportunities"] != runs["candidate"]["opportunities"]:
        raise ValueError("The two receivers had different signed opportunities")
    if "candidate" in eligible and runs["candidate"]["bootstrap"]["receiver_recipe"] != receiver["recipe"]:
        raise ValueError("Successful candidate publication lacks the enrolled receiver recipe")
    env = environment(root)
    env.update(TMPDIR=str(root/"tmp"), XDG_CACHE_HOME=str(root/"tmp"))
    recomputed = json.loads(subprocess.check_output([RELEASE/"venv/bin/python", "-IB", __file__, "proof",
                                                     packets["stock"], packets["candidate"]], env=env, timeout=15))
    geographic = (calibration_comparison({name: runs[name]["science"] for name in eligible}, BAND.inputs.workload.id)
                  if eligible else dict(runs={}, status="no published position available"))
    for name in set(order)-geographic["runs"].keys():
        geographic["runs"][name] = dict(horizontal_error_km=dict.fromkeys(ARMS), rf_rms_hz=dict.fromkeys(ARMS))
    speedup = logs["stock"]["clock"]["elapsed_s"]/logs["candidate"]["clock"]["elapsed_s"] if len(eligible) == 2 else None
    write(output, dict(pre_score_sha256=sha(witness.read_bytes()), admission=admission, original=runs,
                       geographic=geographic, error_delta_m=paired_error_delta(geographic), speedup=speedup,
                       conditioning=read(root/"conditioning.json"), preflight=read(root/"preflight.json"), cavity_diagnosis=cavity_diagnosis(logs),
                       saved_graph_proof_recheck=recomputed, verification=dict(same_opportunities=True, eligible_for_timing_panel=len(eligible) == 2)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    for name, fields in (("score", ("root", "output")), ("proof", ("stock", "candidate"))):
        sub = commands.add_parser(name)
        for key in fields:
            sub.add_argument(key, type=Path)
    args = vars(parser.parse_args())
    if args.pop("mode") == "score":
        score(**args)
    else:
        print(json.dumps(proofs(args), allow_nan=False))
