"""Freeze, resume and export the full DS30 charted original-file comparison."""

import argparse
from contextlib import contextmanager
from dataclasses import asdict
import errno
import fcntl
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from time import monotonic, process_time, sleep, time_ns
from uuid import uuid4

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]

from ds30_paired_inputs import (ARMS, AUDIT, BULK, CALIBRATIONS, FIRST100, MANIFEST, SEED, SMOKE, UNITS, assignments,
                               checked, digest, encode, historical_input, historical_membership, load_cohort, publish, read, write)
from ds30_paired_worker import PYTHON, STOCK, TIMING_SCOPE, environment, original_options, publication, run_attempt

OUTPUT = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
SOURCE_MOUNTS = (BULK, OUTPUT.parent)
LOCK = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
STAGES = (2, 8, 30, 100, 455)
VERIFIED = {"complete", "withheld", "solver_failed"}
SOURCE_ERRORS = {errno.ENOENT, errno.EACCES, errno.EPERM, errno.ENOTDIR}


def source_pins():
    return {name: digest((HERE / name).read_bytes()) for name in
            (Path(__file__).name, "ds30_paired_inputs.py", "ds30_paired_worker.py", "guarded_stage_idle.py")}


def init(root, args):
    from leo.contracts.algo08_region import Algo08Region
    from tools.pipeline_eval.qualification.paired_publication import verified_v3

    members, units, _ = load_cohort()
    cohort = assignments(members, units, historical_membership(args.first100))
    entry, build = args.entry.resolve(strict=True), args.build.resolve(strict=True)
    checked(build, args.build_sha256)
    offer = checked(args.region, args.region_sha256)
    Algo08Region.parse(json.loads(offer))
    if args.timeout <= 0:
        raise ValueError("Freeze a positive arm timeout")
    frozen = dict(schema="ds30-charted-original-pair-v1", manifest_sha256=MANIFEST, evaluation_units_sha256=UNITS,
                  historical_input_audit_sha256=AUDIT, seed=SEED, smoke=list(SMOKE), stages=list(STAGES),
                  timeout_s=args.timeout, timing_scope=TIMING_SCOPE, cpu=2, nice=15, io_priority="idle",
                  stock=verified_v3(STOCK), candidate=dict(entry=str(entry), entry_sha256=digest(entry.read_bytes()),
                                                          manifest=str(build), sha256=digest(build.read_bytes())),
                  offered_region_sha256=digest(offer), historical_first100_sha256=FIRST100,
                  driver_sources=source_pins(), cases=cohort)
    publish(root / "offer.json", offer)
    write(root / "plan.json", frozen)


def device_stats():
    return {str(root): Path(f"/sys/dev/block/{os.major(device)}:{os.minor(device)}/stat")
            for root in SOURCE_MOUNTS for device in (root.stat().st_dev,)}


def storage_sample():
    from guarded_stage_idle import sample

    result = {}
    for name, device in device_stats().items():
        state = asdict(sample(device, monotonic))
        counters = device.read_text().split()
        result[name] = state | dict(read_sectors=int(counters[2]), written_sectors=int(counters[6]))
    return result


def quiet_window():
    from guarded_stage_idle import Load, MIN_QUIET_S, POLL_S, QuietInterval

    guards = {name: QuietInterval() for name in device_stats()}
    deadline = monotonic() + 2 * MIN_QUIET_S
    while True:
        state = storage_sample()
        accepted = [guard.observe(Load(**{key: state[name][key] for key in Load.__dataclass_fields__}))
                    for name, guard in guards.items()]
        if all(accepted) or monotonic() >= deadline:
            return all(accepted), state
        sleep(POLL_S)


@contextmanager
def exclusive(path, mode):
    with path.open(mode) as fd:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield fd


