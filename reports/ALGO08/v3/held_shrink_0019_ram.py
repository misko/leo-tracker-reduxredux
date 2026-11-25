"""Run the frozen saved worker in a positive-path mount and network sandbox."""

import argparse
from ctypes import CDLL, c_char_p, c_int, c_uint, c_void_p
import errno
from hashlib import sha256
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from shutil import copyfile
import signal
import socket
import subprocess
import sys
from time import monotonic, sleep, time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import held_shrink_0019 as saved  # noqa: E402
from joint_recovery_0049_admission import QUIET, QUIET_PIN, device_stats  # noqa: E402
from joint_recovery_0049_direct import require_driver_idle  # noqa: E402
from joint_recovery_0049_wait import lease  # noqa: E402


ROOT = Path("/dev/shm/leo-v3-held-shrink-0019-ram01")
OUTPUT = ROOT / "output"
PLAN = "8f70fb297815438ed935f716c271c9551f3fed03177e42df532cd7f97324b664"
READY = "30b9afd3a02cd03f131cb0483e7a5122c633c9a9ab265307546b9ea0fdfa96a7"
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
PAYLOAD = Path("/opt/leo-algo08/algo08v3")
THREADS = ("BLIS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
           "OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS")
TIMEOUT = 24
ARTIFACTS = ("plan.json", "derived-native.json", "admission.json")
PROOF = ROOT/"verified-isolation.json"
MODE_ARGS = ()
EXTRA_FILE_NAMES = ()


def headroom():
    state = os.statvfs(OUTPUT)
    available = state.f_bavail * state.f_frsize
    # The independently verified ordinary and timestamp runs each wrote
    # under 20 MiB. Reserve room for the output and scratch variation.
    if available < 64 * 1024**2:
        raise ValueError("Require at least 64 MiB of tmpfs output headroom")
    return available


def network_off():
    libc = CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0):
        raise OSError("Unable to set no_new_privs")
    sc = CDLL("libseccomp.so.2")
    sc.seccomp_init.argtypes = (c_uint,)
    sc.seccomp_init.restype = c_void_p
    sc.seccomp_syscall_resolve_name.argtypes = (c_char_p,)
    sc.seccomp_rule_add.argtypes = (c_void_p, c_uint, c_int, c_uint)
    sc.seccomp_load.argtypes = (c_void_p,)
    sc.seccomp_release.argtypes = (c_void_p,)
    context = sc.seccomp_init(0x7FFF0000)
    if not context:
        raise OSError("Cannot allocate the network-denial filter")
    try:
        for name in (b"socket", b"socketpair", b"io_uring_setup"):
            syscall = sc.seccomp_syscall_resolve_name(name)
            if syscall < 0 or sc.seccomp_rule_add(context, 0x00050000 | errno.EPERM, syscall, 0):
                raise OSError(f"Cannot deny syscall {name!r}")
        if sc.seccomp_load(context):
            raise OSError("Cannot install network-denial filter")
    finally:
        sc.seccomp_release(context)


