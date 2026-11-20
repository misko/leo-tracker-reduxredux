"""Run the frozen secant optimizer over the complete roof panel under a wall cap."""

import argparse
import fcntl
import gzip
import os
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from time import perf_counter

from ..__main__ import encoded, local_output, read_predictions, run_one, save_json, write
from ..scoring import validate_result
from . import phase_confirmation as phase
from . import secant_confirmation as secant

REPORT = phase.corpus.REPO / "reports/2026_11_19_receiver_screening/secant-full"
SCRATCH = Path("/srv/bulk/leo-dev/receiver-screening-20261119/secant-full")
METHOD = secant.METHOD
STOCK = phase.STOCK
CPUS = tuple(range(12, 20))
CAP_S = 480
WALL_CAP_S = 38 * 60
JOURNAL_RESERVE_S = 5


def _verify_files(root, files):
    if any(phase.digest(root / name) != checksum for name, checksum in files.items()):
        raise ValueError(f"{root} differs from its prediction seal")


def _prior(inputs, sources):
    timing = secant.TIMING
    timing_lock_path = timing / "prediction-lock.json"
    timing_lock = phase._read(timing_lock_path)
    timing_sha = phase.digest(timing / "seal.json")
    if timing_sha != timing_lock["source_seal_sha256"]:
        raise ValueError("the timing prediction lock uses a different solver source")
    _verify_files(timing, timing_lock["files"])
    timed = read_predictions(timing / "secant-positions.jsonl.gz")
    if timed.keys() != set(phase.TIMING_IDS) or timed.keys() != set(timing_lock["cases"]):
        raise ValueError("prior timing predictions differ from the six fixed paired cases")

    confirmed_lock_path = secant.REPORT / "receipt.json"
    confirmed_lock = phase._read(confirmed_lock_path)
    _verify_files(secant.REPORT, confirmed_lock["files"])
    confirmed = read_predictions(secant.REPORT / f"{METHOD}.jsonl.gz")
    if (
        confirmed.keys() != set(confirmed_lock["cases"])
        or confirmed.keys() != set(secant.roster(inputs)["cases"])
        or not confirmed.keys().isdisjoint(timed)
        or confirmed_lock["sources"] != sources
    ):
        raise ValueError("prior confirmation predictions differ from their sealed inputs or source")

    adopted = {}
    for rows, measurement in ((timed, "prior_timing"), (confirmed, "prior_confirmation")):
        for ident, row in rows.items():
            item = inputs[ident]
            case = phase._case(item)
            binding = _binding(item, case)
            if any(row[k] != binding[k] for k in ("native_sha256", "catalog_sha256")):
                raise ValueError(f"{ident} prior result uses a different recording or catalogue")
            if measurement == "prior_timing":
                if (
                    row["variant"] != METHOD
                    or row["source_seal_sha256"] != timing_sha
                    or row["input_sha256"] != binding["frozen_request_sha256"]
                ):
                    raise ValueError(f"{ident} prior paired timing request differs")
            else:
                secant._validate(
                    row,
                    ident,
                    case,
                    {k: binding[k] for k in ("native_sha256", "catalog_sha256")},
                    sources,
                )
            validate_result(row["result"])
            normalized = dict(row)
            normalized.update(binding, method=METHOD, source=measurement, source_sha256=sources)
            normalized["prior_input_sha256"] = row["input_sha256"]
            normalized[f"{measurement}_worker_wall_s"] = normalized.pop("worker_wall_s")
            adopted[ident] = normalized
    return adopted, {
        "prior_timing": phase.digest(timing_lock_path),
        "prior_confirmation": phase.digest(confirmed_lock_path),
    }


def _binding(item, case):
    return dict(
        id=item["id"],
        input_sha256=phase.projector_roof.input_hash(case),
        native_sha256=item["native"]["sha256"],
        catalog_sha256=item["catalog"]["sha256"],
        frozen_request_sha256=item["request"]["sha256"],
        tile=item["regions"][0],
    )


def schedule(archive, prior):
    return sorted(
        archive.keys() - prior.keys(), key=lambda ident: (-archive[ident]["worker_wall_s"], ident)
    )