def prepare_case(root, directory, row, member, historical, plan, lease):
    from leo.contracts.algo08_region import Algo08Region
    from tools.pipeline_eval.qualification.paired_publication import child_usage

    started, cpu, children = monotonic(), process_time(), child_usage()["cpu_s"]
    offer_path = root / "offer.json"
    region = Algo08Region.parse(json.loads(checked(offer_path, plan["offered_region_sha256"]))).document()
    inputs = historical_input(row, member, historical, region)
    authority_path = directory / "authority.json"
    if not authority_path.exists():
        trial = directory / "preflight" / uuid4().hex
        trial.mkdir(parents=True)
        for name in ("fonts", "tmp"):
            (trial / name).mkdir()
        command = [str(PYTHON), "-IB", plan["candidate"]["entry"],
                   *original_options(row["recording"], inputs["archive"], offer_path, trial / "unused-publication"),
                   "--prepare-authority", str(trial / "authority.json")]
        with (trial / "stdout.log").open("xb") as stdout, (trial / "stderr.log").open("xb") as stderr:
            done = subprocess.run(command, stdout=stdout, stderr=stderr, env=environment(trial),
                                  pass_fds=(lease.fileno(),), timeout=120, check=False)
        if done.returncode:
            raise ValueError(f"The original metadata adapter failed; see {trial.relative_to(root)}")
        authority = read(trial / "authority.json")
    else:
        authority = read(authority_path)
    if (any(authority[key] != value for key, value in inputs["expected"].items())
            or authority["region_sha256"] != plan["offered_region_sha256"]
            or authority["schema"] != "algo08v3-original-request-v1"):
        raise ValueError("The normal original adapter disagrees with the earlier sealed causal/raw contract")
    write(authority_path, authority)
    inputs.update(authority=authority, authority_sha256=digest(authority_path.read_bytes()))
    write(directory / "input.json", inputs)
    record(directory, "metadata_admitted", elapsed_s=monotonic() - started,
           cpu_s=process_time() - cpu + child_usage()["cpu_s"] - children)
    return inputs


def record(directory, state, **details):
    write(directory / "events" / f"{time_ns():020d}-{uuid4().hex}.json", dict(state=state, **details))


def outcome(directory, algorithm):
    results = sorted((directory / algorithm).glob("attempt-*/result.json"))
    if not results:
        return None, None
    path = results[-1]
    recovered = path.with_name("revalidation.json")
    if recovered.is_file():
        restored = read(recovered)
        if restored["original_attempt_result_sha256"] != digest(path.read_bytes()):
            raise ValueError("The revalidated attempt differs from its original result")
        return restored, recovered
    return read(path), path


def summary(directory):
    path = directory / "pair.json"
    return read(path) if path.is_file() else {}


def next_attempt(directory, arm):
    arm_root = directory / arm
    arm_root.mkdir(exist_ok=True)
    attempts = sorted(arm_root.glob("attempt-*"))
    for path in attempts:
        if not (path / "result.json").exists():
            write(path / "interrupted.json", dict(status="interrupted", preserved_clock=(path / "process.json").is_file()))
    return arm_root / f"attempt-{len(attempts)+1:06d}"


def paired(directory, lease, root, plan, row, member, historical, retry, generation):
    quiet, state = quiet_window()
    if not quiet:
        record(directory, "deferred_storage_busy", io=state)
        return False
    space = os.statvfs(root)
    if space.f_bavail * space.f_frsize < 4 * 1024**3:
        record(directory, "deferred_output_headroom", io=state)
        return False
    try:
        inputs = prepare_case(root, directory, row, member, historical, plan, lease)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        state = "unreachable" if isinstance(error, OSError) and error.errno in SOURCE_ERRORS else "invalid_original_input"
        reason = f"{type(error).__name__}: {error}"
        record(directory, state, reason=reason)
        if not summary(directory):
            write(directory / "pair.json", dict(verified_pair=False, state=state, reason=reason))
        return True
    authority = directory / "authority.json"
    lease_id = uuid4().hex
    for arm in row["order"]:
        observed, _ = outcome(directory, arm)
        if observed and observed.get("generation", 1) == generation and (observed["outcome"] in VERIFIED or not retry):
            continue
        quiet, state = quiet_window()
        if not quiet:
            record(directory, "deferred_storage_busy", io=state, next_arm=arm)
            return False
        run_attempt(next_attempt(directory, arm), plan, inputs, root / "offer.json", authority,
                    arm, lease.fileno(), lease_id, generation, state, storage_sample)
    seal_pair(directory, inputs, row["order"])
    return True