def bindings():
    trial = saved.trial
    headroom()
    book = trial.document(trial.BUILD, trial.BUILD_PIN)
    inputs = {Path(entry["path"]) for entry in (*book["native"].values(), book["png"], book["portable_producer"])}
    acceleration = trial.document(Path(book["native"]["--legacy-first-map-fast"]["path"]),
                                  book["native"]["--legacy-first-map-fast"]["sha256"])
    inputs.update(Path(acceleration[name]["path"]) for name in ("hasher", "projection", "template"))
    inputs.update(saved.STAGE/name for name in ("authority.json", "inventory.json", "offer.json", "catalogue.json"))
    rows = trial.document(saved.STAGE/"catalogue.json", saved.CATALOGUE)
    catalogue = saved.STAGE/"tle/archive/space-track"
    inputs.update(catalogue/name for name in rows)
    # The existing archive reader needs only the staged bodies and their exact
    # basename timestamps. All other stage products are deliberately invisible.
    if any(path.resolve(strict=True) != path or not path.is_relative_to(("/dev/shm" if str(path).startswith("/dev/shm/") else "/tmp"))
           for path in inputs):
        raise ValueError("An enrolled detector/orbit operand escaped the staged tmpfs")
    tmpfs = os.statvfs("/dev/shm").f_fsid, os.statvfs("/tmp").f_fsid
    if any(os.statvfs(path).f_fsid not in tmpfs for path in inputs):
        raise ValueError("All scientific data operands must be on the staged RAM filesystems")
    trial.require_resident(sorted(inputs | {OUTPUT/name for name in ARTIFACTS}))
    sources = (HERE.parents[2], trial.CHARTED, trial.BUILD, RELEASE, PAYLOAD,
               (RELEASE/"venv/bin/python").resolve(strict=True).parents[1], trial.LOCK, Path("/usr"),
               Path("/etc/fonts"), Path("/etc/ld.so.cache"), Path("/etc/passwd"), Path("/etc/group"),
               Path("/sys/devices/system/cpu"))
    return tuple(sorted(inputs)), sources


def command(layout, mode):
    inputs, sources = layout
    options = ["/usr/bin/bwrap", "--unshare-all", "--unshare-user", "--disable-userns", "--die-with-parent",
               "--cap-drop", "ALL", "--clearenv", "--proc", "/proc", "--dev", "/dev",
               "--bind", str(ROOT/"shm-root"), "/dev/shm"]
    for name in ("bin", "lib", "lib64"):
        options += ["--symlink", f"usr/{name}", f"/{name}"]
    for path in (*inputs, *sources):
        options += ["--ro-bind", str(path), str(path)]
    options += ["--bind", str(OUTPUT), str(saved.ROOT)]
    for name in (*ARTIFACTS, *EXTRA_FILE_NAMES):
        options += ["--ro-bind", str(OUTPUT/name), str(saved.ROOT/name)]
    options += ["--remount-ro", "/dev/shm", "--remount-ro", "/", "--chdir", str(saved.ROOT)]
    environment = dict.fromkeys(THREADS, "1") | dict(
        PATH="/usr/bin:/bin", LANG="C.UTF-8", TMPDIR=str(saved.ROOT/"scratch"),
        MPLCONFIGDIR=str(saved.ROOT/"scratch"), XDG_CACHE_HOME=str(saved.ROOT/"scratch"))
    for name, value in environment.items():
        options += ["--setenv", name, value]
    options += ["--", str(RELEASE/"venv/bin/python"), "-IB", str(Path(__file__).resolve()), mode, *MODE_ARGS]
    return options


def isolation_probe():
    with Path("/proc/self/mountinfo").open() as stream:
        mounts = {line.split()[4]: (line.split(" - ", 1)[1].split()[0], line.split()[5].split(","))
                  for line in stream}
    if (any(path == "/srv/bulk" or path.startswith(("/srv/bulk/", "/mnt/qnap01")) for path in mounts)
            or any(t in {"xfs", "nfs", "nfs4", "cifs"} for t, _ in mounts.values())
            or mounts[str(saved.ROOT)][0] != "tmpfs"
            or any("ro" not in flags for path, (_, flags) in mounts.items()
                   if path.startswith("/dev/shm") and path != str(saved.ROOT))):
        raise ValueError("An external data mount is visible inside the position capsule")
    denied = {}
    for path in ("/srv/bulk", "/mnt/qnap01", "/proc/1/root/srv/bulk",
                 str(saved.ROOT/"backing-alias"), str(saved.STAGE/"native.json")):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
        except OSError as error:
            if error.errno not in (errno.ENOENT, errno.EACCES, errno.EPERM):
                raise
            denied[path] = error.errno
        else:
            os.close(fd)
            raise ValueError(f"Forbidden backing or unstaged path opened: {path}")
    for family in (socket.AF_INET, socket.AF_INET6, socket.AF_UNIX):
        try:
            conn = socket.socket(family)
        except PermissionError as error:
            if error.errno != errno.EPERM:
                raise
        else:
            conn.close()
            raise ValueError("The isolated worker opened a socket")
    return dict(denied=denied, mount_namespace=os.readlink("/proc/self/ns/mnt"),
                network_namespace=os.readlink("/proc/self/ns/net"), socket_denied=True,
                output_filesystem=mounts[str(saved.ROOT)][0], readonly_tmpfs_inputs=True)


