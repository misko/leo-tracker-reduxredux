"""Run the frozen short callback comparison with only detached RAM data mounted."""

import argparse
from collections import Counter, deque
import ctypes as ct
import errno
import fcntl
import json
import os
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
import socket
import subprocess
import sys
from time import monotonic, process_time_ns, sleep

from . import sparse8_lag_prefix_measure as trial
from . import sparse8_native_profile as sparse


HERE = Path(__file__).resolve().parent
FILES = (Path(__file__).name, "sparse8_lag_prefix_measure.py", "sparse8_native_profile.py")
RUNTIME = Path("/opt/leo-fast-auto/20261010-r1/python")
LOCK = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
WATCH_S = 180
CHILD_S = 12
PHYSICAL_END_MARGIN_S = 15
LIB = Path("/usr/lib/x86_64-linux-gnu")
UTILS = tuple(Path("/usr/bin") / name for name in ("findmnt", "fincore"))


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def network_off():
    # Same syscall restrictions as the verified held_shrink_0019 capsule.
    libc = ct.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0):
        raise OSError("Could not set no_new_privs")
    lib = ct.CDLL("libseccomp.so.2")
    lib.seccomp_init.argtypes, lib.seccomp_init.restype = (ct.c_uint,), ct.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = (ct.c_char_p,)
    lib.seccomp_rule_add.argtypes = (ct.c_void_p, ct.c_uint, ct.c_int, ct.c_uint)
    lib.seccomp_load.argtypes = lib.seccomp_release.argtypes = (ct.c_void_p,)
    state = lib.seccomp_init(0x7FFF0000)
    if not state:
        raise OSError("Could not initialize the syscall filter")
    try:
        for name in (b"socket", b"socketpair", b"io_uring_setup"):
            syscall = lib.seccomp_syscall_resolve_name(name)
            if syscall < 0 or lib.seccomp_rule_add(state, 0x00050000 | errno.EPERM, syscall, 0):
                raise OSError(f"Could not deny syscall {name!r}")
        if lib.seccomp_load(state):
            raise OSError("Could not install the syscall filter")
    finally:
        lib.seccomp_release(state)


def proof(files):
    mounts = {line.split()[4]: (line.split(" - ", 1)[1].split()[0], line.split()[5].split(","))
              for line in Path("/proc/self/mountinfo").read_text().splitlines()}
    if (any(key.startswith(("/srv", "/mnt/qnap01")) or kind in {"xfs", "nfs", "nfs4", "cifs"}
            for key, (kind, _) in mounts.items()) or mounts["/out"][0] != "tmpfs"
            or "ro" not in mounts["/tmp"][1]
            or any(mounts[str(path)][0] != "tmpfs" or "ro" not in mounts[str(path)][1] for path in files)):
        raise ValueError("External storage or a writable input escaped the RAM capsule")
    denied = {}
    for path in ("/srv/bulk", "/mnt/qnap01", "/srv/postgres-nvme", "/proc/1/root/srv/bulk",
                 "/tmp/leo-v3-ds30-0049-complete-idle01", "/out/backing-alias"):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
        except OSError as error:
            if error.errno not in (errno.ENOENT, errno.EACCES, errno.EPERM):
                raise
            denied[path] = error.errno
        else:
            os.close(fd)
            raise ValueError(f"The kernel exposed unenrolled path {path}")
    for family in (socket.AF_INET, socket.AF_INET6, socket.AF_UNIX):
        try:
            connection = socket.socket(family)
        except PermissionError as error:
            if error.errno != errno.EPERM:
                raise
        else:
            connection.close()
            raise ValueError("Kernel network isolation failed")
    return dict(denied=denied, socket_denied=True, inputs_read_only=True,
                mount_namespace=os.readlink("/proc/self/ns/mnt"), network_namespace=os.readlink("/proc/self/ns/net"))


def paths(build, pin):
    arms, bodies, libraries, assets = trial.book(build, pin)
    data = [build / "build.json", *bodies.values(), *libraries.values(), *assets.values(),
            *(file.parent / "visits.json" for file in bodies.values())]
    return arms, bodies, libraries, assets, data


