"""Run the reserved saved transfer of the frozen endpoint-only repair."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from endpoint_track_repair_0402 import ARMS, ORDER, SOURCE_PINS, checked, inspect, orbit_legends, owner_delta, verify_sources
from prospective_0160_solver import SETTINGS, worker


STAGED = Path("/dev/shm/leo-v3-saved-0160-pair-01")
PRIOR = HERE/"measurements/prospective-0160-confirmation.json.gz"
PRIOR_SHA = "69ac592b164395a5942fd5aef9f592b5aa070c15855f8bcb2dec266200d3feff"
REQUEST_SHA = "c3b6e328f03f79e9d0b0989fabb3ab246394a03c98dd2ca7c2ca4f3a608e3d2e"
NAMED_PUB_SHA = "ebf1a80ae206a9c32cae2374e49b050faa1d0087413b313a3189a541d7e4ed08"
INVENTORY_SHA = "cc3dc7e24fa661a1627e25f9cea0ac6038c18c93b69a32fa2f2475cf9f1b8860"
RULE_SHA = "b3dc4ad2fe3c232b0b94f30bd1e81206aa11303748f0982442ce9006981c3a8a"
PROTOCOL = HERE/"endpoint-track-repair-0160-protocol.md"
PINS = SOURCE_PINS | {"endpoint_track_repair.py": RULE_SHA}


def inputs():
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    job = STAGED/"request.json"
    data = json.loads(checked(job, REQUEST_SHA))
    archive = Path(data["local_archive"]["root"])
    inventory = STAGED/"stock/fast-scan-inputs"/f"{data['session']}.json"
    paths = [archive, inventory, Path(data["native_file"]), Path(data["offer_file"]),
             *(Path(path) for path in data["local_libraries"].values())]
    if (not all(path.resolve(strict=True).is_relative_to(STAGED) for path in paths)
            or archive_identity(archive)["snapshots_sha256"] != data["original_archive"]["snapshots_sha256"]):
        raise ValueError("The enrolled DS30-0160 staged input changed")
    checked(inventory, INVENTORY_SHA)
    return job, data, inventory


def invoke(mode, output, request, inventory):
    import unified_short_bootstrap as entry

    original = entry.publish_active

    def configured(args, *values, **options):
        args.direct_residual_figures = True
        args.direct_orbit_figures = True
        if mode == "control":
            return original(args, *values, **options)
        from endpoint_track_repair import binding

        with binding():
            return original(args, *values, **options)

    with patch.object(entry, "publish_active", configured):
        worker(request, "cumulative", output, source_pins=PINS, inventory_file=inventory, **SETTINGS)


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    job, _, inventory = inputs()
    verify_sources(checked, PINS)
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use fresh tmpfs under the shared slot")
    root.mkdir()
    (root/"tmp").mkdir()
    env = environment(STAGED)
    env["TMPDIR"] = str(root/"tmp")
    driver = Path(__file__)
    write(root/"seal.json", dict(case="DS30-0160", order=ORDER, original_request_sha256=REQUEST_SHA, machine=machine,
          source_sha256=PINS | {path.name: sha256(path.read_bytes()).hexdigest() for path in (PROTOCOL, driver)}))
    for mode in ORDER:
        output = root/mode
        command = [RELEASE/"venv/bin/python", "-IB", __file__, "worker", mode, output, job, inventory]
        timing = measure(command, env, output)
        write(root/f"{mode}-clock.json", dict(timing=timing, command=list(map(str, command))))
        if timing["exit_code"]:
            raise ValueError(timing["stderr_tail"])


def observe_repair(research):
    recovery = research.get("recovered_inference") or {}
    attempts = recovery.get("attempts", []) + [research["route_details"]]
    return [item["endpoint_trim"] for item in attempts if item and "endpoint_trim" in item]


def evaluate(root, output):
    from aperture_trial import read, write
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    _, request, _ = inputs()
    historical = json.loads(gzip.decompress(checked(PRIOR, PRIOR_SHA)))["candidate"]
    named = json.loads(checked(STAGED/"stock/joint-research-receipt.json", NAMED_PUB_SHA))
    actual, repairs, legends = {}, {}, {}
    for mode in ORDER:
        target = root/mode
        timing = read(root/f"{mode}-clock.json")["timing"]
        if timing["exit_code"]:
            raise ValueError("Both sealed workers must have completed")
        audit = read(target/SETTINGS["audit_name"])
        actual[mode] = inspect(target, mode, audit["receipt"], timing, request, **SETTINGS)
        research = read(target/"joint-research-receipt.json")
        actual[mode]["recovered_inference"] = research.get("recovered_inference")
        repairs[mode] = observe_repair(research)
        legends[mode] = orbit_legends(target, actual[mode])
    control, trim = (actual[mode] for mode in ORDER)
    if (control["selected_rows"] != historical["selected_rows"] or control["terminal"] != historical["terminal"]
            or control["science"]["scientific_digests"] != historical["science"]["scientific_digests"]):
        raise ValueError("Fresh control differs from the archived cumulative numerical output")
    if repairs["control"] or sum(r["refit_calls"] for r in repairs["trim"]) > 1:
        raise ValueError("Unexpected endpoint probe or refit invocation")
    ref, = (row["reference"] for row in json.loads(checked(REFERENCE, REFERENCE_SHA256))["cases"]
            if row["dataset_label"] == "DS30-0160" and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    truth = [ref["latitude_deg"], ref["longitude_deg"]]
    scores = {mode: {arm: dict(horizontal_error_km=distance_km(truth, data["latlon"]), rf_rms_hz=data["rf_rms_hz"])
                     for arm, data in result["terminal"]["arms"].items()} for mode, result in actual.items()}
    owners = {label: {arm: owner_delta(source["selected_rows"][arm], trim["selected_rows"][arm]) for arm in ARMS}
              for label, source in (("control", control), ("named", named))}
    media = {name: {k: v == control["figures"][name][k] for k, v in image.items()}
             for name, image in trim["figures"].items()}
    write(output, dict(case="DS30-0160", seal=read(root/"seal.json"), archive_prior_sha256=PRIOR_SHA,
                       results=actual, endpoint_repair=repairs, owners=owners, scores=scores, media_equality=media,
                       orbit_legends=legends, activated=bool(repairs["trim"]), waveform_reads=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("launch").add_argument("root", type=Path)
    child = commands.add_parser("worker")
    child.add_argument("mode", choices=ORDER)
    child.add_argument("output", type=Path)
    child.add_argument("request", type=Path)
    child.add_argument("inventory", type=Path)
    scorer = commands.add_parser("evaluate")
    scorer.add_argument("root", type=Path)
    scorer.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.action == "launch":
        launch(args.root)
    elif args.action == "worker":
        invoke(args.mode, args.output, args.request, args.inventory)
    else:
        evaluate(args.root, args.output)
