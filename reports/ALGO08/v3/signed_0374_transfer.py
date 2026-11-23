"""Bind and time the single DS30-0374 saved publication transfer."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from time import perf_counter

from aperture_trial import ARMS, PAYLOAD, RELEASE, archive_identity, machine
from joint_publication import artifacts, verified_saved
from leo.contracts.digests import canonical_digest
from tools.pipeline_eval.qualification import paired_publication as pairs


HERE = Path(__file__).resolve().parent
PAIR = HERE / "measurements/successor-DS30-0374-pair.json"
PAIR_DIGEST = "b49af1ff154c7123574ffe6190e394c2d4ed7e29ea3da8d0da6dce479f3be82b"
ARCHIVED = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/v3-successor-DS30-0374-20261123-pair/baseline")


def read(path):
    return json.loads(path.read_bytes())


def write(path, data):
    with path.open("x") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")


def verify_stock(data, original, decoded, archived_decoded):
    equality = {key: data[key] == original[key]
                for key in ("raw_authority", "arms", "owners", "reason", "artifacts", "scientific_digests")}
    equality.update(
        terminal=data["receipt"]["terminal_sha256"] == original["receipt"]["terminal_sha256"],
        decoded=decoded["images"] == archived_decoded["images"],
    )
    if not all(equality.values()):
        raise ValueError(f"Saved stock comparison changed: {equality}")
    return equality


def bind():
    contents = PAIR.read_bytes()
    if sha256(contents).hexdigest() != PAIR_DIGEST:
        raise ValueError("Archived DS30-0374 pair has changed")
    pair = json.loads(contents)
    baseline = pair["runs"]["baseline"]
    witness = baseline["witnesses"]
    detection_path, = (ARCHIVED / "fast-scan-automatic-work").glob("*/detections.json")
    native = verified_saved(read(detection_path), witness["detection_sha256"], witness["session_id"],
                            witness["input_manifest_sha256"], baseline["build"]["detector_sha256"])
    if native["source"]["raw_recording_authority_digest"] != baseline["raw_authority"]:
        raise ValueError("Archived raw authority changed")
    region = Path(pair["region_file"])
    archive = Path(pair["archive"]["root"])
    if (sha256(region.read_bytes()).hexdigest() != pair["region_file_sha256"]
            or archive_identity(archive) != pair["archive"]):
        raise ValueError("Original offer or pre-RF archive changed")
    decoded = artifacts(ARCHIVED, baseline["receipt"])
    archived_data = pairs.evidence(ARCHIVED, baseline["receipt"], started_ns=0, read_only=True)
    verify_stock(archived_data, baseline, decoded, decoded)
    return pair, baseline, detection_path, region, archive, decoded


def owner_changes(stock, candidate):
    result = {}
    for arm in ARMS:
        before = {row[0]: tuple(row[1:]) for row in stock["selected_rows"].get(arm, [])}
        after = {row[0]: tuple(row[1:]) for row in candidate["selected_rows"].get(arm, [])}
        shared = before.keys() & after.keys()
        result[arm] = dict(stock=len(before), candidate=len(after), shared=len(shared),
                           removed=len(before.keys() - after.keys()), new=len(after.keys() - before.keys()),
                           changed_norad=sum(before[oid][0] != after[oid][0] for oid in shared),
                           changed_role=sum(before[oid][1] != after[oid][1] for oid in shared))
    return result


def run(output, *, resume=False, load_case=bind, case="DS30-0374", pair_sha256=PAIR_DIGEST):
    system = machine()
    if (system["cpu"] != [2] or system["nice"] < 15 or "prio 7" not in system["ionice"]
            or any(n != "1" for n in system["threads"].values())):
        raise ValueError("Expected one low-priority numerical core")
    pair, expected, saved, region, archive, archived_decoded = load_case()
    witness = expected["witnesses"]
    if resume:
        if not (output / "stock/joint-research-receipt.json").is_file() or (output / "signed").exists() or (output / "pair.json").exists():
            raise ValueError("Resume requires only a completed stock publication")
    else:
        output.mkdir(exist_ok=False)
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (HERE, PAYLOAD, RELEASE / "src", RELEASE))),
                       MPLCONFIGDIR=str(output / "mplconfig"))
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE", "ALGO08_EXPERIMENT_CONFIG"):
        environment.pop(key, None)
    python = str(RELEASE / "venv/bin/python")
    if not resume:
        subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                       env=environment, check=True, timeout=20)
    runs, observers = {}, {}
    common = [python, "-BPs", str(HERE / "joint_publication.py"), "--recording", pair["recording"],
              "--region", str(region), "--archive", str(archive), "--saved", str(saved),
              "--saved-digest", witness["detection_sha256"], "--verify-images"]
    for name, mode in (("stock", "--stock-control"), ("signed", "--signed-finish")):
        root = output / name
        outer = None
        if not (resume and name == "stock"):
            start = pairs.child_usage()
            began = perf_counter()
            child = subprocess.run([*common, mode, "--output", str(root)], env=environment, text=True,
                                   capture_output=True, timeout=120)
            elapsed = perf_counter() - began
            outer = dict(elapsed_s=elapsed, **{key: value - start[key] for key, value in pairs.child_usage().items()})
            if child.returncode:
                raise RuntimeError(f"{name} publication exited {child.returncode}: {child.stderr[-4000:]}")
        source = root / "joint-research-receipt.json"
        result = read(source)
        receipt = result["receipt"]
        decoded = artifacts(root, receipt)
        data = pairs.evidence(root, receipt, started_ns=0, read_only=True)
        native, = (root / "fast-scan-automatic-work").glob("*/detections.json")
        if (result["input"] != "saved detector" or result["saved_handoff_manifest"] != witness["input_manifest_sha256"]
                or canonical_digest(read(native)) != witness["detection_sha256"]
                or data["raw_authority"] != expected["raw_authority"] or receipt["region"] != expected["receipt"]["region"]
                or result["stock_control"] != (name == "stock") or result["signed_finish"] != (name == "signed")):
            raise ValueError("The replayed input, raw authority or requested route changed")
        if receipt["decision"] == "complete" and not result["solve"]["grid_complete"]:
            raise ValueError("A returned fit did not complete the normal grid")
        # PNG sizes are tuple-valued in the in-memory verifier.
        if json.loads(json.dumps(decoded)) != result["evidence"]:
            raise ValueError("The independent artifact check changed")
        validation = verify_stock(data, expected, decoded, archived_decoded) if name == "stock" else None
        observers[name] = result
        runs[name] = dict(**data, outer_clocks=outer, evidence=decoded,
                          route=result["route"], route_details=result["route_details"], solve=result["solve"],
                          selected_roles=result["selected_roles"], source_sha256=result["source_sha256"],
                          publication_cpu_s=result["publication_cpu_s"], publication_elapsed_s=result["publication_elapsed_s"],
                          archived_stock_checks=validation, runner_receipt_sha256=sha256(source.read_bytes()).hexdigest())
    if runs["stock"]["source_sha256"] != runs["signed"]["source_sha256"] or archive_identity(archive) != pair["archive"]:
        raise ValueError("Bounded pair used different source bytes or pre-RF archive")
    write(output / "pair.json", dict(case=case, machine=system, archive=pair["archive"],
                                      original_pair_sha256=pair_sha256, saved_native_sha256=witness["detection_sha256"],
                                      order=list(runs), stock_resumed=resume, runs=runs,
                                      owner_changes=owner_changes(observers["stock"], observers["signed"])))


def score(output, destination):
    from aperture_score import PHYSICAL, distance_km

    pair_path = output / "pair.json"
    raw = pair_path.read_bytes()
    pair = json.loads(raw)
    arms = pair["runs"]
    for mode, decision in arms.items():
        root = output / mode
        if sha256((root / "joint-research-receipt.json").read_bytes()).hexdigest() != decision["runner_receipt_sha256"]:
            raise ValueError("Output receipt changed after sealing")
        again = pairs.evidence(root, decision["receipt"], started_ns=0, read_only=True)
        if any(again[key] != decision[key] for key in ("arms", "owners", "artifacts", "scientific_digests")):
            raise ValueError("Published evidence changed after sealing")
    reference_bytes = PHYSICAL.read_bytes()
    row, = [row for row in json.loads(reference_bytes)["cases"] if row["dataset_label"] == pair["case"]]
    if not row["authority_eligible"]:
        raise ValueError("Case lacks an eligible archived receiver reference")
    truth = [row["reference"][key] for key in ("latitude_deg", "longitude_deg")]
    errors, rf = {}, {}
    for mode, published in arms.items():
        errors[mode] = {arm: None if data["latlon"] is None else distance_km(data["latlon"], truth)
                        for arm, data in published["arms"].items()}
        rf[mode] = {arm: data.get("rf_rms_hz") for arm, data in published["arms"].items()}
    deltas = {arm: None if errors["signed"][arm] is None else errors["signed"][arm] - errors["stock"][arm] for arm in ARMS}
    write(destination, dict(pair_sha256=sha256(raw).hexdigest(), reference_sha256=sha256(reference_bytes).hexdigest(),
                            horizontal_error_km=errors, delta_error_km=deltas, rf_rms_hz=rf,
                            triage_pass=arms["signed"]["route"] == "complete"
                            and all(value is not None and value <= .25 for value in deltas.values()), **pair))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    timing = subs.add_parser("run")
    timing.add_argument("output", type=Path)
    timing.add_argument("--resume", action="store_true")
    scoring = subs.add_parser("score")
    scoring.add_argument("output", type=Path)
    scoring.add_argument("destination", type=Path)
    settings = vars(parser.parse_args())
    action = settings.pop("action")
    (run if action == "run" else score)(**settings)
