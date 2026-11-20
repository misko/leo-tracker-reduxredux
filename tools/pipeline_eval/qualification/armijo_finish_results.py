"""Publish matched Armijo finish controls before scoring their geographic outcomes."""

import argparse
import gzip
import json
import os
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from ..__main__ import encoded, local_output, read_predictions, save_json, write
from ..scoring import ARMS, ROLES, distance_km, validate_result
from ..variants import compact_finish, v5_armijo_fit, v5_lean
from . import armijo_finish_phase_retry as retry
from . import armijo_finish_trial as trial
from . import projector_roof
from .armijo_confirmation import original_result
from .broad_search_budget import _case, _stock_archive
from .full_v5_check import _load_case, _sha
from .prefix_figures import csv_file
from .secant_end_to_end_worker import cpu_s, stamp
from .secant_fit_trial import failed_result

METHODS = {
    trial.METHOD: "positions.jsonl.gz",
    "orbit_projector": "stock-cavity-positions.jsonl.gz",
    "v5_armijo_fit": "armijo-cavity-positions.jsonl.gz",
    "compact_finish": "stock-finish-positions.jsonl.gz",
}
CAVITY_CONTROL = "DS26-0002"


def entry(ident, method, record, path, source):
    result = record["result"]
    validate_result(result)
    binding = trial.public_binding(ident)
    allowed = (
        {binding["input_sha256"], binding["request_sha256"]}
        if source == "six-case"
        else {binding["input_sha256"]}
    )
    if record["id"] != ident or record["input_sha256"] not in allowed:
        raise ValueError(f"{ident} differs from its matched case or request receipt")
    for key in ("native_sha256", "catalog_sha256", "request_sha256"):
        if key in record and record[key] != binding[key]:
            raise ValueError(f"{ident} historical {key} differs from its frozen inputs")
    return dict(
        record,
        **binding,
        method=method,
        receipt_source=source,
        archived_input_sha256=record["input_sha256"],
        upstream_receipt_sha256=_sha(path),
    )


def run_cavity(work):
    locked = json.loads(trial.SEAL.read_bytes())
    if locked != trial.source_lock() or os.sched_getaffinity(0) != {trial.CPUS[CAVITY_CONTROL]}:
        raise ValueError("the new cavity control needs the sealed source and original lane CPU")
    path = local_output(work) / CAVITY_CONTROL
    if not (path / "prediction.json").is_file():
        raise ValueError("the finish must complete on this lane first")
    case = _case(_load_case(CAVITY_CONTROL))
    wall, cpu = perf_counter(), cpu_s()
    timeout = v5_lean.TIMEOUT_S
    try:
        v5_lean.TIMEOUT_S = trial.CASE_LIMIT_S - 4
        result = v5_armijo_fit.run(case, path / "cavity")
    finally:
        v5_lean.TIMEOUT_S = timeout
    duration = stamp(wall, cpu)
    if "exceeded its " in result.get("reason", ""):
        result["status"] = "timed_out"
    validate_result(result)
    if locked != trial.source_lock():
        raise ValueError("sealed sources changed during the cavity control")
    receipt = dict(
        trial.public_binding(CAVITY_CONTROL),
        method="v5_armijo_fit",
        cpu=trial.CPUS[CAVITY_CONTROL],
        worker_wall_s=duration["wall_s"],
        worker_cpu_s=duration["cpu_s"],
        resources=duration,
        source_lock_sha256=_sha(trial.SEAL),
        result=result,
    )
    save_json(path / "armijo-cavity-control.json", receipt)
    print(
        CAVITY_CONTROL, "Armijo cavity", result["status"], round(duration["wall_s"], 3), flush=True
    )


def archive_armijo(directory):
    path = directory / "armijo-positions.jsonl.gz"
    lock = json.loads((directory / "prediction-lock.json").read_bytes())
    if lock["source_seal_sha256"] != _sha(trial.SCREEN / "seal.json") or lock["files"][
        path.name
    ] != _sha(path):
        raise ValueError("historical Armijo cavity differs from its sealed output")
    rows = read_predictions(path)
    if set(rows) != set(lock["cases"]):
        raise ValueError("historical Armijo cavity roster changed")
    return path, rows


