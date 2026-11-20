"""Confirm the frozen two-refresh budget on hash-selected roof recordings."""

import argparse
import fcntl
import gzip
import importlib
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from queue import SimpleQueue
from time import perf_counter

from .. import corpus
from ..__main__ import (
    encoded,
    local_output,
    module_name,
    read_predictions,
    run_one,
    save_json,
    write,
)
from ..scoring import ARMS, ROLES, distance_km, distribution, thresholds, validate_result
from ..variants import orbit_projector, v5_core, v5_lean
from . import projector_roof
from .broad_search_budget import _case, _pair_summary, _read, _stock_archive, frozen_inputs
from .prefix_figures import TIMING_IDS, csv_file
from .search_budget import digest
from .v5_postfit import ARCHIVE
from .v5_prefix_audit import DS29

METHOD = "v5_two_refresh"
STOCK = projector_roof.METHOD
REPORT = corpus.REPO / "reports/2026_11_19_receiver_convergence/phase-confirmation"
SCRATCH = Path("/srv/bulk/leo-dev/receiver-convergence-20261119/phase-confirmation")
CAP_S = 480
CPUS = frozenset({16, 17, 18, 19})
PREFIX = "phase-refresh-confirm-v1:"


def confirmation_ids(inputs):
    eligible = set(inputs) - set(TIMING_IDS)
    ds26 = sorted(
        (ident for ident in eligible if ident.startswith("DS26-")),
        key=lambda ident: corpus._sha((PREFIX + ident).encode()),
    )[:16]
    ds29 = sorted(ident for ident in eligible if ident.startswith("DS29-"))
    if len(ds26) != 16 or len(ds29) != 5:
        raise ValueError("the frozen confirmation roster must provide 16 DS26 and five DS29")
    return ds26, ds29


def roster(inputs):
    ds26, ds29 = confirmation_ids(inputs)
    cases = ds26 + ds29
    return dict(
        cases=cases,
        ds26_in_hash_order=ds26,
        ds29=ds29,
        timing_cases=list(TIMING_IDS),
        hash_prefix=PREFIX,
        deadline_s=CAP_S,
        protocol_sha256=digest(REPORT / "PROTOCOL.md"),
        case_bindings={
            ident: {f"{k}_sha256": inputs[ident][k]["sha256"] for k in ("native", "catalog")}
            for ident in cases
        },
    )


def pinned_sources(method=METHOD):
    module = importlib.import_module(module_name(method))
    paths = (
        module.__file__,
        v5_core.__file__,
        v5_lean.__file__,
        orbit_projector.__file__,
        orbit_projector.KERNEL,
    )
    return {Path(path).name: digest(path) for path in paths}


def _validate_candidate(row, ident, case, binding, sources, *, method=METHOD, cli_digest=None):
    if (
        row["id"] != ident
        or row["method"] != method
        or row["source_sha256"] != sources
        or row["deadline_s"] != CAP_S
        or row["cpu"] not in CPUS
        or row["worker_wall_s"] <= 0
        or row["input_sha256"] != projector_roof.input_hash(case)
        or any(row[k] != value for k, value in binding.items())
    ):
        raise ValueError(f"{ident} candidate differs from its frozen request or source")
    result = row["result"]
    validate_result(result)
    module = module_name(method).rsplit(".", 1)[1] + ".py"
    if result["status"] == "ok" and (
        row["implementation_sha256"] != (cli_digest or sources[module])
        or result["metrics"].get("kernel_sha256") != sources["orbit_projector.c"]
        or (method == METHOD and result["metrics"].get("outer_phase_limit") != 2)
        or set(result.get("arms", {})) != set(ARMS)
    ):
        raise ValueError(f"{ident} did not complete the frozen paired compact cavity worker")
    return row


