"""Isolate, admit and seal the two enrolled DS30-0218 saved position workers."""

import argparse
import errno
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
import signal
import socket
import subprocess
import sys
from time import monotonic, sleep, time_ns

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import held_shrink_0019_ram as ram  # noqa: E402
import masked_cfo_0218 as held  # noqa: E402
import masked_cfo_0218_owner_residuals as observer  # noqa: E402
import masked_cfo_0218_score as scoring  # noqa: E402
from field_crossover_admission_watch import recent_deferral  # noqa: E402
from joint_recovery_0049_direct import DRIVER, require_driver_idle  # noqa: E402
from joint_recovery_0049_wait import lease  # noqa: E402
from masked_cfo_0218 import saved, signed  # noqa: E402


CELLS = ("ordinary", "corrected")
DRIVER_PIN = "26b996e90e7ad4c467c551426a69e048d6078cf3c8087c741f9eef3c10f7df31"
OBSERVER = Path(observer.__file__)
WORKER = Path(__file__).resolve()
TIMEOUT = 24
FRESH_NS = 2_000_000_000
STAGE_FILES = ("authority.json", "inventory.json", "offer.json", "catalogue.json")


def ram_path(path, *, cell=False):
    wanted = ("/dev/shm",) if cell else ("/dev/shm", "/tmp")
    if path.resolve(strict=True) != path or not any(path.is_relative_to(base) for base in wanted):
        raise ValueError(f"Expected a direct staged RAM path: {path}")
    if os.statvfs(path).f_fsid not in {os.statvfs(base).f_fsid for base in wanted}:
        raise ValueError(f"Staged path is outside the enrolled RAM filesystems: {path}")
    return path


def operands(cell, pin, mode):
    ram_path(cell, cell=True)
    plan = saved.document(cell/"plan.json", pin)
    if mode == "probe":
        valid = plan["case"] == "DS30-0019" and plan["probe"] and plan["enabled"]
    else:
        valid = plan["case"] == held.CASE and not plan["probe"] and plan["enabled"] == (mode == "corrected")
    if not valid:
        raise ValueError("The staged plan does not enroll this saved role")
    stage = ram_path(Path(plan["stage"]), cell=True)
    if stage != (held.KNOWN if mode == "probe" else cell.parent/"stage"):
        raise ValueError("The worker stage is outside the enrolled local fixture or field cohort")
    admission = saved.document(cell/"admission.json", plan["admission_sha256"])
    authority = saved.document(stage/"authority.json", admission["authority_pin"])
    catalogue = saved.document(stage/"catalogue.json")
    view = {name:row["sha256"] if mode == "probe" else row for name,row in catalogue.items()}
    if (len(view) != plan["references"] or signed.canonical(view) != authority["archive_sha256"]
            or any(Path(name).name != name or not name.endswith("-"+digest+".tle")
                   or int(name.split("-", 1)[0]) >= authority["causal_cutoff_utc_ns"] for name,digest in view.items())):
        raise ValueError("The stage lacks the exact complete causal catalogue")
    bodies = {stage/"tle/archive/space-track"/name:digest for name,digest in view.items()}
    book = saved.document(saved.BUILD, saved.BUILD_PIN)
    files = {Path(item["path"]) for item in (*book["native"].values(), book["png"], book["portable_producer"])}
    transport = book["native"]["--legacy-first-map-fast"]
    acceleration = saved.document(ram_path(Path(transport["path"])), transport["sha256"])
    files |= {Path(acceleration[name]["path"]) for name in ("hasher", "projection", "template")}
    files |= {stage/name for name in STAGE_FILES} | bodies.keys()
    inputs = sorted({*files, *(cell/name for name in ram.ARTIFACTS)})
    saved.require_resident([ram_path(path) for path in inputs])
    if any(saved.identifier(path) != digest for path,digest in bodies.items()):
        raise ValueError("An already resident causal body differs from its signed bytes")
    available = os.statvfs(cell)
    if available.f_bavail*available.f_frsize < 64*1024**2:
        raise ValueError("Require at least 64 MiB of tmpfs output headroom")
    return plan, inputs, sorted(files)