def seal_pair(directory, inputs, expected_order):
    findings = [outcome(directory, arm) for arm in ARMS]
    results = [document for document, _ in findings]
    generation = {item.get("generation", 1) for item in results}
    actual_order = sorted(ARMS, key=lambda arm: results[ARMS.index(arm)]["process"]["started_unix_ns"])
    chronological = (actual_order == expected_order and
                     results[ARMS.index(actual_order[0])]["process"]["finished_unix_ns"]
                     <= results[ARMS.index(actual_order[1])]["process"]["started_unix_ns"])
    matching = all(item["outcome"] in VERIFIED and item["raw_identity"] == inputs["authority"] for item in results)
    result = dict(verified_pair=matching and len(generation) == 1 and chronological,
                  generation=max(generation), actual_order=actual_order, chronological=chronological,
                  state="observed_pair", authority_sha256=inputs["authority_sha256"],
                  same_lease=results[0]["lease_id"] == results[1]["lease_id"],
                  attempt_result_sha256={arm: digest(location.read_bytes()) for arm, (_, location)
                                         in zip(ARMS, findings, strict=True)})
    if summary(directory):
        record(directory, "retry_finished", previous=summary(directory), current=result)
    publish(directory / "pair.json", encode(result) + b"\n", replace=True)


def amend_validation(root, plan):
    from inspect import signature
    from leo.storage.fast_scan import FastScanStore

    if "create" not in signature(FastScanStore.automatic_workspace).parameters:
        raise ValueError("The orchestrator requires the current read-only standard store")
    write(root / "validation-revision.json", dict(
        plan_sha256=digest((root / "plan.json").read_bytes()),
        original_driver_sources=plan["driver_sources"], current_driver_sources=source_pins(),
        store_sha256=digest(Path(sys.modules[FastScanStore.__module__].__file__).read_bytes()),
        reason="Create the installed launcher's empty output root and use the read-only standard verifier"))


def check_revision(root, plan):
    if plan["driver_sources"] == source_pins():
        return
    from leo.storage.fast_scan import FastScanStore

    revision = read(root / "validation-revision.json")
    if (revision["plan_sha256"] != digest((root / "plan.json").read_bytes())
            or revision["original_driver_sources"] != plan["driver_sources"]
            or revision["current_driver_sources"] != source_pins()
            or revision["store_sha256"] != digest(Path(sys.modules[FastScanStore.__module__].__file__).read_bytes())):
        raise ValueError("The launch driver differs from the sealed campaign and its validation revision")


def revalidate(root, plan, case):
    check_revision(root, plan)
    directory = root / "cases" / case
    failed, path = outcome(directory, "successor")
    if failed["outcome"] != "invalid_publication" or failed["process"]["exit_code"] != 0:
        raise ValueError("The original candidate must already have exited successfully")
    inputs = read(directory / "input.json")
    attempt = path.parent
    measured = read(attempt / "process.json")
    begin, cpu = monotonic(), process_time()
    result = publication(attempt / "publication", attempt, "successor", inputs, measured, plan["candidate"])
    validation = dict(elapsed_s=monotonic() - begin, cpu_s=process_time() - cpu)
    write(attempt / "revalidation.json", result | dict(
        process=measured, validation=validation, timing_scope="raw_launcher_exit_with_deferred_publication_verification",
        elapsed_s=measured["elapsed_s"] + validation["elapsed_s"], cpu_s=measured["cpu_s"] + validation["cpu_s"],
        authority_sha256=failed["authority_sha256"], algorithm="successor", lease_id=failed["lease_id"],
        generation=failed.get("generation", 1),
        original_attempt_result_sha256=digest(path.read_bytes())))
    record(directory, "candidate_revalidated_without_raw_rerun")
    seal_pair(directory, inputs, next(row["order"] for row in plan["cases"] if row["case"] == case))


def stage_cases(plan):
    by_case = {row["case"]: row for row in plan["cases"]}
    return [by_case[case] for case in plan["smoke"]] + [row for row in plan["cases"] if row["case"] not in plan["smoke"]]


