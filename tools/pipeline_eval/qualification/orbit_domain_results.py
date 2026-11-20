"""Seal causal orbit-support predictions and score the matched retrospective panel."""

import argparse
import json
from pathlib import Path

from .. import corpus
from ..__main__ import read_predictions, save_json
from ..scoring import ARMS, ROLES, distance_km, distribution, validate_result
from . import orbit_domain_trial as trial
from .armijo_finish_results import pack
from .compact_roof_selection_results import match_original_roles
from .full_v5_check import _sha
from .prefix_figures import csv_file

POSITIONS = "positions.jsonl.gz"
COMPACT = "compact-positions.jsonl.gz"
DIAGNOSES = "diagnostic-traces.jsonl.gz"
LOCK = "prediction-lock.json"
BINDING_FIELDS = (
    "native_sha256", "catalog_sha256", "input_sha256", "frozen_request_sha256", "tile"
)


def publish(work, diagnostic):
    report = trial.REPORT
    source = report / "source-lock.json"
    frozen = json.loads(source.read_bytes())
    if frozen != json.loads(json.dumps(trial.source_lock())):
        raise ValueError("orbit domain inputs or frozen worker changed before publication")
    stock = trial.archived()
    rows = []
    for ident in trial.CASES:
        row = json.loads((work / ident / "prediction.json").read_bytes())
        if (
            row["id"] != ident or row["method"] != trial.METHOD
            or row["source_lock_sha256"] != _sha(source)
            or any(row[key] != stock[ident][key] for key in BINDING_FIELDS)
        ):
            raise ValueError(f"{ident} result differs from its frozen matched evidence")
        validate_result(row["result"])
        rows.append(row)
    diagnoses = []
    for ident in trial.FAILED + trial.ASSERTIONS:
        data = json.loads((diagnostic / ident / "diagnostic.json").read_bytes())
        if ident in trial.FAILED and (
            not data["witnesses"] or data["error"] != "orbit phase interpolation never extrapolates"
        ):
            raise ValueError("missing original orbit failure witness")
        diagnoses.append(dict(id=ident, **data))
    files = {
        POSITIONS: pack(report, POSITIONS, rows),
        COMPACT: pack(report, COMPACT, [stock[k] for k in trial.CASES]),
        DIAGNOSES: pack(report, DIAGNOSES, diagnoses),
    }
    save_json(report / LOCK, dict(cases=trial.CASES, files=files, source_lock_sha256=_sha(source)))


def _measures(row, arm, truth):
    endpoint = row["result"]["arms"][arm]
    return dict(
        status=row["result"]["status"],
        error_km=distance_km(endpoint["latlon"], truth),
        conditional_rms_hz=endpoint.get("rf_rms_hz"),
        wall_s=row.get("worker_wall_s"),
    )


def score():
    report = trial.REPORT
    prediction_lock = report / LOCK
    lock = json.loads(prediction_lock.read_bytes())
    if lock["cases"] != list(trial.CASES) or lock["source_lock_sha256"] != _sha(
        report / "source-lock.json"
    ) or any(_sha(report / k) != v for k, v in lock["files"].items()):
        raise ValueError("the orbit support prediction seal does not verify")
    compact_score = trial.compact.REPORT / "score-lock.json"
    original_lock = json.loads(compact_score.read_bytes())
    original_names = ("original-roles.json", "original-role-bindings.json")
    if any(_sha(trial.compact.REPORT / name) != original_lock["files"][name]
           for name in original_names):
        raise ValueError("original capture-era roles do not match their score lock")
    original_roles, original_bindings = (
        json.loads((trial.compact.REPORT / name).read_bytes()) for name in original_names
    )
    candidate, compact = (read_predictions(report / name) for name in (POSITIONS, COMPACT))
    refs = {row["id"]: row for row in corpus.references("ds26-all159")}
    _, _, files = trial.compact.roster()
    items = corpus._index(corpus._read_frozen("inputs.jsonl", files))
    scores, pairs, verified = [], [], {}
    for ident in trial.CASES:
        ref = refs[ident]
        original, binding = match_original_roles(ref, items[ident])
        if original != original_roles[ident] or binding != original_bindings[ident]:
            raise ValueError(f"{ident} original v5 role authority changed")
        verified[ident] = dict(outcomes=original, bindings=binding)
        for arm in ARMS:
            cand = candidate[ident]
            old = compact[ident]
            comparison = dict(
                id=ident, group="failed-support" if ident in trial.FAILED else "unchanged-control",
                arm=arm, orbit_domain=_measures(cand, arm, ref["truth"]),
                compact=_measures(old, arm, ref["truth"]),
                same_input_endpoint_delta_km=distance_km(
                    cand["result"]["arms"][arm]["latlon"], old["result"]["arms"][arm]["latlon"]
                ),
            )
            pairs.append(comparison)
            scores.append(dict(
                id=ident, group=comparison["group"], arm=arm,
                same_input_endpoint_delta_km=comparison["same_input_endpoint_delta_km"],
                **{f"{method}_{key}": value for method in ("orbit_domain", "compact")
                   for key, value in comparison[method].items()},
                **{f"{role}_{key}": original[role][arm].get(key) for role in ROLES
                   for key in ("status", "error_km", "rf_rms_hz", "matched_rf_rms_hz", "wall_s")},
            ))
    summaries = {
        group: {
            arm: {
                method: {
                    key: distribution(
                        row[method][key] for row in pairs
                        if row["group"] == group and row["arm"] == arm
                    ) for key in ("error_km", "conditional_rms_hz", "wall_s")
                } for method in ("orbit_domain", "compact")
            } for arm in ARMS
        } for group in ("failed-support", "unchanged-control")
    }
    csv_file(report / "scores.csv", scores)
    save_json(report / "summary.json", dict(groups=summaries, matched_arms=pairs))
    save_json(report / "original-roles.json", verified)
    save_json(report / "score-lock.json", dict(
        prediction_lock_sha256=_sha(prediction_lock),
        previous_role_score_lock_sha256=_sha(compact_score),
        files={name: _sha(report / name)
               for name in ("scores.csv", "summary.json", "original-roles.json")},
    ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("publish", "score"))
    parser.add_argument("--work", type=Path, default=Path("/tmp/leo-orbit-domain-candidate-v2"))
    parser.add_argument(
        "--diagnostic", type=Path, default=Path("/tmp/leo-orbit-domain-diagnostics-v1")
    )
    args = parser.parse_args()
    if args.stage == "publish":
        publish(args.work, args.diagnostic)
    else:
        score()


if __name__ == "__main__":
    main()