def inside(mode, build, pin):
    network_off()
    arms, bodies, libraries, assets, data = paths(build, pin)
    isolation = proof(data)
    before = trial.runtime_footprint(bodies, libraries, assets)
    for name, library in libraries.items():
        sparse.checked(library, arms[name]["sha256"]["library"])
    for edge, asset in assets.items():
        sparse.checked(asset, sparse.PILOTS[edge])
    if mode == "probe":
        return dict(isolation=isolation, residency=before, numerical_calls=0, waveform_payload_opens=0)
    if (os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) < 15
            or not os.path.samestat(os.fstat(0), LOCK.stat()) or not all(os.environ[x] == "1" for x in sparse.THREADS)):
        raise ValueError("Comparison must inherit the pinned Gauss CPU slot and original exclusive lease descriptor")
    original, start, cpu = getrusage(RUSAGE_SELF), monotonic(), process_time_ns()
    result = trial.measure(arms, libraries, assets, start)
    final = getrusage(RUSAGE_SELF)
    return dict(**result, isolation=isolation, before=before, after=trial.runtime_footprint(bodies, libraries, assets),
                measured_cpu_ns=process_time_ns()-cpu, measured_input_blocks=final.ru_inblock-original.ru_inblock,
                major_faults=final.ru_majflt-original.ru_majflt, build_sha256=pin)


def command(root, mode, build, pin):
    _, _, _, _, data = paths(build, pin)
    cli = ["/usr/bin/bwrap", "--unshare-all", "--unshare-user", "--disable-userns", "--die-with-parent",
           "--cap-drop", "ALL", "--clearenv", "--proc", "/proc", "--dev", "/dev",
           "--bind", str(root / "tmp-root"), "/tmp", "--bind", str(root / "output"), "/out",
           "--ro-bind", str(root / "src"), "/trial-src", "--symlink", "usr/lib", "/lib",
           "--symlink", "usr/lib64", "/lib64", "--ro-bind", "/usr/lib", "/usr/lib",
           "--ro-bind", "/usr/lib64", "/usr/lib64"]
    for value in (*data, LOCK, sparse.RELEASE, RUNTIME, *UTILS):
        cli.extend(("--ro-bind", str(value), str(value)))
    for key, value in (dict.fromkeys(sparse.THREADS, "1") | dict(PATH="/usr/bin", LANG="C.UTF-8",
                            PYTHONPATH=f"/trial-src:{sparse.RELEASE / 'src'}", TMPDIR="/out")).items():
        cli.extend(("--setenv", key, value))
    cli.extend(("--remount-ro", "/tmp", "--remount-ro", "/", "--chdir", "/out", "--",
                str(sparse.RELEASE / "venv/bin/python"), "-B", "-m", "reports.ALGO08.v3.sparse8_lag_prefix_ram",
                mode, "/out", str(build), pin))
    return cli


def prepare(root, build, pin):
    root.mkdir(mode=0o700)
    for name in ("tmp-root", "output"):
        (root / name).mkdir()
    (root / "output/backing-alias").symlink_to("/srv/bulk")
    code = root / "src/reports/ALGO08/v3"
    code.mkdir(parents=True)
    source_pins = {}
    for name in FILES:
        payload = (HERE / name).read_bytes()
        target = code / name
        target.write_bytes(payload)
        target.chmod(0o444)
        source_pins[name] = sparse.digest(payload)
    runtime = [*UTILS, (sparse.RELEASE / "venv/bin/python").resolve(),
               *(LIB / name for name in ("libfftw3f.so.3", "libm.so.6", "libc.so.6", "libseccomp.so.2"))]
    runtime_pins = {str(path.resolve()): sparse.digest(path.read_bytes()) for path in runtime}
    capture = subprocess.run(command(root, "probe", build, pin), capture_output=True, text=True, timeout=8)
    if capture.returncode:
        raise ValueError(capture.stderr)
    isolated = json.loads(capture.stdout)
    if any(isolated["isolation"][name + "_namespace"] == os.readlink(f"/proc/self/ns/{k}")
           for name, k in (("mount", "mnt"), ("network", "net"))):
        raise ValueError("The preflight unexpectedly shares the caller namespaces")
    write(root / "proof.json", dict(**isolated, source_sha256=source_pins, runtime_sha256=runtime_pins,
                                    build_sha256=pin))


