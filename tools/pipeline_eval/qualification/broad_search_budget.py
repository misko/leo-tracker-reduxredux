"""Qualify first-ranked compact v5 on all original branch disagreements."""

import argparse
import fcntl
import gzip
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from queue import SimpleQueue

from .. import corpus
from ..__main__ import (
    DEFAULT_OUT,
    encoded,
    local_output,
    read_predictions,
    run_one,
    save_json,
    write,
)
from ..scoring import ARMS, distance_km, distribution, thresholds, validate_result
from ..variants import v5_lean
from . import initial_branch_audit, projector_roof, search_budget
from .prefix_figures import TIMING_IDS, csv_file, load_rows

METHOD = "v5_first_ranked"
BROAD = "v5_first_ranked_broad"
REPORT = search_budget.REPORT / "broad"
CHECKPOINTS = search_budget.REPORT / "initial-checkpoints"
SCRATCH = Path("/srv/bulk/leo-dev/short-receiver-20261119/search-budget-broad")
TIMING_RUNS = SCRATCH.with_name("search-budget")
CAP_S = 600
CONTROL_COUNT = 3
DISAGREEMENT_REUSE = "DS26-0036"
STOCK = projector_roof.METHOD
METHODS = (BROAD, STOCK, "baseline")
COHORTS = ("scheduled", "replayed", "original_nonzero_rank", "sha_agreement", "timing_agreement")


def _read(path):
    return json.loads(path.read_bytes())


def frozen_inputs():
    ds26, files = corpus._selection("ds26-common127")
    roof, _ = corpus._selection("roof16")
    ids = ds26 + [ident for ident in roof if ident.startswith("DS29-")]
    if len(set(ids)) != 135 or len(ds26) != 127:
        raise ValueError("expected the frozen 127 DS26 and eight DS29 recordings")
    index = corpus._index(corpus._read_frozen("inputs.jsonl", files))
    return {ident: index[ident] for ident in ids}


def _archive_ranks(inputs):
    lock = _read(CHECKPOINTS / "receipt.json")
    name = f"{initial_branch_audit.STOCK}.jsonl.gz"
    path = CHECKPOINTS / name
    if (
        lock["scientific_source"] != v5_lean.SOURCE_SHA256
        or set(lock["cases"]) != inputs.keys()
        or lock["files"][name] != search_budget.digest(path)
    ):
        raise ValueError("original initial branch archive differs from its receipt")
    records = read_predictions(path)
    if records.keys() != inputs.keys():
        raise ValueError("original branch archive differs from the frozen recording roster")
    ranks = {}
    for ident, item in inputs.items():
        row = records[ident]
        if row["method"] != initial_branch_audit.STOCK or any(
            row[f"{kind}_sha256"] != item[kind]["sha256"] for kind in ("native", "catalog")
        ):
            raise ValueError(f"{ident} archive is bound to a different observation or catalogue")
        metrics = row["result"]["metrics"]
        rank = metrics["winning_rank"]
        if type(rank) is not int or not 0 <= rank < metrics["refined_hypotheses"]:
            raise ValueError(f"{ident} has an invalid initial branch rank")
        ranks[ident] = rank
    return ranks


def select_roster(ranks, timing_ids):
    disagree = sorted(ident for ident, rank in ranks.items() if rank != 0)
    agree = sorted(
        (ident for ident in ranks if not ranks[ident] and ident not in timing_ids),
        key=lambda ident: corpus._sha(f"v5-first-ranked-broad-v1:{ident}".encode()),
    )
    return disagree, agree[:CONTROL_COUNT]


def plan(inputs):
    ranks = _archive_ranks(inputs)
    disagree, controls = select_roster(ranks, TIMING_IDS)
    if len(disagree) != 31 or set(disagree) & set(TIMING_IDS) != {DISAGREEMENT_REUSE}:
        raise ValueError("original disagreement roster differs from the declared experiment")
    return dict(
        cases=sorted(inputs),
        winning_ranks=ranks,
        disagreements=disagree,
        agreement_controls=controls,
        timing_cases=list(TIMING_IDS),
        fresh_cases=sorted((set(disagree) | set(controls)) - set(TIMING_IDS)),
        deadline_s=CAP_S,
        source=search_budget.source_lock(),
        scientific_source=v5_lean.SOURCE_SHA256,
        preregistration_sha256=search_budget.digest(REPORT / "PROTOCOL.md"),
        original_ranks_receipt_sha256=search_budget.digest(CHECKPOINTS / "receipt.json"),
    )


