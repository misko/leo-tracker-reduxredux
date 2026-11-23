"""Measure signed publication cost on the prespecified short physical v3 recording."""

import argparse
from hashlib import sha256
from pathlib import Path

from aperture_trial import FROZEN, archive_identity
from joint_publication import artifacts, verified_saved
from signed_0374_transfer import pairs, read, run, score, verify_stock
from leo.contracts.algo08_region import Algo08Region
from leo.contracts.digests import canonical_digest


CASE = "DS30-0316"
PAIR = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/publications") / CASE / "pair.json"
PAIR_SHA = "334790daefa5a26511aa72328ecd2dc3124a92c826257df9019f8afa793415ed"


def bind():
    if sha256(PAIR.read_bytes()).hexdigest() != PAIR_SHA:
        raise ValueError("The frozen short recording changed")
    pair = read(PAIR)
    if pair["candidate_specification_digest"] != "sha256:" + FROZEN:
        raise ValueError("This arm is not the installed v3 specification")
    baseline = pair["runs"]["candidate"]
    receipt = baseline["receipt"]
    root = PAIR.parent / "candidate"
    work = root / "fast-scan-automatic-work"
    native_file, = work.glob("*/detections.json")
    terminal = read(work / receipt["run_id"] / "terminal.json")
    region, archive = Path(pair["region"]), Path(pair["archive"]["root"])
    if (canonical_digest(terminal) != receipt["terminal_sha256"] or terminal["session_id"] != receipt["session_id"]
            or terminal["region"] != Algo08Region.parse(read(region)).document() or terminal["region"] != receipt["region"]
            or archive_identity(archive) != pair["archive"]):
        raise ValueError("Terminal, orbit archive or region changed")
    native = read(native_file)
    inventory = native["source"]["input_manifest_sha256"]
    verified_saved(native, terminal["native_sha256"], receipt["session_id"], inventory,
                   pair["candidate_specification"]["detector_sha256"])
    if native["source"]["raw_recording_authority_digest"] != baseline["raw_authority"]:
        raise ValueError("Recording authority changed")
    decoded = artifacts(root, receipt)
    verify_stock(pairs.evidence(root, receipt, started_ns=0, read_only=True), baseline, decoded, decoded)
    witness = dict(detection_sha256=terminal["native_sha256"], input_manifest_sha256=inventory)
    return pair, dict(baseline, witnesses=witness), native_file, region, archive, decoded


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    run(args.work, load_case=bind, case=CASE, pair_sha256=PAIR_SHA)
    score(args.work, args.receipt)
