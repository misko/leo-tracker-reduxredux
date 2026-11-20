import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

import pytest

from tools.pipeline_eval import iq_service

UNIT = "leo-iq-bench-012345abcdef.service"
INVOCATION = "c" * 32
SYSTEMCTL_QUERY = iq_service._show


@pytest.mark.parametrize(
    ("service", "expected"),
    [
        ({"exit_code": None, "systemd": {"Result": "success"}}, True),
        ({"exit_code": 0, "systemd": {"Result": "success"}}, True),
        ({"exit_code": 1, "systemd": {"Result": "success"}}, False),
        ({"exit_code": 0, "systemd": {"Result": "timeout"}}, False),
        ({"exit_code": None, "systemd": {"Result": "oom-kill"}}, False),
        ({"exit_code": 0, "systemd": {}}, True),
        ({"exit_code": 1}, False),
        ({"exit_code": None}, False),
    ],
)
def test_success_for_recovered_and_historical_receipts(service, expected):
    assert iq_service.succeeded(service) is expected


@pytest.fixture
def attempt(tmp_path, monkeypatch):
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    (attempt / "plan.json").write_text(json.dumps({"cpus": [4, 5], "limit_s": 360}))
    (attempt / "service.log").write_text(f"Running as unit: {UNIT}\nstage: raw complete\n")
    group = iq_service._cgroup(UNIT)
    (attempt / "start.json").write_text(
        json.dumps(
            {
                "cgroup": group,
                "cpus": [4, 5],
                "memory.max": iq_service.MEMORY,
                "memory.swap.max": 0,
                "pid": 42,
                "monotonic_s": 11,
            }
        )
    )
    root = tmp_path / "cgroup"
    root.mkdir()
    (root / "cgroup.controllers").write_text("cpu memory\n")
    monkeypatch.setattr(iq_service, "CGROUP", root)
    state = dict(
        Id=UNIT,
        LoadState="loaded",
        ActiveState="failed",
        SubState="failed",
        Transient="yes",
        InvocationID=INVOCATION,
        MainPID="0",
        ControlPID="0",
        ControlGroup="",
        ExecMainPID="42",
        ExecStart=(
            f"{{ argv[]=/usr/bin/taskset -c 4,5 /usr/bin/python -B -m "
            f"tools.pipeline_eval.whole_iq worker {attempt} ; ignore_errors=no }}"
        ),
        Environment=f"TMPDIR={attempt}",
        MemoryMax=str(iq_service.MEMORY),
        MemorySwapMax="0",
        KillMode="control-group",
        Result="timeout",
        CPUUsageNSec="90000000000",
        MemoryPeak=str(iq_service.MEMORY),
        MemorySwapPeak="0",
        ActiveEnterTimestampMonotonic="10000000",
        ActiveExitTimestampMonotonic="370000000",
        InactiveEnterTimestampMonotonic="410000000",
    )
    monkeypatch.setattr(iq_service, "_show", lambda unit: dict(state))
    return attempt, state


def test_concurrent_recovery_converges_and_keeps_unmeasured_supervisor_fields_empty(attempt):
    path, _ = attempt
    log = (path / "service.log").read_bytes()
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(iq_service.reconcile, [path] * 4))
    assert receipts == [receipts[0]] * 4
    record = receipts[0]
    assert record["systemd"]["Result"] == "timeout"
    assert record["service_active_s"] == 360 and record["service_wall_s"] == 400
    assert record["exit_code"] is None and record["supervisor_s"] is None
    assert record["binding"]["cgroup_state"] == "removed"
    assert (path / "service.log").read_bytes() == log
    receipt = path / "service.json"
    before = receipt.stat()
    assert iq_service.reconcile(path) == record
    assert receipt.stat().st_mtime_ns == before.st_mtime_ns
    (path / "service.log").write_bytes(log + b"later output\n")
    with pytest.raises(ValueError):
        iq_service.reconcile(path)


@pytest.mark.parametrize("live", ["manager", "cgroup"])
def test_recovery_waits_for_the_process_and_entire_cgroup(attempt, live):
    path, state = attempt
    if live == "manager":
        state.update(ActiveState="deactivating", MainPID="42")
    else:
        group = iq_service.CGROUP / iq_service._cgroup(UNIT).lstrip("/")
        group.mkdir(parents=True)
        (group / "cgroup.events").write_text("populated 1\nfrozen 0\n")
    with pytest.raises(iq_service.UnsettledService):
        iq_service.reconcile(path)
    assert not (path / "service.json").exists()


def test_recovery_refuses_a_valid_unit_running_a_different_attempt(attempt):
    path, state = attempt
    state["ExecStart"] = state["ExecStart"].replace(str(path), str(path.parent / "other"))
    with pytest.raises(ValueError):
        iq_service.reconcile(path)
    assert not (path / "service.json").exists()