def _case(item):
    bulk = Path(os.environ.get("PIPELINE_EVAL_BULK_ROOT", corpus.DEFAULT_BULK)).resolve()
    blind = Path(os.environ.get("PIPELINE_EVAL_BLIND_ROOT", corpus.DEFAULT_BLIND)).resolve()
    return corpus._public(item, bulk, blind, DEFAULT_OUT / "inputs")


def _validate_candidate(row, item, seal, case=None):
    if (
        row["id"] != item["id"]
        or row["method"] != METHOD
        or row["source_sha256"] != seal
        or any(row[f"{kind}_sha256"] != item[kind]["sha256"] for kind in ("native", "catalog"))
        or (case is not None and row["input_sha256"] != projector_roof.input_hash(case))
        or row["worker_wall_s"] <= 0
    ):
        raise ValueError(f"{item['id']} candidate replay provenance differs from the source lock")
    result = row["result"]
    validate_result(result)
    if result["status"] == "ok" and (
        row["implementation_sha256"] != seal["v5_search_budget.py"]
        or result["metrics"].get("kernel_sha256") != seal["orbit_projector.c"]
        or result["metrics"].get("initial_branches") != 1
        or result["metrics"].get("initial_policy") != METHOD
        or "arms" not in result
    ):
        raise ValueError(f"{item['id']} candidate is not the complete single-branch cavity fit")
    return row


