"""Time one resident North raw publication and independently seal its result."""

import argparse
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from aperture_trial import RELEASE, read, write
from empty_bootstrap import bind_native, checked
from north_held_anchor_pair import publication_evidence, require_resident, tmpfs
from raw_cfo_north_trial import COMPRESSED_BYTES, MEMBERS, STOCK_PACKET, workload


REFERENCE = Path("/dev/shm/leo-north-held-anchor-20261123")
REFERENCE_PINS = {
    "binding": "7a077f22f27d506c8c3ae9156467d6dfa675cf79ac4d504e88742add0519d4f5",
    "sealed": "87c644ca50ee678f0a4eeb097ff4195cd1fc4157806d92ff3a405d45c98f08f2",
}
PACK = Path("/dev/shm/leo-anchored-cfo-raw-pack01")
PACK_SHA = "0d590b0c7e4ffc468fb17804146362b8534d33d115d83055ae7bbc1dafd967a9"
PROTOCOL = HERE / "joint-held-north-raw-protocol.md"
ARM_NAMES = ("c0", "fitted_c")
SELECTOR = "--select-before-cfo"
EXACT_PACKETS = (
    (Path("/dev/shm/leo-eight-ms-north/12ms"), "2b4e1282f8205a5c90cef2ab6acb7c666d445592963634e93911160205403427"),
    (Path("/dev/shm/leo-v3-north-cfo-final-03/containing"),
     "83d1c79b8acb8dc1d8720999af9791264558b2ac43505b6312e535fe832b91d0"),
)
CFO = "fractional_tracking_cfo_hz"
ROUNDOFF = {CFO: 1e-6, "fractional_exact_score": 1e-10,
            "fractional_control_score": 1e-10, "fractional_margin": 1e-10}


def references():
    for name, pin in REFERENCE_PINS.items():
        checked(REFERENCE / f"{name}.json", pin)
    binding, seal = (read(REFERENCE / f"{name}.json") for name in REFERENCE_PINS)
    stock = seal["results"]["stock"]
    if (seal["binding_sha256"] != REFERENCE_PINS["binding"] or stock["native_sha256"] != STOCK_PACKET
            or stock["clock"]["exit_code"] or stock["clock"]["major_faults"] or stock["clock"]["input_blocks"]):
        raise ValueError("Historical denominator must be the named resident through-exit publication")
    require_resident(stock["cache"])
    return binding, seal["results"]


def cache_snapshot_for_run(store, request, manifests, query):
    from tools.pipeline_eval.qualification.cache_residency import bound_snapshot, cache_snapshot

    recording = Path(request["recording"])
    page_size = os.sysconf("SC_PAGE_SIZE")
    snapshots = dict(
        payload=bound_snapshot(store, recording, manifests, page_size, query),
        index=cache_snapshot([(recording, name, size) for name, size in request["indexes"]], page_size, query),
    )
    for cache in snapshots.values():
        require_resident(cache)
        if cache["members"] != MEMBERS:
            raise ValueError("Expected each original public North member and its index")
    return snapshots


def validate_workload(request, assignment, machine, reference_machine):
    fields = ("recording", "inventory", "session", "archive", "compressed_bytes")
    if (any(request[field] != assignment[field] for field in fields)
            or request["issued"] != assignment["windows"] or request["inside_offer"] != assignment["region_file"]
            or request["inside_offer_sha256"] != assignment["region_sha256"]
            or request["authority"] != assignment["stock"]["raw_authority"] or machine != reference_machine):
        raise ValueError("Candidate and historical control require the same raw assignment and worker settings")


