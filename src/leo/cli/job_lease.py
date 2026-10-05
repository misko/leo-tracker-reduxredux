"""Lease supervision for command-line jobs and their subprocess groups."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from contextlib import suppress

from leo.catalog.errors import LeaseLostError


class LeaseSupervisor:
    """Serialize terminal writes with renewal; stop children on uncertain ownership."""

    def __init__(self, catalog, lease, *, lease_for, interval=60.0):
        self.catalog = catalog
        self.lease = lease
        self.lease_for = lease_for
        self.interval = interval
        if not 0 < interval < lease_for.total_seconds():
            raise ValueError("heartbeat interval must be shorter than the lease")
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._error = None
        self._deadline = 0.0
        self._finished = False
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _renew(self):
        # Use the time before the database call: a slow response must not extend
        # our local estimate beyond the database's actual ownership window.
        started = time.monotonic()
        self.catalog.heartbeat_job(
            job_id=self.lease.job_id,
            worker_id=self.lease.worker_id,
            lease_for=self.lease_for,
        )
        self._deadline = started + self.lease_for.total_seconds()

    def __enter__(self):
        self._renew()
        self._thread.start()
        return self

    def _loop(self):
        while not self._stop.wait(self.interval):
            with self._lock:
                if self._finished or self._stop.is_set():
                    return
                try:
                    self._renew()
                except Exception as error:
                    self._error = error
                    self._stop.set()
                    return

    def ensure_owned(self):
        if self._error is not None or time.monotonic() >= self._deadline:
            raise LeaseLostError(
                f"lease supervision failed for job {self.lease.job_id}"
            ) from self._error

    def __getattr__(self, name):
        method = getattr(self.catalog, name)
        if name not in {"complete_job", "fail_job", "yield_adaptive_analysis_job"}:
            return method

        def terminal(**kwargs):
            with self._lock:
                self.ensure_owned()
                result = method(**kwargs)
                self._finished = True
                self._stop.set()
                return result

        return terminal

    def __exit__(self, *_args):
        self._stop.set()
        # A database outage must not strand a worker in thread.join forever.
        self._thread.join(timeout=2.0)


def _stop_group(process, grace=5.0):
    """Kill descendants even if the immediate child has already exited."""
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.communicate(timeout=grace)
    except subprocess.TimeoutExpired:
        pass
    finally:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.communicate()


def run_process(command, *, supervisor, poll_seconds=1.0, maximum_seconds=7200):
    """Drain output while checking ownership and an independent execution limit."""
    supervisor.ensure_owned()
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        while True:
            supervisor.ensure_owned()
            if time.monotonic() - started >= maximum_seconds:
                raise subprocess.TimeoutExpired(command, maximum_seconds)
            try:
                stdout, stderr = process.communicate(timeout=poll_seconds)
                supervisor.ensure_owned()
                return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                if time.monotonic() - started >= maximum_seconds:
                    raise
    finally:
        _stop_group(process)