def isolated(mode):
    network_off()
    proof = isolation_probe()
    expected_fd = saved.ROOT/"plan.json" if mode == "sandbox-preflight" else saved.trial.LOCK
    if not os.path.samestat(os.fstat(0), expected_fd.stat()):
        raise ValueError("The read-only descriptor was not inherited through the capsule")
    proof["inherited_readonly_descriptor"] = True
    print(json.dumps(proof, sort_keys=True), flush=True)
    if mode == "sandbox-preflight":
        saved.run_worker(PLAN, smoke=True)
    else:
        # stdin is the already-locked read-only benchmark FD inherited through
        # the namespace wrapper. The real stock worker verifies its inode.
        saved.run_worker(PLAN, fd=0)


def prepare():
    trial = saved.trial
    ready = trial.document(saved.ROOT/"ready.json", READY)
    plan = trial.document(saved.ROOT/"plan.json", PLAN)
    if ready["plan_sha256"] != PLAN or ready["input"] != plan["change"]["derived_native_sha256"]:
        raise ValueError("Source preparation is not the original frozen CFO packet")
    ROOT.mkdir(mode=0o700)
    (ROOT/"shm-root").mkdir()
    OUTPUT.mkdir(mode=0o700)
    (OUTPUT/"scratch").mkdir()
    for name, pin in zip(ARTIFACTS, (PLAN, ready["input"], plan["admission_sha256"]), strict=True):
        data = saved.ROOT/name
        trial.document(data, pin)
        dest = OUTPUT/name
        copyfile(data, dest)
        dest.chmod(0o400)
        trial.document(dest, pin)
    (OUTPUT/"backing-alias").symlink_to("/srv/bulk", target_is_directory=True)


def preflight(*, changed=366, refs=47):
    layout = bindings()
    with (OUTPUT/"plan.json").open("rb") as descriptor:
        output = subprocess.run(command(layout, "sandbox-preflight"), text=True, capture_output=True,
                                timeout=8, check=False, stdin=descriptor)
    if output.returncode:
        raise ValueError(output.stderr)
    proof, smoke = map(json.loads, output.stdout.splitlines())
    if (proof["network_namespace"] == os.readlink("/proc/self/ns/net")
            or proof["mount_namespace"] == os.readlink("/proc/self/ns/mnt")
            or smoke != dict(case=saved.CASE, changed=changed, refs=refs, acquired=0, waveform_reads=0, solver_runs=0)):
        raise ValueError("The protected path must pass the independent same-worker no-solve smoke")
    print(saved.trial.write(PROOF, dict(proof=proof, smoke=smoke, tmpfs_available_bytes=headroom(),
          plan=PLAN, paths=[str(p) for p in layout[0]], readonly_sources=[str(p) for p in layout[1]],
          launcher_sha256=saved.trial.identifier(Path(__file__)), backing_reads=0)))


def nvme_quiet(*, continuous):
    import runpy
    if saved.trial.identifier(QUIET) != QUIET_PIN:
        raise ValueError("The existing non-bulk storage guard changed")
    scope = runpy.run_path(str(QUIET))
    paths = device_stats(Path("/proc/self/mountinfo").read_text().splitlines())
    guard = scope["QuietInterval"]()
    deadline = monotonic()+1.5
    while monotonic() < deadline:
        sample = scope["sample"](paths["/srv/postgres-nvme"], monotonic)
        ready = guard.observe(sample)
        if guard.since is None:
            raise ValueError("Read-only source filesystem is not quiet")
        if ready or not continuous:
            return dict(in_flight=sample.in_flight, full_avg10=sample.full_avg10,
                        queue_mean=guard.queue_mean, interval_full_pct=guard.current_full)
        sleep(scope["POLL_S"])
    raise ValueError("No quiet interval on the read-only source filesystem")


