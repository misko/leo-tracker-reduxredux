"""Seal the isolated prior-decay trials and compare both calibration arms."""

import argparse
import json
from pathlib import Path

from .. import corpus
from ..__main__ import read_predictions, save_json
from ..scoring import ARMS, ROLES, distance_km, validate_result
from . import previous_orbit_trial as trial
from .armijo_finish_results import pack
from .compact_roof_selection_results import match_original_roles
from .full_v5_check import _sha
from .orbit_domain_results import BINDING_FIELDS, COMPACT, DIAGNOSES, POSITIONS, _measures
from .prefix_figures import csv_file

REPORT = trial.REPORT
SEAL = REPORT / "prediction-lock.json"
SOURCE = REPORT / "source-lock.json"


def publish(work, diagnostic):
    if json.loads(SOURCE.read_bytes()) != trial.source_lock():
        raise ValueError("previous-orbit source or input roster changed before sealing")
    original = trial.domain.archived()
    rows, traces = [], []
    for ident in trial.CASES:
        row = json.loads((work / ident / "prediction.json").read_bytes())
        if (
            row["id"] != ident or row["method"] != trial.METHOD
            or row["source_lock_sha256"] != _sha(SOURCE)
            or any(row[key] != original[ident][key] for key in BINDING_FIELDS)
        ):
            raise ValueError(f"{ident} candidate differs from the matched frozen inputs")
        validate_result(row["result"])
        rows.append(row)
        if ident in trial.FAILED:
            folder = diagnostic / ident
            request = json.loads((folder / "request.json").read_bytes())
            data = json.loads((folder / "diagnostic.json").read_bytes())
            if (
                request["job"]["native_input"]["sha256"] != "sha256:" + row["native_sha256"]
                or request["job"]["search_center"] != row["tile"]["center"]
                or not data["invalid_previous"]
                or any(x["current_codes"] != [0, 0, 0] or not x["current_full_grid_valid"]
                       for x in data["invalid_previous"])
            ):
                raise ValueError("original previous-orbit assertion is missing its causal witness")
            traces.append(dict(id=ident, **data))
    files = {
        POSITIONS: pack(REPORT, POSITIONS, rows),
        COMPACT: pack(REPORT, COMPACT, [original[k] for k in trial.CASES]),
        DIAGNOSES: pack(REPORT, DIAGNOSES, traces),
    }
    save_json(SEAL, dict(cases=trial.CASES, files=files, source_lock_sha256=_sha(SOURCE)))


def score():
    lock = json.loads(SEAL.read_bytes())
    if (
        lock["cases"] != list(trial.CASES) or lock["source_lock_sha256"] != _sha(SOURCE)
        or any(_sha(REPORT / name) != value for name, value in lock["files"].items())
    ):
        raise ValueError("candidate or original compact outcome changed after the position seal")
    output = {k: read_predictions(REPORT / name)
              for k, name in (("previous_orbit", POSITIONS), ("compact", COMPACT))}
    refs = {r["id"]: r for r in corpus.references("ds26-all159")}
    _, _, files = trial.domain.compact.roster()
    items = corpus._index(corpus._read_frozen("inputs.jsonl", files))
    roles, scores = {}, []
    for ident in trial.CASES:
        ref = refs[ident]
        original, bindings = match_original_roles(ref, items[ident])
        roles[ident] = dict(outcomes=original, bindings=bindings)
        for arm in ARMS:
            paired = {k: _measures(rows[ident], arm, ref["truth"]) for k, rows in output.items()}
            gap = distance_km(*(rows[ident]["result"]["arms"][arm]["latlon"]
                                for rows in output.values()))
            scores.append(dict(
                id=ident, arm=arm, panel="prior-decay" if ident in trial.FAILED else "control",
                identical_input_endpoint_delta_km=gap,
                **{f"{k}_{name}": value for k, values in paired.items()
                   for name, value in values.items()},
                **{f"{k}_{name}": original[k][arm].get(name) for k in ROLES
                   for name in ("status", "error_km", "rf_rms_hz", "matched_rf_rms_hz")},
            ))
    csv_file(REPORT / "scores.csv", scores)
    save_json(REPORT / "original-roles.json", roles)
    save_json(REPORT / "score-lock.json", dict(
        prediction_lock_sha256=_sha(SEAL),
        files={name: _sha(REPORT / name) for name in ("scores.csv", "original-roles.json")},
    ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("publish", "score"))
    parser.add_argument("--work", type=Path, default=trial.WORK)
    parser.add_argument("--diagnostic", type=Path, default=trial.DIAG)
    args = parser.parse_args()
    if args.stage == "publish":
        publish(args.work, args.diagnostic)
    else:
        score()


if __name__ == "__main__":
    main()
