"""Bound one ALGO04 numerical add-on per completed published ALGO03 job."""

from leo.application.automatic_fast_graph import execute


def process(job, *, store, command, maximum_seconds=1200, runner=execute):
    if (
        not command
        or isinstance(maximum_seconds, bool)
        or not isinstance(maximum_seconds, int)
        or not 1 <= maximum_seconds <= 1200
    ):
        raise ValueError("Explicit ALGO04 command and numerical budget of 1..1200s required")
    with store.owner(job["job_id"]) as acquired:
        if not acquired:
            return None
        output = store.path(job["job_id"]) / "output"
        previous = store.status(job["job_id"])
        if previous is not None or output.exists():
            if previous is None or previous["state"] == "running":
                try:
                    terminal, receipt = store.terminal(job)
                    return store.update(
                        job, state=terminal["state"], result=terminal, terminal=receipt
                    )
                except (OSError, ValueError, KeyError):
                    return store.update(
                        job,
                        state="failed",
                        failure="Interrupted ALGO04 attempt; no automatic retry",
                    )
            return previous
        store.verify_input(job)
        store.update(job, state="running")
        invocation = [
            *command,
            "--job",
            job["source_job"]["job_id"],
            "--output",
            str(output),
            "--maximum-seconds",
            str(maximum_seconds),
        ]
        try:
            with (store.path(job["job_id"]) / "worker.log").open("ab") as log:
                code = runner(invocation, log=log, timeout=maximum_seconds + 15)
            terminal, receipt = store.terminal(job)
            if code and terminal["state"] != "failed":
                raise ValueError("ALGO04 worker exit status contradicts its terminal")
            return store.update(
                job,
                state=terminal["state"],
                result=terminal,
                terminal=receipt,
                failure=terminal.get("failure"),
            )
        except Exception as error:
            store.update(job, state="failed", failure=f"{type(error).__name__}: {error}")
            raise