def launch(root, *, continued=False):
    from anchored_cfo_raw import verified_pack
    from dense_geographic_trial import host
    from full_short_physical import CACHE_LIB, CACHE_SHA, environment
    from leo.storage.fast_scan import FastScanStore
    from raw_0016_best_trial import PROJECTION, PROJECTION_SHA
    from raw_cfo_north_trial import CURVATURE_FLAGS, PUBLICATION_FLAGS
    from short_raw_diagnostic import measure
    from tools.pipeline_eval.qualification.cache_residency import load_query
    from tools.pipeline_eval.qualification.paired_publication import NAMED_V3, verified_v3

    reference, _ = references()
    assignment = reference["assignment"]
    for path in (root.parent, assignment["recording"], assignment["archive"]["root"], assignment["region_file"]):
        tmpfs(path)
    request, manifests = workload(root)
    machine = host()
    validate_workload(request, assignment, machine, reference["machine"])
    verified_v3(NAMED_V3)
    checked(PACK / "pack.json", PACK_SHA)
    verified_pack(PACK)
    checked(CACHE_LIB, CACHE_SHA)
    library_root = Path("/dev/shm/leo-v3-saved-0402-pair-01")
    pins = {flag: dict(path=str(library_root / f"{flag[2:].replace('-', '_')}.so"), sha256=row["sha256"])
            if flag != "--short-binary" else row for flag, row in reference["binaries"].items()}
    pins["--grid-feature-projection-library"] = dict(path=str(PROJECTION), sha256=PROJECTION_SHA)
    library_flags = []
    for flag, row in pins.items():
        checked(Path(row["path"]), row["sha256"])
        library_flags.extend((flag, row["path"]))
    checkout = HERE.parents[2]
    git = ["git", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("The candidate and benchmark sources must be committed before launch")
    commit = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    root.mkdir()
    for name in ("fonts", "tmp"):
        (root / name).mkdir()
    env = environment(root)
    env.update(TMPDIR=str(root / "tmp"), XDG_CACHE_HOME=str(root / "tmp"))
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=25)
    guarded_entry = HERE / "anchored_cfo_raw.py"
    entry = HERE / "continued_cfo.py" if continued else guarded_entry
    protocol = HERE / "continued-cfo-north-protocol.md" if continued else PROTOCOL
    sources = {entry, guarded_entry, Path(__file__), protocol, HERE / "held_cycle_refined.py",
               HERE / "unified_short_bootstrap.py", HERE / "short_cfo_raw.py"}
    if continued:
        sources.add(HERE / "continued_cfo_north_trial.py")
    cli = [python, "-IB", entry, "--anchored-cfo-pack", PACK]
    options = subprocess.run([*cli, "--help"], env=env, capture_output=True, timeout=15, check=True).stdout
    if any(flag.encode() not in options.split() for flag in (SELECTOR, "--named-survivor-finish")):
        raise ValueError("The guarded normal entry did not expose the frozen joint selector and finish")
    output = root / "containing"
    command = ["/usr/bin/timeout", "--kill-after=2s", "90s", *cli, "--recording", request["recording"],
               "--archive", request["archive"]["root"], "--region", request["inside_offer"], "--output", output,
               *library_flags, *CURVATURE_FLAGS, *PUBLICATION_FLAGS, *(() if continued else (SELECTOR,))]
    binding = dict(request=request, assignment=assignment, historical=REFERENCE_PINS, command=list(map(str, command)),
                   machine=machine, selector=SELECTOR, commit=commit, libraries=pins, pack_sha256=PACK_SHA,
                   source_sha256={path.name: sha256(path.read_bytes()).hexdigest() for path in sorted(sources)})
    write(root / "binding.json", binding)
    query, store = load_query(CACHE_LIB), FastScanStore(root)
    write(root / "cache-before.json", cache_snapshot_for_run(store, request, manifests, query))
    clock = measure(command, env, output)
    write(root / "clock.json", clock)
    write(root / "cache-after.json", cache_snapshot_for_run(store, request, manifests, query))
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])


