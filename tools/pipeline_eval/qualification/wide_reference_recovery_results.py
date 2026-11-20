"""Seal fresh predictions before opening the original-v5 controls and roof truth."""

import argparse
import gzip
import json
from math import fsum, sqrt
from pathlib import Path

from .. import corpus, whole_iq
from ..__main__ import local_output, save_json
from ..scoring import ARMS, ROLES, distance_km, validate_result
from . import wide_full_v5_results as full
from . import wide_reference_recovery as trial
from .full_receiver_comparison import read, require_fields, seal, sha
from .winner_stream_results import csv_file

METHOD = "wide_original_v5_recovery"
REPEATS = "repeats.jsonl.gz"
PREDICTIONS = "prediction-lock.json"
COMBINED = "positions.jsonl.gz"
COMPARATORS = (full.FULL, full.COMPACT)


def pack(path, rows):
    data = "".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in rows)
    path.write_bytes(gzip.compress(data.encode(), mtime=0))


def unpack(path):
    with gzip.open(path, "rt") as handle:
        return [json.loads(line) for line in handle]


def conditional_residuals(receipt):
    result = {}
    for arm in ARMS:
        rows = receipt["prediction_rows"][arm]
        selected = [r["residual_hz"] for r in rows if r["role"] == "conditional"]
        if not selected:
            raise ValueError("the official fit has no conditional residual observations")
        result[arm] = dict(
            conditional_rms_hz=sqrt(fsum(value**2 for value in selected) / len(selected)),
            conditional_points=len(selected),
            other_points=len(rows) - len(selected),
        )
    return result


def identity(ident, plan):
    row = plan["cases"][ident]
    return dict(
        id=ident,
        mode="matched-tile",
        tile=row["tile"],
        native_sha256=row["native_sha256"],
        catalog_sha256=row["catalog_sha256"],
        capture_era_native_sha256=row["capture_native_sha256"],
        input_sha256=row["request_sha256"],
        original_wide_request_sha256=row["original_request_sha256"],
    )


def seal_repeats(work, dest):
    pin = sha(dest / "source-lock.json")
    if pin != (work / "study.sha256").read_text().strip():
        raise ValueError("numerical run differs from the source lock")
    plan = read(dest / "source-lock.json")
    require_fields(plan, dict(cpu=trial.CPU, cap_s=trial.LIMIT, order=list(trial.CASES)))
    whole_iq.checked(Path(trial.__file__), plan["launcher_sha256"])
    whole_iq.checked(Path(trial.bound.v5.__file__), plan["lean_source_sha256"])
    files = [
        "source-lock.json",
        "PROTOCOL.md",
        "setup-source-lock.json",
        "setup-failures.json",
        REPEATS,
        "resources.json",
    ]
    rows, resources = [], {}
    for ident in trial.CASES:
        run = work / ident
        binding = identity(ident, plan)
        whole_iq.checked(run / "request.json", binding["input_sha256"])
        whole_iq.checked(run / "native.json", binding["native_sha256"])
        service = read(run / "service.json")
        log = whole_iq.checked(run / "service.log", service["log_sha256"])
        resource = full.run_resources(run, service)
        if service["exit_code"] == 0 and service["systemd"]["Result"] == "success":
            raw_path = run / "position.json"
            original = f"{ident}-lean-result.json.gz"
            (dest / original).write_bytes(gzip.compress(raw_path.read_bytes(), mtime=0))
            files.append(original)
            result = read(raw_path)
            for arm in ARMS:
                key = f"{arm}_conditional_rms_hz"
                if key in result["metrics"]:
                    result["arms"][arm]["rf_rms_hz"] = result["metrics"][key]
        else:
            status = "timed_out" if service["systemd"]["Result"] == "timeout" else "failed"
            result = trial.bound.v5._no_fix("Lean original v5 ended as " + status, status=status)
        validate_result(result)
        rows.append(dict(binding, method=METHOD, result=result))
        resources[ident] = resource
        log_name = f"{ident}-service.log"
        (dest / log_name).write_bytes(log.read_bytes())
        files.append(log_name)
    pack(dest / REPEATS, rows)
    save_json(dest / "resources.json", resources)
    save_json(
        dest / PREDICTIONS,
        dict(
            cases=list(trial.CASES),
            source_lock_sha256=pin,
            files={filename: sha(dest / filename) for filename in files},
        ),
    )


