"""Stage two independently isolated full saved 0138 publications."""

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
import errno
import fcntl
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import resource
from shutil import copyfile
import signal
import socket
import subprocess
import sys
from time import monotonic, perf_counter_ns, process_time_ns, time_ns
from unittest.mock import patch


CODE = Path(__file__).resolve().parent
ROOT = Path("/dev/shm/leo-v3-profiled-grid-0138-03")
STAGE = Path("/dev/shm/leo-v3-causal-0138-stage01")
HISTORICAL = Path("/dev/shm/leo-v3-exact-grid-0138-active01")
ARCHIVED = Path("/var/tmp/leo-v3-exact-grid-0138")
PORTABLE = Path("/dev/shm/leo-v3-portable-orbit-prep-02")
PROJECTION = Path("/dev/shm/leo-grid-feature-projection-02/native-map.so")
LIBRARY = Path("/tmp/leo-profiled-grid-export-capsule-02/profiled.so")
LIBRARY_PIN = "8f65bd73d24ff04f6fded7ac414e06fb5dc08600d3a5c61f86203bb6dceff03f"
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
PAYLOAD = Path("/opt/leo-algo08/algo08v3/payload")
OFFICIAL = Path("/tmp/leo-v3-ds30-paired-evaluation/reports/ALGO08/v3/ds30_paired_evaluation.py")
OFFICIAL_PIN = "26b996e90e7ad4c467c551426a69e048d6078cf3c8087c741f9eef3c10f7df31"
LOCK = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
CORE = ARCHIVED/"reports/ALGO08/v3/exact_grid_0138.py"
CORE_PIN = "cc1b1f68c586dc6d5ca82db1114bee64db07113cc0f197f8b82295ae203b74d1"
CELLS = ("ordinary", "profiled")
BINDINGS = {
    "binding.json": "442ee000708f30dc92aac0a049ed2a82e899c06ea74df98f98af5c4d7239c0c0",
    "route-binding.json": "ef193ab5884984b6ac50ff3310e1e66a2af74538e6c69a197ea49e0af008f68e",
    "grid-binding.json": "71394d999de87401eb130a01680742f34e797022f448efd3195688b2311df6ba",
    "template.so": "d55bb5bbcd33de7a610221558c3727d86e827279c56b09d9142524afd4e4aa0b",
}
HISTORICAL_SCORE_PIN = "6aff05ab7cf624995dcd4e9351d4c407976ec3d7d9a1232bcb1380d32bdaab48"
REQUEST_PIN = "16826e2aa70e6baf377ef3d3efc847bdfdff1f569ed4b64289b6861a580b4797"
CAP_SECONDS = 24
FRESH_NS = 2_000_000_000
THREADS = ("BLIS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "OMP_NUM_THREADS",
           "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS")


def digest(file):
    return sha256(file.read_bytes()).hexdigest()


def checked(file, pin):
    if digest(file) != pin:
        raise ValueError(f"Expected unchanged source or saved input {file}")
    return file


def read(file):
    return json.loads(file.read_bytes())


def write(file, answer):
    with file.open("x") as out:
        json.dump(answer, out, sort_keys=True, allow_nan=False, indent=2)
        out.write("\n")


def require_resident(files):
    tmpfs = (Path("/dev/shm"), Path("/tmp"))
    devices = {root.stat().st_dev for root in tmpfs}
    if any(p.resolve(strict=True) != p or not any(p.is_relative_to(root) for root in tmpfs)
           or not p.is_file() or p.stat().st_dev not in devices for p in files):
        raise ValueError("Require exact local tmpfs operands")
    rows = json.loads(subprocess.check_output(["/usr/bin/fincore", "--bytes", "--json", "-o", "RES,SIZE", *files]))["fincore"]
    if len(files) != len(rows) or any(row["res"] < row["size"] for row in rows):
        raise ValueError("The exact staged inputs are no longer fully resident")
    return sum(row["size"] for row in rows)


def operands():
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    checked(STAGE/"request.json", REQUEST_PIN)
    inputs = read(checked(HISTORICAL/"binding.json", BINDINGS["binding.json"]))["input"]
    for path, pin in inputs["packets"].items():
        checked(Path(path), pin)
    _, _, producer_pin = inputs["portable"]
    checked(PORTABLE/"artifact-bind.json", producer_pin)
    request = read(STAGE/"request.json")
    refs = TleArchiveReader(STAGE/"tle").list_snapshots("space-track")
    archive = canonical_digest({ref.path.name: ref.sha256 for ref in refs})
    if ((len(refs), archive) != (50, request["local_archive"]["snapshots_sha256"])
            or any(ref.collected_utc_ns >= request["causal_cutoff_utc_ns"] for ref in refs)):
        raise ValueError("The original causal archive enrollment changed")
    checked(PROJECTION, "7ac9f74eb08d1992bde8738dbc8f6ec9687eb7fe4f5d5f4ae3301ddfa061d0fb")
    checked(LIBRARY, LIBRARY_PIN)
    files = (*(ref.path for ref in refs), *map(Path, inputs["packets"]), STAGE/"request.json", PORTABLE/"artifact-bind.json",
             PROJECTION, LIBRARY, LOCK)
    return files