def paid(layout, fd, gate, machine):
    trial = saved.trial
    args = command(layout, "sandbox-worker")
    intent = trial.write(ROOT/"child-intent.json", dict(admission=gate, max_child_s=TIMEOUT, plan=PLAN))
    with (ROOT/"child.stdout").open("x") as stdout, (ROOT/"child.stderr").open("x") as stderr:
        original, start = getrusage(RUSAGE_CHILDREN), monotonic()
        with subprocess.Popen(args, stdout=stdout, stderr=stderr, stdin=fd, start_new_session=True) as child:
            try:
                status = child.wait(max(0, TIMEOUT-(monotonic()-start)))
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                status = 124
        after, end = getrusage(RUSAGE_CHILDREN), monotonic()
    elapsed = trial.write(OUTPUT/"clock.json", dict(elapsed_s=end-start, exit_code=status,
                         cpu_s=(after.ru_utime+after.ru_stime)-(original.ru_utime+original.ru_stime),
                         input_blocks=after.ru_inblock-original.ru_inblock, max_rss_kib=after.ru_maxrss,
                         clock_scope="namespace launch through ordinary saved worker exit",
                         intent_sha256=intent))
    print(trial.write(OUTPUT/"prediction-seal.json", dict(plan_sha256=PLAN, clock=elapsed, machine=machine,
          receipt=trial.identifier(OUTPUT/"receipt.json") if status == 0 else None,
          protocol=trial.protocol(saved.EXPERIMENT), waveform_reads=0, survey_reads=0)))
    return status


def watch(pid, pin):
    trial = saved.trial
    proof = trial.document(PROOF, pin)
    layout = bindings()
    if (proof["launcher_sha256"] != trial.identifier(Path(__file__)) or proof["plan"] != PLAN
            or proof["paths"] != list(map(str, layout[0])) or proof["readonly_sources"] != list(map(str, layout[1]))):
        raise ValueError("The exact isolated worker and its allowlist must pass preflight unchanged")
    machine = trial.attrs(expected_priority="idle")
    runtime = saved.ready_runtime()
    import second_curve_gate_trial as gate

    if trial.identifier(Path(gate.__file__)) != runtime.PRIOR_WATCH:
        raise ValueError("The official deferral observer changed")

    def admit(case, root, proof_path, proof_pin, event):
        if case != saved.CASE or root != ROOT/"watch" or proof_path != PROOF or proof_pin != pin:
            raise ValueError("Wrong fixed saved opportunity")
        gate.event_admits(event)
        require_driver_idle(pid)
        quiet = nvme_quiet(continuous=True)
        with lease() as fd:
            actual = bindings()
            quiet_on_lease = nvme_quiet(continuous=False)
            require_driver_idle(pid)
            gate.event_admits(event)
            return paid(actual, fd, dict(event=event, driver_pid=pid, quiet=quiet,
                        quiet_on_lease=quiet_on_lease, tmpfs_available_bytes=headroom(),
                        admitted_unix_ns=time_ns()), machine)

    with (patch.object(gate, "WINDOW_S", 180), patch.object(gate, "launch", admit)):
        return gate.watch(saved.CASE, ROOT/"watch", PROOF, pin)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "preflight", "watch", "sandbox-preflight", "sandbox-worker", "score"))
    parser.add_argument("--pin")
    parser.add_argument("--driver-pid", type=int)
    args = parser.parse_args()
    if args.mode == "watch":
        sys.exit(watch(args.driver_pid, args.pin))
    elif args.mode.startswith("sandbox-"):
        isolated(args.mode)
    elif args.mode == "score":
        import held_shrink_0019_score as scorer
        with patch.object(scorer, "ROOT", OUTPUT):
            scorer.score(args.pin)
    else:
        {"prepare": prepare, "preflight": preflight}[args.mode]()