def in_scope(root, plan, target, selected, retry):
    ordered = stage_cases(plan)
    if selected is not None:
        if (selected not in plan["smoke"] and not retry) or selected not in {r["case"] for r in ordered}:
            raise ValueError("Select only a frozen smoke case or explicitly retry a known infrastructure failure")
        return [row for row in ordered if row["case"] == selected]
    for size in plan["stages"]:
        phase = ordered[:size]
        if size >= target:
            return phase
        states = [summary(root / "cases" / r["case"]) for r in phase]
        if not all(states):
            return phase
        if size == 2:
            if not all(r.get("verified_pair") for r in states):
                raise ValueError("Review unresolved smoke-pair operations before scaling")
        elif sum(r.get("state") in ("observed_pair", "invalid_original_input") and not r.get("verified_pair") for r in states) >= 2:
            raise ValueError(f"Review repeated operational failures before scaling beyond {size} cases")
    raise ValueError("Unknown campaign stage")


def run(root, plan, args):
    from tools.pipeline_eval.qualification.paired_publication import verified_v3

    if socket.gethostname().split(".")[0] != "gauss" or 2 not in os.sched_getaffinity(0):
        raise ValueError("Use Gauss CPU 2 for the original-file study")
    os.sched_setaffinity(0, {2})
    os.setpriority(os.PRIO_PROCESS, 0, max(15, os.getpriority(os.PRIO_PROCESS, 0)))
    subprocess.run(["ionice", "-c3", "-p", str(os.getpid())], check=True)
    check_revision(root, plan)
    if plan["stock"] != verified_v3(STOCK):
        raise ValueError("The original installed build differs from the sealed run")
    build = plan["candidate"]
    checked(Path(build["entry"]), build["entry_sha256"])
    checked(Path(build["manifest"]), build["sha256"])
    members, _, audit = load_cohort()
    lookup = {member["dataset_label"]: member for member in members}
    attempts = 0
    while attempts < args.max_pairs:
        rows = in_scope(root, plan, args.target, args.case, args.retry_infrastructure)
        pending = []
        for row in rows:
            saved = summary(root / "cases" / row["case"])
            if not saved or args.retry_infrastructure or (args.replay_smoke and saved.get("generation", 1) == 1):
                pending.append(row)
        if not pending:
            return 0
        row = pending[0]
        directory = root / "cases" / row["case"]
        try:
            with exclusive(LOCK, "rb") as lease:
                print("DS30 pair", row["case"], "→".join(row["order"]), flush=True)
                done = paired(directory, lease, root, plan, row, lookup[row["case"]],
                              audit[row["case"]], args.retry_infrastructure, generation=2 if args.replay_smoke else 1)
        except BlockingIOError:
            record(directory, "deferred_shared_lease")
            done = False
        export(root, plan)
        if done:
            attempts += 1
            print("DS30 recorded", row["case"], summary(directory), flush=True)
            if args.case is not None:
                return 0
        elif args.watch:
            sleep(30)
        else:
            return 75
    return 0


