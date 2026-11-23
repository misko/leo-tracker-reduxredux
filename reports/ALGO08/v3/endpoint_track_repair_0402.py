"""Run one saved cumulative publication pair with an optional endpoint repair."""

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

from owner_loss_0402 import ARCHIVED, ARCHIVED_SHA, SOURCE_PINS, STAGED, request
from prospective_0402_solver import ARMS, SETTINGS, checked, inspect, invoke, orbit_legends, owner_delta, verify_sources


BASE = "6d968060c"
ORDER = ("control", "trim")
PROTOCOL = HERE/"endpoint-track-repair-0402-protocol.md"
DIAGNOSIS = Path("/dev/shm/leo-v3-fragment-cross-0402-03/diagnostic/cross.json")
DIAGNOSIS_PIN = "0f4c04276d7fe8ec08aeec166e21da9782dc6746e97c2f75a4eedac05249f3cf"


def worker(mode, root):
    import unified_short_bootstrap as entry

    verify_sources(checked, SOURCE_PINS)
    original = entry.publish_active

    def active(*args, **kwargs):
        from endpoint_track_repair import binding

        with binding():
            return original(*args, **kwargs)

    with patch.object(entry, "publish_active", active if mode == "trim" else original):
        invoke(STAGED/"request.json", "cumulative", root)


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    job, jobdoc = request()
    crossed = json.loads(checked(DIAGNOSIS, DIAGNOSIS_PIN))
    if (crossed["native_sha256"] != SETTINGS["native_sha"]
            or crossed["archive"] != jobdoc["local_archive"]["snapshots_sha256"]
            or crossed["cutoff_utc_ns"] != jobdoc["causal_cutoff_utc_ns"]):
        raise ValueError("The crossed diagnosis used another signed input")
    verify_sources(checked, SOURCE_PINS)
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Expected fresh tmpfs output")
    root.mkdir()
    temporary = root/"tmp"
    temporary.mkdir()
    env = environment(STAGED)
    env["TMPDIR"] = str(temporary)
    measured_sources = [Path(__file__), HERE/"endpoint_track_repair.py", HERE/"fragment_gate_cross.py", PROTOCOL]
    write(root/"seal.json", dict(base=BASE, order=ORDER, machine=machine, diagnosis_sha256=DIAGNOSIS_PIN,
          request_sha256=sha256(job.read_bytes()).hexdigest(),
          source_sha256=SOURCE_PINS | {path.name: sha256(path.read_bytes()).hexdigest() for path in measured_sources}))
    for mode in ORDER:
        target = root/mode
        command = [RELEASE/"venv/bin/python", "-IB", __file__, "worker", target, mode]
        timing = measure(command, env, target)
        write(root/f"{mode}-clock.json", dict(timing=timing, command=list(map(str, command))))
        if timing["exit_code"]:
            raise ValueError(f"Saved {mode} worker failed: {timing['stderr_tail']}")


def evaluate(root, output):
    from aperture_trial import read, write
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    _, request_doc = request()
    archive = json.loads(gzip.decompress(checked(ARCHIVED, ARCHIVED_SHA)))
    actual, legends = {}, {}
    for mode in ORDER:
        target = root/mode
        timing = read(root/f"{mode}-clock.json")["timing"]
        trace = read(target/SETTINGS["audit_name"])
        if timing["exit_code"]:
            raise ValueError(f"Worker {mode} must have finished with an exit clock")
        actual[mode] = inspect(target, "cumulative", trace["receipt"], timing, request_doc, **SETTINGS)
        legends[mode] = orbit_legends(target, actual[mode])
    control, trim = (actual[mode] for mode in ORDER)
    previous = archive["runs"]["cumulative"]
    media_equal = json.loads(json.dumps(control["figures"])) == previous["figures"]
    if (control["terminal"] != previous["terminal"] or control["selected_rows"] != previous["selected_rows"]
            or control["science"]["scientific_digests"] != previous["science"]["scientific_digests"] or not media_equal):
        raise ValueError("Fresh control changed the archived cumulative result")
    ref, = (row["reference"] for row in json.loads(checked(REFERENCE, REFERENCE_SHA256))["cases"]
            if row["dataset_label"] == "DS30-0402" and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    truth = [ref["latitude_deg"], ref["longitude_deg"]]
    scores = {mode: {arm: dict(horizontal_error_km=distance_km(truth, t["latlon"]), rf_rms_hz=t["rf_rms_hz"])
                     for arm, t in row["terminal"]["arms"].items()} for mode, row in actual.items()}
    owners = {}
    for label, baseline in (("control", control), ("named", archive["runs"]["stock"])):
        owners[label] = {arm: owner_delta(baseline["selected_rows"][arm], trim["selected_rows"][arm]) for arm in ARMS}
    for arm in ARMS:
        baseline = control["selected_rows"][arm]
        ids = {row[0] for row in baseline}
        common = [row for row in trim["selected_rows"][arm] if row[0] in ids]
        owners["control"][arm]["retained_order_matches"] = common == baseline
    action = trim["route_details"].get("endpoint_trim", {})
    improved_both = all(scores["trim"][arm]["horizontal_error_km"] <= scores["control"][arm]["horizontal_error_km"]
                        for arm in ARMS)
    media = {name: {k: v == control["figures"][name][k] for k, v in image.items()}
             for name, image in trim["figures"].items()}
    write(output, dict(case="DS30-0402", seal=read(root/"seal.json"), archival_comparison_sha256=ARCHIVED_SHA,
                       results=actual, repair=action, scores=scores, owners=owners, orbit_legends=legends,
                       media_equality=media, prospective_0160=dict(reserved=True, ran=False,
                           both_arms_improved_or_equal=improved_both)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("launch").add_argument("root", type=Path)
    child = commands.add_parser("worker")
    child.add_argument("root", type=Path)
    child.add_argument("mode", choices=ORDER)
    scorer = commands.add_parser("evaluate")
    scorer.add_argument("root", type=Path)
    scorer.add_argument("output", type=Path)
    opts = parser.parse_args()
    if opts.action == "launch":
        launch(opts.root)
    elif opts.action == "worker":
        worker(opts.mode, opts.root)
    else:
        evaluate(opts.root, opts.output)