def command(cell, pin, mode, inputs, *, proof_only=False):
    work = cell/"capsule-scratch"
    runtime = (ram.RELEASE/"venv/bin/python").resolve(strict=True).parents[1]
    sources = (HERE.parents[2], saved.CHARTED, saved.BUILD, ram.RELEASE, ram.PAYLOAD, runtime, saved.LOCK,
               *(Path(path) for path in ("/usr", "/etc/fonts", "/etc/ld.so.cache", "/etc/passwd", "/etc/group",
                                         "/sys/devices/system/cpu")))
    args = ["/usr/bin/bwrap", "--unshare-all", "--unshare-user", "--disable-userns", "--die-with-parent",
            "--cap-drop", "ALL", "--clearenv", "--proc", "/proc", "--dev", "/dev",
            "--bind", str(cell/"capsule-shm-root"), "/dev/shm"]
    for name in ("bin", "lib", "lib64"):
        args += ["--symlink", f"usr/{name}", f"/{name}"]
    for path in (*inputs, *sources):
        args += ["--ro-bind", str(path), str(path)]
    args += ["--bind", str(cell), str(cell)]
    for name in ram.ARTIFACTS:
        source = str(cell/name)
        args += ["--ro-bind", source, source]
    args += ["--remount-ro", "/dev/shm", "--remount-ro", "/", "--chdir", str(cell)]
    for key, value in (dict.fromkeys(ram.THREADS, "1") | dict(PATH="/usr/bin:/bin", LANG="C.UTF-8",
            TMPDIR=str(work), MPLCONFIGDIR=str(work), XDG_CACHE_HOME=str(work))).items():
        args += ["--setenv", key, value]
    return args + ["--", str(ram.RELEASE/"venv/bin/python"), "-IB", str(WORKER),
                   "child", str(cell), "--pin", pin, "--cell", mode, *(["--probe-only"] if proof_only else [])]


def isolation(cell, stage, *, probe):
    ram.network_off()
    mounts = {}
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        left, right = line.split(" - ", 1)
        _, _, _, _, name, flags, *_ = left.split()
        mounts[name] = (right.split()[0], flags.split(","))
    if (any(name.startswith(("/srv/bulk", "/mnt/qnap01")) or source in {"xfs", "nfs", "nfs4", "cifs"}
            for name,(source,_) in mounts.items()) or mounts[str(cell)][0] != "tmpfs"
            or any("ro" not in mounts[name][1] for name in ("/", "/dev/shm", str(HERE.parents[2]),
                    str(saved.CHARTED), str(saved.LOCK), *(str(cell/name) for name in ram.ARTIFACTS)))
            or any("ro" not in flags for name,(_,flags) in mounts.items() if name.startswith(str(stage)+"/"))):
        raise ValueError("The capsule exposed writable input or an external data mount")
    denied = {}
    for path in ("/srv/bulk", "/mnt/qnap01", "/proc/1/root/srv/bulk", str(cell/"backing-alias"), str(stage/"native.json")):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
        except OSError as error:
            if error.errno not in (errno.ENOENT, errno.EACCES, errno.EPERM):
                raise
            denied[path] = error.errno
        else:
            os.close(fd)
            raise ValueError(f"An unenrolled data path opened: {path}")
    for family in (socket.AF_INET, socket.AF_INET6, socket.AF_UNIX):
        with_expected_socket_denial(family)
    expected = cell/"plan.json" if probe else saved.LOCK
    if not os.path.samestat(os.fstat(0), expected.stat()):
        raise ValueError("The capsule lost the inherited descriptor")
    return dict(denied=denied, socket_denied=True, inherited_descriptor=True, readonly_operands=True,
                mount_namespace=os.readlink("/proc/self/ns/mnt"), network_namespace=os.readlink("/proc/self/ns/net"))


def with_expected_socket_denial(family):
    try:
        with socket.socket(family):
            raise ValueError("The capsule opened a network socket")
    except PermissionError as error:
        if error.errno != errno.EPERM:
            raise


