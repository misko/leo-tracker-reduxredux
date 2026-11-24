"""Measure the frozen ordinary-format raw candidate and installed v3 on DS30-0107."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from time import perf_counter


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
CONTROL = ("eight-ms-0107-pair.json.gz", "2cf87dd38df076e00ac1bc555a38cb4bd57e65f5404800897bbfaddb149a6b3e")
SOURCES = (Path(__file__).name, "history-risk-physical-cohort-protocol.md", "history_risk_0016_raw.py",
           "raw_0016_best_trial.py", "eight_ms_0107_pair.py", "exact_named_raw.py", "unified_short_bootstrap.py")


def read(path):
    return json.loads(path.read_bytes())


def source_pins():
    return {name: sha256((HERE/name).read_bytes()).hexdigest() for name in SOURCES}


def controls():
    from continued_cfo_small_raw import CASE, INPUTS, RECORDING
    from eight_ms_0107_pair import archived
    from empty_bootstrap import checked
    from guarded_cfo_small_raw import PRIOR, PRIOR_RESULT, PRIOR_SEAL

    archive = archived(CONTROL)["documents"]["post-verification.json"]
    earlier = json.loads(checked(PRIOR/"result.json", PRIOR_RESULT))
    checked(PRIOR/"prediction-seal.json", PRIOR_SEAL)
    old = earlier["admission"]
    rows = archive["modes"]
    candidate = rows["candidate"]["bootstrap"]
    if (archive["case"] != CASE.id or not all(archive["expected_withholds"].values())
            or old["inventory"] != INPUTS.inventory or earlier["prediction_seal_sha256"] != PRIOR_SEAL
            or old["raw_authority"] != candidate["receiver_audit"]["recording_authority"]):
        raise ValueError("The authenticated complete 0107 policy controls changed")
    request = dict(recording=str(RECORDING), inventory=INPUTS.inventory, session=old["session"],
                   region=str(PRIOR/"offer.json"), offer_sha256=old["offer_sha256"],
                   archive={"root": str(PRIOR/"tle"), "snapshots_sha256": INPUTS.archive},
                   cutoff_utc_ns=INPUTS.cutoff_ns, authority=old["raw_authority"],
                   detector=candidate["detector_recipe_sha256"], native=rows["candidate"]["native_sha256"])
    return request, old, rows


def launch(root):
    from portable_orbit_index_trial import local_launcher_tools

    local_launcher_tools()
    from aperture_trial import write
    from continued_cfo_small_raw import CASE, RECORDING, input_inventory, residency
    from dense_geographic_trial import host
    from eight_ms_0107_pair import is_resident, verified_scope
    from eight_ms_south_transfer import environment_for
    from empty_bootstrap import RELEASE, checked
    from exact_named_raw import staged_path
    from guarded_cfo_small_raw import PRIOR
    from history_risk_0016_raw import ADAPTERS, LIBRARIES, ORDER, arguments, pinned_archive, roster, route_options
    from leo.operations.tle_archive import TleArchiveReader
    from raw_0016_best_trial import measure_mode
    from short_raw_diagnostic import pairs

    started = perf_counter()
    machine = host()
    staged = PRIOR/RECORDING.name
    verified_scope(staged, RECORDING)
    staged_path(root.parent)
    req, old, _ = controls()
    session, members = input_inventory()
    if session != req["session"] or any(dict(path=str(p), bytes=size, sha256=digest) != old["members"][name]
                                        for name, (p, size, digest) in members.items()):
        raise ValueError("The private read-only mount must bind the exact original signed inventory")
    offer, archive = staged_path(Path(req["region"])), staged_path(Path(req["archive"]["root"]))
    checked(offer, req["offer_sha256"])
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if (len(refs) != 51 or pairs.archive_identity(archive) != req["archive"]
            or any(ref.collected_utc_ns >= req["cutoff_utc_ns"] for ref in refs)):
        raise ValueError("Expected the original causal 0107 catalogue")
    files = [staged_path(ref.path, root=archive) for ref in refs]
    residence = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE", *files]))["fincore"]
    if len(residence) != len(refs) or any(row["res"] < row["size"] for row in residence):
        raise ValueError("All causal catalogue bodies must already be resident")
    flags = ("--short-binary", "--geographic-library", "--regional-track-library", "--frontier-block-library")
    all_libraries = pinned_archive(LIBRARIES)["raw_binding"]["libraries"]
    libraries = {flag: all_libraries[flag] for flag in flags}
    for item in libraries.values():
        checked(Path(item["path"]), item["sha256"])
    identity = pairs.verified_v3(pairs.NAMED_V3)
    if identity != old["named"]:
        raise ValueError("Installed release differs from the original v3 control")
    commands = arguments(root, req, pairs.NAMED_V3, RELEASE/"venv/bin/python", libraries)
    options = route_options(commands["candidate"])

    def resident():
        verified_scope(staged, RECORDING)
        caches = residency(members)
        if not is_resident(caches):
            raise ValueError("All original 0107 member and index pages must remain resident")
        return caches["payload"] | {"index_cache": caches["index"]}

    resident()
    root.mkdir()
    (root/"tmp").mkdir()
    shutil.copytree(PRIOR/"fonts", root/"fonts")
    env = environment_for(root)
    help_text = subprocess.run([*commands["candidate"][:6], "--help"], check=True, timeout=10,
                               capture_output=True, env=env).stdout
    if b"--history-risk-route" not in help_text:
        raise ValueError("The isolated exact raw option is unavailable")
    write(root/"admission.json", dict(case=CASE.id, machine=machine, request=req, order=ORDER, stock=identity, commands=commands,
         sources=source_pins(), adapters={name: sha256((HERE.parents[2]/name).read_bytes()).hexdigest() for name in ADAPTERS},
         active_options=options, candidate_libraries=libraries, stage=str(staged), member_files=old["members"],
         catalogue=dict(snapshots=len(refs), bytes=sum(item["size"] for item in residence)),
         original_backing_bytes=0, conditioning_bytes=0, setup_wall_s=perf_counter()-started))
    try:
        for mode in ORDER:
            measure_mode(root, mode, commands[mode], env, resident, require_success=False)
    finally:
        write(root/"prediction-seal.json", roster(root))


def published(root, mode, log, req, expected):
    from empty_bootstrap import bind_native
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from tools.pipeline_eval.qualification import paired_publication as pairs

    output = root/mode
    candidate = mode == "candidate"
    bootstrap = read(output/"unified-short-bootstrap.json") if candidate else None
    receipt = bootstrap["receipt"] if candidate else json.loads(output.with_suffix(".stdout").read_text().splitlines()[-1])
    terminal_path = output/"fast-scan-automatic-work"/receipt["run_id"]/"terminal.json"
    terminal = read(terminal_path)
    store = FastStandardAnalysisStore(output)
    detail = store.detail(receipt["run_id"])
    path = native_packet(output)
    document = path.read_bytes()
    native = json.loads(document)
    digest = "sha256:"+sha256(document).hexdigest()
    detector = req["detector"][7:] if candidate else pairs.V3_IDENTITY["detector_sha256"]
    bind_native(native, req["session"], req["inventory"], detector, expected=expected["native_sha256"])
    probes = native["source"]["probes"]
    if (log["clock"]["exit_code"] or digest != expected["native_sha256"]
            or canonical_digest(terminal) != receipt["terminal_sha256"]
            or receipt["terminal_sha256"] != expected["science"]["receipt"]["terminal_sha256"]
            or terminal["reason"] != "no_active_curvature" or receipt["decision"] != "withheld"
            or receipt["region"] != expected["science"]["receipt"]["region"] or terminal["region"] != receipt["region"]
            or receipt["counts"] != dict(processed=27, invalid_capture=2, skipped_fast_score=0)
            or len(probes) != 54 or receipt["window_count"] != 29 or receipt["session_id"] != req["session"]
            or terminal["native_sha256"] != digest or detail["terminal_sha256"] != receipt["terminal_sha256"]
            or detail["state"] != "withheld" or detail["reason"] != terminal["reason"]
            or detail["raw_authority"] != req["authority"] or native["source"]["raw_recording_authority_digest"] != req["authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != req["cutoff_utc_ns"]
            or set(terminal["arms"]) != {"c0", "fitted_c"}
            or any(arm["latlon"] is not None or arm.get("rf_rms_hz") is not None for arm in terminal["arms"].values())
            or detail["arms"] or detail["artifacts"] or store.position_grid(receipt["run_id"]) is not None
            or store.position_path(receipt["run_id"]) is not None or any(output.rglob("*.png"))):
        raise ValueError("The original scientific withholding terminal or its zero-product policy changed")
    if candidate:
        witness = read(output/"exact-named-raw-witness.json")
        if (bootstrap["native_sha256"] != digest or bootstrap["raw_acquisitions"] != 1 or bootstrap["verified_handoffs"] != 1
                or bootstrap["requested_offer_sha256"] != req["offer_sha256"] or bootstrap["archive_root"] != req["archive"]["root"]
                or bootstrap["frozen_specification"] != pairs.V3_IDENTITY["frozen_specification"]
                or bootstrap.get("packed_ci16_input") is not None or bootstrap["one_pass_web_png"]["enabled"]
                or bootstrap["route"] != "authenticated_installed_graph_ineligible" or bootstrap["scientific_imports_after"]
                or bootstrap["graph_proof"] != expected["bootstrap"]["graph_proof"]
                or witness["ports"] is not None
                or witness["history_risk"] != dict(requested=True, reason="receiver_side_withhold")):
            raise ValueError("The one signed raw handoff did not reach the enrolled early withholding policy")
    else:
        pairs.verify_v3_publication(output, receipt)
    opportunities = [{k: v for k, v in probe.items() if k != "candidates"} for probe in probes]
    return dict(process=log, digest=digest, science=dict(receipt=receipt, arms=terminal["arms"], reason=terminal["reason"],
         raw_authority=detail["raw_authority"]), opportunities=canonical_digest(opportunities),
         excluded=native["provenance"]["excluded_windows"], figures={}, sidecars=None, owner_counts={},
         factors=sum(len(p["candidates"]) for p in probes), route=None,
         phases=bootstrap["phases"] if bootstrap else None, bootstrap=bootstrap,
         time_boundaries=dict(detector_file_s=(path.stat().st_mtime_ns-log["clock"]["started_unix_ns"])/1e9,
                              terminal_file_s=(terminal_path.stat().st_mtime_ns-log["clock"]["started_unix_ns"])/1e9),
         native_parity=True, terminal_parity=True)


def score(root, destination):
    from portable_orbit_index_trial import local_launcher_tools

    local_launcher_tools()
    from aperture_trial import write
    from history_risk_0016_raw import ORDER, roster, route_options

    seal = root/"prediction-seal.json"
    admission = read(root/"admission.json")
    request, _, expected = controls()
    if (read(seal) != roster(root) or admission["request"] != request or admission["sources"] != source_pins()
            or admission["active_options"] != route_options(admission["commands"]["candidate"])):
        raise ValueError("Frozen physical control or source changed before scoring")
    logs = {mode: read(root/f"{mode}-clock.json") for mode in ORDER}
    if any(row["command"] != admission["commands"][mode] for mode, row in logs.items()):
        raise ValueError("Measured child argv differs from admission")
    runs = {mode: published(root, mode, row, request, expected[mode]) for mode, row in logs.items()}
    first, second = (runs[mode] for mode in ORDER)
    same = (first["opportunities"] == second["opportunities"] == expected["stock"]["opportunities"]
            and first["excluded"] == second["excluded"]
            and logs["candidate"]["clock"]["started_unix_ns"] < logs["stock"]["clock"]["started_unix_ns"])
    if not same or [first["factors"], second["factors"]] != [19, 0]:
        raise ValueError("Expected the exact original 54 opportunities and candidate-first launch order")
    ratios = {key: logs["stock"]["clock"][key]/logs["candidate"]["clock"][key] for key in ("cpu_s", "elapsed_s")}
    write(destination, dict(case="DS30-0107", admission=admission, runs=runs, measured_exits=logs, qualified=True,
                same_opportunities=same, ratio=ratios, pre_score_sha256=sha256(seal.read_bytes()).hexdigest(),
                timing_boundary="fresh CLI process through verified exit; offline scoring excluded"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.action == "score":
        if args.output is None or args.output.resolve().is_relative_to(args.root.resolve()):
            parser.error("Supply a score output outside the sealed publication")
        score(args.root, args.output)
    else:
        launch(args.root)
