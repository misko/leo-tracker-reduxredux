"""One full isolated-salvage/endpoint publication on the existing causal saved packet."""

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


ENDPOINT = Path("/dev/shm/leo-v3-endpoint-trim-0402-score01.json")
ENDPOINT_PIN = "ad413b4a3024265e95784716b4c9499674a9b818607d3fdc241932e1aef950c7"
ENDPOINT_SOURCE_SHA = "b3dc4ad2fe3c232b0b94f30bd1e81206aa11303748f0982442ce9006981c3a8a"
LOSS = HERE / "measurements/owner-loss-0402.json.gz"
LOSS_PIN = "92d7ce67d7cda1caca8345de6e6166ecdbe44c276a96652dc0be5f3769defd83"
POLICY_PINS = SOURCE_PINS | {"endpoint_track_repair.py": ENDPOINT_SOURCE_SHA}


def worker(root):
    import unified_short_bootstrap as entry

    verify_sources(checked, POLICY_PINS)
    original = entry.publish_active

    def active(*args, **kwargs):
        from isolated_salvage import binding

        with binding():
            return original(*args, **kwargs)

    with patch.object(entry, "publish_active", active):
        invoke(STAGED / "request.json", "cumulative", root)


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    job, jobdoc = request()
    verify_sources(checked, POLICY_PINS)
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Expected a fresh private tmpfs output")
    root.mkdir()
    temporary = root / "tmp"
    temporary.mkdir()
    env = environment(STAGED)
    env["TMPDIR"] = str(temporary)
    sources = ("isolated-salvage-0402-protocol.md", "isolated_salvage.py", Path(__file__).name,
               "provisional_salvage.py", "fragment_gate_cross.py")
    write(root / "launch.json", dict(machine=machine, archive=jobdoc["local_archive"]["snapshots_sha256"],
          native_sha256=jobdoc["native_sha256"], request_sha256=sha256(job.read_bytes()).hexdigest(),
          source_sha256=POLICY_PINS | {name: sha256((HERE / name).read_bytes()).hexdigest() for name in sources}))
    target = root / "candidate"
    command = [RELEASE / "venv/bin/python", "-IB", __file__, "worker", target]
    timing = measure(command, env, target)
    write(root / "candidate-clock.json", dict(timing=timing, command=list(map(str, command))))
    if timing["exit_code"]:
        raise ValueError("Combined saved worker failed. Its exact process clock and logs were sealed.")


def known_targets(loss, output, arm):
    actual = {oid: (norad, role) for oid, norad, role in output}
    targets = {(62735, "conditional"): [], (62735, "predictive"): [], (58377, "conditional"): []}
    for row in loss["loss"]["by_arm"][arm]["rows"]:
        key = row["norad"], row["role"]
        targets[key].append((row["observation_id"], actual.get(row["observation_id"])))
    return {f"{norad}_{role}": dict(
        expected=len(cases), exact=sum(assigned == (norad, role) for _, assigned in cases),
        missing=[oid for oid, assigned in cases if assigned is None],
        reassigned=[(oid, *assigned) for oid, assigned in cases if assigned is not None and assigned != (norad, role)],
    ) for (norad, role), cases in targets.items()}


def evaluate(root, result):
    from aperture_trial import read, write
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    _, doc = request()
    archived = json.loads(gzip.decompress(checked(ARCHIVED, ARCHIVED_SHA)))
    losses = json.loads(gzip.decompress(checked(LOSS, LOSS_PIN)))
    endpoint = json.loads(checked(ENDPOINT, ENDPOINT_PIN))
    job = root / "candidate"
    clock = read(root / "candidate-clock.json")["timing"]
    receipt = read(job / SETTINGS["audit_name"])
    if clock["exit_code"] or not receipt["no_waveform"]:
        raise ValueError("Expected one successful actual saved combined process")
    current = inspect(job, "cumulative", receipt["receipt"], clock, doc, **SETTINGS)
    if current["science"]["receipt"]["decision"] != "complete":
        raise ValueError("Expected the enrolled physical case's standard completed output")
    comparators = dict(named=archived["runs"]["stock"], cumulative=archived["runs"]["cumulative"],
                       endpoint_only=endpoint["results"]["trim"])
    if (comparators["endpoint_only"]["terminal"]["native_sha256"] != current["terminal"]["native_sha256"]
            or comparators["endpoint_only"]["terminal"]["region"] != current["terminal"]["region"]
            or endpoint["seal"]["request_sha256"] != read(root / "launch.json")["request_sha256"]):
        raise ValueError("The endpoint-only comparator has different signed acquisition or offer")
    reference, = (row["reference"] for row in json.loads(checked(REFERENCE, REFERENCE_SHA256))["cases"]
                  if row["dataset_label"] == "DS30-0402" and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    survey = [reference["latitude_deg"], reference["longitude_deg"]]
    runs = comparators | {"isolated_plus_endpoint": current}
    scores = {mode: {arm: dict(horizontal_error_km=distance_km(survey, t["latlon"]), rf_rms_hz=t["rf_rms_hz"])
                     for arm, t in row["terminal"]["arms"].items()} for mode, row in runs.items()}
    owners = {mode: {arm: owner_delta(row["selected_rows"][arm], current["selected_rows"][arm]) for arm in ARMS}
              for mode, row in comparators.items()}
    targets = {mode: {arm: known_targets(losses, row["selected_rows"][arm], arm) for arm in ARMS}
               for mode, row in runs.items()}
    figures = json.loads(json.dumps(current["figures"]))
    media = {name: {key: value == comparators["endpoint_only"]["figures"][name][key] for key, value in image.items()}
             for name, image in figures.items()}
    legends = orbit_legends(job, current)
    publication = dict(terminal=current["terminal"], science=current["science"],
                       sidecars=current["sidecars"], figures=figures, legends=legends)
    details = current["route_details"]
    isolated = details.get("provisional_salvage", {})
    write(result, dict(launch=read(root / "launch.json"), process=clock, worker=receipt,
                       publication=publication, isolated_attempt=isolated,
                       endpoint_attempt=details.get("endpoint_trim", isolated.get("endpoint_trim", {})),
                       signed_final=details.get("signed"),
                       scores=scores, owners=owners, targets=targets, endpoint_media_equality=media,
                       comparison_pins=dict(archive=ARCHIVED_SHA, loss=LOSS_PIN, endpoint=ENDPOINT_PIN,
                                            reference=REFERENCE_SHA256),
                       comparison_clocks={mode: data["process"] for mode, data in comparators.items()}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("launch", "worker", "evaluate"):
        sub = commands.add_parser(action)
        sub.add_argument("root", type=Path)
        if action == "evaluate":
            sub.add_argument("result", type=Path)
    options = vars(parser.parse_args())
    globals()[options.pop("action")](**options)