def take_comparators(dest):
    pinned = seal(dest, PREDICTIONS, (REPEATS, "source-lock.json"))
    source = read(dest / "source-lock.json")
    parent = trial.bound.REPORT
    parent_lock = seal(parent, PREDICTIONS, (COMBINED, "source-lock.json"))
    require_fields(parent_lock["files"], {"source-lock.json": source["parent_source_lock_sha256"]})
    original = {(row["id"], row["method"]): row for row in unpack(parent / COMBINED)}
    repeats = unpack(dest / REPEATS)
    combined, residuals = [], {}
    for repeat in repeats:
        ident = repeat["id"]
        combined.append(repeat)
        for method in COMPARATORS:
            row = original[ident, method]
            require_fields(
                row, {key: repeat[key] for key in ("tile", "native_sha256", "catalog_sha256")}
            )
            if (
                method == full.FULL
                and row["input_sha256"] != repeat["original_wide_request_sha256"]
            ):
                raise ValueError("comparison is not the original rebound wide request")
            if method == full.FULL and row["result"]["status"] == "ok":
                name = f"{ident}-worker-result.json.gz"
                official = whole_iq.checked(parent / name, parent_lock["files"][name])
                values = conditional_residuals(json.loads(gzip.decompress(official.read_bytes())))
                residuals[ident] = dict(
                    official_receipt_sha256=sha(official),
                    arms=values,
                )
                for arm, item in values.items():
                    row["result"]["arms"][arm]["conditional_rms_hz"] = item["conditional_rms_hz"]
            combined.append(row)
    pack(dest / COMBINED, combined)
    save_json(dest / "original-residuals.json", residuals)
    save_json(
        dest / "comparison-source.json",
        dict(
            repeat_prediction_lock_sha256=sha(dest / PREDICTIONS),
            primary_prediction_lock_sha256=sha(parent / PREDICTIONS),
            primary_positions_sha256=parent_lock["files"][COMBINED],
            cases=pinned["cases"],
        ),
    )
    save_json(
        dest / "comparison-lock.json",
        dict(
            cases=pinned["cases"],
            source_lock_sha256=sha(dest / "source-lock.json"),
            files={
                n: sha(dest / n)
                for n in (
                    COMBINED,
                    "comparison-source.json",
                    "original-residuals.json",
                    REPEATS,
                    PREDICTIONS,
                    "resources.json",
                )
            },
        ),
    )


def score(source, dest):
    seal(source, PREDICTIONS, (REPEATS, "source-lock.json"))
    seal(
        source,
        "comparison-lock.json",
        (COMBINED, "comparison-source.json", "original-residuals.json", REPEATS),
    )
    rows = {(row["id"], row["method"]): row["result"] for row in unpack(source / COMBINED)}
    if set(rows) != {(i, m) for i in trial.CASES for m in (METHOD, *COMPARATORS)}:
        raise ValueError("the comparison does not cover both frozen recordings and all roles")
    refs = {r["id"]: r for r in corpus.references("roof16")}
    stats, parity = [], {}
    for ident in trial.CASES:
        ref = refs[ident]
        lean, primary = (rows[ident, m] for m in (METHOD, full.FULL))
        parity[ident] = dict(primary_status=primary["status"], lean_status=lean["status"], arms={})
        for arm in ARMS:
            lean_value, original = (result["arms"][arm] for result in (lean, primary))
            if lean_value["latlon"] is not None and original["latlon"] is not None:

                def matched(left, right):
                    return left == right if left is not None and right is not None else None

                parity[ident]["arms"][arm] = dict(
                    position_delta_m=distance_km(lean_value["latlon"], original["latlon"]) * 1000,
                    same_coordinates=lean_value["latlon"] == original["latlon"],
                    same_conditional_rms=matched(
                        lean_value.get("rf_rms_hz"), original.get("conditional_rms_hz")
                    ),
                    same_frequency_score=matched(
                        *(
                            result["metrics"].get(f"{arm}_frequency_score")
                            for result in (lean, primary)
                        )
                    ),
                    same_associated_observations=matched(
                        *(
                            result["metrics"].get(f"{arm}_associated_observations")
                            for result in (lean, primary)
                        )
                    ),
                )
            else:
                parity[ident]["arms"][arm] = None
            compact = rows[ident, full.COMPACT]["arms"][arm]
            parity[ident].setdefault("compact_endpoint_delta_m", {})[arm] = (
                distance_km(lean_value["latlon"], compact["latlon"]) * 1000
                if lean_value["latlon"] and compact["latlon"]
                else None
            )
            for method in (METHOD, *COMPARATORS):
                result = rows[ident, method]
                fit = result["arms"][arm]
                stats.append(
                    dict(
                        id=ident,
                        arm=arm,
                        method=method,
                        status=result["status"],
                        error_km=distance_km(ref["truth"], fit["latlon"])
                        if fit["latlon"]
                        else None,
                        conditional_rms_hz=fit.get("conditional_rms_hz")
                        if method == full.FULL
                        else fit.get("rf_rms_hz"),
                        full_evidence_residual_rms_hz=fit.get("rf_rms_hz")
                        if method == full.FULL
                        else None,
                        frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
                        **{r: ref["reference"][r][arm]["error_km"] for r in ROLES},
                    )
                )
    dest.mkdir(exist_ok=True, parents=True)
    csv_file(dest / "scores.csv", stats)
    save_json(dest / "parity.json", parity)
    return parity


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "compare", "score"))
    p.add_argument("source", type=local_output)
    p.add_argument("--out", type=local_output, default=trial.REPORT)
    args = p.parse_args()
    if args.action == "seal":
        seal_repeats(args.source, args.out)
    elif args.action == "compare":
        take_comparators(args.source)
        results = score(args.source, args.out)
        if args.source == args.out:
            lock = args.source / "comparison-lock.json"
            receipt = read(lock)
            receipt["files"].update({n: sha(args.out / n) for n in ("scores.csv", "parity.json")})
            save_json(lock, receipt)
        print(json.dumps(results, indent=2))
    else:
        print(json.dumps(score(args.source, args.out), indent=2))


if __name__ == "__main__":
    main()