def command(cell, mode, filter_fd):
    area = ROOT/cell
    runtime = (RELEASE/"venv/bin/python").resolve(strict=True).parents[1]
    args = ["/usr/bin/bwrap", "--unshare-all", "--unshare-user", "--disable-userns",
            "--die-with-parent", "--cap-drop", "ALL", "--clearenv", "--seccomp", str(filter_fd),
            "--proc", "/proc", "--dev", "/dev", "--bind", str(ROOT/"shm-root"), "/dev/shm"]
    for name in ("bin", "lib", "lib64"):
        args += ["--symlink", f"usr/{name}", f"/{name}"]
    paths = (Path("/usr"), Path("/etc/ld.so.cache"), Path("/etc/fonts"), Path("/etc/passwd"), Path("/etc/group"),
             Path("/sys/devices/system/cpu"), RELEASE, runtime, PAYLOAD.parent, ARCHIVED, CODE.parents[2],
             STAGE, PORTABLE/"dense-orbits.bin", PORTABLE/"artifact-bind.json", PROJECTION, LIBRARY, LOCK)
    for path in paths:
        args += ["--ro-bind", str(path), str(path)]
    args += ["--bind", str(area), str(area)]
    for name in BINDINGS:
        path = str(area/name)
        args += ["--ro-bind", path, path]
    args += ["--remount-ro", "/dev/shm", "--remount-ro", "/", "--chdir", str(area)]
    environment = dict.fromkeys(THREADS, "1") | dict(PATH="/usr/bin:/bin", LANG="C.UTF-8",
        MPLCONFIGDIR=str(area/"fonts"), TMPDIR=str(area/"tmp"), XDG_CACHE_HOME=str(area/"tmp"))
    for name, value in environment.items():
        args += ["--setenv", name, value]
    args += ["--", str(RELEASE/"venv/bin/python"), "-IB", str(Path(__file__).resolve()), mode, "--cell", cell]
    if mode == "worker":
        return ["/usr/bin/taskset", "-c", "2", "/usr/bin/nice", "-n", "15", "/usr/bin/ionice", "-c", "3", *args]
    return args


def isolated(cell):
    area = ROOT/cell
    mounts = {}
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields = line.split()
        mounts[fields[4]] = (fields[5].split(","), fields[fields.index("-")+1])
    if (mounts.get(str(area), ((), None))[1] != "tmpfs"
            or any(path.startswith(("/srv/bulk", "/mnt/qnap01")) for path in mounts)
            or not all("ro" in mounts.get(str(path), ((), None))[0]
                       for path in (Path("/dev/shm"), STAGE, LIBRARY, LOCK))):
        raise ValueError("An unwanted backing mount is visible")
    checks = ("/srv/bulk", "/mnt/qnap01", "/proc/1/root/srv/bulk")
    if any(Path(path).exists() for path in checks):
        raise ValueError("Backing paths are visible")
    for protocol in (socket.AF_INET, socket.AF_INET6, socket.AF_UNIX):
        try:
            with socket.socket(protocol):
                raise ValueError("Network or local socket access is active")
        except OSError as error:
            if error.errno != errno.EPERM:
                raise
    return dict(mount=os.readlink("/proc/self/ns/mnt"), network=os.readlink("/proc/self/ns/net"), denied=checks,
                readonly_stage=True, output_filesystem="tmpfs", sockets_denied=True)


def historical_core():
    return module("_pinned_grid_worker_0138", checked(CORE, CORE_PIN))


def module(name, path):
    spec = spec_from_file_location(name, path)
    core = module_from_spec(spec)
    spec.loader.exec_module(core)
    return core


