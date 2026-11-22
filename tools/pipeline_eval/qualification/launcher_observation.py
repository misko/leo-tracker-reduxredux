"""Observe the timed leader's final Linux scheduler counters before reaping it."""

import os
import selectors
import signal
import subprocess
import time
from contextlib import ExitStack, suppress
from pathlib import Path


def _schedstat(pid):
    try:
        fields = Path(f"/proc/{pid}/schedstat").read_text().split()
        cpu, runnable, slices = map(int, fields)
        if cpu <= 0 or runnable < 0 or slices <= 0:
            raise ValueError("scheduler counters unavailable")
    except (OSError, ValueError) as error:
        return {"unavailable": str(error)}
    return dict(cpu_ns=cpu, runnable_wait_ns=runnable, timeslices=slices)


def run(command, *, env, timeout, started):
    """Drain both normal capture pipes and select on the unreaped leader's pidfd."""
    if not hasattr(os, "pidfd_open"):
        raise RuntimeError("Scheduler observation requires Linux pidfd support")
    parent_before = _schedstat("self")
    parent_cpu = time.process_time_ns()
    with subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as child:
        try:
            deadline = time.monotonic() + timeout
            return _observe(child, command, timeout, started, deadline, parent_before, parent_cpu)
        except BaseException:
            # An unreaped leader guarantees its PID has not been reused. A
            # descendant retaining either pipe must not keep the arm open after timeout.
            if child.returncode is None:
                with suppress(ProcessLookupError):
                    os.killpg(child.pid, signal.SIGKILL)
            raise


def _observe(child, command, timeout, started, deadline, parent_before, parent_cpu):
    streams = {child.stdout: [], child.stderr: []}
    closed = 0
    leader = None
    with ExitStack() as stack:
        poll = stack.enter_context(selectors.DefaultSelector())
        pidfd = os.pidfd_open(child.pid)
        stack.callback(os.close, pidfd)
        poll.register(pidfd, selectors.EVENT_READ)
        for stream in streams:
            poll.register(stream, selectors.EVENT_READ)
        while poll.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            for event, _ in poll.select(remaining):
                if event.fd == pidfd:
                    leader = dict(
                        exit_observed_s=time.monotonic() - started, schedstat=_schedstat(child.pid)
                    )
                    poll.unregister(pidfd)
                    continue
                data = os.read(event.fd, 32768)
                if data:
                    streams[event.fileobj].append(data)
                else:
                    poll.unregister(event.fileobj)
                    closed += 1
                    if closed == len(streams):
                        eof_observed = time.monotonic() - started

    _, status, usage = os.wait4(child.pid, 0)
    child.returncode = os.waitstatus_to_exitcode(status)
    stdout, stderr = (
        b"".join(chunks)
        .decode(stream.encoding, stream.errors)
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        for stream, chunks in streams.items()
    )
    parent_after = _schedstat("self")
    parent_wait = None
    if "runnable_wait_ns" in parent_before and "runnable_wait_ns" in parent_after:
        parent_wait = parent_after["runnable_wait_ns"] - parent_before["runnable_wait_ns"]
    result = subprocess.CompletedProcess(command, child.returncode, stdout, stderr)
    return result, dict(
        pid=child.pid,
        leader=leader,
        pipes_eof_observed_s=eof_observed,
        wait4_cpu_s=usage.ru_utime + usage.ru_stime,
        wait4_input_blocks=usage.ru_inblock,
        monitor_cpu_ns=time.process_time_ns() - parent_cpu,
        monitor_runnable_wait_ns=parent_wait,
    )
