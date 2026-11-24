"""Verify a one-child guarded continuation transfer on the existing whole DS30-0107 stage."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from continued_cfo_small_raw import CASE, INPUTS, RECORDING, ROUTE_FLAGS, input_inventory, prediction_seal, residency
from empty_bootstrap import RELEASE, checked


PRIOR = Path("/dev/shm/leo-v3-continued-cfo-0107-pair01")
NORTH = Path("/dev/shm/leo-v3-continued-north-result01")
PRIOR_RESULT = "6403e569639637fdeecbfa18ba97d2d299460c90cd3aeaa2b1fa3602b8c9bf80"
PRIOR_SEAL = "f53118ac2659b2f7c1d46e375fae821f481987be8ac0bdc49b1230d79a3f4f48"
NORTH_BINDING = "ed37b61ea850c8f6eca9362c17a06c97fa141b0323a327ece77bd0285337ac3b"
NORTH_SEAL = "4411ba5508e7cec22d0ded179af3da1d50fc2c8a3e75c235852a646e66dfb424"
LIBRARIES = {
    "--short-binary": "short",
    "--geographic-library": "geographic",
    "--regional-track-library": "regional",
    "--frontier-block-library": "block",
    "--grid-feature-projection-library": "projection",
}


def controls():
    from aperture_trial import read
    from joint_held_north_raw import PACK, PACK_SHA
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    previous = json.loads(checked(PRIOR / "result.json", PRIOR_RESULT))
    existing_seal = json.loads(checked(PRIOR / "prediction-seal.json", PRIOR_SEAL))
    north = json.loads(checked(NORTH / "binding.json", NORTH_BINDING))
    remote = json.loads(checked(NORTH / "sealed.json", NORTH_SEAL))
    north_recipe = remote["raw"]["receiver_recipe"]
    admission = previous["admission"]
    north_flags = set(ROUTE_FLAGS) - {"--withhold-empty-family-calibration"}
    if (existing_seal != prediction_seal(PRIOR) or admission != read(PRIOR / "admission.json")
            or previous["prediction_seal_sha256"] != PRIOR_SEAL or previous["case"] != CASE.id
            or remote["binding_sha256"] != NORTH_BINDING or north["pack_sha256"] != PACK_SHA
            or tuple(admission["route_flags"]) != ROUTE_FLAGS
            or not north_flags <= set(north["command"])
            or canonical_digest(north_recipe) != remote["raw"]["detector_recipe_sha256"]
            or archive_identity(PRIOR / "tle")["snapshots_sha256"] != INPUTS.archive):
        raise ValueError("The previously sealed matched inputs or the guarded North recipe changed")
    checked(PRIOR / "offer.json", admission["offer_sha256"])
    for each, digest in north["source_sha256"].items():
        checked(HERE / each, digest)
    for flag, name in LIBRARIES.items():
        pin = north["libraries"][flag]["sha256"]
        if admission["library_sha256"][name] != pin:
            raise ValueError("DS30 and North solver library pins differ")
        checked(PRIOR / (name + ".so"), pin)
    checked(PACK / "pack.json", PACK_SHA)
    from anchored_cfo_raw import verified_pack

    verified_pack(PACK)
    return previous, north, north_recipe


def command(output, pack):
    argv = [RELEASE / "venv/bin/python", "-IB", HERE / "continued_cfo.py", "--anchored-cfo-pack", pack,
            "--recording", RECORDING, "--archive", PRIOR / "tle", "--region", PRIOR / "offer.json",
            "--output", output / "candidate"]
    for flag, name in LIBRARIES.items():
        argv.extend((flag, PRIOR / (name + ".so")))
    return [*argv, *ROUTE_FLAGS]


def candidate_seal(root):
    paths = [root / name for name in ("binding.json", "candidate-clock.json", "candidate-held-cycle-refined.json",
                                     "candidate.stdout", "candidate.stderr")]
    paths.extend(path for path in (root / "candidate").rglob("*") if path.is_file())
    return {str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest() for path in sorted(paths)}


def launch(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from joint_held_north_raw import PACK, PACK_SHA
    from raw_0016_best_trial import measure_mode
    from short_raw_diagnostic import require_warm

    machine = host()
    previous, north, recipe = controls()
    staged = PRIOR / RECORDING.name
    if (not os.path.ismount(RECORDING) or os.stat(RECORDING)[:2] != os.stat(staged)[:2]
            or not os.statvfs(RECORDING).f_flag & os.ST_RDONLY
            or root.parent.stat().st_dev != Path("/dev/shm").stat().st_dev):
        raise ValueError("Expected the pre-existing full original under a private read-only tmpfs bind")
    session, members = input_inventory()
    admission = previous["admission"]
    if session != admission["session"]:
        raise ValueError("The staged original no longer binds its signed session")

    def resident():
        observed = residency(members)
        for cache in observed.values():
            require_warm(cache)
        return observed["payload"] | {"index_cache": observed["index"]}

    root.mkdir()
    (root / "tmp").mkdir()
    env = environment(root)
    env.update(TMPDIR=str(root / "tmp"), XDG_CACHE_HOME=str(root / "tmp"))
    write(root / "binding.json", dict(case=CASE.id, prior_result_sha256=PRIOR_RESULT,
          prior_prediction_sha256=PRIOR_SEAL, north_binding_sha256=NORTH_BINDING, north_seal_sha256=NORTH_SEAL,
          pack_sha256=PACK_SHA, machine=machine, offer=admission["offer"], archive=admission["archive"],
          original_session=session, expected_north_recipe=recipe, sources=north["source_sha256"],
          driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))
    measure_mode(root, "candidate", command(root, PACK), env, resident, require_success=False)
    write(root / "prediction-seal.json", candidate_seal(root))


def verify(root, result):
    from aperture_trial import read, write
    from continued_cfo_north_trial import compare_rows
    from joint_held_north_raw import compare_factors
    from leo.contracts.digests import canonical_digest
    from local_future_cli_trial import native_packet
    from raw_0016_best_score import process_rows

    seal = root / "prediction-seal.json"
    if read(seal) != candidate_seal(root):
        raise ValueError("The sealed guarded publication changed")
    previous, north, recipe = controls()
    saved = previous["runs"]
    binding = read(root / "binding.json")
    admission = previous["admission"] | {"sources": north["source_sha256"]}
    bootstrap = read(root / "candidate/unified-short-bootstrap.json")
    choice = read(root / "candidate-held-cycle-refined.json")
    pin = canonical_digest(recipe)
    if (binding["sources"] != admission["sources"] or binding["expected_north_recipe"] != recipe
            or bootstrap["receiver_recipe"] != recipe or bootstrap["detector_recipe_sha256"] != pin
            or choice != bootstrap["held_anchor_route"] or choice["selected_recipe_sha256"] != pin
            or choice["selected_native_sha256"] != bootstrap["native_sha256"]):
        raise ValueError("The live receiver did not execute the sealed North guarded/continued recipe")
    run = process_rows(root, admission, INPUTS, modes=("candidate",), candidate_recipe=pin[7:],
                       archive_root=PRIOR / "tle")["candidate"]
    raw_stock = saved["stock"]["science"]
    if (run["science"]["receipt"]["decision"] != "withheld"
            or run["science"]["reason"] != raw_stock["reason"] or run["science"]["arms"] != raw_stock["arms"]
            or run["opportunities"] != saved["stock"]["opportunities"] or run["figures"] or run["sidecars"]):
        raise ValueError("Guarded outcome, signed opportunities, or withheld artifacts differ from the named control")
    (old_native, new_native) = (json.loads(checked(native_packet(folder), row["native_file_sha256"]))
                                for folder,row in ((PRIOR / "candidate", saved["candidate"]), (root / "candidate", run)))
    chronologies = compare_rows(new_native["source"]["probes"], old_native["source"]["probes"])
    if any(new_native[key] != old_native[key] for key in ("clock_anchor", "delivery_clocks")):
        raise ValueError("The guarded candidate did not use the same physical timeline")
    old_choice = saved["candidate"]["bootstrap"]["held_anchor_route"]
    if (any(selection["choice"]["route"] != "unfiltered" or selection["refinement_attempts"]
            for selection in (choice, old_choice))):
        raise ValueError("The exact unamended packet must be the original factor control")
    roundoff = compare_factors(old_native, old_native, new_native, choice)
    if roundoff["mismatches"]:
        raise ValueError("Guarded continuation changed factor membership or exceeded the North roundoff limits")
    write(result, dict(case=CASE.id, admission=binding, guarded=run, prior=saved,
         exact_detector_comparison=chronologies | {"roundoff": roundoff}, solver_route=bootstrap["route"],
         calibrations=previous["calibrations"], verification_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
         new_waveform_backing_bytes=0, new_archive_backing_bytes=0, new_conditioning_bytes=0,
         prediction_seal_sha256=sha256(seal.read_bytes()).hexdigest(),
         guarded_launches=1, new_stock_launches=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("launch", "verify"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--receipt", type=Path)
    options = parser.parse_args()
    if options.mode == "launch":
        if options.receipt is not None:
            parser.error("--receipt applies to verification")
        launch(options.root)
    else:
        verify(options.root, options.receipt or options.root / "result.json")
