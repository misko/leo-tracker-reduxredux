import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from leo.cli.algo07v3 import supervise
from tests.operations.test_localization_v3_job import request_fixture, save_fixture


def test_cli_resume_is_a_real_owned_subprocess_and_needs_no_native_inputs(tmp_path):
    request = request_fixture(tmp_path)
    saved = save_fixture(request)
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request))
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "leo.cli.algo07v3",
            "resume",
            "--request",
            str(path),
            "--work-dir",
            str(tmp_path / "attempt"),
            "--timeout",
            "20",
        ],
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(result.stdout)
    assert report["status"] == "exited" and report["worker"]["resumed"] is True
    assert report["worker"]["publication"]["terminal_sha256"] == saved["sha256"]
    assert json.loads((tmp_path / "attempt/supervisor.json").read_bytes()) == report


def test_supervisor_timeout_kills_worker_and_signal_ignoring_descendant(tmp_path):
    pidfile = tmp_path / "descendant"
    code = (
        "import subprocess,sys,time; "
        "p=subprocess.Popen([sys.executable,'-c',"
        "'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)']); "
        f"open({str(pidfile)!r},'w').write(str(p.pid)); time.sleep(60)"
    )
    with (tmp_path / "log").open("wb") as log:
        result = supervise(
            [sys.executable, "-c", code],
            log=log,
            timeout=0.5,
            environment=os.environ.copy(),
            grace=0.1,
        )
    assert result["status"] == "timed_out" and result["returncode"] == 124
    with pytest.raises(ProcessLookupError):
        os.kill(result["pid"], 0)
    descendant = int(pidfile.read_text())
    # A killed adopted process may briefly remain a zombie until PID 1 reaps it.
    for _ in range(100):
        stat = Path(f"/proc/{descendant}/stat")
        if not stat.exists() or stat.read_text().split()[2] == "Z":
            break
        time.sleep(0.01)
    else:
        os.kill(descendant, signal.SIGKILL)
        pytest.fail("Timed-out worker left a running descendant")


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), 7201])
def test_supervisor_refuses_unbounded_deadline(tmp_path, timeout):
    with (tmp_path / "log").open("wb") as log, pytest.raises(ValueError, match="timeout"):
        supervise(["must-not-launch"], log=log, timeout=timeout, environment={})


def test_supervisor_timeout_cleans_up_actual_owned_pair(tmp_path):
    code = (
        'import os,signal,time\n'
        'from pathlib import Path\n'
        'from leo.operations.localization_v3_parallel import map_initial_arms\n'
        'from leo.operations.localization_v3_job import JobInterrupted\n'
        'def interrupted(*args): raise JobInterrupted("cancel")\n'
        'signal.signal(signal.SIGTERM, interrupted)\n'
        'def fit(arm):\n'
        ' signal.signal(signal.SIGTERM, signal.SIG_IGN)\n'
        f' Path({str(tmp_path)!r}, arm).write_text(str(os.getpid()))\n'
        ' time.sleep(60)\n'
        'try: map_initial_arms(fit, ("c0", "fitted_c"))\n'
        'except JobInterrupted: pass\n'
    )
    with (tmp_path / 'log').open('wb') as log:
        result = supervise([sys.executable, '-B', '-c', code], log=log, timeout=1.5,
                            environment=os.environ.copy(), grace=1.)
    assert result['status'] == 'timed_out'
    for arm in ('c0', 'fitted_c'):
        with pytest.raises(ProcessLookupError):
            os.kill(int((tmp_path / arm).read_text()), 0)


def test_supervisor_cancellation_reaps_worker(tmp_path):
    from leo.operations.localization_v3_job import JobInterrupted

    pidfile = tmp_path / "pid"

    def interrupted(*_):
        raise JobInterrupted("cancel test")

    previous = signal.signal(signal.SIGALRM, interrupted)
    try:
        signal.setitimer(signal.ITIMER_REAL, 0.5)
        with (tmp_path / "log").open("wb") as log, pytest.raises(JobInterrupted):
            supervise(
                [
                    sys.executable,
                    "-c",
                    (
                        "import os,time; "
                        f"open({str(pidfile)!r},'w').write(str(os.getpid())); time.sleep(60)"
                    ),
                ],
                log=log,
                timeout=10,
                environment=os.environ.copy(),
                grace=0.1,
            )
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)