def check_arms(arms):
    if (set(arms) != set(ARM_NAMES) or any(
            row.get("latlon") is None or len(row["latlon"]) != 2
            or not all(isfinite(value) for value in row["latlon"])
            or row.get("rf_rms_hz") is None or not isfinite(row["rf_rms_hz"])
            for row in arms.values())):
        raise ValueError("A complete fix must retain finite positions and RF for both calibration arms")


def check_handoff(bootstrap, research, native, candidate, request):
    from leo.contracts.digests import canonical_digest

    source = native["source"]
    detector = bootstrap["detector_recipe_sha256"]
    acquisition = bootstrap["receiver_audit"]
    if (not detector.startswith("sha256:") or canonical_digest(bootstrap["receiver_recipe"]) != detector
            or bootstrap["native_sha256"] != candidate["native_sha256"]
            or bootstrap["receipt"] != research["receipt"] or research["input"] != "raw recording"
            or research["saved_handoff_manifest"] is not None or not research["solve"]
            or bootstrap["route"] != "optimized_installed_graph" or bootstrap["raw_acquisitions"] != 1
            or bootstrap["verified_handoffs"] != 1 or acquisition["issued"] != request["issued"]
            or acquisition["input_manifest"] != request["inventory"]
            or acquisition["recording_authority"] != request["authority"]
            or source["raw_recording_authority_digest"] != request["authority"]
            or bootstrap["causal_cutoff_utc_ns"] != request["cutoff_utc_ns"]
            or candidate["cutoff_utc_ns"] != request["cutoff_utc_ns"]
            or bootstrap["requested_offer_sha256"] != request["inside_offer_sha256"]
            or bootstrap["archive_root"] != request["archive"]["root"]):
        raise ValueError("One raw traversal, exact offer and bound signed handoff must reach the normal active solve")
    bind_native(native, request["session"], request["inventory"], detector[7:], expected=candidate["native_sha256"])


def check_selector(bootstrap, selection, native, request):
    from leo.contracts.digests import canonical_digest

    parent_recipe = dict(bootstrap["receiver_recipe"])
    policy = parent_recipe.pop("held_cycle_before_cfo")
    native_counts = bootstrap["receiver_audit"]["native"]
    counts = [row["counts"] for row in native_counts["cfo_refinement"]["lanes"]]
    if (selection != bootstrap["held_anchor_route"] or selection["policy"] != policy
            or "guarded_phase" not in parent_recipe or "fixed_epoch_cfo_refinement" not in parent_recipe
            or selection["input_recipe_sha256"] != canonical_digest(parent_recipe)
            or selection["selected_recipe_sha256"] != bootstrap["detector_recipe_sha256"]
            or selection["selected_native_sha256"] != bootstrap["native_sha256"]
            or selection["input_inventory"] != request["inventory"] or selection["session"] != request["session"]
            or selection["measured"] != sum(native_counts["factors"].values())
            or selection["selected"] != sum(bool(row["candidates"]) for row in native["source"]["probes"])
            or selection["refinement_attempts"] != sum(row["attempted"] for row in counts)
            or selection["changed"] != sum(row["changed"] for row in counts)
            or selection["choice"]["route"] not in ("history", "unfiltered")):
        raise ValueError("The frozen selector must bind original guard, actual edits, and selected detections")