def missing(ident, method, reason):
    return dict(
        trial.public_binding(ident),
        method=method,
        receipt_source="scheduled-missing",
        worker_wall_s=None,
        result=failed_result("missing", reason),
    )


def read_fresh(ident, method, path):
    if not path.is_file():
        return missing(ident, method, "No scheduled worker receipt returned")
    row = json.loads(path.read_bytes())
    if (
        row["method"] != method
        or row["source_lock_sha256"] != _sha(trial.SEAL)
        or row["cpu"] != trial.CPUS[ident]
        or row["worker_wall_s"] <= 0
        or row["worker_wall_s"] > trial.CASE_LIMIT_S
    ):
        raise ValueError(f"{ident} fresh output differs from its bounded qualification")
    worker_log = path.parent / "position/worker.log"
    if (
        row["result"]["status"] == "unavailable"
        and worker_log.is_file()
        and b"Traceback (most recent call last)" in worker_log.read_bytes()
    ):
        row["result"]["status"] = "failed"
        row["worker_failure_log_sha256"] = _sha(worker_log)
    return entry(ident, method, row, path, "fresh-replay")


def read_finish(ident, path):
    if not path.is_file():
        return missing(ident, "compact_finish", "No authenticated stock compact finish receipt")
    record = json.loads(path.read_bytes())
    allowed = json.loads((trial.ARCHIVE / "source-versions.json").read_bytes())
    if (
        record["method"] != "compact_finish"
        or record["qualification"] != "adapter_confirmation"
        or record["implementation_sha256"]
        not in {
            allowed[k]
            for k in (
                "confirmed_adapter_source_before_import_spacing",
                "confirmed_adapter_source_before_output_guard",
            )
        }
        or record["result"]["boundary"] != compact_finish.BOUNDARY
        or record["result"]["metrics"]["kernel_sha256"] != allowed["projector_kernel"]
    ):
        raise ValueError(f"{ident} archived stock finish bindings differ")
    return entry(ident, "compact_finish", record, path, "archived-adapter")


def pack(output, name, rows):
    path = output / name
    write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))
    return _sha(path)


def publish(output, work):
    if json.loads(trial.SEAL.read_bytes()) != trial.source_lock():
        raise ValueError("source lock differs before publication")
    stock, hashes = _stock_archive()
    stock_path = projector_roof.REPORT / projector_roof.PREDICTIONS
    stress_path, stress = archive_armijo(trial.SCREEN / "stress")
    six_path, six = archive_armijo(trial.SCREEN)
    rows = {method: [] for method in METHODS}
    for ident in trial.CASES:
        rows[trial.METHOD].append(read_fresh(ident, trial.METHOD, work / ident / "prediction.json"))
        case = _case(_load_case(ident))
        validated = projector_roof.validate_prediction(stock[ident], hashes, case=case)
        rows["orbit_projector"].append(
            entry(ident, "orbit_projector", validated, stock_path, "archived-stock")
        )
        rows["compact_finish"].append(
            read_finish(ident, trial.ARCHIVE / "adapter" / f"{ident}.json")
        )
        if ident == CAVITY_CONTROL:
            armijo = read_fresh(ident, "v5_armijo_fit", work / ident / "armijo-cavity-control.json")
        elif ident in stress:
            armijo = entry(ident, "v5_armijo_fit", stress[ident], stress_path, "archived-stress")
        else:
            armijo = entry(ident, "v5_armijo_fit", six[ident], six_path, "six-case")
        rows["v5_armijo_fit"].append(armijo)
    files = {name: pack(output, name, rows[method]) for method, name in METHODS.items()}
    save_json(
        output / "prediction-lock.json",
        dict(cases=trial.CASES, files=files, source_lock_sha256=_sha(trial.SEAL)),
    )