def plan(inputs):
    sources = secant.frozen_sources()
    prior, seals = _prior(inputs, sources)
    archive, _ = phase._stock_archive()
    order = schedule(archive, prior)
    if len(inputs) != 135 or archive.keys() != inputs.keys() or len(order) != 121:
        raise ValueError("expected 135 exact inputs with 121 fresh and 14 authenticated outcomes")
    fields = dict(
        cases=sorted(inputs),
        fresh_cases=order,
        prior_cases={k: row["source"] for k, row in prior.items()},
        prior_seals=seals,
        priority_wall_s={k: archive[k]["worker_wall_s"] for k in order},
        protocol_sha256=phase.digest(REPORT / "PROTOCOL.md"),
        scientific_source=phase.v5_lean.SOURCE_SHA256,
        source_sha256=sources,
        cli_implementation_sha256=secant._cli_digest(),
        stock_receipt_sha256=phase.digest(
            phase.projector_roof.REPORT / phase.projector_roof.ARCHIVE_RECEIPT
        ),
        cpus=list(CPUS),
        max_worker_wall_s=CAP_S,
        max_replay_wall_s=WALL_CAP_S,
    )
    return fields, prior


def _seconds_left(deadline, now):
    return min(CAP_S, int(deadline - now - JOURNAL_RESERVE_S))


def _validate_fresh(row, binding, plan):
    if (
        any(row[k] != value for k, value in binding.items())
        or row["method"] != METHOD
        or row["source"] != "fresh_full_panel"
        or row["source_sha256"] != plan["source_sha256"]
        or row["cpu"] not in CPUS
        or not 0 < row["deadline_s"] <= CAP_S
        or row["worker_wall_s"] <= 0
    ):
        raise ValueError(f"{row['id']} candidate differs from its frozen request or source")
    result = row["result"]
    validate_result(result)
    if result["status"] == "ok" and (
        row["implementation_sha256"] != plan["cli_implementation_sha256"]
        or result["metrics"].get("kernel_sha256") != plan["source_sha256"]["orbit_projector.c"]
        or not result["metrics"].get("initial_phase_refresh_counts")
        or any(n != 5 for n in result["metrics"]["initial_phase_refresh_counts"])
        or set(result.get("arms", {})) != set(phase.ARMS)
    ):
        raise ValueError(f"{row['id']} did not complete the sealed five-refresh cavity worker")