def compare_factors(original, refined, candidate, selection):
    from collections import Counter
    from anchor_exposure import enroll
    from anchor_holds import history_rows
    from leo.contracts.digests import canonical_digest

    def metadata(row):
        return {key: value for key, value in row.items() if key != "candidates"}

    original_rows, exact_rows, found_rows = (packet["source"]["probes"] for packet in (original, refined, candidate))
    expected_rows = history_rows(original_rows) if selection["choice"]["route"] == "history" else original_rows
    max_delta = dict.fromkeys(ROUNDOFF, 0.0)
    retained, changed, exact_changed, mismatches = Counter(), Counter(), Counter(), Counter()
    changed_rows = []
    for source, projected, exact, actual, event in zip(original_rows, expected_rows, exact_rows, found_rows,
                                                       enroll(candidate), strict=True):
        if any(metadata(source) != metadata(row) for row in (projected, exact, actual)):
            raise ValueError("The comparison changed an original ordered signed opportunity")
        before, keep, reference, found = (row["candidates"] for row in (source, projected, exact, actual))
        if len(before) != len(reference) or len(before) > 1:
            raise ValueError("Archived exact refinement did not preserve original strongest factors")
        mode = event[4]
        if before:
            exact_changed[mode] += before[0][CFO] != reference[0][CFO]
        if bool(found) != bool(keep):
            mismatches["selection"] += 1
        if not found:
            continue
        retained[mode] += 1
        if not reference or len(found) != 1:
            mismatches["reference_factor"] += 1
            continue
        observed, expected = found[0], reference[0]
        if {k: v for k, v in observed.items() if k not in ROUNDOFF} != {
                k: v for k, v in expected.items() if k not in ROUNDOFF}:
            mismatches["position_rank_gate"] += 1
        for key, tolerance in ROUNDOFF.items():
            delta = abs(observed[key] - expected[key])
            max_delta[key] = max(max_delta[key], delta)
            if delta > tolerance:
                mismatches[key] += 1
        if abs(observed[CFO] - before[0][CFO]) > ROUNDOFF[CFO]:
            changed[mode] += 1
            changed_rows.append((actual["visit_index"], actual["receiver_id"], before[0][CFO], observed[CFO]))
    return dict(archived_pre_refinement_probes_sha256=canonical_digest(original_rows),
                recorded_pre_refinement_probes_sha256=selection["pre_refinement_probes_sha256"],
                retained=dict(retained), paid_exact_archived_cfo_edits=dict(exact_changed),
                retained_signed_edits_vs_exact_unamended=dict(changed), retained_changed_rows=changed_rows,
                max_abs_delta_from_exact_refinement=max_delta, mismatches=dict(mismatches))


def compare_figure(found, reference):
    return dict(file_equal=found["sha256"] == reference["sha256"],
                pixels_equal=found["rgba_sha256"] == reference["rgba_sha256"],
                dimensions_equal=tuple(found["size"]) == tuple(reference["size"]))