def replay(
    work, cpus, frozen_source, *, method=METHOD, select=roster, validate=_validate_candidate
):
    if not cpus or len(cpus) != len(set(cpus)) or not set(cpus) <= CPUS & os.sched_getaffinity(0):
        raise ValueError("select distinct available CPUs from cores 16–19")
    if frozen_source != pinned_sources(method):
        raise ValueError(f"{method} source differs from the independent source lock")
    work = local_output(work)
    work.mkdir(parents=True, exist_ok=True)
    with (work / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        inputs = frozen_inputs()
        plan = dict(select(inputs), sources=frozen_source, scientific_source=v5_lean.SOURCE_SHA256)
        plan_path = work / "plan.json"
        if plan_path.exists():
            if plan != _read(plan_path):
                raise ValueError("the confirmation roster or source has changed")
        else:
            save_json(plan_path, plan)
        journal = work / "runs"
        journal.mkdir(exist_ok=True)
        available = SimpleQueue()
        for cpu in cpus:
            available.put(cpu)

        def measure(ident):
            case = _case(inputs[ident])
            binding = plan["case_bindings"][ident]
            target = journal / f"{ident}.json"
            if target.exists():
                return validate(_read(target), ident, case, binding, frozen_source)
            cpu = available.get()
            try:
                row = run_one(method, case, work, CAP_S, cpu)
            finally:
                available.put(cpu)
            if frozen_source != pinned_sources(method):
                raise ValueError("candidate source changed during qualification")
            row.update(
                method=method,
                source="fresh_confirmation",
                cpu=cpu,
                deadline_s=CAP_S,
                source_sha256=frozen_source,
                **binding,
            )
            validate(row, ident, case, binding, frozen_source)
            save_json(target, row)
            return row

        started = perf_counter()
        with ThreadPoolExecutor(max_workers=len(cpus)) as pool:
            futures = [pool.submit(measure, ident) for ident in plan["cases"]]
            for done, job in enumerate(as_completed(futures), 1):
                row = job.result()
                print(
                    done,
                    row["id"],
                    row["result"]["status"],
                    round(row["worker_wall_s"], 2),
                    flush=True,
                )
        save_json(work / "run-receipt.json", dict(cpus=list(cpus), wall_s=perf_counter() - started))


def _original_v5_bindings(item):
    root = ARCHIVE if item["id"].startswith("DS26-") else DS29
    directory = root / f"{item['id']}-r0"
    request_digests = {}
    baseline_catalogue = None
    for role in ROLES:
        request = _read(directory / role / "experimental-request.json")
        execution = directory / f"{role}-execution.json"
        recorded = _read(execution)
        job = request["job"]
        snapshots = request["causal_snapshots"]
        recent = max(
            (int(name.split("-")[0]), checksum.removeprefix("sha256:"))
            for name, checksum in snapshots.items()
            if int(name.split("-")[0]) < item["cutoff_utc_ns"]
        )
        checksum = "sha256:" + corpus._sha(encoded(request))
        if baseline_catalogue is None:
            baseline_catalogue = snapshots
        if (
            recorded["request_sha256"] != checksum
            or recorded["worker"]["request_sha256"] != checksum
            or request["role"] != role
            or recorded["role"] != role
            or recorded["status"] != "complete"
            or request["source"]["sha256"] != v5_lean.SOURCE_SHA256
            or job["identity"]["session_id"] != item["session_id"]
            or job["evaluation_reference"] is not None
            or job["search_center"] != item["regions"][0]["center"]
            or job["native_input"]["sha256"] != "sha256:" + item["native"]["sha256"]
            or recent != (item["catalog_timestamp_ns"], item["catalog"]["sha256"])
            or snapshots != baseline_catalogue
        ):
            raise ValueError(f"{item['id']} original {role} was not bound to the same inputs")
        request_digests[role] = dict(request_sha256=checksum, execution_sha256=digest(execution))
    return request_digests


def seal(work, output, *, method=METHOD, select=roster, validate=_validate_candidate):
    inputs = frozen_inputs()
    plan = _read(work / "plan.json")
    if plan != dict(
        select(inputs), sources=pinned_sources(method), scientific_source=v5_lean.SOURCE_SHA256
    ):
        raise ValueError("the saved confirmation plan differs from the replay sources or roster")
    archive, stock_hashes = _stock_archive()
    candidate, stock = [], []
    for ident in plan["cases"]:
        case = _case(inputs[ident])
        binding = plan["case_bindings"][ident]
        path = work / "runs" / f"{ident}.json"
        row = validate(_read(path), ident, case, binding, plan["sources"])
        candidate.append(dict(row, original_run_sha256=digest(path)))
        saved = dict(projector_roof.validate_prediction(archive[ident], stock_hashes, case=case))
        if row["result"]["status"] == "ok" and any(
            row["result"]["metrics"][key] != saved["result"]["metrics"][key]
            for key in ("initial_branches", "observations", "tracks")
        ):
            raise ValueError(f"{ident} observation or original branch count differs from stock")
        saved["archived_worker_wall_s"] = saved.pop("worker_wall_s")
        saved["archive_source"] = saved.pop("source")
        stock.append(dict(saved, source="archived_projector", method=STOCK, **binding))

    save_json(output / "plan.json", plan)
    for name, records in ((method, candidate), (STOCK, stock)):
        write(
            output / f"{name}.jsonl.gz",
            gzip.compress(b"".join(encoded(r) + b"\n" for r in records), mtime=0),
        )
    primary = ("plan.json", f"{method}.jsonl.gz", f"{STOCK}.jsonl.gz")
    predicted = {name: digest(output / name) for name in primary}
    save_json(output / "prediction-lock.json", dict(cases=plan["cases"], files=predicted))

    original = {ident: _original_v5_bindings(inputs[ident]) for ident in plan["cases"]}
    save_json(output / "original-v5-inputs.json", original)
    files = (*primary, "prediction-lock.json", "original-v5-inputs.json")
    save_json(
        output / "receipt.json",
        dict(
            cases=plan["cases"],
            files={name: digest(output / name) for name in files},
            sources=plan["sources"],
            scientific_source=plan["scientific_source"],
            stock_receipt_sha256=digest(projector_roof.REPORT / projector_roof.ARCHIVE_RECEIPT),
            deadline_s=CAP_S,
            run=_read(work / "run-receipt.json"),
        ),
    )


def score(output, *, candidate_method=METHOD):
    receipt = _read(output / "receipt.json")
    expected = {
        "plan.json",
        "prediction-lock.json",
        "original-v5-inputs.json",
        f"{candidate_method}.jsonl.gz",
        f"{STOCK}.jsonl.gz",
    }
    if receipt["files"].keys() != expected or any(
        digest(output / name) != checksum for name, checksum in receipt["files"].items()
    ):
        raise ValueError("no intact confirmation prediction seal")
    candidate = read_predictions(output / f"{candidate_method}.jsonl.gz")
    stock = read_predictions(output / f"{STOCK}.jsonl.gz")
    if candidate.keys() != stock.keys() or candidate.keys() != set(receipt["cases"]):
        raise ValueError("method predictions differ from the same declared roster")
    if any(r["input_sha256"] != stock[ident]["input_sha256"] for ident, r in candidate.items()):
        raise ValueError("method predictions use differing recording inputs")
    prediction_lock = _read(output / "prediction-lock.json")
    if prediction_lock != dict(
        cases=receipt["cases"],
        files={
            name: receipt["files"][name]
            for name in ("plan.json", f"{candidate_method}.jsonl.gz", f"{STOCK}.jsonl.gz")
        },
    ):
        raise ValueError("released predictions differ from their pre-reference lock")
    refs = {r["id"]: r for r in projector_roof.roster() if r["id"] in candidate}
    original = _read(output / "original-v5-inputs.json")
    rows = []
    for ident in receipt["cases"]:
        ref = refs[ident]
        a, b = candidate[ident], stock[ident]
        root = ARCHIVE if ident.startswith("DS26-") else DS29
        old = {}
        for role in ROLES:
            path = root / f"{ident}-r0" / f"{role}-execution.json"
            if digest(path) != original[ident][role]["execution_sha256"]:
                raise ValueError(f"{ident} original {role} execution record changed")
            old[role] = _read(path)["worker"]["arms"]
        for arm in ARMS:
            endpoints = {r["method"]: r["result"].get("arms", {}).get(arm, {}) for r in (a, b)}
            endpoints.update({role: ref["reference"][role][arm] for role in ROLES})
            for role in ROLES:
                frozen_point = endpoints[role]["latlon"]
                archived_point = old[role][arm]["endpoint_latlon"]
                separation = distance_km(frozen_point, archived_point)
                if (frozen_point is None) != (archived_point is None) or (
                    separation is not None and separation > 1e-6
                ):
                    raise ValueError(
                        f"{ident} original {role}/{arm} endpoint differs from frozen reference"
                    )
            row = dict(
                recording=ident,
                dataset=ref["group"],
                arm=arm,
                source=a["source"],
                status=a["result"]["status"],
                reason=a["result"].get("reason"),
                worker_wall_s=a.get("worker_wall_s"),
                prior_timing_worker_wall_s=a.get("prior_timing_worker_wall_s"),
                prior_confirmation_worker_wall_s=a.get("prior_confirmation_worker_wall_s"),
                archived_stock_worker_wall_s=b["archived_worker_wall_s"],
                candidate_to_stock_km=distance_km(
                    endpoints[candidate_method].get("latlon"), endpoints[STOCK].get("latlon")
                ),
                candidate_to_baseline_km=distance_km(
                    endpoints[candidate_method].get("latlon"), endpoints["baseline"]["latlon"]
                ),
            )
            for method, fit in endpoints.items():
                row[f"{method}_error_km"] = distance_km(fit.get("latlon"), ref["truth"])
                row[f"{method}_rf_rms_hz"] = fit.get("rf_rms_hz")
            rows.append(row)

    summaries = []
    for dataset in ("DS26", "DS29", "all"):
        for arm in ARMS:
            selected = [r for r in rows if r["arm"] == arm and dataset in ("all", r["dataset"])]
            candidate_error = f"{candidate_method}_error_km"
            for method in (candidate_method, STOCK, *ROLES):
                errors = [r[f"{method}_error_km"] for r in selected]
                paired = [
                    (r[candidate_error], error)
                    for r, error in zip(selected, errors, strict=True)
                    if r[candidate_error] is not None and error is not None
                ]
                regressions = sorted(
                    (
                        dict(recording=r["recording"], error_increase_km=r[candidate_error] - error)
                        for r, error in zip(selected, errors, strict=True)
                        if r[candidate_error] is not None
                        and error is not None
                        and r[candidate_error] > error
                    ),
                    key=lambda r: (-r["error_increase_km"], r["recording"]),
                )
                summaries.append(
                    dict(
                        dataset=dataset,
                        arm=arm,
                        method=method,
                        scheduled=len(selected),
                        error_km=distribution(errors),
                        within_km=thresholds(errors),
                        rf_rms_hz=distribution(r[f"{method}_rf_rms_hz"] for r in selected),
                        paired_errors=_pair_summary(paired) if method != candidate_method else None,
                        matched_candidate_error_km=distribution(pair[0] for pair in paired),
                        matched_method_error_km=distribution(pair[1] for pair in paired),
                        worst_regressions=regressions[:5],
                    )
                )
    csv_file(output / "per-recording.csv", rows)
    timing = {}
    for dataset in ("DS26", "DS29", "all"):
        one_arm = [r for r in rows if r["arm"] == ARMS[0] and dataset in ("all", r["dataset"])]
        timing[dataset] = dict(
            candidate_statuses=dict(Counter(r["status"] for r in one_arm)),
            source_counts=dict(Counter(r["source"] for r in one_arm)),
            **{
                name: distribution(r[name] for r in one_arm)
                for name in (
                    "worker_wall_s",
                    "prior_timing_worker_wall_s",
                    "prior_confirmation_worker_wall_s",
                    "archived_stock_worker_wall_s",
                )
            },
        )
    save_json(output / "summary.json", dict(groups=summaries, timing=timing))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("roster", "run", "seal", "score"))
    parser.add_argument("--work", type=Path, default=SCRATCH)
    parser.add_argument("--output", type=Path, default=REPORT)
    parser.add_argument("--cpus", type=int, nargs="+")
    parser.add_argument("--source-lock", type=Path)
    args = parser.parse_args()
    if args.command == "roster":
        save_json(args.output / "roster.json", roster(frozen_inputs()))
    elif args.command == "run":
        if args.source_lock is None:
            parser.error("run needs the finalized --source-lock")
        replay(args.work, args.cpus, _read(args.source_lock))
    elif args.command == "seal":
        seal(args.work, args.output)
    else:
        score(args.output)


if __name__ == "__main__":
    main()
