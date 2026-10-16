"""One bounded subprocess per exported fast input, with no automatic failed retries."""

import math
import os
import signal
import subprocess
from contextlib import suppress


def pending(store, active=()):
    for job in store.inputs():
        if job["job_id"] in active:
            continue
        status = store.status(job["job_id"])
        if status is None or status["state"] == "running":
            return job
    return None


def execute(command, *, log, timeout):
    """Bound the whole process group, including any inference descendants."""
    environment = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                       MKL_NUM_THREADS="1")
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                               start_new_session=True, env=environment)
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=5)
        # Kill descendants even if the leader already exited after TERM.
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        raise


def process(job, *, store, command, maximum_seconds=1200, runner=execute, plot_command=None):
    if (not math.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 1200
            or not command):
        raise ValueError("explicit shared inference command and bounded budget required")
    with store.owner(job["job_id"]) as acquired:
        if not acquired:
            return None
        previous = store.status(job["job_id"])
        if previous is not None or store.launched(job["job_id"]):
            if previous is None or previous["state"] == "running":
                return store.update(job, state="failed",
                    failure="Interrupted prior shared inference; automatic retry disabled")
            return previous
        store.launch(job)
        invocation = [*command, "--input", job["input_path"], "--output",
                      str(store.output_path(job["job_id"])),
                      "--maximum-seconds", str(maximum_seconds)]
        try:
            store.verify_input(job)
            with store.log(job["job_id"]) as log:
                code = runner(invocation, log=log, timeout=maximum_seconds+15)
            if code:
                raise RuntimeError(f"Shared inference exited {code}; see worker log")
            document, receipt = store.terminal(job)
            result = store.update(job, state=document["state"], terminal=receipt,
                                  result=document, failure=document.get("failure"))
        except Exception as error:
            store.update(job, state="failed", failure=f"{type(error).__name__}: {error}")
            raise
        if plot_command and document['state'] == 'complete':
            try:
                with store.log(job['job_id']) as log:
                    code = runner([*plot_command, '--job-id', job['job_id']], log=log, timeout=180)
                if code:
                    raise RuntimeError(f'Shared orbit rendering exited {code}')
                result = store.update(result, plot_state='complete', plot_failure=None)
            except Exception as error:
                # Presentation failure never invalidates a successful scientific fit.
                result = store.update(result, plot_state='failed', plot_failure=str(error))
        return result