def seal(root):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from raw_cfo_north_trial import native_file

    binding = read(root / "binding.json")
    clock = read(root / "clock.json")
    if clock["exit_code"]:
        raise ValueError("The waveform process failed before the required scientific publication")
    for name, pin in binding["source_sha256"].items():
        path = HERE / name
        if path == Path(__file__).resolve():
            checkout = HERE.parents[2]
            original = subprocess.check_output(["git", "-C", str(checkout), "show",
                                                f"{binding['commit']}:{path.relative_to(checkout)}"])
            if sha256(original).hexdigest() != pin:
                raise ValueError("The recorded launch verifier source changed")
        else:
            checked(path, pin)
    reference, controls = references()
    if binding["historical"] != REFERENCE_PINS or binding["assignment"] != reference["assignment"]:
        raise ValueError("The frozen comparison denominator changed after launch")
    stock = controls["stock"]
    cache = {when: read(root / f"cache-{when}.json") for when in ("before", "after")}
    for side in cache.values():
        for census in side.values():
            require_resident(census)
    output = root / "containing"
    bootstrap = read(output / "unified-short-bootstrap.json")
    research = read(output / "joint-research-receipt.json")
    receipt, request = bootstrap["receipt"], binding["request"]
    candidate = publication_evidence(output, receipt, clock, binding["assignment"])
    native = candidate.pop("native")
    check_handoff(bootstrap, research, native, candidate, request)
    check_arms(candidate["verified"]["arms"])
    packet = native_file(output)
    route_path = root / "containing-held-cycle-refined.json"
    selection = read(route_path)
    check_selector(bootstrap, selection, native, request)
    if route_path.stat().st_mtime_ns > packet.stat().st_mtime_ns:
        raise ValueError("The route sidecar must seal before the selected packet enters publication")
    original, exact = (json.loads(checked(native_file(path), pin)) for path, pin in EXACT_PACKETS)
    features = compare_factors(original, exact, native, selection)
    if (candidate["opportunity_sha256"] != stock["opportunity_sha256"]
            or candidate["cutoff_utc_ns"] != stock["cutoff_utc_ns"]
            or not candidate["detector_ready_s"] <= candidate["verified"]["terminal_file_s"]
            <= candidate["report_ready_s"] <= clock["elapsed_s"]):
        raise ValueError("The signed opportunities or measured publication boundaries differ")
    store = FastStandardAnalysisStore(output)
    grid, path = store.position_grid(receipt["run_id"]), store.position_path(receipt["run_id"])
    if (not grid["matched_c_grid"] or grid["planned_points"] != len(grid["points"])
            or grid["evaluated_points"] != len(grid["points"]) or not path["stages"]):
        raise ValueError("Expected the complete matched calibration grid and position path")
    roles = {arm: research["selected_rows"][arm] for arm in ARM_NAMES}
    for arm, rows in roles.items():
        owners = {identifier: satellite for identifier, satellite, _ in rows}
        if not owners or len(owners) != len(rows) or canonical_digest(owners) != candidate["verified"]["owners"][arm]:
            raise ValueError("Ordered final observation rows must bind the verified arm owners")
    plots = {name: compare_figure(image, stock["figures"][name])
             for name, image in candidate["figures"].items()}
    write(root / "sealed.json", dict(binding_sha256=sha256((root / "binding.json").read_bytes()).hexdigest(),
        clock=clock, cache=cache, candidate=candidate, raw=bootstrap, packet=str(packet), owners=roles, plots=plots,
        selector_sha256=sha256(route_path.read_bytes()).hexdigest(), factors=features,
        verifier_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        stock_clock=stock["clock"], held_anchor_clock=controls["candidate"]["clock"],
        launch_to_detector_mb_s=COMPRESSED_BYTES / (1e6 * candidate["detector_ready_s"]),
        solver={name: research.get(name) for name in ("route", "route_details", "solve", "recovered_inference")}))


def score(root):
    from north_interlaced_raw import NORTH, TRUTH_SHA
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    sealed = root / "sealed.json"
    result = read(sealed)
    reference, controls = references()
    key_file = HERE.parent / "regional-release/scoring-key.json"
    key = json.loads(checked(key_file, TRUTH_SHA))
    (truth,) = {tuple(row["truth"]) for row in key["answers"].values() if row["recording"] == NORTH}
    offer = reference["assignment"]["offered_region"]
    truth_clearance = face_clearance_km(offer, truth)
    if abs(truth_clearance - 0.1) > 0.001:
        raise ValueError("Expected the original containing offer")
    candidates = dict(named=controls["stock"], prior_held_anchor=controls["candidate"], joint_held=result["candidate"])
    scores = {label: {arm: dict(position=values["latlon"], error_km=distance_km(truth, values["latlon"]),
                                rf_rms_hz=values["rf_rms_hz"], face_km=face_clearance_km(offer, values["latlon"]))
                      for arm, values in data["verified"]["arms"].items()} for label, data in candidates.items()}
    changes = {arm: scores["joint_held"][arm]["error_km"] - scores["named"][arm]["error_km"] for arm in ARM_NAMES}
    write(root / "score.json", dict(sealed_sha256=sha256(sealed.read_bytes()).hexdigest(), scoring_key_sha256=TRUTH_SHA,
                                   truth_face_km=truth_clearance, outcomes=scores, delta_named_error_km=changes,
                                   meets_containing_allowance=all(change <= 0.25 for change in changes.values())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("launch", "seal", "score"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    {"launch": launch, "seal": seal, "score": score}[args.mode](args.root)
