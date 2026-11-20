"""Render the ORBCOMM trial with its unidentified calibration arm explicit."""

import argparse
import gzip
import json
from hashlib import sha256
from pathlib import Path

from .. import figure_books
from ..__main__ import local_output, save_json
from ..scoring import ARMS, validate_result
from .armijo_finish_results import pack
from .external_orbcomm_trial import REPORT, check

ORIGINAL = "positions.jsonl.gz"
DERIVED = "figure-positions.jsonl.gz"
SEAL = "figure-lock.json"


def mark_unavailable(row):
    result = row["result"]
    arms = result["arms"]
    endpoint = arms["fitted_c"]
    if result["metrics"].get("rf_slope_identifiable") is not False:
        raise ValueError("the sealed result did not declare RF calibration unidentifiable")
    display = dict(result, arms=dict(arms, fitted_c=dict(endpoint, status="unavailable")))
    validate_result(display)
    return dict(row, result=display)


def publish(out):
    out = local_output(out)
    measured = check(out, "prediction-lock.json")
    scores = check(out, "score-lock.json")
    if measured["cases"] != scores["cases"] or ORIGINAL not in measured["files"]:
        raise ValueError("the score and prediction locks cover different trials")
    with gzip.open(out / ORIGINAL, "rt") as handle:
        rows = [mark_unavailable(json.loads(line)) for line in handle]
    pack(out, DERIVED, rows)
    names = (*scores["files"], "score-lock.json", DERIVED)
    files = {name: sha256((out / name).read_bytes()).hexdigest() for name in names}
    save_json(out / SEAL, dict(cases=scores["cases"], files=files))
    path = out / "figures.json"
    specs = json.loads(path.read_bytes())["charts"]
    for spec in specs:
        if spec["scope"] != "transfer" or any(
            row["file"] not in (ORIGINAL, DERIVED) for row in spec["series"]
        ):
            raise ValueError("the figure descriptor must use the matched ORBCOMM prediction rows")
        for row in spec["series"]:
            row["file"] = DERIVED
        spec["seal"] = SEAL
        spec["provenance"] = list(dict.fromkeys([*spec["provenance"], ORIGINAL, "score-lock.json"]))
        spec["caption"] = (
            "Four disjoint VHF day pairs at one station with deposited site-conditioned "
            "identities. Per-pass offsets span the RF calibration term. Only c = 0 is fit."
        )
    save_json(path, dict(version=2, charts=specs))
    return figure_books.generate(
        out / "charts",
        ARMS,
        methods=[spec["id"] for spec in specs],
        panel="screening",
        evidence=out,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=REPORT)
    args = parser.parse_args()
    publish(args.evidence)


if __name__ == "__main__":
    main()