def watch_slot(root, build, pin, proof_sha):
    from . import empty_lane_directed_replay as field
    from . import empty_lane_directed_watch as gates
    from ds30_paired_evaluation import storage_sample

    probe = json.loads(sparse.checked(root / "proof.json", proof_sha))
    runtime = probe["runtime_sha256"]
    sources = probe["source_sha256"]
    if (probe["build_sha256"] != pin or not probe["isolation"]["socket_denied"] or set(sources) != set(FILES)
            or os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) < 15):
        raise ValueError("The watcher needs the proven runtime and low-priority CPU2 affinity")
    for path, expected in runtime.items():
        sparse.checked(Path(path), expected)
    for name, expected in sources.items():
        sparse.checked(root / "src/reports/ALGO08/v3" / name, expected)
    launch = command(root, "worker", build, pin)
    counts, last, samples = Counter(), {}, deque(maxlen=4)
    deadline = monotonic() + WATCH_S
    while monotonic() < deadline:
        event, fresh = field.prefix.occupied()
        state = storage_sample()
        storage = {"/srv/postgres-nvme": state["/srv/postgres-nvme"]}
        rolling = next((result for old in reversed(samples) if (result := gates.rolling_window(old, storage))), None)
        samples.append(storage)
        remaining = gates.FIELD_SLEEP_S - event["age_s"]
        busy = fresh and gates.lock_present(LOCK, Path("/proc/locks").read_text())
        reason = gates.eligible(event, fresh, storage, busy, rolling)
        if reason is None and remaining - CHILD_S < PHYSICAL_END_MARGIN_S:
            reason = "insufficient-field-sleep-margin"
        record = dict(event=event, storage=state, rolling_visible_storage=rolling,
                      field_sleep_remaining_s=remaining, passive_lease_busy=busy)
        if reason is None:
            with LOCK.open("r") as lease:
                try:
                    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    reason = "lease-won-by-other"
                else:
                    newest, still_fresh = field.prefix.occupied()
                    if (monotonic() >= deadline or not still_fresh or newest["sha256"] != event["sha256"]
                            or gates.FIELD_SLEEP_S - newest["age_s"] - CHILD_S < PHYSICAL_END_MARGIN_S):
                        reason = "field-wake-margin-recheck"
                    else:
                        child = subprocess.run(["/usr/bin/time", "-f", "elapsed=%e user=%U system=%S rss_kib=%M input_blocks=%I exit=%x",
                                                "-o", str(root / "process.txt"), "/usr/bin/timeout", "--kill-after=.1", "11.8s", *launch],
                                               stdin=lease, capture_output=True, text=True)
                        write(root / "watch.json", dict(launched=True, exit=child.returncode, **record,
                                                        final_deferral_event=newest, polls=dict(counts), stderr=child.stderr,
                                                        proof_sha256=proof_sha))
                        if child.returncode == 0 and child.stdout:
                            write(root / "native.json", json.loads(child.stdout))
                        return child.returncode
        counts[reason] += 1
        last[reason] = record
        sleep(max(0., min(1., deadline - monotonic())))
    write(root / "watch.json", dict(launched=False, polls=dict(counts), last_refusals=last, proof_sha256=proof_sha))
    return 75


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("prepare", "watch", "probe", "worker"))
    p.add_argument("root", type=Path)
    p.add_argument("build", type=Path)
    p.add_argument("build_sha256")
    p.add_argument("--proof-sha256")
    args = p.parse_args()
    if args.mode == "prepare":
        prepare(args.root, args.build, args.build_sha256)
    elif args.mode == "watch":
        sys.exit(watch_slot(args.root, args.build, args.build_sha256, args.proof_sha256))
    else:
        print(json.dumps(inside(args.mode, args.build, args.build_sha256), allow_nan=False), flush=True)
