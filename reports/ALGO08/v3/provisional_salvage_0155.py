"""Run the unmodified provisional salvage rule on one authenticated saved transfer."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from prospective_0155_solver import ARMS, CASE, INVENTORY_SHA, PINS as ORIGINAL_PINS, SETTINGS, orbit_legends
from prospective_0316_solver import inspect, owner_delta, verify_sources
from prospective_small_physical import checked
from provisional_salvage_dense import trigger
import provisional_salvage_trial as original


HERE = Path(__file__).resolve().parent
STAGED = Path("/dev/shm/leo-v3-saved-0155-pair-01")
BASELINE = Path("/dev/shm/leo-v3-saved-0155-result.json")
CROSS = Path("/dev/shm/leo-v3-cross-roster-0155-score.json")
REQUEST_PIN = "c0533ae6b92b66593d59a2f9a7aaf2b64194563c18ef8038ec2afdfc66c1da79"
TRACE_PIN = "b82d5b1aa6c86109646eae0666779fe72b2457c487b8437f3e21ebeecd99325f"
BASELINE_PIN = "63efc82d3c0fa0889f3c85e630ddb427f041b6174a7c9f175676c1f0fec64d75"
CROSS_PIN = "28780656e6672b36f9e72c6b1f02309ed51f571e805d49bb248cd45685ec1c66"
PROTOCOL = HERE / "provisional-salvage-0155-protocol.md"
TRACE = STAGED / "cumulative/joint-research-receipt.json"
PINS = original.PINS | ORIGINAL_PINS | {
    "provisional_salvage_trial.py": "03d17c1850798804f08cadd830a5f608df492af947f4dc1b066c3be9e3422ccc",
    "prospective_0316_solver.py": "73e3fb562115933bd5f6fb28d7a3e281c11c8f11c834a45d4b1c0914c33a280c",
}


def before_run():
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    job, inventory = STAGED / "request.json", STAGED / "inventory.json"
    request = json.loads(checked(job, REQUEST_PIN))
    trace = json.loads(checked(TRACE, TRACE_PIN))
    archive = Path(request["local_archive"]["root"])
    paths = (archive, inventory, Path(request["native_file"]), Path(request["offer_file"]),
             *(Path(name) for name in request["local_libraries"].values()))
    if (any(not path.resolve(strict=True).is_relative_to(STAGED) for path in paths)
            or archive_identity(archive)["snapshots_sha256"] != request["local_archive"]["snapshots_sha256"]
            or trace["receipt"]["session_id"] != request["session"]):
        raise ValueError("The saved trial requires the original authenticated staged authority")
    checked(inventory, INVENTORY_SHA)
    checked(Path(request["native_file"]), SETTINGS["native_sha"])
    checked(Path(request["offer_file"]), request["offer_sha256"])
    proof = trigger(trace["route_details"]["support"])
    if proof != dict(eligible=True, initial_curved=2940, restored=386, rechecked_curved=3051,
                     lost_restored_points=275, lost_restored_tracks=6):
        raise ValueError("The independently prescribed earlier salvage trigger differs")
    return job, inventory, proof


def worker(job, inventory, output):
    import unified_short_bootstrap as entry

    publish = entry.publish_active

    def configured(args, *values, **options):
        args.direct_residual_figures = True
        args.direct_orbit_figures = True
        return publish(args, *values, **options)

    with (patch.object(entry, "publish_active", configured), patch.object(original, "PINS", PINS)):
        original.candidate_worker(CASE, job, inventory, output, runtime=SETTINGS)


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    verify_sources(checked, PINS)
    job, inventory, eligibility = before_run()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Expected a private tmpfs result directory")
    root.mkdir()
    (root / "tmp").mkdir()
    write(root / "seal.json", dict(machine=machine, request_sha256=REQUEST_PIN, archived_trace_sha256=TRACE_PIN,
                                  trigger=eligibility, protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest(),
                                  source_sha256=PINS, driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))
    output = root / "candidate"
    env = environment(STAGED)
    env["TMPDIR"] = str(root / "tmp")
    command = [RELEASE / "venv/bin/python", "-IB", __file__, "worker", job, inventory, output]
    clock = measure(command, env, output)
    write(root / "candidate-clock.json", dict(timing=clock, command=list(map(str, command))))


def stages(route):
    if not route:
        return None
    support, repair = route["support"], route.get("repair")
    return dict(first_gate=dict(full=support["full_curved"], survivors=support["initial_curved"],
                                rejected=support["cold_rejected_tracks"]),
                salvage=dict(restored=support["curved_restored"], offers=support["salvage"]),
                second_gate=dict(survivors=support["rechecked_curved"], rejected=support["second_curved_rejections"]),
                provisional=route.get("provisional_salvage"), ordinary_pair_passed=route["pair_passes"],
                last_repair=repair, predictive_support=support["predictive_labels"],
                signed_update=route.get("signed", {}).get("status"))


def score(root, output):
    from aperture_trial import read, write
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    clock = read(root / "candidate-clock.json")["timing"]
    if clock["exit_code"]:
        raise ValueError("The single staged worker exited unsuccessfully")
    seal, directory = read(root / "seal.json"), root / "candidate"
    if seal["driver_sha256"] != sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("The executed candidate driver changed")
    request = json.loads(checked(STAGED / "request.json", REQUEST_PIN))
    original_trace = json.loads(checked(TRACE, TRACE_PIN))
    archived = json.loads(checked(BASELINE, BASELINE_PIN))
    crossed = json.loads(checked(CROSS, CROSS_PIN))
    own = read(directory / SETTINGS["audit_name"])
    candidate = inspect(directory, "cumulative", own["receipt"], clock, request, **SETTINGS)
    route = candidate["route_details"]
    trial = route["provisional_salvage"]
    if trial["fit_calls"] != 1 or not candidate["worker"]["graph"]["enabled"]:
        raise ValueError("The original one-fit policy or exact graph did not run")
    ref, = (row["reference"] for row in json.loads(checked(REFERENCE, REFERENCE_SHA256))["cases"]
            if row["dataset_label"] == CASE and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    truth = [ref[key] for key in ("latitude_deg", "longitude_deg")]
    paired_scores = dict(archived["scores"], provisional={
        arm: dict(horizontal_error_km=distance_km(truth, row["latlon"]) if row["latlon"] else None,
                  rf_rms_hz=row.get("rf_rms_hz")) for arm, row in candidate["terminal"]["arms"].items()})
    baseline = archived["runs"]["cumulative"]
    equals = dict(terminal=candidate["terminal"] == baseline["terminal"],
                  owners=candidate["selected_rows"] == baseline["selected_rows"],
                  science=candidate["science"]["scientific_digests"] == baseline["science"]["scientific_digests"],
                  figures=json.loads(json.dumps(candidate["figures"])) == baseline["figures"])
    owners = {mode: {arm: owner_delta(archived["runs"][mode]["selected_rows"][arm],
                                     candidate["selected_rows"].get(arm, [])) for arm in ARMS}
              for mode in ("stock", "cumulative")}
    if trial["status"] == "reverted" and not all(equals.values()):
        raise ValueError("The original scientific and media publication changed after reversion")
    legends = orbit_legends(directory, candidate) if candidate["terminal"]["decision"] == "complete" else None
    write(output, dict(case=CASE, seal=seal, no_waveform=True, reference_sha256=REFERENCE_SHA256,
                       candidate=candidate, scores=paired_scores, owner_deltas=owners, equality=equals,
                       stages={"historical_cumulative": stages(original_trace["route_details"]), "candidate": stages(route)},
                       control_clocks={mode: archived["runs"][mode]["process"] for mode in ("stock", "cumulative")},
                       controls=dict(historical=BASELINE_PIN, crossed=CROSS_PIN, crossed_errors_km=crossed["scored_errors_km"]),
                       cairo_legends=legends))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action, fields in (("launch", ("root",)), ("worker", ("job", "inventory", "output")), ("score", ("root", "output"))):
        sub = commands.add_parser(action)
        for name in fields:
            sub.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    globals()[args.pop("action")](**args)