def replay(work, cpus):
    if (
        not cpus
        or len(cpus) > 6
        or len(set(cpus)) != len(cpus)
        or not set(cpus) <= os.sched_getaffinity(0)
    ):
        raise ValueError("select at most six distinct CPUs permitted in this process")
    work = local_output(work)
    work.mkdir(parents=True, exist_ok=True)
    with (work / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        inputs = frozen_inputs()
        fixed = plan(inputs)
        locked = work / "plan.json"
        if locked.exists() and _read(locked) != fixed:
            raise ValueError("broad replay plan or implementation changed after lock")
        save_json(locked, fixed)
        journal = work / "runs"
        journal.mkdir(exist_ok=True)
        ready = SimpleQueue()
        for cpu in cpus:
            ready.put(cpu)

        def measure(ident):
            item = inputs[ident]
            case = _case(item)
            path = journal / f"{ident}.json"
            if path.exists():
                return _validate_candidate(_read(path), item, fixed["source"], case)
            cpu = ready.get()
            try:
                record = run_one(METHOD, case, work, CAP_S, cpu)
            finally:
                ready.put(cpu)
            if search_budget.source_lock() != fixed["source"]:
                raise ValueError("replay implementation changed during qualification")
            record.update(
                method=METHOD,
                source="broad_fresh",
                cpu=cpu,
                cap_s=CAP_S,
                source_sha256=fixed["source"],
                native_sha256=item["native"]["sha256"],
                catalog_sha256=item["catalog"]["sha256"],
            )
            _validate_candidate(record, item, fixed["source"], case)
            save_json(path, record)
            return record

        print(f"Fresh attempts {len(fixed['fresh_cases'])}; CPUs {cpus}; {CAP_S} s cap", flush=True)
        print(f"Agreement controls {fixed['agreement_controls']}", flush=True)
        with ThreadPoolExecutor(max_workers=len(cpus)) as workers:
            futures = [workers.submit(measure, ident) for ident in fixed["fresh_cases"]]
            for done, future in enumerate(as_completed(futures), 1):
                row = future.result()
                print(
                    done,
                    row["id"],
                    row["result"]["status"],
                    round(row["worker_wall_s"], 2),
                    flush=True,
                )


def _stock_archive():
    source = projector_roof.REPORT
    lock = _read(source / projector_roof.ARCHIVE_RECEIPT)
    hashes = (lock["implementation_sha256"], lock["kernel_sha256"])
    if (
        lock["schema_version"] != 1
        or hashes[1] != projector_roof.source_hashes()[1]
        or lock["files"]
        != projector_roof.archive_digests(source, source, projector_roof.CHECKPOINTS)
    ):
        raise ValueError("matched stock projector archive differs from its authenticated sources")
    return read_predictions(source / projector_roof.PREDICTIONS), hashes


def _check_timing_stock(ordinary, path, item, case, fixed):
    fresh = _read(path)
    sources = fixed["source"]
    hashes = (sources["orbit_projector.py"], sources["orbit_projector.c"])
    projector_roof.validate_prediction(fresh, hashes, case=case, allow_failure=True)
    if (
        fresh["method"] != STOCK
        or fresh["source_sha256"] != sources
        or any(fresh[f"{kind}_sha256"] != item[kind]["sha256"] for kind in ("native", "catalog"))
    ):
        raise ValueError(f"{item['id']} current timing stock differs from its source lock")
    old_result, new_result = ordinary["result"], fresh["result"]
    return dict(
        id=item["id"],
        historical_module_sha256=ordinary["implementation_sha256"],
        fresh_module_sha256=fresh.get("implementation_sha256"),
        fresh_run_sha256=search_budget.digest(path),
        same_input=ordinary["input_sha256"] == fresh["input_sha256"],
        old_status=old_result["status"],
        new_status=new_result["status"],
        same_arms=old_result.get("arms") == new_result.get("arms"),
        same_numerical_work=all(
            old_result["metrics"].get(k) == new_result["metrics"].get(k)
            for k in (
                "initial_branches",
                "initial_arm_fits",
                "cavity_offered",
                "observations",
                "tracks",
                "compact_projections",
            )
        ),
    )


def _candidate_record(ident, item, case, fixed, work, timing):
    ranking = dict(winning_rank=fixed["winning_ranks"][ident])
    if ident in fixed["fresh_cases"]:
        path = work / "runs" / f"{ident}.json"
        record = _validate_candidate(_read(path), item, fixed["source"], case)
        if record["source"] != "broad_fresh" or record["cap_s"] != CAP_S:
            raise ValueError(f"{ident} broad replay differs from the declared worker boundary")
        return dict(record, method=BROAD, original_run_sha256=search_budget.digest(path), **ranking)
    if ident in fixed["timing_cases"]:
        path = timing / ident / (METHOD + ".json")
        record = _validate_candidate(_read(path), item, fixed["source"], case)
        record["prior_study_wall_s"] = record.pop("worker_wall_s")
        return dict(
            record,
            method=BROAD,
            source="six_pair_replay",
            cap_s=CAP_S,
            original_run_sha256=search_budget.digest(path),
            **ranking,
        )
    if ranking["winning_rank"] != 0:
        raise ValueError(f"{ident} disagreement is missing its fresh replay")
    return dict(
        id=ident,
        method=BROAD,
        input_sha256=projector_roof.input_hash(case),
        native_sha256=item["native"]["sha256"],
        catalog_sha256=item["catalog"]["sha256"],
        source="unmeasured_agreement",
        **ranking,
        result=dict(
            status="missing",
            reason="compact initial node and gate equality unverified",
            boundary="Scheduled first-ranked cavity comparison",
            metrics={},
            arms={arm: {"latlon": None} for arm in ARMS},
        ),
    )


def seal(work, timing, output):
    inputs = frozen_inputs()
    fixed = plan(inputs)
    if _read(work / "plan.json") != fixed:
        raise ValueError("saved plan differs from the replay sources or roster")
    stock, hashes = _stock_archive()
    if stock.keys() != inputs.keys():
        raise ValueError("matched projector archive omits a scheduled recording")
    candidate_records = []
    stock_records = []
    timing_stock_checks = []
    for ident in fixed["cases"]:
        item = inputs[ident]
        case = _case(item)
        candidate = _candidate_record(ident, item, case, fixed, work, timing)
        ordinary = dict(projector_roof.validate_prediction(stock[ident], hashes, case=case))
        ordinary["archive_source"] = ordinary.pop("source")
        ordinary["archived_worker_wall_s"] = ordinary.pop("worker_wall_s")
        ordinary.update(
            method=STOCK,
            source="archived_projector",
            native_sha256=item["native"]["sha256"],
            catalog_sha256=item["catalog"]["sha256"],
            winning_rank=candidate["winning_rank"],
        )
        validate_result(candidate["result"])
        candidate_records.append(candidate)
        stock_records.append(ordinary)
        if ident in fixed["timing_cases"]:
            timing_stock_checks.append(
                _check_timing_stock(ordinary, timing / ident / (STOCK + ".json"), item, case, fixed)
            )

    files = {}
    for method, rows in ((BROAD, candidate_records), (STOCK, stock_records)):
        file = output / f"{method}.jsonl.gz"
        write(file, gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0))
        files[file.name] = search_budget.digest(file)
    save_json(output / "plan.json", fixed)
    files["plan.json"] = search_budget.digest(output / "plan.json")
    save_json(output / "timing-stock-check.json", timing_stock_checks)
    files["timing-stock-check.json"] = search_budget.digest(output / "timing-stock-check.json")
    source = projector_roof.REPORT / projector_roof.ARCHIVE_RECEIPT
    save_json(
        output / "receipt.json",
        dict(
            cases=fixed["cases"],
            files=files,
            deadline_s=CAP_S,
            source=fixed["source"],
            scientific_source=fixed["scientific_source"],
            stock_archive_receipt_sha256=search_budget.digest(source),
            candidate_sources=dict(Counter(row["source"] for row in candidate_records)),
        ),
    )


