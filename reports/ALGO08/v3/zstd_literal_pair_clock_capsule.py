"""Launch one isolated comparator only during an official DS30-0218 deferral."""

import argparse
import errno
import fcntl
import json
import os
from pathlib import Path
import socket
import subprocess
from time import time_ns

from .zstd_literal_pair import HERE, digest
from .zstd_literal_pair_check import CASES, FILES, load_owned, resident
from .zstd_literal_pair_clock import LEASE


RUN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124/cases/DS30-0218")
UNIT = "leo-ds30-paired-evaluation-20261124.service"
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
PYTHON = RELEASE / "venv/bin/python"
THREADS = ("BLIS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "OMP_NUM_THREADS",
           "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS")


def input_paths(case):
    return tuple(CASES[case][0] / name for name in FILES)


def isolation(case):
    selected = {str(path) for path in input_paths(case)}
    data = {}
    for row in Path("/proc/self/mountinfo").read_text().splitlines():
        columns = row.split()
        at = columns[4]
        if at.startswith("/dev/shm/"):
            data[at] = columns[5].split(",")
    if set(data) != selected or any("ro" not in flags for flags in data.values()):
        raise ValueError("The capsule exposed more than the three admitted original fixture files")
    denied = {}
    for path in ("/srv/bulk", "/mnt/qnap01", "/proc/1/root/srv/bulk", "/run", str(RUN)):
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
        except OSError as error:
            if error.errno != errno.ENOENT:
                raise
            denied[path] = error.errno
        else:
            os.close(descriptor)
            raise ValueError(f"Unexpected backing or service path: {path}")
    # An unshared namespace has no routable network or host sockets.
    if len(socket.if_nameindex()) != 1 or socket.if_nameindex()[0][1] != "lo":
        raise ValueError("The capsule shares an external network interface")
    return dict(mount=os.readlink("/proc/self/ns/mnt"), network=os.readlink("/proc/self/ns/net"),
                denied=denied, read_only_wave_paths=sorted(selected), interfaces=["lo"])


def namespace(shm_root, state_root, libraries, case, snippet):
    files = input_paths(case)
    owner = files[0].stat()
    roots = (RELEASE, PYTHON.resolve().parents[1], Path("/usr"), Path("/etc/ld.so.cache"), Path("/etc/fonts"),
             HERE.parents[2] / "reports", HERE.parents[2] / "tools", LEASE, *libraries, *files)
    args = ["/usr/bin/setpriv", "--reuid", str(owner.st_uid), "--regid", str(owner.st_gid), "--clear-groups",
            "/usr/bin/bwrap", "--unshare-all", "--unshare-user", "--disable-userns",
            "--die-with-parent", "--cap-drop", "ALL", "--clearenv",
            "--proc", "/proc", "--dev", "/dev", "--bind", str(shm_root), "/dev/shm",
            "--tmpfs", "/tmp", "--ro-bind", str(state_root), "/output"]
    for name in ("bin", "lib", "lib64"):
        args += ["--symlink", f"usr/{name}", f"/{name}"]
    for entry in roots:
        args += ["--ro-bind", str(entry), str(entry)]
    args += ["--remount-ro", "/dev/shm", "--remount-ro", "/", "--chdir", "/output"]
    environment = dict.fromkeys(THREADS, "1") | dict(PATH="/usr/bin:/bin", LANG="C.UTF-8",
                                                       PYTHONPATH=f"{HERE.parents[2]}:{RELEASE}/src",
                                                       MPLCONFIGDIR="/tmp/mpl", XDG_CACHE_HOME="/tmp/cache",
                                                       HOST_MOUNT=os.readlink("/proc/self/ns/mnt"))
    for name, value in environment.items():
        args += ["--setenv", name, value]
    return [*args, "--", str(PYTHON), "-B", *snippet]


def official_deferral(clock=time_ns):
    events = sorted((RUN / "events").glob("*.json"))
    if not events:
        return None
    leaf = events[-1]
    payload = leaf.read_bytes()
    event = json.loads(payload)
    stamp = int(leaf.name.split("-", 1)[0])
    if (not 0 <= clock()-stamp <= 2_000_000_000 or event["state"] != "deferred_storage_busy"
            or event.get("next_arm", "successor") != "successor"):
        return None
    prior = json.loads((RUN / "installed/attempt-000001/result.json").read_bytes())
    if (prior["outcome"] != "complete" or prior["process"]["exit_code"] != 0 or
            any((RUN / "successor").glob("attempt-*")) or (RUN / "pair.json").exists()):
        return None
    main = subprocess.check_output(("systemctl", "show", "-p", "MainPID", "--value", UNIT), text=True).strip()
    if not main.isdigit() or int(main) <= 1 or Path(f"/proc/{main}/task/{main}/children").read_text().strip():
        return None
    if not 0 <= clock()-stamp <= 2_000_000_000:
        return None
    return dict(event=str(leaf), event_sha256=digest(payload), unix_ns=stamp, driver_pid=int(main), body=event)


