"""Admit one <=8 s CPU2 feature-only comparison after a fresh official deferral."""

import argparse
import ctypes
import errno
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
import runpy
import select
from shutil import copyfile
import subprocess
import sys
from time import monotonic, time_ns

from .held_cfo_features_trial import CASES, CONFIG, HERE, PLAN, checked_bytes


RELEASE = CONFIG.parents[1]
RUNTIME = (RELEASE/"venv/bin/python").resolve().parents[1]
CAMPAIGN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
LOCK = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
DRIVER = "/tmp/leo-v3-ds30-paired-evaluation/reports/ALGO08/v3/ds30_paired_evaluation.py"
DRIVER_PIN = "26b996e90e7ad4c467c551426a69e048d6078cf3c8087c741f9eef3c10f7df31"
WATCHER = Path("/srv/postgres-nvme/leo-ds30-research-worktrees/field-receiver-solver-cross/reports/ALGO08/v3/field_crossover_admission_watch.py")
WATCHER_PIN = "5a30d1cfcfa675db74f023a28ed0c026746c19784a8efa97ae757426e2ffd023"
THREADS = ("BLIS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "OMP_NUM_THREADS",
           "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS")
FRESH_NS = 2_000_000_000
LIMIT = 8


def write(path, value):
    with path.open("x") as out:
        json.dump(value, out, indent=2, allow_nan=False)
        out.write("\n")