def replay(work, output=REPORT):
    start = perf_counter()
    deadline = start + WALL_CAP_S
    if not set(CPUS) <= os.sched_getaffinity(0):
        raise ValueError("the full replay requires CPUs 12–19")
    work = local_output(work)
    work.mkdir(parents=True, exist_ok=True)
    with (work / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        inputs = phase.frozen_inputs()
        fixed, _ = plan(inputs)
        if (work / "plan.json").exists():
            raise FileExistsError(
                "the full replay is a single bounded attempt; choose a new work directory"
            )
        save_json(work / "plan.json", fixed)
        save_json(output / "roster.json", fixed)
        journal = work / "runs"
        journal.mkdir()
        remaining, guard = deque(fixed["fresh_cases"]), Lock()

        def loop(cpu):
            while _seconds_left(deadline, perf_counter()) > 0:
                with guard:
                    if not remaining:
                        return
                    ident = remaining.popleft()
                item = inputs[ident]
                case = phase._case(item)
                binding = _binding(item, case)
                cap = _seconds_left(deadline, perf_counter())
                if cap <= 0:
                    return
                row = run_one(METHOD, case, work, cap, cpu)
                if row["input_sha256"] != binding["input_sha256"]:
                    raise ValueError(f"{ident} standard worker ran a different case")
                row.update(
                    binding,
                    method=METHOD,
                    source="fresh_full_panel",
                    deadline_s=cap,
                    cpu=cpu,
                    source_sha256=fixed["source_sha256"],
                )
                _validate_fresh(row, binding, fixed)
                save_json(journal / f"{ident}.json", row)
                print(
                    ident, cpu, row["result"]["status"], round(row["worker_wall_s"], 2), flush=True
                )

        print(f"Running 121 jobs on {CPUS}; absolute cap {WALL_CAP_S}s", flush=True)
        with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
            list(pool.map(loop, CPUS))
        if secant.frozen_sources() != fixed["source_sha256"]:
            raise ValueError("numeric sources changed during the full run")
        rows = [phase._read(path) for path in journal.glob("*.json")]
        save_json(
            work / "run-receipt.json",
            dict(
                cpus=list(CPUS),
                wall_s=perf_counter() - start,
                fresh_statuses=dict(Counter(r["result"]["status"] for r in rows)),
                attempted=len(rows),
                requested=len(fixed["fresh_cases"]),
            ),
        )


def _missing(binding, orphaned):
    return dict(
        binding,
        method=METHOD,
        source="interrupted_supervisor" if orphaned else "unattempted_wall_limit",
        result=dict(
            status="failed" if orphaned else "missing",
            reason="supervisor exited without a worker receipt"
            if orphaned
            else "no attempt before the replay wall limit",
            boundary="Complete native GLRT inputs to compact v5 cavity positions",
            metrics={},
            arms={arm: dict(latlon=None) for arm in phase.ARMS},
        ),
    )


def seal(work, output):
    with (work / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _seal_locked(work, output)


def _seal_locked(work, output):
    inputs = phase.frozen_inputs()
    fixed, prior = plan(inputs)
    if fixed != phase._read(work / "plan.json"):
        raise ValueError("the full replay schedule or science source changed after launch")
    originals, hashes = phase._stock_archive()
    completed = {path.stem: path for path in (work / "runs").glob("*.json")}
    if not completed.keys() <= set(fixed["fresh_cases"]):
        raise ValueError("an unexpected recording entered the full replay journal")
    orphaned = {phase._read(path)["id"] for path in work.glob(f"{METHOD}-*/input.json")}
    run_path = work / "run-receipt.json"
    run = (
        phase._read(run_path)
        if run_path.is_file()
        else {
            "cpus": list(CPUS),
            "wall_s": None,
            "attempted": len(completed) + len(orphaned),
            "requested": len(fixed["fresh_cases"]),
            "terminal_reason": "no supervisor receipt",
        }
    )
    if run["wall_s"] is not None and (
        run["attempted"] != len(completed) or run["wall_s"] > WALL_CAP_S
    ):
        raise ValueError("replay completion receipt differs from its recorded cap or journal")
    launcher = work / "launcher.json"
    if launcher.is_file():
        run["launcher"] = phase._read(launcher)
    log = work / "replay.log"
    if log.is_file():
        run["supervisor_log_sha256"] = phase.digest(log)

    candidate, stock = [], []
    for ident in fixed["cases"]:
        item = inputs[ident]
        case = phase._case(item)
        binding = _binding(item, case)
        if ident in prior:
            row = prior[ident]
        elif path := completed.get(ident):
            row = phase._read(path)
            _validate_fresh(row, binding, fixed)
            row["original_run_sha256"] = phase.digest(path)
        else:
            row = _missing(binding, ident in orphaned)
        saved = dict(phase.projector_roof.validate_prediction(originals[ident], hashes, case=case))
        if row["result"]["status"] == "ok" and any(
            row["result"]["metrics"][k] != saved["result"]["metrics"][k]
            for k in ("initial_branches", "observations", "tracks")
        ):
            raise ValueError(f"{ident} observations, tracks or initial branches differ from stock")
        request_digest = phase.digest(Path(case["request_path"]))
        row["resolved_request_sha256"] = request_digest
        candidate.append(row)
        saved["archived_worker_wall_s"] = saved.pop("worker_wall_s")
        saved["archive_source"] = saved.pop("source")
        saved.update(
            binding,
            method=STOCK,
            source="archived_projector",
            resolved_request_sha256=request_digest,
        )
        stock.append(saved)

    save_json(output / "plan.json", fixed)
    for name, rows in ((METHOD, candidate), (STOCK, stock)):
        payload = b"".join(encoded(row) + b"\n" for row in rows)
        write(output / f"{name}.jsonl.gz", gzip.compress(payload, mtime=0))
    primary = ("plan.json", f"{METHOD}.jsonl.gz", f"{STOCK}.jsonl.gz")
    predicted = {name: phase.digest(output / name) for name in primary}
    save_json(output / "prediction-lock.json", dict(cases=fixed["cases"], files=predicted))

    original = {ident: phase._original_v5_bindings(inputs[ident]) for ident in fixed["cases"]}
    save_json(output / "original-v5-inputs.json", original)
    files = (*primary, "prediction-lock.json", "original-v5-inputs.json")
    save_json(
        output / "receipt.json",
        dict(
            cases=fixed["cases"],
            files={name: phase.digest(output / name) for name in files},
            sources=fixed["source_sha256"],
            scientific_source=fixed["scientific_source"],
            stock_receipt_sha256=fixed["stock_receipt_sha256"],
            prior_seals=fixed["prior_seals"],
            max_replay_wall_s=WALL_CAP_S,
            deadline_s=CAP_S,
            run=run,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "seal", "score"), nargs="?", default="run")
    parser.add_argument("--work", type=Path, default=SCRATCH)
    parser.add_argument("--output", type=Path, default=REPORT)
    args = parser.parse_args()
    if args.command == "run":
        replay(args.work, args.output)
    elif args.command == "seal":
        seal(args.work, args.output)
    else:
        phase.score(args.output, candidate_method=METHOD)


if __name__ == "__main__":
    main()
