"""Replay the prespecified southern development offers, then score the sealed outputs."""

import argparse
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import subprocess
from time import perf_counter

from aperture_trial import BENCH, PAYLOAD, RELEASE, archive_identity, machine, read, write


HERE = Path(__file__).resolve().parent
INSIDE = BENCH / "exact-curved-lookahead-south-inside/pair.json"
FAR = BENCH / "exact-curved-lookahead-south-offers.json"


def checked(path, pin):
    payload = path.read_bytes()
    if sha256(payload).hexdigest() != pin:
        raise ValueError(f"Frozen assignment changed: {path}")
    return json.loads(payload)


def invoke(args):
    path = os.pathsep.join(map(str, (HERE, PAYLOAD, RELEASE / "src", RELEASE, HERE.parents[2])))
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = perf_counter()
    subprocess.run([RELEASE / "venv/bin/python", "-BPs", str(HERE / "full_short_run.py"), *args],
                   env=dict(os.environ, PYTHONPATH=path), check=True, timeout=100)
    elapsed = perf_counter() - start
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return dict(elapsed_s=elapsed, cpu_s=after.ru_utime-before.ru_utime+after.ru_stime-before.ru_stime)


def run(root, binary, *, near_replay=False):
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from full_short_raw import RECIPE_SHA

    host = machine()
    if host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"] or set(host["threads"].values()) != {"1"}:
        raise ValueError("Use the shared low-priority Gauss slot")
    assignment = checked(INSIDE, "48fed3c62639ef81fb99e4b76921bcacd999e769a78ebb607b2b886b6f0951f0")
    far = checked(FAR, "5181abf1c8a36d45dfe140e8851f0a423b69ec69b8ca231a3f87bcc9fdcecca9")
    baseline = assignment["runs"]["candidate"]
    record, archive = assignment["recording"], Path(assignment["archive"]["root"])
    original_offer = Path(assignment["region"])
    if (assignment["archive"] != archive_identity(archive) or assignment["archive"] != far["archive"]
            or far["specification"] != assignment["candidate_specification_digest"]
            or Algo08Region.parse(read(original_offer)).document() != baseline["receipt"]["region"]):
        raise ValueError("Archive, region or installed comparison changed")
    missing = root / "far-offer.json"
    if binary is not None:
        root.mkdir(exist_ok=False)
        write(missing, far["results"]["south-far"]["offer"])
    if read(missing) != far["results"]["south-far"]["offer"]:
        raise ValueError("The missing-region offer differs from the prespecified control")
    offers = [("containing", original_offer), ("far", missing)]
    if near_replay:
        mirror_path = HERE.parent / "single-core-2x/measurements/region-mirrors.json.gz"
        mirror = mirror_path.read_bytes()
        if sha256(mirror).hexdigest() != "ee8f80ec6267e7fe333d05ac794775fb54bc349cd143022a55599bf2f9af4728":
            raise ValueError("Southern mirrored offer changed")
        near = root / "near-offer.json"
        write(near, json.loads(gzip.decompress(mirror))["sites"]["south"]["outside"]["offer"])
        offers.append(("near", near))
    shared = ["--recording", record, "--archive", archive]
    cases = {}
    for name, offer in offers:
        output = root / name
        clock_path = root / f"{name}-process.json"
        if binary is not None or name == "near":
            mode = ["--short-binary", binary] if name == "containing" else ["--saved", detection, "--saved-digest", native_pin]
            write(clock_path, invoke([*shared, "--region", offer, "--output", output, *mode]))
        clocks = read(clock_path)
        report = read(output / "joint-research-receipt.json")
        receipt = report["receipt"]
        work = output / "fast-scan-automatic-work"
        terminal = read(work / receipt["run_id"] / "terminal.json")
        saved_path, = work.glob("*/detections.json")
        readout = read(saved_path)
        packet_pin = terminal["native_sha256"]
        if name == "containing":
            detection, native_pin = saved_path, packet_pin
        expected_save = None if name == "containing" else cases["containing"]["native_pin"]
        if (receipt["region"] != Algo08Region.parse(read(offer)).document() or terminal["region"] != receipt["region"]
                or receipt["terminal_sha256"] != canonical_digest(terminal)
                or canonical_digest(readout) != packet_pin or report["saved_digest"] != expected_save
                or (expected_save is not None and packet_pin != expected_save)
                or readout["provenance"]["detector_sha256"] != "sha256:" + RECIPE_SHA
                or readout["source"]["raw_recording_authority_digest"] != baseline["raw_authority"]):
            raise ValueError("Unbound native, terminal, or region in transfer")
        proof, = report["early_regional"]
        cases[name] = dict(receipt=receipt, terminal=terminal, native_pin=native_pin, saved_digest=expected_save,
                           source_sha256=report["source_sha256"], solve=report["solve"], route=report["route"],
                           proof=proof, evidence=report["evidence"], owners={k: len(v) for k,v in report["selected_rows"].items()},
                           publication_cpu_s=report["publication_cpu_s"], publication_elapsed_s=report["publication_elapsed_s"],
                           process=clocks)
    from aperture_score import references
    from mixture_score import section
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km

    truth = references()["south-containing"]
    for case in cases.values():
        case["truth_clearance_km"] = face_clearance_km(case["receipt"]["region"], truth)
        case["score"] = section(case["terminal"]["arms"], truth, baseline["arms"])
    record = dict(cases=cases, archive=assignment["archive"], machine=host,
                  stock=dict(score=section(baseline["arms"], truth, baseline["arms"]), raw_authority=baseline["raw_authority"],
                             inside=baseline["receipt"]["decision"], far=far["results"]["south-far"]["status"]),
                  receiver=read(root / "containing/full-short-recipe.json"))
    write(root / ("near-score.json" if near_replay else "score.json"), record)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    action = cli.add_mutually_exclusive_group(required=True)
    action.add_argument("--binary", type=Path, help="Run the frozen raw and saved sequence in a fresh directory")
    action.add_argument("--score-only", action="store_true", help="Read both completed publications and process clocks")
    action.add_argument("--near-replay", action="store_true", help="Apply the prespecified near offer to the sealed containing packet")
    options = cli.parse_args()
    run(options.root, options.binary, near_replay=options.near_replay)