@contextmanager
def observed_grid(cell, counts, activity, port):
    handoff = port.handoff
    with ExitStack() as scope:
        if cell == "profiled":
            scope.enter_context(port.profiled_grid(LIBRARY, LIBRARY_PIN, activity, proof=True))
        ordinary = handoff.grid_handoff

        @contextmanager
        def grid(port, library, in_grid):
            start = process_time_ns()
            with ordinary(port, library, in_grid) as result:
                counts["grid_port_setup_cpu_ns"] += process_time_ns()-start
                capture = handoff.Capture.run

                def timed(*args, **kwargs):
                    start, wall = process_time_ns(), perf_counter_ns()
                    try:
                        return capture(*args, **kwargs)
                    finally:
                        counts["calls"] += 1
                        counts["capture_cpu_ns"] += process_time_ns()-start
                        counts["capture_wall_ns"] += perf_counter_ns()-wall

                with patch.object(handoff.Capture, "run", timed):
                    yield result

        scope.enter_context(patch.object(handoff, "grid_handoff", grid))
        yield


def worker(cell, *, smoke):
    area = ROOT/cell
    proof = isolated(cell)
    if not smoke and (os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) != 15
                      or not os.path.samestat(os.fstat(0), LOCK.stat())):
        raise ValueError("Expected the admitted shared lease and CPU")
    core = historical_core()
    import empty_bootstrap as boot

    counts, activity = Counter(), Counter()
    original_scope = core._load_grid
    ports = []

    @contextmanager
    def load(bootstrap, original, root, probe, audit):
        with ExitStack() as stack:
            stack.enter_context(original_scope(bootstrap, original, root, probe, audit))
            loaded = bootstrap.load_runtime

            def bind():
                runtime = loaded()
                port = module("_profiled_grid_research", CODE/"profiled_grid_export.py")
                ports.append(port)
                stack.enter_context(observed_grid(cell, counts, activity, port))
                return runtime

            stack.enter_context(patch.object(bootstrap, "load_runtime", bind))
            yield

    if smoke:
        with load(boot, boot.load_runtime, area, False, {}):
            boot.load_runtime()
            from tools import algo08_position

            port, = ports
            stock = checked(PAYLOAD/"posterior-grid-handoff.so", port.STOCK_POSTERIOR_SHA256)
            with port.handoff.grid_handoff(algo08_position, stock, lambda: False):
                pass
        print(json.dumps(dict(isolation=proof, setup=dict(counts), activity=dict(activity), solver_calls=0)))
        return
    write(area/"isolation.json", proof)
    with patch.object(core, "_load_grid", load):
        core.worker(area, False)
    write(area/"callback-clocks.json", dict(clocks=dict(counts), activity=dict(activity),
                                           candidate_binary_sha256=LIBRARY_PIN if cell == "profiled" else None))


def sources():
    return {str(path): digest(path) for path in (Path(__file__).resolve(), CORE, CODE/"profiled_grid_export.py",
        CODE/"profiled_grid_export_admission.py", CODE/"profiled_grid_0138_score.py",
        CODE/"profiled-grid-export-0138-protocol.md")}


def headroom():
    fs = os.statvfs(ROOT)
    if (space := fs.f_bavail*fs.f_frsize) < 64*1024**2:
        raise ValueError("The private output filesystem needs 64 MiB of available room")
    return space


def prepare():
    from reports.ALGO08.v3.held_cfo_features_capsule import sock_filter

    start, cpu = monotonic(), process_time_ns()
    files = operands()
    checked(CORE, CORE_PIN)
    historical = read(checked(HISTORICAL/"score.json", HISTORICAL_SCORE_PIN))
    if not all(historical["parity"].values()):
        raise ValueError("Expected the prior exact positive control")
    resident = require_resident(files)
    ROOT.mkdir(mode=0o700)
    (ROOT/"shm-root").mkdir()
    sock_filter(ROOT/"sockets.bpf")
    records = {}
    for cell in CELLS:
        area = ROOT/cell
        area.mkdir(mode=0o700)
        (area/"tmp").mkdir()
        (area/"fonts").mkdir()
        for name, pin in BINDINGS.items():
            copyfile(checked(HISTORICAL/name, pin), area/name)
        font, = (HISTORICAL/"fonts").glob("fontlist-*.json")
        copyfile(font, area/"fonts"/font.name)
        with (ROOT/"sockets.bpf").open("rb") as sock:
            result = subprocess.run(command(cell, "smoke", sock.fileno()), pass_fds=(sock.fileno(),),
                                    capture_output=True, text=True, check=False, timeout=8)
        if result.returncode:
            raise ValueError(f"{cell} isolated imports failed: {result.stderr}")
        if (result.stdout.count("\n") != 1
                or (record := json.loads(result.stdout))["solver_calls"]
                or record["isolation"]["mount"] == os.readlink("/proc/self/ns/mnt")
                or record["isolation"]["network"] == os.readlink("/proc/self/ns/net")
                or record["activity"]):
            raise ValueError("The same-worker no-solve isolation check failed")
        records[cell] = record
    write(ROOT/"ready.json", dict(case="DS30-0138", sources=sources(), inputs=tuple(map(str, files)),
        resident_bytes=resident, smoke=records, filesystem_free=headroom(),
        seccomp_sha256=digest(ROOT/"sockets.bpf"), prior=HISTORICAL_SCORE_PIN,
        setup_wall_s=monotonic()-start, setup_cpu_ns=process_time_ns()-cpu,
        no_solver_calls=True, child_limit_s=CAP_SECONDS))
    print(digest(ROOT/"ready.json"))


