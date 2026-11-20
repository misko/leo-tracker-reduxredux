"""Persist and reconcile terminal receipts for bounded whole-IQ services.

Run ``python -m tools.pipeline_eval.iq_service recover ATTEMPT`` after a lost
supervisor. A retained systemd result supplies the active and inactive clocks.
A collected unit needs matching journal events and terminal result evidence.
An active PID, occupied cgroup, or missing evidence leaves the attempt open.
Recovered receipts preserve null for clocks and exit codes the supervisor never wrote.
"""

import argparse
import fcntl
import json
import os
import re
import shlex
import stat
import subprocess
from hashlib import file_digest
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import monotonic, monotonic_ns, sleep

from .__main__ import local_output

UNIT = r"leo-iq-bench-[0-9a-f]{12}\.service"
ANNOUNCEMENT = re.compile(rf"Running as unit: ({UNIT})(?:; invocation ID: ([0-9a-f]{{32}}))?\n?")
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
CGROUP = Path("/sys/fs/cgroup")
MODULE = "tools.pipeline_eval.whole_iq"
MEMORY = 512 * 1024**2
PROPERTIES = (
    "Id",
    "LoadState",
    "ActiveState",
    "SubState",
    "Transient",
    "InvocationID",
    "ControlGroup",
    "MainPID",
    "ControlPID",
    "ExecMainPID",
    "ExecMainCode",
    "ExecMainStatus",
    "ExecStart",
    "Environment",
    "MemoryMax",
    "MemorySwapMax",
    "RuntimeMaxUSec",
    "KillMode",
    "Result",
    "CPUUsageNSec",
    "MemoryPeak",
    "MemorySwapPeak",
    "ActiveEnterTimestampMonotonic",
    "ActiveExitTimestampMonotonic",
    "InactiveEnterTimestampMonotonic",
    "ExecMainStartTimestampMonotonic",
    "ExecMainExitTimestampMonotonic",
)
JOURNAL_STARTED = "39f53479d3a045ac8e11786248231fbf"
JOURNAL_FAILED = "d9b373ed55a64feb8242e02dbe79a49c"
JOURNAL_STOPPED = "9d1aaa27d60140bd96365438aad20286"
JOURNAL_ACCOUNTED = "ae8f7b866b0347b9af31fe1c80b127c0"
ACCOUNTING = {
    "CPUUsageNSec": "CPU_USAGE_NSEC",
    "MemoryPeak": "MEMORY_PEAK",
    "MemorySwapPeak": "MEMORY_SWAP_PEAK",
}


class UnsettledService(RuntimeError):
    """Terminal state cannot yet be authenticated. The attempt still owns its service."""


def succeeded(service):
    """Accept authenticated success or an explicit zero from a historical supervisor."""
    code = service.get("exit_code")
    result = (service.get("systemd") or {}).get("Result")
    if result is None:
        return code == 0
    return result == "success" and code in (None, 0)