def child(cell, pin, mode, *, probe_only):
    plan = saved.document(cell/"plan.json", pin)
    evidence = isolation(cell, Path(plan["stage"]), probe=probe_only)
    saved.write(cell/("preflight-isolation.json" if probe_only else "worker-isolation.json"), evidence)
    sys.addaudithook(saved.deny_backing)
    if probe_only:
        with observer.observe_worker([]):
            saved.worker(cell, pin, held.experiment(probe=plan["probe"]), smoke=True, original_control=True,
                enrollment=(plan["case"], Path(plan["stage"]), plan["admission_sha256"], plan["references"]),
                admission_path=cell/"admission.json")
        return
    if mode not in CELLS:
        raise ValueError("The local proof cannot invoke the numerical worker")
    saved.attrs(expected_priority="idle")
    observer.entry(cell, pin, mode, 0)


def setup(cell):
    (cell/"capsule-scratch").mkdir(mode=0o700)
    # The existing staging validator checks st_dev against /dev/shm.
    (cell/"capsule-shm-root").mkdir(mode=0o700)
    (cell/"backing-alias").symlink_to("/srv/bulk", target_is_directory=True)


def preflight(cell, pin, mode, observer_pin):
    if saved.identifier(OBSERVER) != observer_pin:
        raise ValueError("The selected observer source differs from its pin")
    plan, inputs, mounts = operands(cell, pin, mode)
    setup(cell)
    with (cell/"plan.json").open("rb") as descriptor:
        result = subprocess.run(["/usr/bin/taskset", "-c", "3", *command(cell, pin, mode, mounts, proof_only=True)],
                                capture_output=True, text=True, timeout=12, stdin=descriptor, check=False)
    if result.returncode:
        raise ValueError(result.stderr.strip())
    proof = saved.document(cell/"preflight-isolation.json")
    smoke = json.loads(result.stdout)
    if (any(proof[f"{ns}_namespace"] == os.readlink(f"/proc/self/ns/{name}")
            for ns,name in (("network", "net"), ("mount", "mnt")))
            or smoke != dict(case=plan["case"], changed=0, refs=plan["references"], acquired=0, waveform_reads=0, solver_runs=0)):
        raise ValueError("The exact worker failed its independent no-solve isolation proof")
    return saved.write(cell/"capsule-ready.json", dict(plan=pin, cell=mode, proof=proof, smoke=smoke,
        observer=observer_pin, launcher=saved.identifier(WORKER), inputs=list(map(str,inputs))))


def sealed_cell(cell, mode, pin):
    paths = {"plan":"plan.json", "clock":"clock.json", "observation":"masked-cfo-observation-witness.json",
             "receipt":"receipt.json", "isolation":"worker-isolation.json",
             "residuals":"owner-residuals.json", "export_clock":"owner-residual-export-clock.json"}
    pins = {key:saved.identifier(cell/name) for key,name in paths.items()}
    if pins["plan"] != pin.removeprefix("sha256:"):
        raise ValueError("The exited plan differs from the admitted plan")
    _, _, scope, run = scoring.read_cell(cell, pins, enabled=mode == "corrected")
    isolation_proof = saved.document(cell/paths["isolation"], pins["isolation"])
    if (any(isolation_proof.get(key) is not True for key in ("inherited_descriptor", "socket_denied", "readonly_operands"))
            or isolation_proof["mount_namespace"] == os.readlink("/proc/self/ns/mnt")
            or isolation_proof["network_namespace"] == os.readlink("/proc/self/ns/net")):
        raise ValueError("The worker did not seal its independent RAM-only isolation")
    residuals = saved.document(cell/paths["residuals"], pins["residuals"])
    export = saved.document(cell/paths["export_clock"], pins["export_clock"])
    if (export["residuals_sha256"] != pins["residuals"] or residuals["plan_sha256"] != pin
            or residuals["role"] != mode or residuals["decision"] != scope["decision"]
            or residuals["terminal_sha256"] != run["receipt"]["terminal_sha256"]
            or residuals["publication_witness_sha256"] != run["witness"] or residuals["native_sha256"] != run["input"]
            or residuals["ordinary_receipt_sha256"] != pins["receipt"]
            or residuals["observation_witness_sha256"] != pins["observation"]
            or residuals["observer_source_sha256"] != saved.identifier(OBSERVER)):
        raise ValueError("The optional residual artifact differs from the sealed worker publication")
    return dict(pins, plan=pin)