def rows(root, plan):
    for row in plan["cases"]:
        directory = root / "cases" / row["case"]
        pair = summary(directory)
        inputs = read(directory / "input.json") if (directory / "input.json").is_file() else {}
        events = sorted((directory / "events").glob("*.json"))
        last_event = read(events[-1])["state"] if events else None
        for arm in ARMS:
            result, path = outcome(directory, arm)
            evidence = result.get("evidence", {}) if result else {}
            receipt = evidence.get("receipt")
            blank_arms = {a: dict(latlon=None, rf_rms_hz=None) for a in CALIBRATIONS}
            arm_rows = {a: dict(blank_arms[a], **evidence.get("arms", {}).get(a, {})) for a in CALIBRATIONS}
            process = result["process"] if result else {}
            validator = result["validation"] if result else {}
            build = plan["stock"]["frozen_specification"] if arm == "installed" else plan["candidate"]["sha256"]
            attempt_sha = digest(path.read_bytes()) if path else None
            sealed_attempt = pair.get("attempt_result_sha256", {}).get(arm, attempt_sha)
            same_generation = not result or result.get("generation", 1) == pair.get("generation", 1)
            if same_generation and sealed_attempt != attempt_sha:
                raise ValueError("The sealed paired attempt changed")
            observed = result.get("raw_identity", {}) if result else {}
            yield row | dict(algorithm=arm, build_sha256=build, first=row["order"][0],
                 outcome=result["outcome"] if result else pair.get("state", "pending"),
                 admission_state=pair.get("state", last_event or "pending"),
                 elapsed_s=result["elapsed_s"] if result else None, cpu_s=result["cpu_s"] if result else None,
                 child_elapsed_s=process.get("elapsed_s"), child_cpu_s=process.get("cpu_s"),
                 child_started_unix_ns=process.get("started_unix_ns"), child_finished_unix_ns=process.get("finished_unix_ns"),
                 generation=result.get("generation", 1) if result else None, actual_order=pair.get("actual_order"),
                 validator_elapsed_s=validator.get("elapsed_s"), validator_cpu_s=validator.get("cpu_s"),
                 input_blocks=process.get("input_blocks"), output_blocks=process.get("output_blocks"),
                 timing_scope=result["timing_scope"] if result else None, verified_pair=pair.get("verified_pair", False) and same_generation,
                 same_lease=pair.get("same_lease"), authority_sha256=inputs.get("authority_sha256"),
                 raw_authority_sha256=observed.get("raw_authority_sha256"), arms=arm_rows,
                 requested_raw_authority_sha256=inputs.get("authority", {}).get("raw_authority_sha256"),
                 acquisition_verified=bool(observed),
                 reached_solver=result.get("reached_solver", result["outcome"] == "complete") if result else None,
                 terminal_sha256=receipt.get("terminal_sha256") if receipt else None,
                 receipt_sha256=digest(encode(receipt)) if receipt else None,
                 attempt_result_sha256=attempt_sha,
                 attempt=str(path.relative_to(root)) if path else None,
                 reason=(result.get("reason") or evidence.get("reason")) if result else pair.get("reason"))


def export(root, plan):
    publish(root / "rows.jsonl", b"".join(encode(row) + b"\n" for row in rows(root, plan)), replace=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    freeze = modes.add_parser("init")
    for name in ("entry", "build", "region", "first100"):
        freeze.add_argument("--" + name, type=Path, required=True)
    for name in ("build-sha256", "region-sha256"):
        freeze.add_argument("--" + name, required=True)
    freeze.add_argument("--timeout", type=int, default=1800)
    drive = modes.add_parser("run")
    drive.add_argument("--target", type=int, choices=STAGES, default=2)
    drive.add_argument("--max-pairs", type=int, default=1)
    drive.add_argument("--case")
    drive.add_argument("--retry-infrastructure", action="store_true")
    drive.add_argument("--replay-smoke", action="store_true", help="Rerun the two original unqualified smoke pairs in frozen order")
    drive.add_argument("--watch", action="store_true")
    modes.add_parser("export")
    modes.add_parser("amend-validation")
    verify = modes.add_parser("revalidate")
    verify.add_argument("case", choices=SMOKE)
    args = parser.parse_args()
    root = OUTPUT
    if root.resolve(strict=True) != root or root.stat().st_dev != OUTPUT.parent.stat().st_dev:
        parser.error("Use only the approved local research NVMe destination")
    with exclusive(root / "driver.lock", "a+b"):
        if args.mode == "init":
            init(root, args)
        plan = read(root / "plan.json")
        try:
            if args.mode == "amend-validation":
                amend_validation(root, plan)
            if args.mode == "revalidate":
                with exclusive(LOCK, "rb"):
                    revalidate(root, plan, args.case)
            if args.mode == "run":
                if (args.max_pairs <= 0 or (args.retry_infrastructure and not args.case)
                        or (args.replay_smoke and (args.target != 2 or args.retry_infrastructure))):
                    parser.error("Use a positive pair budget and an explicit compatible retry scope")
                return run(root, plan, args)
        finally:
            export(root, plan)
    return 0


if __name__ == "__main__":
    sys.exit(main())
