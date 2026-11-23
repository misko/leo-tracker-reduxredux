"""Publish and score one preregistered complete saved DS30-0374 recording."""

import argparse
from hashlib import sha256
import os
from pathlib import Path
import subprocess

from aperture_trial import ARMS, PAYLOAD, RELEASE, archive_identity, machine, read, write
from joint_publication import artifacts
from signed_0374_transfer import bind
from tools.pipeline_eval.qualification import paired_publication as pairs


HERE = Path(__file__).resolve().parent


def run(output):
    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or any(n != "1" for n in host["threads"].values())):
        raise ValueError("Single low-priority core required")
    pair, expected, saved, region, archive, _ = bind()
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (HERE, PAYLOAD, RELEASE / "src", RELEASE))))
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE", "ALGO08_EXPERIMENT_CONFIG"):
        environment.pop(key, None)
    subprocess.run([str(RELEASE / "venv/bin/python"), "-BPs", str(HERE / "joint_publication.py"),
                    "--recording", pair["recording"], "--archive", str(archive), "--region", str(region),
                    "--saved", str(saved), "--saved-digest", expected["witnesses"]["detection_sha256"],
                    "--full-catalogue", "--verify-images", "--output", str(output)], check=True, env=environment)


def score(output, destination):
    from aperture_score import PHYSICAL, distance_km
    from leo.contracts.digests import canonical_digest

    pair, expected, _, _, archive, _ = bind()
    path = output / "joint-research-receipt.json"
    candidate = read(path)
    receipt = candidate["receipt"]
    official = read(HERE / "measurements/signed-DS30-0374-publication.json")
    if (candidate.get("full_catalogue") is not True or candidate["saved_digest"] != official["saved_native_sha256"]
            or candidate["saved_digest"] != expected["witnesses"]["detection_sha256"]
            or receipt["region"] != expected["receipt"]["region"]
            or archive_identity(archive) != official["archive"] or pair["archive"] != official["archive"]):
        raise ValueError("Wrong route, input, catalogue or offered region")
    evidence = pairs.evidence(output, receipt, started_ns=0, read_only=True)
    decoded = artifacts(output, receipt)
    if (evidence["raw_authority"] != expected["raw_authority"] or
            canonical_digest(decoded) != canonical_digest(candidate["evidence"])):
        raise ValueError("Authority or rendered artifacts changed")
    reference, = [r for r in read(PHYSICAL)["cases"] if r["dataset_label"] == official["case"] and r["authority_eligible"]]
    if sha256(PHYSICAL.read_bytes()).hexdigest() != official["reference_sha256"]:
        raise ValueError("Site reference changed")
    truth = [reference["reference"][k] for k in ("latitude_deg", "longitude_deg")]
    errors = {arm: distance_km(evidence["arms"][arm]["latlon"], truth) if evidence["arms"][arm]["latlon"] else None
              for arm in ARMS}
    deltas = {arm: None if e is None else e - official["horizontal_error_km"]["stock"][arm] for arm, e in errors.items()}
    compare = {mode: dict(cpu_s=v["solve"]["cpu_s"], publication_cpu_s=v["publication_cpu_s"],
                          publication_elapsed_s=v["publication_elapsed_s"], error_km=official["horizontal_error_km"][mode],
                          rf_rms_hz=official["rf_rms_hz"][mode],
                          equal_owner_digests=evidence["owners"] == v["owners"],
                          equal_scientific_path_and_grid=evidence["scientific_digests"] == v["scientific_digests"],
                          identical_images=[key for key, image in candidate["evidence"]["images"].items()
                                            if image == v["evidence"]["images"].get(key)])
               for mode, v in official["runs"].items()}
    write(destination, dict(case=official["case"], sealed_receipt_sha256=sha256(path.read_bytes()).hexdigest(),
                            archive=official["archive"], saved_digest=candidate["saved_digest"], raw_authority=evidence["raw_authority"],
                            decision=receipt["decision"], solver=candidate["solve"], route=candidate["route"],
                            publication_cpu_s=candidate["publication_cpu_s"], publication_elapsed_s=candidate["publication_elapsed_s"],
                            arms=evidence["arms"], owners=evidence["owners"], rendered=decoded, error_km=errors,
                            delta_error_km=deltas, passes=all(v is not None and v <= .25 for v in deltas.values()),
                            comparators=compare, source_sha256=candidate["source_sha256"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    subs.add_parser("run").add_argument("output", type=Path)
    scorer = subs.add_parser("score")
    scorer.add_argument("output", type=Path)
    scorer.add_argument("destination", type=Path)
    args = vars(parser.parse_args())
    (run if args.pop("action") == "run" else score)(**args)
