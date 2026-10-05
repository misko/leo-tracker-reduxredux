import sys
import threading
import time
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.catalog.errors import LeaseLostError
from leo.cli.job_lease import LeaseSupervisor, run_process


class Catalog:
    def __init__(self):
        self.calls = 0
        self.finished = False
        self.fail = False

    def heartbeat_job(self, **kwargs):
        assert not self.finished, "heartbeat after terminal write"
        if self.fail:
            raise LeaseLostError("ownership moved")
        self.calls += 1

    def complete_job(self, **kwargs):
        time.sleep(0.06)
        self.finished = True


def guard(catalog):
    return LeaseSupervisor(
        catalog,
        SimpleNamespace(job_id=1, worker_id="unique"),
        lease_for=timedelta(seconds=0.3),
        interval=0.03,
    )


def test_long_child_and_validation_keep_lease_and_complete_without_race():
    catalog = Catalog()
    with guard(catalog) as supervisor:
        result = run_process(
            [sys.executable, "-c", "import time; time.sleep(.7); print('done')"],
            supervisor=supervisor,
            poll_seconds=0.02,
        )
        assert result.stdout.strip() == "done"
        before = catalog.calls
        time.sleep(0.12)  # Result validation must also remain covered.
        assert catalog.calls > before
        supervisor.complete_job(job_id=1, worker_id="unique")
        time.sleep(0.06)
    assert catalog.finished
    assert catalog.calls > 10


@pytest.mark.parametrize("interrupt", [False, True])
def test_lease_loss_or_shutdown_terminates_child_and_grandchild(tmp_path, interrupt):
    catalog = Catalog()
    pid_file = tmp_path / "grandchild"
    code = (
        "import subprocess,sys,time,pathlib; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid)); time.sleep(60)"
    )

    def lose():
        deadline = time.monotonic() + 5
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        catalog.fail = True

    thread = threading.Thread(target=lose)
    thread.start()
    with (
        guard(catalog) as supervisor,
        pytest.raises(KeyboardInterrupt if interrupt else LeaseLostError),
    ):
        if interrupt:
            original = supervisor.ensure_owned

            def ensure_owned():
                if catalog.fail:
                    raise KeyboardInterrupt
                original()

            supervisor.ensure_owned = ensure_owned
        run_process([sys.executable, "-c", code], supervisor=supervisor, poll_seconds=0.02)
    thread.join()
    pid = int(pid_file.read_text())
    # An orphan can briefly remain a zombie until PID 1 reaps it; it cannot execute.
    status = Path(f"/proc/{pid}/stat")

    def running():
        try:
            return status.read_text().split()[2] != "Z"
        except (FileNotFoundError, ProcessLookupError):
            return False

    deadline = time.monotonic() + 2
    while running() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not running()
    assert not catalog.finished


def test_watchdog_stops_a_child_even_with_fresh_heartbeats():
    import subprocess

    with guard(Catalog()) as supervisor, pytest.raises(subprocess.TimeoutExpired):
        run_process(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            supervisor=supervisor,
            poll_seconds=0.02,
            maximum_seconds=0.12,
        )


def test_local_deadline_rejects_stalled_renewal():
    with guard(Catalog()) as supervisor:
        supervisor._stop.set()
        time.sleep(0.35)
        with pytest.raises(LeaseLostError):
            supervisor.complete_job(job_id=1, worker_id="unique")