def _published(result, arm):
    prediction = result.get("arms", {}).get(arm, {})
    return prediction.get("latlon"), prediction.get("rf_rms_hz")


def _paired_rows(refs, candidate, stock, checkpoints):
    rows = []
    for ref in refs:
        ident = ref["id"]
        trial, control = candidate[ident], stock[ident]
        details = checkpoints[ident][2]["stages"]["final"]
        for arm in ARMS:
            point, rms = _published(trial["result"], arm)
            stock_point, stock_rms = _published(control["result"], arm)
            ref_point = ref["reference"]["baseline"][arm]["latlon"]
            rows.append(
                dict(
                    recording=ident,
                    dataset=ref["group"],
                    arm=arm,
                    source=trial["source"],
                    original_winning_rank=trial["winning_rank"],
                    candidate_status=trial["result"]["status"],
                    candidate_reason=trial["result"].get("reason"),
                    fresh_worker_wall_s=trial.get("worker_wall_s"),
                    timing_study_worker_wall_s=trial.get("prior_study_wall_s"),
                    archived_stock_worker_wall_s=control["archived_worker_wall_s"],
                    cpu=trial.get("cpu"),
                    deadline_s=trial.get("cap_s"),
                    v5_first_ranked_broad_error_km=distance_km(point, ref["truth"]),
                    orbit_projector_error_km=distance_km(stock_point, ref["truth"]),
                    baseline_error_km=distance_km(ref_point, ref["truth"]),
                    candidate_to_stock_km=distance_km(point, stock_point),
                    candidate_to_baseline_km=distance_km(point, ref_point),
                    v5_first_ranked_broad_conditional_rms_hz=rms,
                    orbit_projector_conditional_rms_hz=stock_rms,
                    baseline_conditional_rms_hz=details[arm]["conditional_rms_hz"],
                )
            )
    return rows


def _in_cohort(row, cohort):
    match cohort:
        case "scheduled":
            return True
        case "replayed":
            return row["source"] != "unmeasured_agreement"
        case "original_nonzero_rank":
            return row["original_winning_rank"] != 0
        case "sha_agreement":
            return not row["original_winning_rank"] and row["source"] == "broad_fresh"
        case "timing_agreement":
            return not row["original_winning_rank"] and row["source"] == "six_pair_replay"
    raise ValueError(f"unknown cohort {cohort}")


def _pair_summary(pairs):
    differences = [candidate - control for candidate, control in pairs]
    return dict(
        pairs=len(pairs),
        at_most_5pct_worse=sum(candidate <= 1.05 * control for candidate, control in pairs),
        at_most_10pct_worse=sum(candidate <= 1.10 * control for candidate, control in pairs),
        improved_over_1m=sum(difference < -0.001 for difference in differences),
        within_1m=sum(abs(difference) <= 0.001 for difference in differences),
        worsened_over_1m=sum(difference > 0.001 for difference in differences),
        worsened_over_100m=sum(difference > 0.1 for difference in differences),
        error_difference_km=distribution(differences),
    )


