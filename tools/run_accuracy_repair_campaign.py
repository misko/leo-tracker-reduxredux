"""Run a frozen repair campaign in fixed CPU lanes and report repeated measurements.

No RF collection. Each lane executes one worker at a time; every recording and
its repetitions retain one CPU. Invocation waves are bounded and resume saved
outcomes automatically. Failed/missing/timed-out outcomes remain in coverage.
"""

import argparse
import fcntl
import json
import math
import os
import shutil
import statistics
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import evaluate_accuracy_repair as repair


def distribution(values):
    values = sorted(value for value in values if value is not None and math.isfinite(value))

    def percentile(q):
        if not values:
            return None
        rank = (len(values) - 1) * q
        low, high = math.floor(rank), math.ceil(rank)
        return values[low] + (values[high] - values[low]) * (rank - low)

    return dict(count=len(values), mean=statistics.mean(values) if values else None,
                median=percentile(.5), p90=percentile(.9), p95=percentile(.95),
                p99=percentile(.99), max=values[-1] if values else None)


def plan(manifest_path, cpus):
    manifest = repair.ev.read(manifest_path)
    repair.check_bindings(manifest)
    cpu_list = [int(cpu) for cpu in cpus.split(",")]
    if len(cpu_list) != len(set(cpu_list)) or not 1 <= len(cpu_list) <= 4:
        raise ValueError("One to four distinct fixed CPU lanes required")
    if not set(cpu_list) <= os.sched_getaffinity(0):
        raise ValueError("Requested CPUs unavailable")
    groups = list(dict.fromkeys((row["dataset"], row["group"]) for row in manifest["schedule"]))
    lanes = {group: index % len(cpu_list) for index, group in enumerate(groups)}
    return dict(schema_version=1, model="accuracy-repair-fixed-lanes-v1",
                manifest_path=str(Path(manifest_path).resolve()),
                manifest_sha256=repair.ev.digest(manifest), cpus=cpu_list,
                assignments=[dict(dataset=row["dataset"], case=row["case"],
                                  repetition=row["repetition"],
                                  lane=lanes[row["dataset"], row["group"]])
                             for row in manifest["schedule"]],
                runner=str(Path(__file__).resolve()),
                runner_sha256=repair.ev.file_digest(__file__),
                execution_mode="four-or-fewer fixed CPU lanes; shared-host contention; "
                               "sequential configurations and repeats within each recording lane; "
                               "wall times are descriptive, not isolated latency qualification",
                environment={key: repair.ENVIRONMENT[key] for key in
                             ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")},
                created_host=repair.host())


def check_plan(campaign):
    if campaign["runner_sha256"] != repair.ev.file_digest(campaign["runner"]):
        raise ValueError("Frozen campaign runner changed")
    manifest = repair.ev.read(campaign["manifest_path"])
    if campaign["manifest_sha256"] != repair.ev.digest(manifest):
        raise ValueError("Frozen scientific manifest changed")
    repair.check_bindings(manifest)
    expected = plan(campaign["manifest_path"], ",".join(map(str, campaign["cpus"])))
    for key in ("assignments", "environment", "execution_mode"):
        if campaign[key] != expected[key]:
            raise ValueError("Frozen campaign " + key + " changed")
    return manifest


def record_path(manifest, assignment, role):
    return (Path(manifest["output"]) /
            (assignment["case"] + "-r" + str(assignment["repetition"])) /
            (role + "-execution.json"))


def outcomes(manifest):
    rows = []
    for assignment in manifest["schedule"]:
        for role in manifest["roles"]:
            path = record_path(manifest, assignment, role)
            record = repair.ev.read(path) if path.exists() else dict(status="absent")
            rows.append(dict(case=assignment["case"], repetition=assignment["repetition"],
                             role=role, dataset=assignment["dataset"],
                             group=assignment["group"], split=assignment["split"], record=record))
    return rows


def repeat_measurements(values):
    if len(values) != 2:
        raise ValueError("Repeat variation requires exactly two measurements")
    first, second = values
    mean = statistics.mean(values)
    return dict(first=first, second=second, delta=second-first,
                ratio=second/first if first else None,
                population_cv=statistics.pstdev(values)/abs(mean) if mean else None)


def repeated_report(manifest, campaign):
    rows = outcomes(manifest)
    expected_repeats = set(range(manifest["repeats"]))
    cases = sorted({row["case"] for row in rows})
    indexed = {(row["case"], row["role"], row["repetition"]): row for row in rows}
    common = [case for case in cases if all(
        indexed[case, role, repetition]["record"]["status"] == "complete"
        for role in manifest["roles"] for repetition in expected_repeats)]
    measured = {}
    for row in rows:
        if row["record"]["status"] == "complete":
            reference = manifest["cohorts"][row["dataset"]]["references"][row["case"]]
            measured[row["case"], row["role"], row["repetition"]] = repair.measured_arms(
                row["record"]["worker"], reference)
    summaries = {}
    for role in manifest["roles"]:
        for cohort, cohort_cases in (("all_successful", cases), ("same_successful_cohort", common)):
            for repetition in expected_repeats:
                usable = [row for row in rows if row["role"] == role and
                          row["repetition"] == repetition and row["case"] in cohort_cases and
                          row["record"]["status"] == "complete"]
                summaries[f"{cohort}/{role}/r{repetition}"] = dict(
                    count=len(usable), timing={metric: distribution(
                        row["record"]["process"][metric] for row in usable
                        if row["record"]["process"]["cpu_complete"])
                        for metric in ("wall_seconds", "cpu_seconds")},
                    arms={arm: {metric: distribution(
                        measured[row["case"], role, repetition][arm][metric] for row in usable)
                        for metric in repair.ev.METRICS} for arm in repair.ev.ARMS})
    repeat_rows = []
    if manifest["repeats"] == 2:
        for case in cases:
            for role in manifest["roles"]:
                pair = [indexed[case, role, repetition]["record"] for repetition in (0, 1)]
                row = dict(case=case, role=role, statuses=[record["status"] for record in pair],
                           same_successful_cohort=case in common)
                if all(record["status"] == "complete" and record["process"]["cpu_complete"]
                       for record in pair):
                    row["timing"] = {metric: repeat_measurements(
                        [record["process"][metric] for record in pair])
                        for metric in ("wall_seconds", "cpu_seconds")}
                    row["arms"] = {arm: {metric: repeat_measurements(
                        [measured[case, role, repetition][arm][metric] for repetition in (0, 1)])
                        for metric in repair.ev.METRICS
                        if all(measured[case, role, repetition][arm][metric] is not None
                               for repetition in (0, 1))} for arm in repair.ev.ARMS}
                repeat_rows.append(row)
    variation = {role: {cohort: {metric: {stat: distribution(
        row["timing"][metric][stat] for row in repeat_rows if row["role"] == role and
        "timing" in row and (cohort == "all_successful" or row["same_successful_cohort"]))
        for stat in ("delta", "ratio", "population_cv")}
        for metric in ("wall_seconds", "cpu_seconds")}
        for cohort in ("all_successful", "same_successful_cohort")}
        for role in manifest["roles"]}
    finished = sum(row["record"]["status"] not in ("absent", "started") for row in rows)
    return dict(schema_version=1, expected_workers=len(rows), finished_workers=finished,
                coverage_complete=finished == len(rows), expected_cases=len(cases),
                same_successful_cases=common, same_successful_case_count=len(common),
                statuses={role: dict(Counter(row["record"]["status"] for row in rows
                                            if row["role"] == role))
                          for role in manifest["roles"]},
                coverage=[{key: value for key, value in row.items() if key != "record"} |
                          dict(status=row["record"]["status"]) for row in rows],
                summaries=summaries, repeat_measurements=repeat_rows,
                repeat_variation=variation, campaign=campaign,
                note="Position errors and selected-fit frequency metrics are separate. "
                     "Both c=0 and fitted-c use matched frozen input, candidate policies and "
                     "search budgets; frequency fit alone does not establish location accuracy. "
                     "CV uses population standard deviation over the two repeats. "
                     "Shared-host contention remains uncontrolled.")


def save_reports(manifest, campaign):
    comparison = repair.save_report(manifest)  # validates every finished scientific archive
    result = repeated_report(manifest, campaign)
    output = Path(manifest["output"])
    repair.write(output / "repeat-comparison.json", result)
    lines = ["# DS26 four configurations, two repetitions", "",
             f"Coverage: {result['finished_workers']}/{result['expected_workers']} outcomes; "
             f"{result['expected_cases']} frozen cases; "
             f"{result['same_successful_case_count']} cases complete in every role and repetition.",
             "", campaign["execution_mode"] + ".", "", result["note"], "",
             "| Configuration | Statuses |", "| --- | --- |"]
    for role, counts in result["statuses"].items():
        lines.append(f"| {role} | {json.dumps(counts, sort_keys=True)} |")
    lines += ["", "Same successful cohort, separately for each repeat:", "",
              ("| Role / repeat | Cases | Arm | Mean error m | Median m | p90 m | p95 m | "
               "p99 m | Max m | Mean wall s | Median wall s | p95 wall s | Mean CPU s |"),
              ("| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
               "---: | ---: |")]

    def fmt(value, scale=1):
        return "n/a" if value is None else f"{value * scale:.3f}"

    for role in manifest["roles"]:
        for repetition in range(manifest["repeats"]):
            row = result["summaries"][f"same_successful_cohort/{role}/r{repetition}"]
            for arm in repair.ev.ARMS:
                gps = row["arms"][arm]["gps_error_km"]
                error = " | ".join(fmt(gps[key], 1000) for key in
                                   ("mean", "median", "p90", "p95", "p99", "max"))
                wall, cpu = row["timing"]["wall_seconds"], row["timing"]["cpu_seconds"]
                lines.append(f"| {role} / r{repetition} | {row['count']} | {arm} | {error} | "
                             f"{fmt(wall['mean'])} | {fmt(wall['median'])} | {fmt(wall['p95'])} | "
                             f"{fmt(cpu['mean'])} |")
    lines += ["", "Repeat 1 / repeat 0, same successful cohort:", "",
              "| Configuration | Timing | Median ratio | p95 ratio | Median delta s | Median CV |",
              "| --- | --- | ---: | ---: | ---: | ---: |"]
    for role in manifest["roles"]:
        for metric, row in result["repeat_variation"][role]["same_successful_cohort"].items():
            lines.append(f"| {role} | {metric} | {fmt(row['ratio']['median'])} | "
                         f"{fmt(row['ratio']['p95'])} | {fmt(row['delta']['median'])} | "
                         f"{fmt(row['population_cv']['median'])} |")
    lines += ["", "Full mean/median/p90/p95/p99/max distributions for errors, frequency scores, "
              "residuals, wall and CPU seconds, all successful cases, common cases, and every "
              "per-case repeat delta/ratio/CV are in repeat-comparison.json. Paired baseline "
              "changes and matched-observation frequency residuals are in comparison.json.", ""]
    (output / "repeat-report.md").write_text("\n".join(lines))
    return comparison, result


def execute_one(manifest, assignment, role, cpu):
    path = record_path(manifest, assignment, role)
    if path.exists():
        record = repair.ev.read(path)
        if record["status"] == "started":
            raise RuntimeError("Interrupted worker requires investigation: " + str(path))
        repair.validate_record(manifest, assignment, role, record)
        return False
    repair.check_bindings(manifest)
    request = repair.worker_request(manifest, assignment, role)
    record = dict(status="missing" if request is None else "started", role=role,
                  request_sha256=repair.ev.digest(request), before=repair.host(), cpu=cpu)
    repair.write(path, record)
    if request is not None:
        destination = Path(request["job"]["output_root"])
        destination.mkdir(exist_ok=False)
        request_path = destination / "experimental-request.json"
        repair.write(request_path, request)
        command = ["taskset", "-c", str(cpu), manifest["python"], "-B", manifest["worker"],
                   "worker", "--request", str(request_path)]
        environment = dict(repair.ENVIRONMENT,
                           PYTHONPATH=manifest["source"]["root"] + ":" +
                           str(Path(manifest["worker"]).parent))
        record.update(command=command, timeout_seconds=manifest["timeout_seconds"])
        record["process"] = repair.supervise_worker(
            command, destination / "worker.log", manifest["timeout_seconds"], environment)
        worker_path = destination / "worker-result.json"
        if record["process"]["status"] == "timed_out":
            record["status"] = "timed_out"
        elif record["process"]["returncode"] or not worker_path.exists():
            record["status"] = "failed"
        else:
            record.update(status="complete", worker=repair.ev.read(worker_path))
    record["after"] = repair.host()
    repair.write(path, record)
    repair.validate_record(manifest, assignment, role, record)
    print(json.dumps(dict(case=assignment["case"], repetition=assignment["repetition"],
                          role=role, cpu=cpu, status=record["status"],
                          wall_seconds=record.get("process", {}).get("wall_seconds"))), flush=True)
    return True


def run(campaign_path, *, wave_seconds=1800, reserve_gib=20):
    campaign = repair.ev.read(campaign_path)
    manifest = check_plan(campaign)
    if not manifest["timeout_seconds"] <= wave_seconds <= 1800:
        raise ValueError("Wave budget must cover the full worker timeout and be <=1800 seconds")
    output = repair.bulk_output(manifest["output"])
    output.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    assignments = {(row["case"], row["repetition"]): row for row in manifest["schedule"]}

    def lane_wave(lane):
        began = time.monotonic()
        admitted = 0
        for row in campaign["assignments"]:
            if row["lane"] != lane:
                continue
            assignment = assignments[row["case"], row["repetition"]]
            for role in assignment["order"]:
                path = record_path(manifest, assignment, role)
                if path.exists():
                    saved = repair.ev.read(path)
                    if saved["status"] == "started":
                        raise RuntimeError(
                            "Interrupted worker requires investigation: " + str(path))
                    repair.validate_record(manifest, assignment, role, saved)
                    continue
                if (stop.is_set() or
                        time.monotonic() - began > wave_seconds - manifest["timeout_seconds"]):
                    return admitted
                if shutil.disk_usage(output).free / 1024**3 < reserve_gib:
                    raise RuntimeError("Bulk free-space reserve reached")
                admitted += execute_one(manifest, assignment, role, campaign["cpus"][lane])
        return admitted

    with (output / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        wave = 0
        while True:
            check_plan(campaign)
            wave += 1
            try:
                with ThreadPoolExecutor(max_workers=len(campaign["cpus"])) as executor:
                    futures = [executor.submit(lane_wave, lane)
                               for lane in range(len(campaign["cpus"]))]
                    admitted = sum(future.result() for future in futures)
            except BaseException:
                stop.set()
                raise
            _, report = save_reports(manifest, campaign)
            repair.write(output / "campaign-progress.json", dict(
                wave=wave, admitted_workers=admitted, finished_workers=report["finished_workers"],
                expected_workers=report["expected_workers"],
                coverage_complete=report["coverage_complete"],
                after=repair.host()))
            if report["coverage_complete"]:
                return 0
            if not admitted:
                raise RuntimeError("No campaign progress; inspect saved outcomes and budgets")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prepare = sub.add_parser("plan")
    prepare.add_argument("--manifest", type=Path, required=True)
    prepare.add_argument("--cpus", required=True)
    prepare.add_argument("--campaign", type=Path, required=True)
    execute = sub.add_parser("run")
    execute.add_argument("--campaign", type=Path, required=True)
    execute.add_argument("--wave-seconds", type=float, default=1800)
    execute.add_argument("--reserve-gib", type=float, default=20)
    report = sub.add_parser("report")
    report.add_argument("--campaign", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == "plan":
        document = plan(args.manifest, args.cpus)
        path = repair.bulk_output(args.campaign)
        if path.exists():
            raise ValueError("Campaign plan already exists; preserve the frozen plan")
        repair.write(path, document)
        return 0
    if args.action == "report":
        campaign = repair.ev.read(args.campaign)
        save_reports(check_plan(campaign), campaign)
        return 0
    return run(args.campaign, wave_seconds=args.wave_seconds, reserve_gib=args.reserve_gib)


if __name__ == "__main__":
    raise SystemExit(main())
