"""Score the frozen three RF-block decisions after binding their inputs and results."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from aperture_score import PHYSICAL, SIMULATED, face_clearance_km, references
from leo.contracts.digests import canonical_digest
from mixture_score import section
from rf_block_trial import CASES


FULL = Path(__file__).parent / "measurements/blind-joint-signed.json.gz"
PIN = "de4a1be32d35c5b4c7ae6164ae663f450f8408937f4eb6de46c3977436dcfc54"


def score(directory, output, archive, label="block"):
    original = FULL.read_bytes()
    if sha256(original).hexdigest() != PIN:
        raise ValueError("Full-recording comparator changed")
    controls = json.loads(gzip.decompress(original))["receipts"]
    trials, raw_receipts = {}, {}
    for case in CASES:
        row = json.loads((directory / f"{case}.json").read_bytes())
        decision = row["decision"]
        full = controls[case]
        if (row["case"] != case or row["input"] != full["identity"] or row["stock"]["arms"] != full["control"]["arms"]
                or canonical_digest(decision) != row["sealed_outcome"]):
            raise ValueError("Input, baseline or decision seal changed")
        if decision["status"] != "failed":
            raw = (directory / f"{case}.solver.json").read_bytes()
            if sha256(raw).hexdigest() != decision["full_solver_receipt_sha256"]:
                raise ValueError("Full solver receipt changed")
            raw_receipts[case] = raw.decode()
        trials[case] = row

    truth = references()
    for case, row in trials.items():
        full = controls[case]
        arms = row["decision"].get("arms", {})
        stock = full["control"]["arms"]
        row["scores"] = {name: section(values, truth[case], stock) for name, values in
                         ((label, arms), ("full_signed", full["result"]["arms"]), ("v3", stock))}
        row["baseline_clocks"] = dict(v3=full["control_clocks"], full_signed=full["charged"])
        contained = face_clearance_km(row["input"]["offer"], truth[case]) >= 0
        changes = [arm["delta_error_km"] for arm in row["scores"][label]["arms"].values()]
        status = row["decision"]["status"]
        row["quality_screen"] = (status == "ok" and all(d is not None and d <= .25 for d in changes)
                                 if contained else status == "withheld")
    result = dict(full_comparator_sha256=PIN, scoring_pins={p.name: sha256(p.read_bytes()).hexdigest()
                                                           for p in (PHYSICAL, SIMULATED)}, cases=trials)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    with archive.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(raw_receipts, separators=(",", ":")).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--label", default="block")
    score(**vars(parser.parse_args()))