def test_collected_service_uses_its_journal_invocation_and_terminal_log(attempt, monkeypatch):
    path, state = attempt
    command = state["ExecStart"].split("argv[]=", 1)[1].split(" ; ", 1)[0]
    state.update(LoadState="not-found", ActiveState="inactive", SubState="dead", Result="success")
    (path / "service.log").write_text(
        f"Running as unit: {UNIT}; invocation ID: {INVOCATION}\nFinished with result: success\n"
    )
    journal = [
        dict(
            MESSAGE_ID=iq_service.JOURNAL_STARTED,
            JOB_TYPE="start",
            JOB_RESULT="done",
            MESSAGE=f"Started {UNIT} - [systemd-run] {command}.",
            __MONOTONIC_TIMESTAMP="10000000",
        ),
        dict(
            MESSAGE_ID=iq_service.JOURNAL_ACCOUNTED,
            __MONOTONIC_TIMESTAMP="95000000",
            CPU_USAGE_NSEC="42000000000",
            MEMORY_PEAK="123",
            MEMORY_SWAP_PEAK="0",
        ),
    ]
    for row in journal:
        row.update(_PID="17", USER_INVOCATION_ID=INVOCATION)
    monkeypatch.setattr(iq_service, "_journal", lambda *args: journal)
    journal[-1]["USER_INVOCATION_ID"] = "d" * 32
    with pytest.raises(iq_service.UnsettledService):
        iq_service.reconcile(path)
    assert not (path / "service.json").exists()
    journal[-1]["USER_INVOCATION_ID"] = INVOCATION
    record = iq_service.reconcile(path)
    assert record["systemd"]["Result"] == "success"
    assert record["systemd"]["CPUUsageNSec"] == "42000000000"
    assert record["systemd"]["MemoryPeak"] == "123"
    assert record["monotonic"]["source"] == "systemd-journal"
    assert record["service_wall_s"] == 85 and record["service_active_s"] is None


def test_launch_retains_single_claim_after_supervisor_wait_timeout(attempt, monkeypatch):
    path, state = attempt
    (path / "service.log").unlink()
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        f"--unit={UNIT}",
        "--property=RuntimeMaxSec=360s",
        f"--property=MemoryMax={iq_service.MEMORY}",
        "--property=MemorySwapMax=0",
        "--property=KillMode=control-group",
        f"--setenv=TMPDIR={path}",
        "taskset",
        "-c",
        "4,5",
        "/usr/bin/python",
        "-B",
        "-m",
        iq_service.MODULE,
        "worker",
        str(path),
    ]
    launches = []

    def lose_wait(args, *, stdout, stderr, timeout):
        launches.append(args)
        stdout.write(f"Running as unit: {UNIT}; invocation ID: {INVOCATION}\n".encode())
        stdout.flush()
        with pytest.raises(iq_service.UnsettledService, match="active writer"):
            iq_service.reconcile(path)
        raise subprocess.TimeoutExpired(args, timeout)

    monkeypatch.setattr(iq_service.subprocess, "run", lose_wait)
    monkeypatch.setattr(iq_service, "sleep", lambda seconds: None)
    monkeypatch.setattr(iq_service, "monotonic_ns", lambda: 1_000_000_000)
    state.update(ActiveState="deactivating", MainPID="42")
    with pytest.raises(iq_service.UnsettledService):
        iq_service.run(path, command, UNIT, 378)
    assert json.loads((path / "service-launch.json").read_bytes())["unit"] == UNIT
    assert not (path / "service.json").exists()
    with pytest.raises(iq_service.UnsettledService):
        iq_service.run(path, command, UNIT, 378)
    assert launches == [command]
    state.update(ActiveState="failed", MainPID="0")
    receipt = iq_service.reconcile(path)
    assert receipt["exit_code"] is None and receipt["reason"] == "supervisor wait timed out"
    assert receipt["systemd"]["Result"] == "timeout"


@pytest.mark.parametrize("command", ["systemctl", "journalctl"])
@pytest.mark.parametrize(
    "error", [OSError("manager bus unavailable"), subprocess.TimeoutExpired("lookup", 6)]
)
def test_observation_failure_is_unsettled_and_leaves_no_terminal_receipt(
    attempt, monkeypatch, command, error
):
    path, state = attempt
    if command == "systemctl":
        monkeypatch.setattr(iq_service, "_show", SYSTEMCTL_QUERY)
    else:
        state.update(LoadState="not-found", ActiveState="inactive", SubState="dead")

    def unavailable(args, **kwargs):
        assert args[0] == command
        raise error

    monkeypatch.setattr(iq_service.subprocess, "run", unavailable)
    with pytest.raises(iq_service.UnsettledService):
        iq_service.reconcile(path)
    assert not (path / "service.json").exists()
