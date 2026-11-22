import os
import resource
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tools.pipeline_eval.qualification import launcher_observation

pytestmark = pytest.mark.skipif(not hasattr(os, "pidfd_open"), reason="Linux pidfd API required")


def observe(source, *args, timeout=3.0):
    return launcher_observation.run(
        [sys.executable, "-c", source, *map(str, args)],
        env=None,
        started=time.monotonic(),
        timeout=timeout,
    )


def test_output_pipes_are_drained_and_have_standard_text_semantics():
    result, observation = observe(
        "import os; os.write(1, b'x' * 262144 + b'\\r\\n'); "
        "os.write(2, b'y' * 262144 + b'\\r'); raise SystemExit(7)"
    )
    assert result.returncode == 7
    assert result.stdout == "x" * 262144 + "\n"
    assert result.stderr == "y" * 262144 + "\n"
    assert observation["leader"]["exit_observed_s"] > 0
    assert observation["pipes_eof_observed_s"] > 0
    with pytest.raises(ChildProcessError):
        os.waitpid(observation["pid"], os.WNOHANG)


def test_waited_child_cpu_is_accounted_separately_from_leader_runtime():
    nested = "import time; end=time.process_time()+0.06\nwhile time.process_time()<end: pass\n"
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    result, observation = observe(
        "import subprocess,sys; subprocess.run([sys.executable, '-c', sys.argv[1]], check=True)",
        nested,
    )
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    assert result.returncode == 0
    assert observation["wait4_cpu_s"] == pytest.approx(
        (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime),
        abs=0.00001,
    )
    counters = observation["leader"]["schedstat"]
    if "unavailable" in counters:
        pytest.skip("Kernel does not expose per-task scheduler counters")
    assert observation["wait4_cpu_s"] - counters["cpu_ns"] / 1e9 > 0.04
    assert counters["runnable_wait_ns"] >= 0


def test_descendant_holding_pipes_is_kept_in_elapsed_boundary():
    result, observation = observe(
        "import subprocess,sys; subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(0.35); print(\"descendant\")']); print('leader', flush=True)"
    )
    assert result.stdout == "leader\ndescendant\n"
    assert observation["pipes_eof_observed_s"] - observation["leader"]["exit_observed_s"] > 0.2


def test_timeout_kills_pipe_holding_descendant_even_after_leader_exit(tmp_path):
    pid_file = tmp_path / "descendant"
    with pytest.raises(subprocess.TimeoutExpired):
        observe(
            "import subprocess,sys,pathlib; "
            "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)']); "
            "pathlib.Path(sys.argv[1]).write_text(str(p.pid))",
            pid_file,
            timeout=0.6,
        )
    stat = Path(f"/proc/{pid_file.read_text()}/stat")
    deadline = time.monotonic() + 0.75
    while time.monotonic() < deadline:
        try:
            if stat.read_text().rsplit(") ", 1)[-1].split()[0] == "Z":
                break
        except FileNotFoundError:
            break
        time.sleep(0.01)
    else:
        pytest.fail("Timeout left the descendant alive")
