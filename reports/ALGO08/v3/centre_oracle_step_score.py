"""Read the geographic references only after both oracle diagnostic receipts seal."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from centre_oracle_step_trial import CASES, HERE
from tools.pipeline_eval.scoring import distance_km


KEY = HERE.parent / "regional-release/scoring-key.json"
SURVEY = "903333eb790009a125088b645a543f15789bb6bc:reports/2026_11_21_ds30_full/reference-audit.json"
PINS = {
    "survey": "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5",
    "north_key": "0bda865a20e62852220a9ab8df63895a449bf203a2deb5370920dc3ce215d37d",
    "weak-combined-raw.json": "a704861e37e40e7364fbf97bcb74e98bb9c701ca474c12821e8ed7df86cab233",
    "north-combined.json": "871105154ab79679308cf7455ee10c236094d8735a02c17ed11bb2412283172e",
}


def checked(blob, name):
    if sha256(blob).hexdigest() != PINS[name]:
        raise ValueError("Archived reference changed")
    return json.loads(blob)


def controls():
    survey = checked(subprocess.check_output(["git", "show", SURVEY], cwd=HERE), "survey")
    physical, = [row["reference"] for row in survey["cases"]
                 if row["dataset_label"] == "DS30-0016" and row["authority_eligible"]]
    north, = {tuple(row["truth"]) for row in checked(KEY.read_bytes(), "north_key")["answers"].values()
              if row["recording"] == "0abe7b4514be674d9f5388e3"}
    weak_doc, north_doc = [checked((HERE / "measurements" / name).read_bytes(), name)
                           for name in ("weak-combined-raw.json", "north-combined.json")]
    return {
        "physical": ((physical["latitude_deg"], physical["longitude_deg"]),
                     weak_doc["runs"]["stock"]["arms"]),
        "north": (north, north_doc["cases"]["stock"]["score"]["arms"]),
    }


def score(directory, output, full):
    documents, blind = {}, {}
    for case in CASES:
        data = (directory / f"{case}.json").read_bytes()
        row = json.loads(data)
        if row["case"] != case or any(
                sha256((HERE / path).read_bytes()).hexdigest() != pin
                for path, pin in row["sources"].items()):
            raise ValueError("Expected the frozen saved diagnostic")
        documents[case] = row
        blind[case] = sha256(data).hexdigest()
    matches = controls()
    cases = {}
    for case, row in documents.items():
        truth, stock = matches[case]
        arms = {}
        for arm, result in row["trials"].items():
            base_error = distance_km(truth, stock[arm]["latlon"])
            original_error = distance_km(truth, row["oracle_arms"][arm]["latlon"])
            candidate_error = distance_km(truth, result["latlon"])
            delta = candidate_error - base_error
            arms[arm] = dict(
                trial=result, v3_error_km=base_error, installed_rf_rms_hz=stock[arm]["rf_rms_hz"],
                archived_unfiltered_error_km=original_error,
                archived_unfiltered_rf_rms_hz=row["oracle_arms"][arm]["rf_rms_hz"],
                candidate_error_km=candidate_error, candidate_minus_v3_km=delta,
                position_gate=delta <= .250,
                held_gate=result["held"]["moved_mse"] < result["held"]["centre_mse"],
                objective_gate=result["endpoint"]["robust_loss"] < result["centre"]["robust_loss"],
            )
        cases[case] = dict(arms=arms, binding=row["binding"], oracle_cpu_ns=row["oracle_cpu_ns"],
                           oracle_support={role: sum(r[2] == role for r in row["oracle_rows"])
                                           for role in ("conditional", "predictive")},
                           paired_candidate_cpu_ns=row["paired_candidate_cpu_ns"])
    passed = all(a["position_gate"] and a["held_gate"] and a["objective_gate"]
                 for c in cases.values() for a in c["arms"].values())
    receipt = dict(cases=cases, blind_sha256=blind, reference_pins=PINS, passed=passed,
                   scorer_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                   raw_reads=0, new_product_publications=0)
    payload = (json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    archive = (json.dumps(dict(complete=documents, summary=receipt), sort_keys=True,
                          separators=(",", ":"), allow_nan=False) + "\n").encode()
    with output.open("xb") as stream:
        stream.write(payload)
    with full.open("xb") as stream:
        stream.write(gzip.compress(archive, mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for label in ("directory", "output", "full"):
        parser.add_argument(label, type=Path)
    score(**vars(parser.parse_args()))
