"""Run one fresh named-versus-combined saved publication on enrolled DS30-0169."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from family_endpoint_enroll import BINDINGS, CAP, DETECTOR, verified
from owner_loss_0402 import SOURCE_PINS
from prospective_0402_solver import ARMS, LIBRARIES, archive_plan, orbit_legends
from prospective_0316_solver import inspect, owner_delta, saved_inventory, verify_sources, worker


ENROLLMENT = HERE / "measurements/family-endpoint-transfer-enrollment.json"
ENROLLMENT_SHA = "0ce4e6ee4925c114d2723514082548b327ecd144e848adfbc55b5b83bfe12313"
ORDER = ("combined", "stock")
POLICY_PINS = SOURCE_PINS | {
    "isolated_salvage.py": "868bc79aa30e4548bd7979a79e458117583f4941cc374a8343568dc0a767d771",
    "endpoint_track_repair.py": "b3dc4ad2fe3c232b0b94f30bd1e81206aa11303748f0982442ce9006981c3a8a",
    "named_survivor_fit.py": "32b4f05449f6e4e0316d66b214a0564dfe4c14acfa413664e89333f40d8c1c2e",
    "provisional_salvage.py": "69dc94c6645f4b97cb6cadf79d7d0fc57a54138fc30cec176a4b5ab4729517af",
    "fragment_gate_cross.py": "a0a19352c3aecb845c8b291f033126f8c1f670c4e3d285d2e5d757ccd6306da0",
}
PRIOR = tuple(Path("/dev/shm") / name for name in ("leo-v3-saved-0402-pair-01", "leo-v3-saved-0160-pair-01",
                                                    "leo-v3-saved-0155-pair-01", "leo-v3-saved-0316-pair-01"))


def enrolled():
    return json.loads(verified(ENROLLMENT, ENROLLMENT_SHA))["selected"]


def settings(req):
    return dict(native_sha=req["native_sha256"], windows=req["issued"], admitted=req["admitted"],
                audit_name="family-endpoint-worker.json")


def stage_archive(enrollment, target):
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    source = Path(enrollment["original_archive"]["root"])
    desired = TleArchiveReader(source).list_snapshots("space-track")
    names = {ref.path.name: ref.sha256 for ref in desired}
    expected = enrollment["original_archive"]["snapshots_sha256"]
    size = sum(ref.byte_size for ref in desired)
    if (not 0 < size <= CAP or size != enrollment["archive_bytes"] or len(desired) != enrollment["snapshots"]
            or canonical_digest(names) != expected or any(r.collected_utc_ns >= enrollment["cutoff_utc_ns"] for r in desired)):
        raise ValueError("Bounded causal archive changed since enrollment")
    reusable = [s for folder in PRIOR for s in TleArchiveReader(folder / "tle").list_snapshots("space-track")]
    plan = archive_plan(desired, reusable)
    output = target / "archive/space-track"
    output.mkdir(parents=True)
    distinct, foreign_bytes, local_bytes = {}, 0, 0
    for name, row in plan.items():
        key = row["sha256"], row["bytes"]
        path = output / name
        if key in distinct:
            path.hardlink_to(distinct[key])
            continue
        origin = Path(row["source"]) if row["source"] else source / "archive/space-track" / name
        data = verified(origin, row["sha256"])
        if len(data) != row["bytes"]:
            raise ValueError("Verified archive snapshot has a different extent")
        path.write_bytes(data)
        distinct[key] = path
        if row["source"]:
            local_bytes += len(data)
        else:
            foreign_bytes += len(data)
    copied = TleArchiveReader(target).list_snapshots("space-track")
    if {r.path.name: r.sha256 for r in copied} != names or sum(r.byte_size for r in copied) != size:
        raise ValueError("Private stage lost a signed snapshot name or bytes")
    return dict(root=str(target), snapshots_sha256=expected, bytes=size, snapshots=len(copied),
                new_source_bytes=foreign_bytes, reused_bytes=local_bytes, distinct_payloads=len(distinct))


def stage(root, enrollment):
    from empty_bootstrap import bind_native
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest

    terminal = json.loads(verified(Path(enrollment["terminal"]), enrollment["terminal_sha256"]))
    raw = verified(Path(enrollment["packet"]), terminal["native_sha256"])
    native = json.loads(raw)
    source = native["source"]
    offer_bytes = Path(enrollment["offer"]).read_bytes()
    binding = json.loads(verified(BINDINGS / (enrollment["case"]+".json"), enrollment["binding_sha256"]))
    pair = json.loads(verified(Path(enrollment["pair"]), enrollment["pair_sha256"]))
    manifests = [[str(Path("/srv/bulk")/row["path"]), "sha256:"+row["sha256"]]
                 for row in binding["case"]["recording"]["segments"]]
    if (source["raw_recording_authority_digest"] != enrollment["authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != enrollment["cutoff_utc_ns"]
            or native["provenance"]["processed_windows"] != enrollment["admitted"] or source["probe_ms"] != 20
            or native["provenance"]["window_count"] != enrollment["issued"]
            or terminal["session_id"] != enrollment["session"]
            or Algo08Region.parse(json.loads(offer_bytes)).document() != terminal["region"]
            or manifests != [[r["path"], r["sha256"]] for r in pair["cache_observation"]["manifests"]]):
        raise ValueError("Archive enrollment, named receiver authority or offer disagree")
    inventory = source["input_manifest_sha256"]
    bind_native(native, enrollment["session"], inventory, DETECTOR, expected=terminal["native_sha256"])
    native_file, offer_file = root / "named-detections.json", root / "operator-offer.json"
    inventory_file = root / "inventory.json"
    native_file.write_bytes(raw)
    offer_file.write_bytes(offer_bytes)
    inventory_file.write_bytes(verified(Path(enrollment["inventory"]), inventory))
    local = stage_archive(enrollment, root / "tle")
    libraries = {}
    for name, (_, pin) in LIBRARIES.items():
        path = PRIOR[0] / f"{name}.so"
        verified(path, pin)
        libraries[name] = str(path)
    request = dict(case=enrollment["case"], issued=enrollment["issued"], admitted=enrollment["admitted"],
                   native_file=str(native_file), native_sha256=terminal["native_sha256"][7:],
                   offer_file=str(offer_file), offer_sha256=sha256(offer_bytes).hexdigest(), offer=terminal["region"],
                   session=enrollment["session"], inventory=inventory, manifests=manifests, recording=enrollment["recording"],
                   raw_authority=enrollment["authority"], causal_cutoff_utc_ns=enrollment["cutoff_utc_ns"],
                   local_archive=local, local_libraries=libraries, enrollment_sha256=ENROLLMENT_SHA)
    saved_inventory(request, inventory_file)
    if canonical_digest(json.loads(inventory_file.read_bytes())) != inventory:
        raise ValueError("Staged canonical inventory changed")
    return request


def invoke(job, mode, output):
    from aperture_trial import write
    import unified_short_bootstrap as entry

    req = json.loads(job.read_bytes())
    witness = {}
    original = entry.publish_active

    def active(args, *values, **options):
        from isolated_salvage import binding as isolate
        from named_survivor_fit import binding as finish

        # Install the exact 0402 composition. The isolated binding owns the endpoint attempt.
        args.direct_residual_figures = True
        args.direct_orbit_figures = True
        with isolate(), finish(witness):
            return original(args, *values, **options)

    with ExitStack() as scope:
        if mode == "combined":
            scope.enter_context(patch.object(entry, "publish_active", active))
        worker(job, "cumulative" if mode == "combined" else "stock", output, source_pins=POLICY_PINS,
               inventory_file=job.parent / "inventory.json", **settings(req))
    write(output / "bound-package.json", dict(mode=mode, entered_fixed_final_fit=bool(witness), witness=witness,
                                               policy_sha256=POLICY_PINS if mode == "combined" else {}))


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    verify_sources(verified, POLICY_PINS)
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use a fresh private tmpfs pair directory")
    root.mkdir()
    scratch = root / "tmp"
    scratch.mkdir()
    start_cpu, start_wall = process_time(), perf_counter()
    request = stage(root, enrolled())
    job = root / "request.json"
    write(job, request)
    write(root / "launch.json", dict(machine=machine, order=ORDER, stage_cpu_s=process_time()-start_cpu,
          stage_elapsed_s=perf_counter()-start_wall, source_sha256=POLICY_PINS,
          driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), waveform_calls=0))
    env = environment(root)
    env["TMPDIR"] = str(scratch)
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=20)
    for mode in ORDER:
        output = root / mode
        command = [python, "-IB", __file__, "worker", job, mode, output]
        clock = measure(command, env, output)
        write(root / f"{mode}-clock.json", dict(timing=clock, command=list(map(str, command))))
        if clock["exit_code"]:
            raise RuntimeError(f"The {mode} process did not complete; see its original measured receipt")


def score(root, output):
    from aperture_trial import read, write
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    request = read(root / "request.json")
    clocks = {m:read(root / f"{m}-clock.json")["timing"] for m in ORDER}
    if any(clock["exit_code"] for clock in clocks.values()):
        raise ValueError("Requires both original process clocks and terminals")
    captured = {}
    for mode in ORDER:
        directory = root / mode
        audit = read(directory / settings(request)["audit_name"])
        observed = inspect(directory, mode, audit["receipt"], clocks[mode], request, **settings(request))
        observed["combined_binding"] = read(directory / "bound-package.json")
        research = read(directory / "joint-research-receipt.json")
        observed["recovered_inference"] = research.get("recovered_inference")
        if observed["terminal"]["region"] != request["offer"]:
            raise ValueError("Publication region changed")
        captured[mode] = observed
    case = enrolled()
    old = json.loads(verified(Path(case["pair"]), case["pair_sha256"]))["runs"]["candidate"]
    stock = captured["stock"]
    science = stock["science"]
    if (any(old[k] != science[k] for k in ("arms", "owners", "raw_authority", "scientific_digests"))
            or old["receipt"]["terminal_sha256"] != science["receipt"]["terminal_sha256"]):
        raise ValueError("Fresh named solver differs from original signed named evidence")
    refs = json.loads(verified(REFERENCE, REFERENCE_SHA256))["cases"]
    match = [r["reference"] for r in refs if r["dataset_label"] == case["case"] and r["authority_eligible"]
             and r["sealed_metadata_digests_verified"]]
    truth = [match[0][k] for k in ("latitude_deg", "longitude_deg")] if len(match) == 1 else None
    scores = {mode: {arm: dict(horizontal_error_km=distance_km(truth, data["latlon"])
                      if truth and data["latlon"] else None, rf_rms_hz=data["rf_rms_hz"])
              for arm, data in run["terminal"]["arms"].items()} for mode, run in captured.items()}
    candidate = captured["combined"]
    differences = {arm:owner_delta(stock["selected_rows"].get(arm, []), candidate["selected_rows"].get(arm, [])) for arm in ARMS}
    figures = {name: dict(equal_png=img["sha256"] == stock["figures"][name]["sha256"],
                          equal_pixels=img["rgba_sha256"] == stock["figures"][name]["rgba_sha256"])
               for name, img in candidate["figures"].items() if name in stock["figures"]}
    write(output, dict(case=case["case"], enrollment=case, request=request, launch=read(root / "launch.json"),
                       results=captured, scores=scores, scores_reference=REFERENCE_SHA256 if truth else None,
                       owners=differences, figures=figures, named_matches_historical=True,
                       orbit_legend=orbit_legends(root / "combined", candidate) if candidate["figures"] else None,
                       waveform_calls=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("launch").add_argument("root", type=Path)
    child = commands.add_parser("worker")
    child.add_argument("job", type=Path)
    child.add_argument("mode", choices=ORDER)
    child.add_argument("output", type=Path)
    audit = commands.add_parser("score")
    audit.add_argument("root", type=Path)
    audit.add_argument("output", type=Path)
    args = vars(parser.parse_args())
    {"launch": launch, "worker": invoke, "score": score}[args.pop("action")](**args)
