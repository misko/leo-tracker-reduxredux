"""Publish fresh aligned predictions before comparing them to the known controls."""

import argparse
from hashlib import sha256
from pathlib import Path

from ..__main__ import encoded, local_output, read_predictions, save_json, write
from ..scoring import ARMS, ROLES, distance_km
from . import armijo_aligned_trial as trial
from . import armijo_finish_results as controls
from . import armijo_finish_trial as primary
from . import projector_roof
from .full_v5_check import _sha
from .prefix_figures import csv_file

FILES = {
    trial.METHOD: "positions.jsonl.gz",
    **{
        method: "unaligned-positions.jsonl.gz" if method == primary.METHOD else name
        for method, name in controls.METHODS.items()
    },
}


def request_pair(ident, before, after):
    def science(path):
        request = trial.read(path)
        request["job"].pop("output_root")
        return request

    request = science(before)
    job = request["job"]
    binding = primary.public_binding(ident)
    if (
        request != science(after)
        or job["native_input"]["sha256"] != "sha256:" + binding["native_sha256"]
        or job["evaluation_reference"] is not None
    ):
        raise ValueError(f"{ident} aligned request differs from the first inference")
    return dict(
        primary_request_sha256=_sha(before),
        aligned_request_sha256=_sha(after),
        scientific_request_sha256=sha256(encoded(request)).hexdigest(),
    )


def receipt(ident, path):
    if not path.is_file():
        return controls.missing(ident, trial.METHOD, "No aligned worker returned a receipt")
    data = trial.read(path)
    if (
        data["method"] != trial.METHOD
        or data["cpu"] != trial.PINS[ident]
        or data["source_lock_sha256"] != _sha(trial.SEAL)
        or not 0 < data["worker_wall_s"] <= primary.CASE_LIMIT_S
    ):
        raise ValueError(f"{ident} aligned result differs from the bounded run lock")
    log = path.parent / "position/worker.log"
    if (
        data["result"]["status"] == "unavailable"
        and log.is_file()
        and b"Traceback (most recent call last)" in log.read_bytes()
    ):
        data["result"]["status"] = "failed"
        data["worker_failure_log_sha256"] = _sha(log)
    return controls.entry(ident, trial.METHOD, data, path, "fresh-aligned-replay")


def publish(output, work, first_work):
    locked = trial.read(trial.SEAL)
    if locked != trial.source_lock():
        raise ValueError("the retrospective cohort or scientific source changed")
    lock = trial.read(primary.REPORT / "prediction-lock.json")
    files = {}
    for method, name in controls.METHODS.items():
        source = primary.REPORT / name
        digest = lock["files"][name]
        if _sha(source) != digest:
            raise ValueError("known primary output or its matched control changed")
        write(output / FILES[method], source.read_bytes())
        files[FILES[method]] = digest
    rows, requests = [], {}
    for ident in trial.PINS:
        worker = work / ident
        row = receipt(ident, worker / "prediction.json")
        if (after := worker / "position/request.json").is_file():
            requests[ident] = request_pair(
                ident, first_work / ident / "position/request.json", after
            )
        elif row["result"]["status"] == "ok":
            raise ValueError(f"{ident} successful worker omitted its exact numerical input receipt")
        rows.append(row)
    name = FILES[trial.METHOD]
    files[name] = controls.pack(output, name, rows)
    name = "matched-requests.json"
    save_json(output / name, requests)
    files[name] = _sha(output / name)
    save_json(
        output / "prediction-lock.json",
        dict(cases=list(trial.PINS), files=files, source_lock_sha256=_sha(trial.SEAL)),
    )


def score(output):
    lock = trial.read(output / "prediction-lock.json")
    if lock["source_lock_sha256"] != _sha(trial.SEAL) or any(
        _sha(output / name) != digest for name, digest in lock["files"].items()
    ):
        raise ValueError("aligned predictions or controls changed before scoring")
    refs = {r["id"]: r for r in projector_roof.roster()}
    methods = {key: read_predictions(output / name) for key, name in FILES.items()}
    scores, gates = [], {}
    for ident in trial.PINS:
        ref = refs[ident]
        selected = methods[trial.METHOD][ident]["result"]
        old = methods[primary.METHOD][ident]["result"]
        control = old if old["status"] == "ok" else None
        same_decision = control is not None and all(
            selected["metrics"].get(k) == old["metrics"].get(k)
            for k in ("checked_residual_addition", "reassociation_selected")
        )
        arm_checks = {}
        for arm in ARMS:
            origin = ref["reference"]["baseline"][arm]["latlon"]
            point = selected["arms"][arm]["latlon"]
            peer = old["arms"][arm]["latlon"] if control else origin
            shift = distance_km(point, peer)
            arm_checks[arm] = shift is not None and shift <= (0.001 if control else 0.050)
            row = dict(
                id=ident,
                arm=arm,
                aligned_to_primary_m=None
                if (delta := distance_km(point, old["arms"][arm]["latlon"])) is None
                else delta * 1000,
                aligned_to_original_m=None
                if (delta := distance_km(point, origin)) is None
                else delta * 1000,
                **{role + "_km": ref["reference"][role][arm].get("error_km") for role in ROLES},
            )
            for method, records in methods.items():
                for key, value in controls.measures(records[ident], arm, ref["truth"]).items():
                    row[f"{method}_{key}"] = value
            scores.append(row)
        gates[ident] = dict(
            status=selected["status"],
            expected_reference="unaligned" if control else "original_no_repair_v5",
            same_primary_decision=same_decision if control else None,
            limits_passed=arm_checks,
            accepted=selected["status"] == "ok"
            and all(arm_checks.values())
            and (not control or same_decision),
        )
    csv_file(output / "scores.csv", scores)
    save_json(output / "retrospective-gates.json", gates)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("publish", "score"))
    cli.add_argument("--out", type=local_output, default=trial.REPORT)
    cli.add_argument("--work", type=Path)
    cli.add_argument("--primary-work", type=Path)
    options = cli.parse_args()
    if options.action == "publish":
        if options.work is None or options.primary_work is None:
            cli.error("provide the new and primary numerical worker directories")
        publish(options.out, options.work, options.primary_work)
    else:
        score(options.out)


if __name__ == "__main__":
    main()