def measures(row, arm, truth):
    result = row["result"]
    metrics = result["metrics"]
    endpoint = result["arms"][arm]
    original = row["method"] == "original_no_repair_v5"
    return dict(
        status=result["status"],
        error_km=distance_km(endpoint["latlon"], truth),
        conditional_doppler_rms_hz=None
        if original
        else metrics.get(f"{arm}_conditional_rms_hz", endpoint.get("rf_rms_hz")),
        published_residual_rms_hz=endpoint.get("rf_rms_hz") if original else None,
        frequency_score=metrics.get(f"{arm}_frequency_score", endpoint.get("frequency_score")),
        associated_observations=metrics.get(
            f"{arm}_associated_observations", endpoint.get("associated_observations")
        ),
    )


def score(output):
    lock = json.loads((output / "prediction-lock.json").read_bytes())
    if lock["source_lock_sha256"] != _sha(trial.SEAL) or any(
        _sha(output / name) != digest for name, digest in lock["files"].items()
    ):
        raise ValueError("predictions or preregistered sources changed before scoring")
    refs = {r["id"]: r for r in projector_roof.roster()}
    positions = {key: read_predictions(output / name) for key, name in METHODS.items()}
    original, original_roles, scores = [], {}, []
    for ident in trial.CASES:
        ref = refs[ident]
        item = _load_case(ident)
        origin = original_result(item, ref, trial.public_binding(ident))
        origin["method"] = "original_no_repair_v5"
        original.append(origin)
        original_roles[ident] = {role: ref["reference"][role] for role in ROLES}
        for arm in ARMS:
            paired = {key: d[ident] for key, d in positions.items()}
            statistics = {
                key: measures(r, arm, ref["truth"])
                for key, r in {**paired, origin["method"]: origin}.items()
            }
            finish = paired[trial.METHOD]["result"]
            pos = finish["arms"][arm]["latlon"]
            row = dict(
                id=ident,
                arm=arm,
                **{
                    role + "_km": original_roles[ident][role][arm].get("error_km") for role in ROLES
                },
            )
            for method, values in statistics.items():
                row.update({f"{method}_{key}": value for key, value in values.items()})
                control = paired.get(method, origin)["result"]["arms"][arm]["latlon"]
                distance = distance_km(pos, control)
                row[f"{method}_to_armijo_finish_m"] = None if distance is None else distance * 1000
            scores.append(row)
    csv_file(output / "scores.csv", scores)
    save_json(output / "original-roles.json", original_roles)
    pack(output, "original-positions.jsonl.gz", original)