def run_child(cell, mode, pin, mounts, fd, event):
    if (cell/"worker-intent.json").exists():
        raise ValueError("This staged worker already spent its one numerical launch")
    intent = saved.write(cell/"worker-intent.json", dict(plan=pin, event=event, cap_s=TIMEOUT))
    with (cell/"worker.stdout").open("xb") as stdout, (cell/"worker.stderr").open("xb") as stderr:
        before, start = getrusage(RUSAGE_CHILDREN), monotonic()
        args = ["/usr/bin/taskset", "-c", "2", *command(cell, pin, mode, mounts)]
        with subprocess.Popen(args, stdin=fd, stdout=stdout, stderr=stderr,
                              start_new_session=True) as process:
            try:
                code = process.wait(max(0, TIMEOUT-(monotonic()-start)))
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                code = 124
        after, end = getrusage(RUSAGE_CHILDREN), monotonic()
    saved.write(cell/"clock.json", dict(exit_code=code, elapsed_s=end-start,
        cpu_s=(after.ru_utime-before.ru_utime)+(after.ru_stime-before.ru_stime),
        input_blocks=after.ru_inblock-before.ru_inblock, output_blocks=after.ru_oublock-before.ru_oublock,
        clock_scope="namespace launch through optional residual export and exit", intent_sha256=intent))
    return code


def live_window(event, pid):
    event_path = held.CAMPAIGN/event["event"]
    if (event_path.parent != held.CAMPAIGN/"cases"/event["case"]/"events"
            or int(event_path.name.split("-", 1)[0]) != event["unix_ns"]
            or saved.document(event_path, event["event_sha256"])["state"] != "deferred_storage_busy"):
        raise ValueError("Require an official storage deferral from the frozen driver")
    require_driver_idle(pid)
    if b"--watch" not in (Path("/proc")/str(pid)/"cmdline").read_bytes().split(b"\0"):
        raise ValueError("Require the official driver's measured 30-second retry mode")
    age = time_ns()-event["unix_ns"]
    if not 0 <= age <= FRESH_NS or 30-age/1e9 < TIMEOUT+2:
        raise ValueError("The deferral no longer leaves the full launch cap and slack")


def finish(root, mode, pin, field_pair, ordinary):
    pins = sealed_cell(root/mode, mode, pin)
    if mode == "ordinary":
        scoring.verify(root, {mode:pins})
        return saved.write(root/"ordinary-gate.json", dict(ordinary=pins, field_pair=field_pair,
                           parity=saved.identifier(root/"ordinary-parity.json")))
    if ordinary is None:
        raise ValueError("The corrected comparison requires the sealed ordinary worker")
    pair_pins = dict(ordinary=ordinary, corrected=pins)
    saved.write(root/"verification-pins.json", pair_pins)
    scoring.verify(root, pair_pins)
    return saved.identifier(root/"score.json")


