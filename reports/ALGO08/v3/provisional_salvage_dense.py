"""Run one saved full mixed-aperture transfer of the frozen salvage policy."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from prospective_0316_solver import ARMS, inspect, owner_delta, verify_sources
from prospective_small_physical import checked
from provisional_salvage_trial import HERE, PINS, candidate_worker


CASE = "DS30-0008"
STAGED = Path("/dev/shm/leo-held-anchor-selected-dense-01")
CONTROL = Path("/dev/shm/leo-cumulative-dense-graph.LiGWLkSN/trial")
REQUEST_SHA = "8abec0e2f60def947cd03883662611c3fcfdbd5f255eb0ba60e8306085abf502"
CONTROL_SHA = "f335120b34ddc8775a55fee321a28826c7bbecfadf6fb16f2efcf335473e387d"
TRACE_SHA = "992f14f511bf7289cb04b8eef3a8f0bbb2921abb5ac0e842df0edf6b6e32e914"
INVENTORY_SHA = "3f08c51c74fa878e0b5993311a840172c2b06d2d0be02988d13f0c29f502034b"
SETTINGS = dict(native_sha="ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85",
                windows=6772, admitted=6765, audit_name="provisional-salvage-dense-worker.json",
                detector="13c4ecdb521d02960e61572e8d401a54f165e2c7882112889ede0582abb3ca40",
                input_description="authenticated saved original unfiltered 20/12 ms packet")
PROTOCOL = HERE / "provisional-salvage-dense-protocol.md"


def trigger(support):
    dropped = set(support["second_curved_rejections"])
    missed = [row["selected"]["points"] for row in support["salvage"]
              if row["selected"] is not None and row["component"] in dropped]
    return dict(eligible=bool(missed and support["past_distribution_qualified"]),
                initial_curved=support["initial_curved"], restored=support["curved_restored"],
                rechecked_curved=support["rechecked_curved"], lost_restored_points=sum(missed),
                lost_restored_tracks=len(missed))


def preflight():
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    request = json.loads(checked(STAGED / "request.json", REQUEST_SHA))
    trace = json.loads(checked(CONTROL / "reused/joint-research-receipt.json", TRACE_SHA))
    if trace["receipt"]["session_id"] != request["session"]:
        raise ValueError("The trigger and unfiltered request describe different native acquisitions")
    support = trigger(trace["route_details"]["support"])
    if support != dict(eligible=True, initial_curved=3391, restored=833, rechecked_curved=3661,
                       lost_restored_points=563, lost_restored_tracks=16):
        raise ValueError("The frozen trace no longer authorizes a paid run")
    archive, native = Path(request["archive"]["root"]), Path(request["original"]["file"])
    inventory_path = STAGED / "selected/fast-scan-inputs" / f"{request['session']}.json"
    local = [archive, inventory_path, native, Path(request["offer"]), *(Path(p) for p in request["libraries"].values())]
    if (any(not path.resolve(strict=True).is_relative_to(STAGED) for path in local)
            or archive_identity(archive)["snapshots_sha256"] != request["archive"]["snapshots_sha256"]):
        raise ValueError("The trial may use only the exact already staged inputs")
    inventory = json.loads(checked(inventory_path, INVENTORY_SHA))
    checked(native, SETTINGS["native_sha"])
    if (request["original"]["detector"] != SETTINGS["detector"] or request["inventory"] != "sha256:"+INVENTORY_SHA
            or inventory["window_count"] != SETTINGS["windows"] or len(inventory["segments"]) != 14):
        raise ValueError("The staged recording no longer matches the full unfiltered aperture")
    handoff = dict(recording=request["recording"], session=request["session"], inventory=request["inventory"],
                   raw_authority=request["authority"], local_archive=request["archive"], local_libraries=request["libraries"],
                   native_file=str(native), offer_file=request["offer"], offer_sha256=request["offer_sha256"],
                   causal_cutoff_utc_ns=request["cutoff_utc_ns"], manifests=[
                       [str(Path(row["path"]) / "manifest.json"), row["manifest_digest"]] for row in inventory["segments"]])
    return handoff, inventory_path, support


def run(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    verify_sources(checked, PINS)
    request, inventory, support = preflight()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Expected a fresh tmpfs output")
    root.mkdir()
    (root / "tmp").mkdir()
    write(root / "request.json", request)
    write(root / "seal.json", dict(machine=machine, request_sha256=REQUEST_SHA, archived_trigger_sha256=TRACE_SHA,
                                  trigger=support, protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest(),
                                  source_sha256=PINS, driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))
    output = root / "candidate"
    env = environment(STAGED)
    env["TMPDIR"] = str(root / "tmp")
    command = [RELEASE / "venv/bin/python", "-IB", __file__, "worker", root / "request.json", inventory, output]
    clock = measure(command, env, output)
    write(root / "candidate-clock.json", dict(timing=clock, command=list(map(str, command))))


def evaluate(root, output):
    from aperture_trial import read, write
    from leo.storage.fast_scan import FastScanStore
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    clock = read(root / "candidate-clock.json")["timing"]
    request = read(root / "request.json")
    if clock["exit_code"]:
        raise ValueError("The sealed candidate worker did not complete")
    candidate_dir = root / "candidate"
    result = inspect(candidate_dir, "cumulative", read(candidate_dir / SETTINGS["audit_name"])["receipt"], clock, request, **SETTINGS)
    research = read(candidate_dir / "joint-research-receipt.json")
    trace = json.loads(checked(CONTROL / "reused/joint-research-receipt.json", TRACE_SHA))
    control = json.loads(checked(CONTROL / "result.json", CONTROL_SHA))["runs"]["reused"]
    control_directory = FastScanStore(CONTROL / "reused").automatic_workspace(trace["receipt"]["run_id"], create=False)
    terminal = json.loads(checked(control_directory / "terminal.json", trace["receipt"]["terminal_sha256"]))
    if (control["science"]["raw_authority"] != request["raw_authority"] or not result["worker"]["graph"]["enabled"]
            or control["science"]["receipt"]["session_id"] != request["session"]
            or terminal["native_sha256"] != "sha256:"+SETTINGS["native_sha"]):
        raise ValueError("The independent signed control does not match issued inputs and graph")
    audit = research["route_details"]["provisional_salvage"]
    if audit["fit_calls"] != 1:
        raise ValueError("The archived trigger did not exercise the one-fit rule")
    refs = json.loads(checked(REFERENCE, REFERENCE_SHA256))
    location, = (row["reference"] for row in refs["cases"] if row["dataset_label"] == CASE and row["authority_eligible"]
                 and row["sealed_metadata_digests_verified"])
    truth = [location[k] for k in ("latitude_deg", "longitude_deg")]
    arms = {name: {a: dict(horizontal_error_km=distance_km(truth, row["latlon"]) if row["latlon"] else None,
                           rf_rms_hz=row.get("rf_rms_hz")) for a, row in run["science"]["arms"].items()}
            for name, run in (("historical_cumulative", control), ("provisional", result))}
    owners = {a: owner_delta(trace["selected_rows"][a], result["selected_rows"].get(a, [])) for a in ARMS}
    figs = {name: dict(row, size=list(row["size"])) for name, row in result["figures"].items()}
    equality = dict(terminal=result["terminal"] == terminal, images=figs == control["images"],
                    path_and_grid=result["science"]["scientific_digests"] == control["science"]["scientific_digests"])
    if audit["status"] == "reverted" and (not all(equality.values()) or any(not own["identical_ordered_rows"] for own in owners.values())):
        raise ValueError("The same original route did not reproduce the complete archived numerical evidence")
    write(output, dict(case=CASE, no_waveform=True, settings=SETTINGS, seal=read(root / "seal.json"), reference_sha=REFERENCE_SHA256,
                       candidate=result, research=research, historical_control=control, arms=arms, owners=owners,
                       equality_vs_historical=equality))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    actions = cli.add_subparsers(dest="action", required=True)
    launch = actions.add_parser("run")
    launch.add_argument("root", type=Path)
    child = actions.add_parser("worker")
    for name in ("request", "inventory", "output"):
        child.add_argument(name, type=Path)
    audit = actions.add_parser("evaluate")
    audit.add_argument("root", type=Path)
    audit.add_argument("output", type=Path)
    args = cli.parse_args()
    if args.action == "run":
        run(args.root)
    elif args.action == "evaluate":
        evaluate(args.root, args.output)
    else:
        candidate_worker(CASE, args.request, args.inventory, args.output, runtime=SETTINGS)