def publish_retry(output, work, retry_output):
    first_path = work / retry.CASE / "prediction.json"
    first = read_fresh(retry.CASE, trial.METHOD, first_path)
    locked = json.loads(retry.LOCK.read_bytes())
    if first["result"]["status"] != "failed" or locked != retry.source_lock(first_path):
        raise ValueError("retry must stay linked to the original failed calculation")
    first_request = first_path.parent / "position/request.json"
    second_request = retry_output / "request.json"

    def science_request(path):
        request = json.loads(path.read_bytes())
        request["job"].pop("output_root")
        return request

    scientific = science_request(first_request)
    if (
        scientific != science_request(second_request)
        or scientific["job"]["evaluation_reference"] is not None
    ):
        raise ValueError("the original and retried workers received different scientific inputs")
    path = retry_output / "prediction.json"
    raw = json.loads(path.read_bytes())
    if (
        raw["method"] != retry.METHOD
        or raw["cpu"] != retry.CPU
        or raw["retry_lock_sha256"] != _sha(retry.LOCK)
        or not 0 < raw["worker_wall_s"] <= trial.CASE_LIMIT_S
    ):
        raise ValueError("retried result differs from its source and run lock")
    shape_path = retry_output / "phase-shape.json"
    shape = shape_path.is_file()
    if raw["phase_shape_sha256"] != (_sha(shape_path) if shape else None):
        raise ValueError("observed ordered initializer sidecar changed")
    if raw["result"]["status"] == "ok" and not shape:
        raise ValueError("position publication needs the exercised phase initializer")
    if (
        raw["result"]["status"] == "unavailable"
        and b"Traceback (most recent call last)" in (retry_output / "worker.log").read_bytes()
    ):
        raw["result"]["status"] = "failed"
    second = entry(retry.CASE, retry.METHOD, raw, path, "fresh-ordered-phase-retry")
    files = {}
    for name, row in (
        ("phase-retry-positions.jsonl.gz", second),
        ("phase-retry-first-attempt.jsonl.gz", first),
    ):
        files[name] = pack(output, name, [row])
    if shape:
        name = "phase-retry-ordered-inputs.json.gz"
        write(output / name, gzip.compress(shape_path.read_bytes(), mtime=0))
        files[name] = _sha(output / name)
    name = "phase-retry-primary-traceback.txt"
    write(output / name, (first_path.parent / "position/worker.log").read_bytes())
    files[name] = _sha(output / name)
    name = "phase-retry-primary-receipt.json"
    write(output / name, first_path.read_bytes())
    files[name] = _sha(output / name)
    primary_lock = json.loads((output / "prediction-lock.json").read_bytes())
    for name in (
        METHODS[trial.METHOD],
        METHODS["orbit_projector"],
        METHODS["v5_armijo_fit"],
        METHODS["compact_finish"],
    ):
        if _sha(output / name) != primary_lock["files"][name]:
            raise ValueError("primary experiment changed before retry publication")
        files[name] = primary_lock["files"][name]
    save_json(
        output / "phase-retry-prediction-lock.json",
        dict(
            cases=[retry.CASE],
            files=files,
            source_lock_sha256=_sha(retry.LOCK),
            scientific_request_sha256=sha256(encoded(scientific)).hexdigest(),
            primary_request_sha256=_sha(first_request),
            retry_request_sha256=_sha(second_request),
        ),
    )


def score_retry(output):
    lock = json.loads((output / "phase-retry-prediction-lock.json").read_bytes())
    if lock["source_lock_sha256"] != _sha(retry.LOCK) or any(
        _sha(output / name) != digest for name, digest in lock["files"].items()
    ):
        raise ValueError("retried result or ordered phase inputs changed after publication")
    ref = next(row for row in projector_roof.roster() if row["id"] == retry.CASE)
    row = read_predictions(output / "phase-retry-positions.jsonl.gz")[retry.CASE]
    cavity = read_predictions(output / METHODS["v5_armijo_fit"])[retry.CASE]
    stock = read_predictions(output / METHODS["compact_finish"])[retry.CASE]
    scores = []
    for arm in ARMS:
        endpoint = row["result"]["arms"][arm]["latlon"]
        result = dict(id=retry.CASE, arm=arm, **measures(row, arm, ref["truth"]))
        for source, point in (
            ("armijo_cavity", cavity["result"]["arms"][arm]["latlon"]),
            ("stock_finish", stock["result"]["arms"][arm]["latlon"]),
            ("original_no_repair_v5", ref["reference"]["baseline"][arm]["latlon"]),
        ):
            shift = distance_km(endpoint, point)
            result[source + "_shift_m"] = None if shift is None else 1000 * shift
        result.update({role + "_km": ref["reference"][role][arm].get("error_km") for role in ROLES})
        scores.append(result)
    csv_file(output / "phase-retry-scores.csv", scores)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("cavity", "publish", "score", "publish-retry", "score-retry")
    )
    parser.add_argument("--work", type=Path)
    parser.add_argument("--retry", type=Path)
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    args = parser.parse_args()
    if args.action in ("cavity", "publish", "publish-retry") and args.work is None:
        parser.error("provide the work directory for inference or prediction publication")
    if args.action == "cavity":
        run_cavity(args.work)
    elif args.action == "publish":
        publish(args.out, args.work)
    elif args.action == "score":
        score(args.out)
    elif args.action == "publish-retry":
        if args.retry is None:
            parser.error("provide the separate retry worker directory")
        publish_retry(args.out, args.work, args.retry)
    else:
        score_retry(args.out)


if __name__ == "__main__":
    main()
