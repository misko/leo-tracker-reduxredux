"""Bounded graph-position subprocesses; storage is supplied through a narrow port."""

from contextlib import suppress
import os
import signal
import subprocess


def execute(command, *, log, timeout):
    environment = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                       MKL_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
    child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                             start_new_session=True, env=environment)
    try:
        return child.wait(timeout=timeout)
    except BaseException:
        with suppress(ProcessLookupError):
            os.killpg(child.pid, signal.SIGTERM)
        with suppress(subprocess.TimeoutExpired):
            child.wait(timeout=3)
        with suppress(ProcessLookupError):
            os.killpg(child.pid, signal.SIGKILL)
        child.wait()
        raise


def process(job, *, store, command, maximum_seconds=1200, runner=execute):
    if not command or not 1 <= maximum_seconds <= 1200:
        raise ValueError("Explicit command and budget of 1..1200s required")
    with store.owner(job["job_id"]) as acquired:
        if not acquired:
            return None
        previous = store.status(job["job_id"])
        output = store.path(job["job_id"]) / "output"
        if previous is not None or output.exists():
            if previous is None or previous["state"] == "running":
                # Recover a durable completed terminal after a watcher crash.
                try:
                    result, receipt = store.terminal(job)
                    return store.update(job, state=result["state"], result=result, terminal=receipt)
                except (OSError, ValueError, KeyError):
                    return store.update(job, state="failed", failure="Interrupted attempt; automatic retry disabled")
            return previous
        store.verify_input(job)
        store.update(job, state="running")
        invocation = [*command, "--input", job["input_path"], "--output", str(output),
                      "--maximum-seconds", str(maximum_seconds)]
        try:
            with (store.path(job["job_id"]) / "worker.log").open("ab") as log:
                code = runner(invocation, log=log, timeout=maximum_seconds + 15)
            result, receipt = store.terminal(job)
            if code and result["state"] != "failed":
                raise ValueError("Worker exit status contradicts terminal")
            return store.update(job, state=result["state"], result=result, terminal=receipt,
                                failure=result.get("reason"))
        except Exception as error:
            store.update(job, state="failed", failure=f"{type(error).__name__}: {error}")
            raise