def _sha(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def _read(path):
    return json.loads(path.read_bytes())


def _publish(path, document):
    """Publish complete bytes without overwriting another supervisor's receipt."""
    created = True
    with NamedTemporaryFile(dir=path.parent) as stream:
        stream.write(
            (json.dumps(document, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
        )
        stream.flush()
        os.fsync(stream.fileno())
        try:
            os.link(stream.name, path)
        except FileExistsError:
            created = False
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return created


def _observe(command):
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False, timeout=6)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise UnsettledService(f"could not observe systemd state with {command[0]}") from error


def _show(unit):
    status = _observe(
        ["systemctl", "--user", "show", unit, "--no-pager", "--property=" + ",".join(PROPERTIES)]
    )
    return dict(line.split("=", 1) for line in status.stdout.splitlines() if "=" in line)


def _journal(unit, boot, invocation):
    queries = [f"USER_INVOCATION_ID={invocation}"] if invocation is not None else []
    status = _observe(
        [
            "journalctl",
            "--user",
            "--no-pager",
            "-o",
            "json",
            "-n",
            "32",
            f"USER_UNIT={unit}",
            *queries,
            f"_BOOT_ID={boot}",
            f"_UID={os.getuid()}",
            "_SYSTEMD_USER_UNIT=init.scope",
        ]
    )
    if status.returncode:
        return []
    return [json.loads(line) for line in status.stdout.splitlines()]


def _cgroup(unit):
    uid = os.getuid()
    return f"/user.slice/user-{uid}.slice/user@{uid}.service/app.slice/{unit}"


def _empty_cgroup(path):
    group = CGROUP / path.removeprefix("/")
    if not (CGROUP / "cgroup.controllers").is_file():
        raise UnsettledService("unified cgroup evidence is unavailable")
    try:
        events = dict(line.split() for line in (group / "cgroup.events").read_text().splitlines())
    except FileNotFoundError:
        if group.exists():
            raise UnsettledService("service cgroup exists without a population receipt") from None
        return "removed"
    if events.get("populated") != "0":
        raise UnsettledService("service cgroup is still populated")
    return "empty"


def _integer(value):
    return int(value) if value and value.isdecimal() else None


def _command_matches(command, attempt, plan):
    cpus = ",".join(map(str, plan["cpus"]))
    return command.startswith(f"/usr/bin/taskset -c {cpus} ") and command.endswith(
        f" -B -m {MODULE} worker {attempt}"
    )


def _journal_terminal(state, log, unit, boot, invocation, attempt, plan):
    rows = _journal(unit, boot, invocation)
    seen = {}
    for row in rows:
        message_id = row.get("MESSAGE_ID")
        if message_id in {JOURNAL_STARTED, JOURNAL_FAILED, JOURNAL_STOPPED, JOURNAL_ACCOUNTED}:
            if message_id in seen:
                raise UnsettledService("journal contains multiple matching service lifecycles")
            seen[message_id] = row
    start = seen.get(JOURNAL_STARTED, {})
    prefix = f"Started {unit} - [systemd-run] "
    command = start.get("MESSAGE", "")
    if not (
        start.get("JOB_TYPE") == "start"
        and start.get("JOB_RESULT") == "done"
        and command.startswith(prefix)
        and _command_matches(command.removeprefix(prefix).removesuffix("."), attempt, plan)
    ):
        raise UnsettledService("journal cannot bind the original unit start to this attempt")
    invocation_id = start.get("USER_INVOCATION_ID", "")
    if (
        re.fullmatch(r"[0-9a-f]{32}", invocation_id) is None
        or _integer(start.get("_PID")) is None
        or (invocation is not None and invocation != invocation_id)
        or any(
            row.get("USER_INVOCATION_ID") != invocation_id or row.get("_PID") != start.get("_PID")
            for row in seen.values()
        )
    ):
        raise UnsettledService("journal terminal evidence uses a different unit invocation")
    failure, stopped, accounting = (
        seen.get(message, {}) for message in (JOURNAL_FAILED, JOURNAL_STOPPED, JOURNAL_ACCOUNTED)
    )
    terminal = accounting or stopped or failure
    result = failure.get("UNIT_RESULT")
    if result is None:
        # Collected successful units leave a resource event and the attached runner's result.
        log.seek(0)
        successes = sum(line.strip() == b"Finished with result: success" for line in log)
        if successes == 1 and terminal:
            result = "success"
    before = _integer(start.get("__MONOTONIC_TIMESTAMP"))
    after = _integer(terminal.get("__MONOTONIC_TIMESTAMP"))
    accounting_values = {name: accounting.get(field) for name, field in ACCOUNTING.items()}
    evidence = dict(
        source="systemd-journal",
        start_event_usec=before,
        terminal_event_usec=after,
        start_cursor=start.get("__CURSOR"),
        terminal_cursor=terminal.get("__CURSOR"),
        terminal_message_id=terminal.get("MESSAGE_ID"),
    )
    terminal_state = {
        key: state[key]
        for key in (
            "Id",
            "LoadState",
            "ActiveState",
            "SubState",
            "MainPID",
            "ControlPID",
            "ControlGroup",
        )
        if key in state
    }
    return (
        dict(terminal_state, **accounting_values, Result=result),
        invocation_id,
        evidence,
        before,
        after,
    )


def _existing(path, attempt, plan_sha, log_sha):
    receipt = _read(path)
    binding = receipt.get("binding", {})
    unit = receipt.get("unit", "") + ".service"
    state = receipt.get("systemd", {})
    if (
        re.fullmatch(UNIT, unit) is None
        or binding.get("attempt") != str(attempt)
        or binding.get("plan_sha256") != plan_sha
        or binding.get("cgroup") != _cgroup(unit)
        or binding.get("cgroup_state") not in {"empty", "removed"}
        or receipt.get("log_sha256") != log_sha
        or state.get("Id") != unit
        or any(state.get(key) != "0" for key in ("MainPID", "ControlPID"))
        or not state.get("Result")
    ):
        raise ValueError("existing terminal receipt uses different attempt or source bytes")
    return receipt


def reconcile(attempt):
    """Recover terminal metrics in place. Never start, stop or rerun a service."""
    attempt = local_output(attempt)
    fd = os.open(attempt / "service.log", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as log:
        if not stat.S_ISREG(os.fstat(log.fileno()).st_mode):
            raise ValueError("service log must be a regular attempt file")
        try:
            fcntl.flock(log, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise UnsettledService("the service log still has an active writer") from error
        try:
            return _reconcile(attempt, log)
        except OSError as error:
            raise UnsettledService("service evidence could not yet be read or persisted") from error


def _reconcile(attempt, log):
    plan_path = attempt / "plan.json"
    receipt_path, launch_path = attempt / "service.json", attempt / "service-launch.json"
    plan, plan_sha = _read(plan_path), _sha(plan_path)
    log_sha = file_digest(log, "sha256").hexdigest()
    if receipt_path.exists():
        return _existing(receipt_path, attempt, plan_sha, log_sha)
    log.seek(0)
    announcement = ANNOUNCEMENT.fullmatch(log.readline().decode("utf-8", errors="replace"))
    if announcement is None:
        raise UnsettledService("service log has no authenticated systemd-run announcement")
    unit, invocation = announcement.groups()
    current_boot = BOOT_ID.read_text().strip().replace("-", "")
    group = _cgroup(unit)
    launch = _read(launch_path) if launch_path.exists() else None
    if launch is not None:
        file = os.fstat(log.fileno())
        if (
            launch["unit"] != unit
            or launch["attempt"] != str(attempt)
            or launch["plan_sha256"] != plan_sha
            or launch["log_inode"] != [file.st_dev, file.st_ino]
        ):
            raise ValueError("service log or plan differs from the recorded launch handle")
    boot = launch["boot_id"] if launch is not None else current_boot
    worker_path = attempt / "start.json"
    worker = _read(worker_path) if worker_path.exists() else None
    if worker is None and launch is None:
        raise UnsettledService("legacy service log is missing its initial cgroup receipt")
    if worker is not None and (
        worker["cgroup"] != group
        or worker["cpus"] != plan["cpus"]
        or worker["memory.max"] != MEMORY
        or worker["memory.swap.max"] != 0
    ):
        raise ValueError("worker cgroup or resources differ from the observed service")
    state = _show(unit)
    if state.get("Id") != unit or state.get("LoadState") not in {"loaded", "not-found"}:
        raise UnsettledService("the original unit is unavailable from the active systemd manager")
    if state.get("ActiveState") not in {"failed", "inactive"} or any(
        state.get(key) != "0" for key in ("MainPID", "ControlPID")
    ):
        raise UnsettledService("systemd service still has work or a live process")
    if state.get("ControlGroup") not in {"", group}:
        raise ValueError("manager reports a different service cgroup")
    active_exit = None
    if state["LoadState"] == "loaded":
        if state.get("Transient") != "yes" or boot != current_boot:
            raise ValueError(
                "systemd does not identify the transient service from the original boot"
            )
        command = (
            state.get("ExecStart", "").partition("argv[]=")[2].partition(" ; ignore_errors=")[0]
        )
        if not _command_matches(command, attempt, plan) or (
            (invocation is not None and invocation != state["InvocationID"])
            or (worker is not None and str(worker["pid"]) != state["ExecMainPID"])
            or f"TMPDIR={attempt}" not in shlex.split(state["Environment"])
            or state["MemoryMax"] != str(MEMORY)
            or state["MemorySwapMax"] != "0"
            or state["KillMode"] != "control-group"
        ):
            raise ValueError("manager process, invocation, command or limits differ from attempt")
        invocation = state["InvocationID"]
        started = _integer(state["ActiveEnterTimestampMonotonic"])
        active_exit = _integer(state["ActiveExitTimestampMonotonic"])
        stopped = _integer(state["InactiveEnterTimestampMonotonic"])
        evidence = dict(
            source="systemd-manager",
            active_enter_usec=started,
            active_exit_usec=active_exit,
            inactive_enter_usec=stopped,
        )
    else:
        state, invocation, evidence, started, stopped = _journal_terminal(
            state, log, unit, boot, invocation, attempt, plan
        )
    if not started or not stopped or stopped < started or not state.get("Result"):
        raise UnsettledService("systemd lacks terminal monotonic timestamps or result")
    if launch is not None and started < launch["reserved_monotonic_usec"]:
        raise ValueError("systemd started before the attempt reserved its unit")
    if worker is not None and not started <= worker["monotonic_s"] * 1e6 <= stopped:
        raise ValueError("worker monotonic timestamp lies outside the service interval")
    population = _empty_cgroup(group)
    log.seek(0)
    if (
        not os.path.samestat(os.fstat(log.fileno()), (attempt / "service.log").lstat())
        or file_digest(log, "sha256").hexdigest() != log_sha
        or _sha(plan_path) != plan_sha
    ):
        raise UnsettledService("service log or attempt plan changed while collecting receipts")
    code_path = attempt / "service-supervisor.json"
    supervisor = _read(code_path) if code_path.exists() else {}
    if supervisor and (
        launch is None
        or supervisor.get("unit") != unit
        or supervisor.get("boot_id") != boot
        or supervisor.get("plan_sha256") != plan_sha
    ):
        raise ValueError("supervisor receipt does not match the launch handle")
    record = dict(
        unit=unit.removesuffix(".service"),
        binding=dict(
            attempt=str(attempt),
            plan_sha256=plan_sha,
            boot_id=boot,
            invocation_id=invocation,
            cgroup=group,
            cgroup_state=population,
        ),
        log_sha256=log_sha,
        exit_code=supervisor.get("exit_code"),
        reason=supervisor.get("reason"),
        supervisor_s=supervisor.get("supervisor_s"),
        service_wall_s=(stopped - started) / 1e6,
        service_active_s=(active_exit - started) / 1e6
        if active_exit and active_exit >= started
        else None,
        monotonic=evidence,
        systemd=state,
    )
    if _publish(receipt_path, record):
        return record
    return _existing(receipt_path, attempt, plan_sha, log_sha)


def run(attempt, command, unit, timeout):
    """Start a new unit once and reconcile its receipt after the bounded wait."""
    attempt = local_output(attempt)
    unit = unit if unit.endswith(".service") else unit + ".service"
    plan_path = attempt / "plan.json"
    plan, plan_sha = _read(plan_path), _sha(plan_path)
    worker = command[-9:]
    unit_options = [arg for arg in command if arg.startswith("--unit=")]
    if (
        re.fullmatch(UNIT, unit) is None
        or not command
        or command[0] != "systemd-run"
        or unit_options not in ([f"--unit={unit}"], [f"--unit={unit.removesuffix('.service')}"])
        or not {
            "--user",
            "--wait",
            "--pipe",
            f"--property=RuntimeMaxSec={plan['limit_s']}s",
            f"--property=MemoryMax={MEMORY}",
            "--property=MemorySwapMax=0",
            "--property=KillMode=control-group",
            f"--setenv=TMPDIR={attempt}",
        }
        <= set(command)
        or not 1 <= plan["limit_s"] <= 600
        or not plan["limit_s"] <= timeout <= plan["limit_s"] + 30
        or len(worker) != 9
        or worker[:3] != ["taskset", "-c", ",".join(map(str, plan["cpus"]))]
        or command[-5:] != ["-B", "-m", MODULE, "worker", str(attempt)]
    ):
        raise ValueError("benchmark launch does not match its planned unit, command or limits")
    launch_path = attempt / "service-launch.json"
    if launch_path.exists() or (attempt / "service.json").exists():
        raise UnsettledService("an existing unit owns this attempt")
    try:
        log = (attempt / "service.log").open("xb")
    except FileExistsError as error:
        raise UnsettledService("an existing service log owns this attempt") from error
    with log:
        fcntl.flock(log, fcntl.LOCK_EX | fcntl.LOCK_NB)
        inode = os.fstat(log.fileno())
        boot_id = BOOT_ID.read_text().strip().replace("-", "")
        binding = dict(
            unit=unit,
            boot_id=boot_id,
            attempt=str(attempt),
            plan_sha256=plan_sha,
            log_inode=[inode.st_dev, inode.st_ino],
            command=list(command),
            reserved_monotonic_usec=monotonic_ns() // 1000,
        )
        if not _publish(launch_path, binding):
            raise UnsettledService("another supervisor already owns this attempt")
        before = monotonic()
        reason = None
        try:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
            code = result.returncode
        except subprocess.TimeoutExpired:
            # The unit's RuntimeMaxSec governs the service even if the client loses its wait.
            code, reason = None, "supervisor wait timed out"
        except OSError as error:
            raise UnsettledService(
                "the supervisor could not establish the service outcome"
            ) from error
        elapsed = monotonic() - before
        try:
            os.fsync(log.fileno())
        except OSError as error:
            raise UnsettledService("the terminal service log could not be persisted") from error
    try:
        _publish(
            attempt / "service-supervisor.json",
            dict(
                unit=unit,
                boot_id=boot_id,
                plan_sha256=plan_sha,
                exit_code=code,
                reason=reason,
                supervisor_s=elapsed,
            ),
        )
    except OSError as error:
        raise UnsettledService("the supervisor receipt could not be persisted") from error
    for _ in range(2):
        try:
            return reconcile(attempt)
        except UnsettledService:
            sleep(0.2)
    return reconcile(attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    recover = commands.add_parser("recover", help="seal an existing terminal service")
    recover.add_argument("attempt", type=local_output)
    args = parser.parse_args()
    try:
        receipt = reconcile(args.attempt)
    except (OSError, ValueError, UnsettledService) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