def sock_filter(path):
    """Install the previous study's three syscall denials via bwrap's BPF input."""
    library = ctypes.CDLL("libseccomp.so.2")
    api = {
        "seccomp_init": ([ctypes.c_uint], ctypes.c_void_p),
        "seccomp_syscall_resolve_name": ([ctypes.c_char_p], ctypes.c_int),
        "seccomp_rule_add": ([ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_uint], ctypes.c_int),
        "seccomp_export_bpf": ([ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
        "seccomp_release": ([ctypes.c_void_p], None),
    }
    for name, (arguments, result) in api.items():
        fn = getattr(library, name)
        fn.argtypes, fn.restype = arguments, result
    resource = library.seccomp_init(0x7FFF0000)
    if not resource:
        raise OSError("Unable to configure socket denial")
    try:
        for name in (b"socket", b"socketpair", b"io_uring_setup"):
            syscall = library.seccomp_syscall_resolve_name(name)
            if syscall < 0 or library.seccomp_rule_add(resource, 0x00050000 | errno.EPERM, syscall, 0):
                raise OSError(f"Unable to deny {name}")
        with path.open("xb") as out:
            if library.seccomp_export_bpf(resource, out.fileno()):
                raise OSError("Unable to export the staged syscall filter")
    finally:
        library.seccomp_release(resource)


def operands():
    return [Path(item) for values in CASES.values() for item in values[::2]]


def require_resident(root):
    files = operands()+[root/"program/measurements"/PLAN.name, root/"program/held_cfo_features.py",
                         root/"program/held_cfo_features_trial.py"]
    out = subprocess.check_output(["/usr/bin/fincore", "-bJ", "-o", "RES,SIZE,FILE", *map(str, files)], text=True)
    rows = json.loads(out)["fincore"]
    if len(rows) != len(files) or any(row["res"] < row["size"] for row in rows):
        raise ValueError("Require resident exact native packets and analysis source")
    return sum(r["size"] for r in rows)


def command(root, case, cpu, fd):
    argv = ["/usr/bin/taskset", "-c", str(cpu), "/usr/bin/bwrap", "--unshare-all", "--unshare-user", "--disable-userns",
            "--die-with-parent", "--cap-drop", "ALL", "--clearenv", "--seccomp", str(fd),
            "--proc", "/proc", "--dev", "/dev", "--bind", str(root/"empty"), "/dev/shm"]
    for name in ("bin", "lib", "lib64"):
        argv += ["--symlink", f"usr/{name}", f"/{name}"]
    sources = (Path("/usr"), Path("/etc/ld.so.cache"), RELEASE/"venv", RELEASE/"src", RUNTIME, CONFIG, *operands())
    for source in sources:
        argv += ["--ro-bind", str(source), str(source)]
    argv += ["--ro-bind", str(root/"program"), "/feature_trial", "--remount-ro", "/dev/shm",
             "--remount-ro", "/", "--chdir", "/"]
    environment = dict.fromkeys(THREADS, "1") | {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
        "PYTHONPATH": f"/:{RELEASE}/src"}
    for name, value in environment.items():
        argv += ["--setenv", name, value]
    return argv + ["--", str(RELEASE/"venv/bin/python"), "-Bm", "feature_trial.held_cfo_features_trial", case, "--isolated"]


def child(root, case, cpu, timeout):
    begin, before = monotonic(), getrusage(RUSAGE_CHILDREN)
    with (root/"sockets.bpf").open("rb") as sc:
        proc = subprocess.run(command(root, case, cpu, sc.fileno()), pass_fds=(sc.fileno(),),
                              capture_output=True, text=True, timeout=timeout, check=False)
    after = getrusage(RUSAGE_CHILDREN)
    if proc.returncode:
        raise ValueError(proc.stderr.strip())
    return dict(complete_process_wall_s=monotonic()-begin,
                wrapper_accounted_cpu_s=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                result=json.loads(proc.stdout))


def prepare(root):
    root.mkdir(mode=0o700)
    (root/"empty").mkdir()
    (root/"program/measurements").mkdir(parents=True)
    for source in (HERE/"held_cfo_features.py", HERE/"held_cfo_features_trial.py", PLAN):
        dest = root/"program"/source.relative_to(HERE)
        copyfile(source, dest)
        dest.chmod(0o400)
    sock_filter(root/"sockets.bpf")
    nbytes = require_resident(root)
    check = child(root, "proof", 3, 5)
    evidence = check["result"]
    if (evidence["network_namespace"] == os.readlink("/proc/self/ns/net")
            or evidence["mount_namespace"] == os.readlink("/proc/self/ns/mnt")):
        raise ValueError("The feature worker shares the outer namespace")
    source_pins = {p.name: sha256(p.read_bytes()).hexdigest() for p in (root/"program").glob("*.py")}
    write(root/"preflight.json", dict(resident_bytes=nbytes, complete_graphs=0, sources=source_pins, **check))


def idle(pid):
    directory = Path("/proc")/str(pid)
    command = (directory/"cmdline").read_bytes().split(b"\0")
    if not any(arg == DRIVER.encode() and command[i+1] == b"run" for i, arg in enumerate(command[:-1])):
        raise ValueError("Require the enrolled live field controller")
    if (directory/"task"/str(pid)/"children").read_text().split():
        raise ValueError("The field controller has active children")


def admit(root, pid, event):
    with LOCK.open("rb") as fd:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = CAMPAIGN/event["event"]
        expected = checked_bytes(path, event["event_sha256"][7:])
        if json.loads(expected)["state"] != "deferred_storage_busy":
            raise ValueError("Require the exact official deferral event")
        idle(pid)
        age = time_ns()-event["unix_ns"]
        if not 0 <= age <= FRESH_NS:
            raise ValueError("Official deferral no longer leaves the protected sleep window")
        started = monotonic()
        rows = []
        for case in CASES:
            result = child(root, case, 2, max(0., LIMIT-(monotonic()-started)))
            rows.append(result)
            write(root/f"{case}.json", result)
        write(root/"timing.json", dict(deferral=event, initial_age_ns=age, driver_pid=pid,
                                      exclusive_slot_wall_s=monotonic()-started, required_stop_seconds=LIMIT, results=rows))


def watch(root, pid):
    checked_bytes(Path(DRIVER), DRIVER_PIN)
    checked_bytes(WATCHER, WATCHER_PIN)
    observer = runpy.run_path(str(WATCHER))
    libc = ctypes.CDLL(None, use_errno=True)
    libc.inotify_add_watch.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32)
    descriptor = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    if descriptor < 0:
        raise OSError(ctypes.get_errno(), "inotify_init1")
    try:
        if libc.inotify_add_watch(descriptor, os.fsencode(CAMPAIGN), observer["MOVED_TO"]) < 0:
            raise OSError(ctypes.get_errno(), "inotify_add_watch")
        start, deadline = time_ns(), monotonic()+55
        write(root/"watch-start.json", {"at": start, "duration_s": 55})
        while (left := deadline-monotonic()) > 0:
            ready, _, _ = select.select([descriptor], [], [], left)
            if not ready or not observer["replaced_export"](os.read(descriptor, 65_536)):
                continue
            event = observer["recent_deferral"](CAMPAIGN, start, time_ns())
            if event is None or time_ns()-event["unix_ns"] > FRESH_NS:
                continue
            write(root/"gate.json", event)
            try:
                admit(root, pid, event)
            except (OSError, ValueError, subprocess.TimeoutExpired) as fault:
                write(root/"watch-end.json", {"status": "declined_or_stopped", "reason": str(fault)})
            else:
                write(root/"watch-end.json", {"status": "complete"})
            return
        write(root/"watch-end.json", {"status": "no_fresh_field_deferral"})
    finally:
        os.close(descriptor)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--watch-driver", type=int)
    args = parser.parse_args()
    if args.root.parent != Path("/dev/shm"):
        parser.error("Use one fresh private tmpfs proof root")
    if args.watch_driver is None:
        prepare(args.root)
    else:
        if not (args.root/"preflight.json").is_file() or (args.root/"watch-start.json").exists():
            parser.error("Require one successful clean preflight and no earlier watch")
        preflight = json.loads((args.root/"preflight.json").read_bytes())
        for name, pin in preflight["sources"].items():
            checked_bytes(args.root/"program"/name, pin)
            checked_bytes(HERE/name, pin)
        require_resident(args.root)
        watch(args.root, args.watch_driver)
