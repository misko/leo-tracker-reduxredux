import json
from pathlib import Path
import subprocess
import time


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "monitor.c"


def build(tmp_path):
    binary = tmp_path / "monitor"
    subprocess.run(
        ["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", str(SOURCE), "-o", str(binary)],
        check=True,
    )
    return binary


def write_stat(root, user0, user1):
    (root / "stat").write_text(
        "cpu 0 0 0 0 0 0 0 0 0 0\n"
        f"cpu0 {user0} 2 3 4 5 6 7 8 9 10\n"
        f"cpu1 {user1} 12 13 14 15 16 17 18 19 20\n"
    )


def write_pid_stat(root, utime, stime):
    pid_dir = root / "4242"
    pid_dir.mkdir(exist_ok=True)
    # The final ')' is the parser boundary; the comm deliberately includes ')' and spaces.
    (pid_dir / "stat").write_text(
        "4242 (scanner ) name) R 1 2 3 4 5 6 7 8 9 10 "
        f"{utime} {stime} 13 14\n"
    )


def test_fake_proc_reports_per_core_and_process_deltas(tmp_path):
    binary = build(tmp_path)
    proc = tmp_path / "proc"
    proc.mkdir()
    write_stat(proc, 100, 200)
    write_pid_stat(proc, 11, 12)
    run = subprocess.Popen(
        [str(binary), "--proc-root", str(proc), "1", "4242"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(0.2)
    write_stat(proc, 111, 225)
    write_pid_stat(proc, 21, 19)
    stdout, stderr = run.communicate(timeout=3)
    assert run.returncode == 0, stderr
    rows = [json.loads(line) for line in stdout.splitlines()]
    assert len(rows) == 2
    assert rows[0]["cores"][0]["raw"]["user"] == 100
    assert rows[0]["cores"][0]["delta"] is None
    assert rows[1]["cores"][0]["delta"]["user"] == 11
    assert rows[1]["cores"][1]["delta"]["user"] == 25
    process = rows[1]["processes"][0]
    assert process["present"] is True
    assert process["delta"] == {"utime_ticks": 10, "stime_ticks": 7}
    # The fake proc root has no directory for the monitor's own PID; absence is explicit.
    assert rows[1]["self"]["present"] is False


def test_rejects_unbounded_duration(tmp_path):
    binary = build(tmp_path)
    result = subprocess.run([str(binary), "181"], text=True, capture_output=True)
    assert result.returncode == 2
    assert "usage:" in result.stderr