def driver_idle(pid):
    checked(OFFICIAL, OFFICIAL_PIN)
    root = Path("/proc")/str(pid)
    words = (root/"cmdline").read_bytes().split(b"\0")
    if not any(a == os.fsencode(OFFICIAL) and b == b"run" for a, b in zip(words, words[1:])):
        raise ValueError("Expected the live original paired-evaluation controller")
    if (root/"task"/str(pid)/"children").read_text().strip():
        raise ValueError("An official child is active")


def admit(event, cell, pid, files, ready_pin):
    area = ROOT/cell
    with LOCK.open("rb") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        driver_idle(pid)
        resident = require_resident(files)
        headroom()
        age = time_ns()-event["unix_ns"]
        if not 0 <= age <= FRESH_NS:
            raise ValueError("Deferral exceeds the frozen admission age")
        with (area/"worker.stdout").open("x") as output, (area/"worker.stderr").open("x") as error, (
                ROOT/"sockets.bpf").open("rb") as sock:
            args = command(cell, "worker", sock.fileno())
            started, before = monotonic(), resource.getrusage(resource.RUSAGE_CHILDREN)
            initial = time_ns()
            if initial-event["unix_ns"] > FRESH_NS:
                raise ValueError("Deferral expired before launch")
            with subprocess.Popen(args, stdin=lease, pass_fds=(sock.fileno(),), stdout=output, stderr=error,
                                  start_new_session=True) as child:
                try:
                    status = child.wait(max(0, CAP_SECONDS-(monotonic()-started)))
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
                    status = 124
            elapsed, after = monotonic()-started, resource.getrusage(resource.RUSAGE_CHILDREN)
        measured = dict(exit_code=status, wall_s=elapsed, resident_bytes=resident, ready_sha256=ready_pin,
                        cpu_s=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                        input_blocks=after.ru_inblock-before.ru_inblock, major_faults=after.ru_majflt-before.ru_majflt,
                        started_unix_ns=initial, gate=event, child_limit_s=CAP_SECONDS)
        write(area/"clock.json", measured)
        return measured


def watch(cell, pid, ready_pin, official_case):
    from reports.ALGO08.v3.profiled_grid_export_admission import observe

    area = ROOT/cell
    if (area/"worker.stdout").exists() or (area/"clock.json").exists():
        raise ValueError("The saved publication attempt was used")
    ready = read(checked(ROOT/"ready.json", ready_pin))
    files = tuple(map(Path, ready["inputs"]))
    if ready["sources"] != sources() or ready["resident_bytes"] != require_resident(files):
        raise ValueError("Sources or resident operands differ from the no-solve preflight")
    checked(ROOT/"sockets.bpf", ready["seccomp_sha256"])
    for name, pin in BINDINGS.items():
        checked(area/name, pin)
    if cell == "profiled":
        verified = read(ROOT/"ordinary/verified.json")
        if not verified["accept"] or verified["clock_sha256"] != digest(ROOT/"ordinary/clock.json"):
            raise ValueError("Expected the verified fresh ordinary comparison first")
    driver_idle(pid)
    result = observe(lambda event: admit(event, cell, pid, files, ready_pin), official_case)
    path = area/f"admission-{result['watching_from']}.json"
    write(path, result)
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("prepare", "smoke", "worker", "watch"))
    cli.add_argument("--cell", choices=CELLS)
    cli.add_argument("--driver-pid", type=int)
    cli.add_argument("--ready-pin")
    cli.add_argument("--official-case")
    args = cli.parse_args()
    if args.action != "prepare" and not args.cell:
        cli.error("Select the enrolled cell")
    if args.action == "prepare":
        prepare()
    elif args.action == "watch":
        if not all((args.driver_pid, args.ready_pin, args.official_case)):
            cli.error("The fresh official deferral and ready proof must be bound")
        print(json.dumps(watch(args.cell, args.driver_pid, args.ready_pin, args.official_case), sort_keys=True))
    else:
        worker(args.cell, smoke=args.action == "smoke")