def launch(state, ram_mount, library, history, hasher, pin, case, *, preflight=False):
    for path, tmp in ((state, Path("/tmp")), (ram_mount, Path("/dev/shm"))):
        if path.parent != tmp or path.stat().st_dev != tmp.stat().st_dev or path.resolve(strict=True) != path:
            raise ValueError("Use new private tmpfs directories for the sealed output and namespace root")
    if (state / "clock.json").exists():
        raise ValueError("The one funded clock already exists")
    libraries = library, history, hasher
    if preflight:
        command = namespace(ram_mount, state, libraries, case, ["-c",
            "from reports.ALGO08.v3.zstd_literal_pair_clock_capsule import probe; import sys; probe(*sys.argv[1:])",
            *map(str, libraries), pin, case])
        completed = subprocess.run(command, capture_output=True, text=True, timeout=8)
        if completed.returncode:
            raise ValueError(f"The detached mount preflight could not run: {completed.stderr.strip()}")
        proof = json.loads(completed.stdout) | dict(case=case, host_residency=resident(input_paths(case)))
        with (state / "isolation.json").open("x") as stream:
            json.dump(proof, stream, sort_keys=True)
        return
    if (not (state / "isolation.json").is_file() or (state / "launch.json").exists() or
            json.loads((state / "isolation.json").read_bytes())["case"] != case):
        raise ValueError("The matched child requires a fresh passed mount preflight and unused launch")
    if not official_deferral():
        print("No fresh eligible DS30-0218 storage deferral; zero numerical attempts")
        return
    before = resident(input_paths(case))
    fd = os.open(LEASE, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("The shared slot is busy; zero numerical attempts")
            return
        gate = official_deferral()
        if gate is None:
            print("The official deferral expired before launch; zero numerical attempts")
            return
        if not 0 <= time_ns() - gate["unix_ns"] <= 2_000_000_000:
            return
        command = namespace(ram_mount, state, libraries, case,
                            ["-m", "reports.ALGO08.v3.zstd_literal_pair_clock",
                             str(library), pin, str(history), str(hasher), case])
        with (state / "launch.json").open("x") as stream:
            json.dump(gate | dict(started_unix_ns=time_ns(), isolation_sha256=digest((state / "isolation.json").read_bytes())), stream)
        run = subprocess.run(["/usr/bin/taskset", "-c", "2", "/usr/bin/nice", "-n", "15", "/usr/bin/ionice", "-c", "3",
                              "/usr/bin/timeout", "--kill-after=1s", "11s", *command], stdin=fd, capture_output=True,
                             timeout=12)
        ended = time_ns()
    finally:
        os.close(fd)
    (state / "stderr.log").write_bytes(run.stderr)
    if run.returncode:
        raise ValueError(f"The single timed child exited {run.returncode}; see its saved stderr")
    result = json.loads(run.stdout) | dict(host_residency_before=before, host_residency_after=resident(input_paths(case)),
                                          finished_unix_ns=ended, official_admission=gate)
    with (state / "clock.json").open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")


def probe(library, history, hasher, pin, case):
    from .zstd_literal_pair import Decoder

    proof = isolation(case)
    if proof["mount"] == os.environ.get("HOST_MOUNT"):
        raise ValueError("Isolation did not change mount namespace")
    load_owned(Decoder(Path(library), pin), Path(history), Path(hasher))
    paths = input_paths(case)
    for path in paths:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        os.close(fd)
    print(json.dumps(proof | dict(allowlisted_descriptors_opened=len(paths)), sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("state", "ram_mount", "library", "history", "hasher"):
        parser.add_argument(name, type=Path)
    parser.add_argument("pin")
    parser.add_argument("case", choices=CASES)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    launch(args.state, args.ram_mount, args.library, args.history, args.hasher, args.pin, args.case,
           preflight=args.preflight)
