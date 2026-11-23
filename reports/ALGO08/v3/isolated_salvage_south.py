"""Replay the measured combined option on two existing South offers."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from shutil import copyfile
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from prospective_0316_solver import ARMS, DETECTOR, LIBRARIES, verify_sources, worker
from prospective_small_physical import checked


MODES = ("containing", "near-omitted")
BENCH = Path("/tmp/leo-algo08v2-2x-bench")
ORIGINAL = BENCH / "exact-curved-lookahead-south-inside"
ARCHIVED_NEAR = BENCH / "exact-curved-lookahead-south-offers.json"
PAIR_SHA = "48fed3c62639ef81fb99e4b76921bcacd999e769a78ebb607b2b886b6f0951f0"
NEAR_SHA = "5181abf1c8a36d45dfe140e8851f0a423b69ec69b8ca231a3f87bcc9fdcecca9"
INSIDE_OFFER_SHA = "471704a6dfcfd4acdb72f3aacae638fe8f6ae6a796b01dd59cfd3d7a9d92610c"
NATIVE_SHA = "26e4ce9c24e81761e4d92cf05e29474e4ced9ba4effdffff89b817c0ea9f9ce3"
INVENTORY_SHA = "d5faad1ea8ba6a2df7dea75db1f9df27efb374f4671b5ae3df200e595d84fa4c"
TRUTH_SHA = "0bda865a20e62852220a9ab8df63895a449bf203a2deb5370920dc3ce215d37d"
DEV_LAUNCH = Path("/dev/shm/leo-v3-isolated-salvage-0402-run01/launch.json")
DEV_LAUNCH_SHA = "44bb7a44fcac00c42cedf35c40134653ed52eb4bc2fa838afd989f6fc86d1aab"
DEV_ROOT = Path("/dev/shm/leo-v3-saved-0402-pair-01")
SETTINGS = dict(native_sha=NATIVE_SHA, windows=1200, admitted=1200, audit_name="isolated-south-worker.json")
PROTOCOL = HERE / "isolated-salvage-south-protocol.md"


def read(path, pin):
    return json.loads(checked(path, pin))


def inherited_sources():
    pins = read(DEV_LAUNCH, DEV_LAUNCH_SHA)["source_sha256"]
    verify_sources(checked, pins)
    return pins


def enrollment():
    from aperture_trial import archive_identity
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest

    pair = read(ORIGINAL / "pair.json", PAIR_SHA)
    near = read(ARCHIVED_NEAR, NEAR_SHA)
    stock = pair["runs"]["candidate"]
    region = Path(pair["region"])
    inside = Algo08Region.parse(read(region, INSIDE_OFFER_SHA)).document()
    near_offer = near["results"]["south-mirror-outside"]
    inherited = pair["archive"]
    archive = Path(inherited["root"])
    native_path, = (ORIGINAL / "candidate/fast-scan-automatic-work").glob("*/detections.json")
    native = read(native_path, NATIVE_SHA)
    inventory_path = ORIGINAL / "candidate/fast-scan-inputs" / (stock["receipt"]["session_id"]+".json")
    inventory = read(inventory_path, INVENTORY_SHA)
    terminal = read(native_path.parent.parent / stock["receipt"]["run_id"] / "terminal.json", stock["receipt"]["terminal_sha256"])
    source = native["source"]
    if (near["pair_sha256"] != PAIR_SHA or near["native_sha256"] != "sha256:"+NATIVE_SHA
            or near["specification"] != pair["candidate_specification_digest"] or near["archive"] != inherited
            or archive_identity(archive) != inherited or terminal["native_sha256"] != canonical_digest(native)
            or inside != terminal["region"] or inside != stock["receipt"]["region"]
            or source["input_manifest_sha256"] != canonical_digest(inventory)
            or source["session_id"] != stock["receipt"]["session_id"] or stock["raw_authority"] != source["raw_recording_authority_digest"]
            or native["provenance"]["detector_sha256"] != "sha256:"+DETECTOR
            or source["probe_ms"] != 20 or native["provenance"]["processed_windows"] != SETTINGS["admitted"]
            or near_offer["status"] != "ok" or not -0.101 < near_offer["truth_clearance_km"] < -0.099):
        raise ValueError("The historical controls do not share the exact signed native packet and archive")
    local_libraries = {}
    for name, (_, pin) in LIBRARIES.items():
        path = DEV_ROOT / (name+".so")
        checked(path, pin)
        local_libraries[name] = str(path)
    request = dict(recording=pair["recording"], native_file=str(native_path), session=source["session_id"],
                   inventory=source["input_manifest_sha256"], raw_authority=source["raw_recording_authority_digest"],
                   causal_cutoff_utc_ns=native["clock_anchor"]["before"]["realtime_ns"], local_archive=inherited,
                   local_libraries=local_libraries, manifests=[[str(Path(row["path"])/"manifest.json"), row["manifest_digest"]]
                                                              for row in inventory["segments"]])
    controls = {
        "containing": dict(status=terminal["decision"], arms=stock["arms"], owners=stock["owners"], offer=inside,
                           raw_elapsed_s=stock["elapsed_s"], raw_cpu_s=stock["cpu_s"], actual_terminal_sha256=stock["receipt"]["terminal_sha256"]),
        "near-omitted": near_offer,
    }
    return request, inventory_path, controls


def candidate(job, inventory, output):
    import unified_short_bootstrap as entry

    original = entry.publish_active

    def publish(args, *values, **options):
        from isolated_salvage import binding

        args.direct_residual_figures = True
        args.direct_orbit_figures = True
        with binding():
            return original(args, *values, **options)

    with patch.object(entry, "publish_active", publish):
        worker(job, "cumulative", output, source_pins=inherited_sources(), inventory_file=inventory, **SETTINGS)


def write(path, document):
    with path.open("x") as handle:
        json.dump(document, handle, sort_keys=True, indent=2, allow_nan=False)
        handle.write("\n")


def launch(root):
    from aperture_trial import RELEASE
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    pins = inherited_sources()
    request, inventory, controls = enrollment()
    paths = (root.parent, Path(request["native_file"]), Path(request["local_archive"]["root"]))
    if any(subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", path], text=True).strip() != "tmpfs" for path in paths):
        raise ValueError("The signed input, archive and output must already be on tmpfs")
    root.mkdir()
    for name in ("tmp", "fonts"):
        (root / name).mkdir()
    copyfile(DEV_ROOT / "fonts/fontlist-v3.11.0.json", root / "fonts/fontlist-v3.11.0.json")
    write(root / "seal.json", dict(machine=machine, inherited=pins, development_receipt_sha256=DEV_LAUNCH_SHA,
                                  pair_sha256=PAIR_SHA, near_sha256=NEAR_SHA, modes=MODES,
                                  protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest(),
                                  adapter_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    for mode in MODES:
        offer_file = root / (mode+"-offer.json")
        write(offer_file, controls[mode]["offer"])
        path = root / (mode+"-request.json")
        write(path, dict(request, offer_file=str(offer_file), offer_sha256=sha256(offer_file.read_bytes()).hexdigest()))
        target = root / mode
        command = [RELEASE / "venv/bin/python", "-IB", __file__, "candidate", path, inventory, target]
        timing = measure(command, env, target)
        write(root / (mode+"-clock.json"), dict(timing=timing, command=list(map(str, command))))


def decision_label(result, clearance):
    if result not in ("ok", "complete", "withheld"):
        raise ValueError("Expected a verified geographic decision")
    if result == "withheld":
        return "withheld" if clearance < 0. else "false_withhold"
    return "false_fix" if clearance < 0. else "fix"


def assess_case(root, mode, control, site):
    from aperture_score import face_clearance_km
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.qualification.paired_publication import evidence
    from tools.pipeline_eval.scoring import distance_km

    clock = json.loads((root / (mode+"-clock.json")).read_bytes())["timing"]
    if clock["exit_code"]:
        return dict(process=clock, status="failed")
    out = root / mode
    chosen = json.loads((out / "joint-research-receipt.json").read_bytes())
    own = json.loads((out / SETTINGS["audit_name"]).read_bytes())
    request = json.loads((root / (mode+"-request.json")).read_bytes())
    receipt = own["receipt"]
    terminal_path, = out.glob("fast-scan-automatic-work/*/terminal.json")
    detector, = out.glob("fast-scan-automatic-work/*/detections.json")
    terminal = read(terminal_path, receipt["terminal_sha256"])
    if (not own["no_waveform"] or own["handoffs"] != 1 or own["native_sha256"] != NATIVE_SHA
            or sha256(detector.read_bytes()).hexdigest() != NATIVE_SHA or terminal["native_sha256"] != "sha256:"+NATIVE_SHA
            or control["offer"] != receipt["region"] or terminal["region"] != receipt["region"]
            or not own["graph"]["enabled"] or receipt != chosen["receipt"]):
        raise ValueError("The candidate route or published native binding changed")
    science = evidence(out, receipt, clock["started_unix_ns"], read_only=True)
    proof = artifacts(out, receipt)
    if science["raw_authority"] != request["raw_authority"] or json.loads(json.dumps(proof)) != chosen["evidence"]:
        raise ValueError("The observed publication differs from the recorded evidence")
    grid_points = None
    if receipt["decision"] == "complete":
        store = FastStandardAnalysisStore(out)
        path, grid = store.position_path(receipt["run_id"]), store.position_grid(receipt["run_id"])
        grid_points = grid["evaluated_points"]
        if (not grid_points or not grid["complete"] or grid_points != grid["planned_points"] or len(proof["images"]) != 8
                or any(doc["binding"]["position_png_sha256"] != proof["images"]["position"]["sha256"] for doc in (path, grid))
                or any(canonical_digest({oid: sat for oid, sat, _ in chosen["selected_rows"][arm]}) != science["owners"][arm]
                       for arm in ARMS)):
            raise ValueError("Incomplete authentic output for a published fix")
    clearance = face_clearance_km(control["offer"], site)

    def position(arms):
        return {arm: dict(position=record["latlon"], rf_rms_hz=record.get("rf_rms_hz"),
                          error_km=distance_km(site, record["latlon"]) if record["latlon"] else None) for arm, record in arms.items()}

    route = chosen.get("route_details") or {}
    isolated = route.get("provisional_salvage", {})
    return dict(status=decision_label(receipt["decision"], clearance), controls_status=decision_label(control["status"], clearance),
                candidate=position(terminal["arms"]), named=position(control["arms"]), clearance_km=clearance,
                process=clock, worker=own, grid_points=grid_points, evidence=proof, science=science,
                raw_status=receipt["decision"], same_owner_digest=science["owners"] == control["owners"],
                selected_roles=chosen["selected_roles"], selected_rows=chosen.get("selected_rows", {}),
                route=chosen["route"], isolated=isolated, endpoint=route.get("endpoint_trim", isolated.get("endpoint_trim")),
                early=chosen.get("early_regional"), recovery=chosen.get("recovered_inference"),
                exterior=route.get("exterior"), signed=route.get("signed"), ordinary_repair=route.get("repair"),
                named_archived=control)


def score(root, output):
    request, _, controls = enrollment()
    launch_seal = json.loads((root / "seal.json").read_bytes())
    if launch_seal["adapter_sha256"] != sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("The saved adapter differs from the launched source")
    scoring = read(HERE.parent / "regional-release/scoring-key.json", TRUTH_SHA)
    site, = {tuple(row["truth"]) for row in scoring["answers"].values()
             if row["recording"] == Path(request["recording"]).name}
    write(output, dict(seal=launch_seal, request=request, truth_sha256=TRUTH_SHA, waveform_calls=0,
                       comparisons={mode: assess_case(root, mode, controls[mode], site) for mode in MODES}))


if __name__ == "__main__":
    app = argparse.ArgumentParser(description=__doc__)
    stages = app.add_subparsers(dest="stage", required=True)
    for action, arguments in (("launch", ("root",)), ("candidate", ("job", "inventory", "output")),
                              ("score", ("root", "output"))):
        sub = stages.add_parser(action)
        for name in arguments:
            sub.add_argument(name, type=Path)
    args = vars(app.parse_args())
    globals()[args.pop("stage")](**args)
