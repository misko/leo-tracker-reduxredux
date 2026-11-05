"""Run/resume a pinned native ALGO07v3 request with a hard process deadline.

Only validation-all-work requests are accepted today. No service is deployed.
The supervisor launches one owned worker, never an earlier ALGO executable.
"""

import argparse
import json
import math
import os
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path


def write(path, value):
    temporary = path.with_suffix(".partial")
    with temporary.open("x") as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def stop_process_group(child, grace=2.0):
    with suppress(ProcessLookupError):
        os.killpg(child.pid, signal.SIGTERM)
    with suppress(subprocess.TimeoutExpired):
        child.wait(timeout=grace)
    # Kill any remaining descendant even if the direct child already exited.
    with suppress(ProcessLookupError):
        os.killpg(child.pid, signal.SIGKILL)
    child.wait()


def supervise(command, *, log, timeout, environment, grace=2.0):
    if not math.isfinite(timeout) or not 0 < timeout <= 7200:
        raise ValueError("Job timeout must be in (0, 7200] seconds")
    began = time.monotonic()
    child = subprocess.Popen(
        command, stdout=log, stderr=subprocess.STDOUT, env=environment, start_new_session=True
    )
    try:
        code = child.wait(timeout=timeout)
        status = "exited"
    except subprocess.TimeoutExpired:
        stop_process_group(child, grace)
        code, status = 124, "timed_out"
    except BaseException:
        stop_process_group(child, grace)
        raise
    return dict(
        status=status, returncode=code, pid=child.pid, process_seconds=time.monotonic() - began
    )


def worker(request_path, outcome_path, resume_only):
    from leo.operations.localization_v3_job import JobInterrupted, execute

    def interrupted(signum, _):
        raise JobInterrupted(f"Native job cancelled by signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        request = json.loads(request_path.read_bytes())
        result = execute(
            request,
            resume_only=resume_only,
            emit=lambda value: print(json.dumps(value), flush=True),
        )
    except JobInterrupted as error:
        write(outcome_path, dict(status="interrupted", error=str(error)))
        return 130
    except Exception as error:
        write(outcome_path, dict(status="failed", error=f"{type(error).__name__}: {error}"))
        return 1
    write(outcome_path, result)
    return 0 if result["status"] == "complete" else 2


def launch(args):
    from leo.contracts.digests import canonical_digest
    from leo.operations.localization_v3_job import JobInterrupted, validate_request

    request = validate_request(json.loads(args.request.read_bytes()))
    directory = args.work_dir.resolve()
    if directory.is_relative_to("/mnt/qnap01"):
        raise ValueError("QNAP is read-only")
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 7200:
        raise ValueError("Job timeout must be in (0, 7200] seconds")
    directory.mkdir(parents=True, exist_ok=False)
    write(directory / "request.json", request)
    command = [
        sys.executable,
        "-B",
        "-m",
        "leo.cli.algo07v3",
        "_worker",
        "--request",
        str(directory / "request.json"),
        "--outcome",
        str(directory / "worker.json"),
    ]
    if args.action == "resume":
        command.append("--resume-only")
    environment = dict(
        os.environ,
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        PYTHONDONTWRITEBYTECODE="1",
    )
    write(
        directory / "launch.json",
        dict(
            command=command,
            timeout_seconds=args.timeout,
            request_sha256=canonical_digest(request),
            action=args.action,
        ),
    )

    def interrupted(signum, _):
        raise JobInterrupted(f"Supervisor cancelled by signal {signum}")

    previous = {s: signal.signal(s, interrupted) for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        with (directory / "worker.log").open("xb") as log:
            try:
                process = supervise(command, log=log, timeout=args.timeout, environment=environment)
            except JobInterrupted as error:
                process = dict(status="cancelled", returncode=130, error=str(error))
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    outcome = directory / "worker.json"
    result = dict(
        process,
        request_sha256=canonical_digest(request),
        worker=json.loads(outcome.read_bytes()) if outcome.exists() else None,
    )
    if (
        result["status"] == "exited"
        and result["returncode"] == 0
        and (not result["worker"] or result["worker"]["status"] != "complete")
    ):
        result.update(status="invalid_completion", returncode=1)
    write(directory / "supervisor.json", result)
    print(json.dumps(result), flush=True)
    return result["returncode"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("run", "resume"):
        command = commands.add_parser(action)
        command.add_argument("--request", type=Path, required=True)
        command.add_argument(
            "--work-dir",
            type=Path,
            required=True,
            help="Fresh local attempt directory (logs and receipts)",
        )
        command.add_argument("--timeout", type=float, default=1200.0)
    command = commands.add_parser("_worker", help=argparse.SUPPRESS)
    command.add_argument("--request", type=Path, required=True)
    command.add_argument("--outcome", type=Path, required=True)
    command.add_argument("--resume-only", action="store_true")
    args = parser.parse_args()
    try:
        return (
            worker(args.request, args.outcome, args.resume_only)
            if args.action == "_worker"
            else launch(args)
        )
    except (ValueError, OSError) as error:
        print(json.dumps(dict(status="failed", error=str(error))), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
