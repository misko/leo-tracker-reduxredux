"""Run one candidate-first guarded selective-CFO DS30-0016 physical pair."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from continued_cfo_small_raw import ROUTE_FLAGS
from empty_bootstrap import RELEASE, checked
from guarded_cfo_0016_stage import INDEX, PAYLOAD, RECORDING, cache_states, fully_resident, signed_members
from guarded_cfo_small_raw import LIBRARIES, NORTH, NORTH_BINDING, NORTH_SEAL
from raw_0016_best_trial import ORIGINAL, frozen_sources, measure_mode


BASE = "c9e65f02fc18e125d36a07f5eeef28823fc1343b"
PRIOR = Path("/dev/shm/leo-v3-raw-0016-best-results-01")
PRIOR_ADMISSION = "bfd940c22e7cfac17040dbc95e4908ed3224370b5d19d27298d8412afc08e774"
RECIPE = "sha256:e49d5059997055d791239d18c0d5051c5060147ed4d8b6a8cbc608076bfbb29e"
CASE = ORIGINAL.workload
ORDER = CASE.order


def commands(root, pack, named):
    common = ["--recording", RECORDING, "--region", PRIOR / "offer.json", "--archive", PRIOR / "tle"]
    candidate = [RELEASE / "venv/bin/python", "-IB", HERE / "continued_cfo.py", "--anchored-cfo-pack", pack,
                 *common, "--output", root / "candidate"]
    for option, library in LIBRARIES.items():
        candidate.extend((option, PRIOR / (library + ".so")))
    return {"candidate": [*candidate, *ROUTE_FLAGS], "stock": [named, *common, "--bulk-root", root / "stock"]}


def upstream():
    from anchored_cfo_raw import verified_pack
    from full_short_physical import REGION_SHA
    from joint_held_north_raw import PACK, PACK_SHA
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    north = json.loads(checked(NORTH / "binding.json", NORTH_BINDING))
    guarded = json.loads(checked(NORTH / "sealed.json", NORTH_SEAL))
    previous = json.loads(checked(PRIOR / "admission.json", PRIOR_ADMISSION))
    recipe = guarded["raw"]["receiver_recipe"]
    if (north["pack_sha256"] != PACK_SHA or guarded["binding_sha256"] != NORTH_BINDING
            or canonical_digest(recipe) != RECIPE or guarded["raw"]["detector_recipe_sha256"] != RECIPE
            or previous["offer_sha256"] != REGION_SHA or previous["inventory"] != ORIGINAL.inventory
            or previous["archive"]["sha256"] != ORIGINAL.archive
            or archive_identity(PRIOR / "tle")["snapshots_sha256"] != ORIGINAL.archive):
        raise ValueError("Verified guarded recipe or original physical archive changed")
    for source, digest in north["source_sha256"].items():
        checked(HERE / source, digest)
    for option, name in LIBRARIES.items():
        pin = north["libraries"][option]["sha256"]
        if previous["library_sha256"][name] != pin:
            raise ValueError("The North and original DS30 solver library pins differ")
        checked(PRIOR / (name + ".so"), pin)
    checked(PACK / "pack.json", PACK_SHA)
    verified_pack(PACK)
    return recipe, PACK, PACK_SHA, previous


def seal(root):
    names = ["admission.json", "candidate-held-cycle-refined.json"]
    paths = [root / name for name in names]
    for mode in ORDER:
        paths.extend(root / f"{mode}{suffix}" for suffix in ("-clock.json", ".stdout", ".stderr"))
        paths.extend(path for path in (root / mode).rglob("*") if path.is_file())
    return {str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest() for path in sorted(paths)}


def launch(root, stage):
    from aperture_trial import write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from short_raw_diagnostic import pairs

    machine = host()
    receipt_bytes = (stage / "staging.json").read_bytes()
    staged = json.loads(receipt_bytes)
    staged_path = stage / RECORDING.name
    if staged["copied_bytes"]:
        if (not os.path.ismount(RECORDING) or os.stat(RECORDING)[:2] != os.stat(staged_path)[:2]
                or not os.statvfs(RECORDING).f_flag & os.ST_RDONLY):
            raise ValueError("Expected the prior stage at the signed canonical recording path")
    elif os.path.ismount(RECORDING):
        raise ValueError("Original residency path unexpectedly became a separate mount")
    signed, request, files, extents = signed_members()
    case = signed["case"]
    if (extents != staged["extents"] or staged["raw_authority"] != case["raw_authority"]
            or staged["inventory"] != ORIGINAL.inventory or not fully_resident(staged["benchmark_cache"])
            or staged["copied_bytes"] not in (0, sum(extents.values()))
            or canonical_digest(request["causal_snapshots"]) != ORIGINAL.archive):
        raise ValueError("The complete signed original and staging receipt must match")

    def resident():
        scopes = cache_states(files)
        if not fully_resident(scopes):
            raise ValueError("Both full segments must remain resident during the timed pair")
        return scopes[PAYLOAD] | {"index_cache": scopes[INDEX]}

    resident()
    recipe, pack, pack_sha, previous = upstream()
    source_sha = frozen_sources(BASE, ("continued_cfo.py", "anchored_cfo_raw.py", "short_cfo_raw.py",
                                       "held_cycle_refined.py", "anchor_cycle_route.py", "empty_family_calibration.py"))
    offer = previous["offer"]
    job = request["job"]
    if (offer["center"] != job["search_center"] or offer["screen_center"] != job["screen_center"]
            or job["evaluation_reference"] is not None or root.parent.stat().st_dev != Path("/dev/shm").stat().st_dev):
        raise ValueError("Original operator offer or local benchmark path changed")
    stock = pairs.verified_v3(pairs.NAMED_V3)
    argv = commands(root, pack, pairs.NAMED_V3)
    root.mkdir()
    (root / "tmp").mkdir()
    env = environment(root)
    env.update(TMPDIR=str(root / "tmp"), XDG_CACHE_HOME=str(root / "tmp"))
    write(root / "admission.json", dict(case=CASE.id, base=BASE, order=ORDER, machine=machine, stock=stock,
          stage_sha256=sha256(receipt_bytes).hexdigest(), stage=staged, prior_source_sha256=PRIOR_ADMISSION,
          north_binding_sha256=NORTH_BINDING, north_seal_sha256=NORTH_SEAL, pack_sha256=pack_sha, receiver_recipe=recipe,
          recipe_sha256=RECIPE, sources=source_sha, route_flags=ROUTE_FLAGS, binding=CASE.binding_sha,
          request=case["request"]["sha256"], inventory=ORIGINAL.inventory, cutoff_utc_ns=ORIGINAL.cutoff_ns,
          offer=offer, offer_sha256=previous["offer_sha256"], issued=CASE.windows, admitted=ORIGINAL.admitted,
          archive=previous["archive"], recording=str(RECORDING), raw_authority=case["raw_authority"],
          session=case["session_id"], library_sha256=previous["library_sha256"],
          driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))
    for mode in ORDER:
        measure_mode(root, mode, argv[mode], env, resident, require_success=False)
    write(root / "prediction-seal.json", seal(root))


def score(root, output):
    from aperture_trial import read, write
    from joint_held_north_raw import check_arms, check_selector
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from prospective_0155_solver import orbit_legends
    from raw_0016_best_score import owner_comparison, process_rows
    from triage_bounds import calibration_comparison

    prediction = root / "prediction-seal.json"
    if read(prediction) != seal(root):
        raise ValueError("Raw process evidence changed before scoring")
    admission = read(root / "admission.json")
    bootstrap = read(root / "candidate/unified-short-bootstrap.json")
    if (admission["recipe_sha256"] != RECIPE or bootstrap["receiver_recipe"] != admission["receiver_recipe"]
            or canonical_digest(bootstrap["receiver_recipe"]) != RECIPE or bootstrap["detector_recipe_sha256"] != RECIPE):
        raise ValueError("Runtime receiver differed from the complete guarded North and DS30-0107 recipe")
    runs = process_rows(root, admission, ORIGINAL, candidate_recipe=RECIPE[7:], archive_root=PRIOR / "tle")
    candidate, stock = (runs[name] for name in ORDER)
    if (candidate["opportunities"] != stock["opportunities"] or candidate["probes"] != stock["probes"]
            or candidate["process"]["clock"]["started_unix_ns"] >= stock["process"]["clock"]["started_unix_ns"]):
        raise ValueError("Candidate-first order or original radio opportunities changed")
    selection = read(root / "candidate-held-cycle-refined.json")
    native = read(native_packet(root / "candidate"))
    check_selector(bootstrap, selection, native, admission)
    for name, run in runs.items():
        if run["science"]["receipt"]["decision"] == "complete":
            check_arms(run["science"]["arms"])
            store = FastStandardAnalysisStore(root / name)
            if not store.position_grid(run["science"]["receipt"]["run_id"])["matched_c_grid"]:
                raise ValueError("Complete publication must use a matched calibration grid")
    complete_pair = all(run["science"]["receipt"]["decision"] == "complete" for run in runs.values())
    owners = owner_comparison(runs) if complete_pair else None
    legends = (orbit_legends(root / "candidate", dict(
        worker=dict(layout=bootstrap["one_pass_web_png"], receipt=candidate["science"]["receipt"]),
        selected_rows=candidate["research"]["selected_rows"], figures=candidate["figures"]))
        if candidate["science"]["receipt"]["decision"] == "complete" else None)
    calibrations = calibration_comparison({name: run["science"] for name,run in runs.items()}, CASE.id)
    clocks = {name: run["process"]["clock"] for name,run in runs.items()}
    write(output, dict(admission=admission, runs=runs, selection=selection, owners=owners, orbit_legends=legends,
          calibrations=calibrations, pre_score_sha256=sha256(prediction.read_bytes()).hexdigest(),
          speedup=clocks["stock"]["elapsed_s"]/clocks["candidate"]["elapsed_s"],
          cpu_speedup=clocks["stock"]["cpu_s"]/clocks["candidate"]["cpu_s"], new_launches=list(ORDER)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("launch", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("input_or_output", type=Path)
    args = parser.parse_args()
    (launch if args.mode == "launch" else score)(args.root, args.input_or_output)