def _summary(rows):
    summaries = []
    for cohort in COHORTS:
        for dataset in ("DS26", "DS29", "all"):
            for arm in ARMS:
                group = [
                    row
                    for row in rows
                    if row["arm"] == arm
                    and dataset in ("all", row["dataset"])
                    and _in_cohort(row, cohort)
                ]
                if not group:
                    continue
                published = [r for r in group if r[f"{BROAD}_error_km"] is not None]
                results = {}
                for method in METHODS:
                    err = f"{method}_error_km"
                    rms = f"{method}_conditional_rms_hz"
                    errors = [r[err] for r in group]
                    results[method] = dict(
                        error_km=distribution(errors),
                        within_km=thresholds(errors),
                        conditional_rms_hz=distribution(r[rms] for r in group),
                        on_candidate_published_error_km=distribution(r[err] for r in published),
                        on_candidate_published_conditional_rms_hz=distribution(
                            r[rms] for r in published
                        ),
                        paired_errors=_pair_summary(
                            [
                                (r[f"{BROAD}_error_km"], r[err])
                                for r in published
                                if r[err] is not None
                            ]
                        )
                        if method != BROAD
                        else None,
                    )
                summaries.append(
                    dict(
                        cohort=cohort,
                        dataset=dataset,
                        arm=arm,
                        scheduled=len(group),
                        sources=dict(Counter(r["source"] for r in group)),
                        candidate_statuses=dict(Counter(r["candidate_status"] for r in group)),
                        candidate_published=len(published),
                        methods=results,
                        candidate_to_stock_km=distribution(
                            r["candidate_to_stock_km"] for r in group
                        ),
                        candidate_to_baseline_km=distribution(
                            r["candidate_to_baseline_km"] for r in group
                        ),
                        candidate_coordinate_changes_over_1m={
                            name: sum(r[key] is not None and r[key] > 0.001 for r in group)
                            for name, key in (
                                (STOCK, "candidate_to_stock_km"),
                                ("baseline", "candidate_to_baseline_km"),
                            )
                        },
                        fresh_worker_wall_s=distribution(r["fresh_worker_wall_s"] for r in group),
                        timing_study_worker_wall_s=distribution(
                            r["timing_study_worker_wall_s"] for r in group
                        ),
                        archived_stock_worker_wall_s=distribution(
                            r["archived_stock_worker_wall_s"] for r in group
                        ),
                    )
                )
    return summaries


def score(output):
    receipt = _read(output / "receipt.json")
    files = {f"{BROAD}.jsonl.gz", f"{STOCK}.jsonl.gz", "plan.json", "timing-stock-check.json"}
    if receipt["files"].keys() != files or any(
        search_budget.digest(output / name) != digest for name, digest in receipt["files"].items()
    ):
        raise ValueError("broad qualification predictions differ from their seal")
    candidate = read_predictions(output / f"{BROAD}.jsonl.gz")
    stock = read_predictions(output / f"{STOCK}.jsonl.gz")
    if candidate.keys() != stock.keys() or candidate.keys() != set(receipt["cases"]):
        raise ValueError("predictions differ from the sealed roster")
    if any(candidate[ident]["input_sha256"] != stock[ident]["input_sha256"] for ident in candidate):
        raise ValueError("stock and first-ranked requests differ")
    rows = _paired_rows(
        projector_roof.roster(), candidate, stock, load_rows(projector_roof.CHECKPOINTS)
    )
    csv_file(output / "per-recording.csv", rows)
    save_json(output / "summary.json", dict(groups=_summary(rows)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=SCRATCH)
    parser.add_argument("--cpus", type=int, nargs="+")
    parser.add_argument("--timing", type=Path, default=TIMING_RUNS)
    parser.add_argument("--output", type=Path, default=REPORT)
    parser.add_argument("--seal", action="store_true")
    parser.add_argument("--score", action="store_true")
    args = parser.parse_args()
    if args.seal:
        seal(args.work, args.timing, args.output)
    if args.score:
        score(args.output)
    if not args.seal and not args.score:
        replay(args.work, args.cpus)


if __name__ == "__main__":
    main()