def watch(root, mode, pid, ready_pin, ordinary_gate_pin):
    cell = root/mode
    ready = saved.document(cell/"capsule-ready.json", ready_pin)
    pin = ready["plan"]
    if (saved.identifier(DRIVER) != DRIVER_PIN or ready["launcher"] != saved.identifier(WORKER)
            or ready["observer"] != saved.identifier(OBSERVER) or ready["cell"] != mode):
        raise ValueError("The live driver, observer or capsule differs from the verified preflight")
    plan, paths, mounts = operands(cell, pin, mode)
    if ready["inputs"] != list(map(str,paths)):
        raise ValueError("The admitted RAM-only path set changed")
    state = held.status()
    if not state["verified_pair"] or plan["original"]["verified_field_pair_sha256"] != state["pair_sha256"].removeprefix("sha256:"):
        raise ValueError("The original field pair is pending or differs from the staged plan")
    ordinary = None
    if mode == "corrected":
        if ordinary_gate_pin is None:
            raise ValueError("Require the sealed ordinary parity gate before the corrected launch")
        gate = saved.document(root/"ordinary-gate.json", ordinary_gate_pin)
        ordinary = gate["ordinary"]
        parity = saved.document(root/"ordinary-parity.json", gate["parity"])
        if (gate["field_pair"] != state["pair_sha256"] or not parity["exact_ordinary_scientific_parity"]
                or sealed_cell(root/"ordinary", "ordinary", ordinary["plan"]) != ordinary):
            raise ValueError("The ordinary scientific parity or its publication files changed")
    elif ordinary_gate_pin is not None:
        raise ValueError("Only the corrected launch takes an ordinary parity gate")
    if (cell/"worker-intent.json").exists():
        raise ValueError("An already used cell cannot launch again")

    if (os.sched_getaffinity(0) != {3} or os.getpriority(os.PRIO_PROCESS, 0) != 15
            or subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip() != "idle"
            or any(os.environ.get(key) != "1" for key in ram.THREADS)):
        raise ValueError("Use CPU3 for the controller and verification, nice 15, idle IO and one numeric thread")
    export = held.CAMPAIGN/"rows.jsonl"
    started, deadline, inode = time_ns(), monotonic()+120, export.stat().st_ino
    while (remaining := deadline-monotonic()) > 0:
        current = export.stat().st_ino
        if current != inode:
            inode = current
            event = recent_deferral(held.CAMPAIGN, started, time_ns())
            if event is not None and 0 <= time_ns()-event["unix_ns"] <= FRESH_NS:
                try:
                    live_window(event, pid)
                    quiet = ram.nvme_quiet(continuous=True)
                    with lease() as fd:
                        saved.require_resident(paths)
                        quiet_on_lease = ram.nvme_quiet(continuous=False)
                        live_window(event, pid)
                        latest = held.status()
                        if not latest["verified_pair"] or latest["pair_sha256"] != state["pair_sha256"]:
                            raise ValueError("The official field pair changed before launch")
                        live_window(event, pid)
                        code = run_child(cell, mode, pin, mounts, fd, dict(event=event, driver_pid=pid,
                                         quiet=quiet, quiet_on_lease=quiet_on_lease))
                except (OSError, ValueError) as error:
                    saved.write(cell/f"admission-{started}.json", dict(started=started, reason=str(error),
                                event=event, launched=(cell/"worker-intent.json").exists()))
                    return 3
                break
        sleep(min(.10, remaining))
    else:
        saved.write(cell/f"admission-{started}.json", dict(started=started, reason="no fresh deferral", launched=False))
        return 3
    if code:
        return code
    return finish(root, mode, pin, state["pair_sha256"], ordinary)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("probe", "preflight", "watch", "child"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--cell", choices=(*CELLS, "probe"))
    cli.add_argument("--pin")
    cli.add_argument("--observer-pin")
    cli.add_argument("--ordinary-gate-pin")
    cli.add_argument("--driver-pid", type=int)
    cli.add_argument("--probe-only", action="store_true")
    args = cli.parse_args()
    if args.mode == "probe":
        if args.root.resolve() != args.root or args.root.parent != Path("/dev/shm") or args.observer_pin is None:
            cli.error("Use one fresh private tmpfs probe root and a pinned observer")
        sys.addaudithook(saved.deny_backing)
        args.root.mkdir(mode=0o700)
        cell = args.root/"probe"
        print(preflight(cell, held.prepare_probe(cell), "probe", args.observer_pin))
        return 0
    if args.pin is None or args.cell is None:
        cli.error("Require the exact stage or readiness pin and selected cell")
    pin = args.pin.removeprefix("sha256:")
    if args.mode == "child":
        child(args.root, pin, args.cell, probe_only=args.probe_only)
        return 0
    ram_path(args.root, cell=True)
    if args.cell not in CELLS:
        cli.error("Require an enrolled ordinary or corrected field cell")
    sys.addaudithook(saved.deny_backing)
    if args.mode == "preflight" and args.observer_pin is not None:
        print(preflight(args.root/args.cell, pin, args.cell, args.observer_pin))
        return 0
    if args.mode == "watch" and args.driver_pid is not None:
        result = watch(args.root, args.cell, args.driver_pid, pin, args.ordinary_gate_pin)
        if isinstance(result, int):
            return result
        print(result)
        return 0
    cli.error("Require the observer pin for preflight or the live campaign PID for an authorized watch")


if __name__ == "__main__":
    sys.exit(main())
