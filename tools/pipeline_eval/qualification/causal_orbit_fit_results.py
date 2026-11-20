"""Seal the composed replay, authenticate standalone comparators, and score its endpoints."""

import argparse
import json
from collections import Counter
from pathlib import Path

from .. import corpus
from ..__main__ import read_predictions, save_json
from ..scoring import ARMS, ROLES, distance_km, validate_result
from . import causal_orbit_fit_trial as trial
from .armijo_finish_results import pack
from .compact_roof_selection_results import match_original_roles, unmeasured
from .full_v5_check import _sha
from .orbit_domain_results import BINDING_FIELDS, COMPACT, POSITIONS, _measures
from .prefix_figures import csv_file

REPORT = trial.REPORT
SOURCE = REPORT / "source-lock.json"
SEAL = REPORT / "prediction-lock.json"
STANDALONE = "standalone-positions.jsonl.gz"
STANDALONE_METHOD = "standalone_orbit_repair"
SCIENTIFIC_FIELDS = tuple(key for key in BINDING_FIELDS if key != "input_sha256")


def _read_sealed(folder, lock_name, file, source):
    path = folder / lock_name
    seal = json.loads(path.read_bytes())
    if _sha(path) != source["comparator_locks_sha256"][folder.name]:
        raise ValueError(f"{folder.name} standalone lock changed before comparison")
    content = folder / file
    if _sha(content) != seal["files"][file]:
        raise ValueError(f"{file} does not bind the measured standalone outcomes")
    return read_predictions(content), _sha(content)


def standalone(source, baseline, frozen):
    domain, domain_hash = _read_sealed(
        trial.domain.REPORT, "prediction-lock.json", POSITIONS, source
    )
    prior, prior_hash = _read_sealed(trial.prior.REPORT, "prediction-lock.json", POSITIONS, source)
    cavity, cavity_hash = _read_sealed(
        trial.CAVITY, "figure-lock.json", "confirmed.jsonl.gz", source
    )
    paired = {}
    for ident in trial.CASES:
        if ident in cavity:
            row, receipt = cavity[ident], cavity_hash
            if row.get("track_config_sha256") != frozen[ident]["track_config"]["sha256"]:
                raise ValueError(f"{ident} standalone cavity used a different track configuration")
        elif ident in prior:
            row, receipt = prior[ident], prior_hash
        else:
            row, receipt = domain[ident], domain_hash
        if any(row[k] != baseline[ident][k] for k in SCIENTIFIC_FIELDS) or (
            "input_sha256" in row and row["input_sha256"] != baseline[ident]["input_sha256"]
        ):
            raise ValueError(f"{ident} standalone repair uses a different scientific request")
        paired[ident] = dict(
            row, mode="matched-tile", method=STANDALONE_METHOD,
            source_method=row["method"], source_receipt_sha256=receipt,
            source_input_sha256=row.get("input_sha256"),
        )
    return paired


def _frozen_inputs():
    _, _, files = trial.domain.compact.roster()
    return corpus._index(corpus._read_frozen("inputs.jsonl", files))


def publish(work):
    source = json.loads(SOURCE.read_bytes())
    if source != trial.source_lock():
        raise ValueError("composed guard sources changed before publication")
    archive = trial.domain.archived()
    repaired = standalone(source, archive, _frozen_inputs())
    rows = []
    for ident in trial.CASES:
        receipt = work / ident / "prediction.json"
        if receipt.is_file():
            row = json.loads(receipt.read_bytes())
            if (
                row["id"] != ident or row["method"] != trial.METHOD
                or row["source_lock_sha256"] != _sha(SOURCE)
                or any(row[k] != archive[ident][k] for k in BINDING_FIELDS)
            ):
                raise ValueError(f"{ident} composed replay did not bind the frozen inputs")
        elif (work / ident).exists():
            raise ValueError(f"{ident} attempted composed replay lacks a worker receipt")
        else:
            row = dict(unmeasured(source["bindings"][ident], False), method=trial.METHOD)
        validate_result(row["result"])
        rows.append(row)
    runtime = json.loads((work / "runtime.json").read_bytes())
    save_json(REPORT / "runtime.json", dict(
        runtime, attempt_counts=dict(Counter(row["result"]["status"] for row in rows)),
        scheduled=len(rows), attempted=sum(row["attempted"] is True for row in rows),
    ))
    files = {
        POSITIONS: pack(REPORT, POSITIONS, rows),
        COMPACT: pack(REPORT, COMPACT, [archive[k] for k in trial.CASES]),
        STANDALONE: pack(REPORT, STANDALONE, repaired.values()),
        "runtime.json": _sha(REPORT / "runtime.json"),
    }
    save_json(SEAL, dict(cases=trial.CASES, files=files, source_lock_sha256=_sha(SOURCE)))


def score():
    seal = json.loads(SEAL.read_bytes())
    if (
        seal["cases"] != list(trial.CASES) or seal["source_lock_sha256"] != _sha(SOURCE)
        or any(_sha(REPORT / name) != value for name, value in seal["files"].items())
    ):
        raise ValueError("composed endpoint or control changed after prediction seal")
    files = {"candidate": POSITIONS, "compact": COMPACT, "standalone": STANDALONE}
    series = {key: read_predictions(REPORT / name) for key, name in files.items()}
    ref = {row["id"]: row for row in corpus.references("ds26-all159")}
    items = _frozen_inputs()
    roles, rows, decisions = {}, [], []
    arm_field = ("status", "error_km", "rf_rms_hz", "matched_rf_rms_hz")
    for ident in trial.CASES:
        reference = ref[ident]
        role, bindings = match_original_roles(reference, items[ident])
        roles[ident] = dict(outcomes=role, bindings=bindings)
        pair = {k: record[ident] for k, record in series.items()}
        for arm in ARMS:
            outcomes = {k: _measures(row, arm, reference["truth"]) for k, row in pair.items()}
            candidate, single = (pair[k]["result"] for k in ("candidate", "standalone"))
            out, comparator = candidate["arms"][arm], single["arms"][arm]
            matched = all(out.get(k) == comparator.get(k) for k in ("latlon", "rf_rms_hz"))
            shared_status = candidate["status"] == single["status"]
            decisions.append(dict(
                id=ident, arm=arm, same_standalone_decision=shared_status and matched,
                same_standalone_reason=candidate.get("reason") == single.get("reason"),
            ))
            rows.append(dict(
                id=ident, arm=arm, comparison_source=pair["standalone"]["source_method"],
                same_standalone_decision=shared_status and matched,
                standalone_endpoint_delta_km=distance_km(out["latlon"], comparator["latlon"]),
                **{f"{k}_{field}": value for k, values in outcomes.items()
                   for field, value in values.items()},
                **{f"{k}_{field}": role[k][arm].get(field) for k in ROLES for field in arm_field},
            ))
    csv_file(REPORT / "scores.csv", rows)
    save_json(REPORT / "original-roles.json", roles)
    save_json(REPORT / "comparison.json", dict(positions_and_rf_match=decisions))
    save_json(REPORT / "score-lock.json", dict(
        prediction_lock_sha256=_sha(SEAL),
        files={name: _sha(REPORT / name)
               for name in ("scores.csv", "original-roles.json", "comparison.json")},
    ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("publish", "score"))
    parser.add_argument("--work", type=Path, default=trial.WORK)
    args = parser.parse_args()
    if args.stage == "publish":
        publish(args.work)
    else:
        score()


if __name__ == "__main__":
    main()
