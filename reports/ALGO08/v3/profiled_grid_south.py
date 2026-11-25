"""Admit the two frozen South saved publications without acquiring a recording."""

import argparse
import fcntl
import json
import os
import resource
import signal
import socket
import subprocess
import sys
from collections import Counter
from contextlib import ExitStack, suppress
from pathlib import Path
from shutil import copyfile
from time import monotonic, time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if __package__ is None:
    sys.path.insert(0, str(HERE.parents[2]))

from reports.ALGO08.v3 import profiled_grid_0138 as prior  # noqa: E402

ROOT = Path("/tmp/leo-grid-proof-south-02")
SHM_ROOT = Path("/dev/shm/leo-grid-proof-south-mount-02")
FROZEN = Path("/tmp/leo-v3-frozen-geographic-audit")
RUNTIME = Path("/tmp/leo-v3-0049-saved-crossover")
CORE = FROZEN / "reports/ALGO08/v3/frozen_south_saved.py"
CORE_PIN = "47d70a51031fad5f83793f01180b4ac30305c9dc71218f7c09debf3c0dc56e9c"
CAMPAIGN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
BUILD = CAMPAIGN / "frozen-build/build.json"
BUILD_PIN = "30cc3b044040f2519677d67abfde731f83693612744d2236d1ba71bb5a31e4ab"
ARCHIVE = Path("/tmp/leo-regional-qZJKBw4W/public/tle")
STOCK = Path("/tmp/leo-v3-frozen-south-saved-01")
STOCK_SEAL = "cddc872a8990560d9342d5dd17b89d21920f527f61de66405dfac8a940f34716"
STAGE = Path("/tmp/leo-v3-integrated-south-result02-containing")
STAGE_PIN = "f94821596f03d0ca1295c725d65f146ad9d0e47d7f36744a13d7e7638323dce8"
NAMED = Path("/tmp/leo-v3-integrated-south-controls/south-result.json")
NAMED_PIN = "e0ac0972934671d6536daed5ba64de4cf21f2d695bc51893c0720a08a7fef903"
PLAN = FROZEN / "reports/ALGO08/v3/measurements/frozen-build-geography.json"
PLAN_PIN = "be4d89302c90b2eee19ff930e4485de7ea22b0ef04e1ba216bf9734e47c4ddd1"
STAGED_CODE = ("profiled_grid_south.py", "profiled_grid_0138.py", "profiled_grid_export.py")
OFFERS = ("containing", "omitted")
CAP_SECONDS = 18
WATCH_SECONDS = 55


def point_in_time_paths():
    sys.path[:0] = [str(prior.RELEASE / "src"), str(prior.RELEASE)]
    from leo.operations.tle_archive import TleArchiveReader

    saved = prior.read(prior.checked(PLAN, PLAN_PIN))
    pair = saved["proposed_saved_pair"]
    build = prior.read(prior.checked(BUILD, BUILD_PIN))
    seal = prior.read(prior.checked(STAGE / "prediction-seal.json", STAGE_PIN))
    required = ("admission.json", "candidate/unified-short-bootstrap.json")
    admission = prior.read(prior.checked(STAGE / required[0], seal[required[0]]))
    assets = list(build["native"].values()) + [build["png"], build["portable_producer"]]
    exact = prior.read(Path(build["native"]["--legacy-first-map-fast"]["path"]))
    assets += [exact[name] for name in ("hasher", "projection", "template")]
    pinned = {Path(a["path"]): a["sha256"] for a in assets}
    pinned.update({Path(a["path"]): a["sha256"] for a in pair["packets"].values()})
    pinned.update({Path(pair["inventory_path"]): pair["inventory_sha256"], NAMED: NAMED_PIN,
                   Path(admission["request"]["offers"]["containing"]):
                   saved["south_existing_raw"]["containing_offer_sha256"],
                   prior.LIBRARY: prior.LIBRARY_PIN})
    pinned.update({STAGE / name: seal[name] for name in required})
    pinned[STAGE / "prediction-seal.json"] = STAGE_PIN
    for path, pin in pinned.items():
        prior.checked(path, pin.removeprefix("sha256:"))
    refs = TleArchiveReader(ARCHIVE).list_snapshots("space-track")
    from leo.contracts.digests import canonical_digest

    if (canonical_digest({r.path.name: r.sha256 for r in refs}) !=
            "sha256:" + pair["causal_archive_sha256"]
            or any(r.collected_utc_ns >= pair["causal_cutoff_utc_ns"] for r in refs)):
        raise ValueError("The causal stage differs from the frozen South request")
    inputs = (*pinned, *(r.path for r in refs))
    return tuple(map(str, pinned)), tuple(map(str, inputs))


def command(offer, mode, filter_fd, files):
    area = ROOT / offer
    runtime = (prior.RELEASE / "venv/bin/python").resolve(strict=True).parents[1]
    args = ["/usr/bin/bwrap", "--unshare-all", "--unshare-user", "--disable-userns",
            "--die-with-parent", "--cap-drop", "ALL", "--clearenv", "--seccomp", str(filter_fd),
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--bind", str(SHM_ROOT), "/dev/shm"]
    for name in ("bin", "lib", "lib64"):
        args += ["--symlink", f"usr/{name}", f"/{name}"]
    visible = ("/usr", "/etc/ld.so.cache", "/etc/fonts", "/etc/passwd", "/etc/group",
               "/sys/devices/system/cpu", prior.RELEASE, runtime, prior.PAYLOAD.parent, FROZEN, RUNTIME,
               ROOT / "src", ARCHIVE, BUILD, prior.LOCK, *files)
    for path in dict.fromkeys(map(str, visible)):
        args += ["--ro-bind", path, path]
    args += ["--bind", str(area), str(area), "--remount-ro", "/dev/shm", "--remount-ro", "/tmp",
             "--remount-ro", "/", "--chdir", str(area)]
    environment = dict.fromkeys(prior.THREADS, "1") | {
        "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "MPLCONFIGDIR": str(area / "fonts"),
        "TMPDIR": str(area / "tmp"), "XDG_CACHE_HOME": str(area / "tmp"),
    }
    for name, value in environment.items():
        args += ["--setenv", name, value]
    args += ["--", str(prior.RELEASE / "venv/bin/python"), "-IB",
             str(ROOT / "src/reports/ALGO08/v3/profiled_grid_south.py"), mode, "--offer", offer]
    return ["taskset", "-c", "3" if mode == "smoke" else "2", "nice", "-n", "15", "ionice", "-c", "3", *args]


def isolated(offer):
    mounts = {}
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields = line.split()
        mounts[fields[4]] = (fields[5].split(","), fields[fields.index("-") + 1])
    readonly = (ARCHIVE, prior.LIBRARY, prior.LOCK, ROOT / "src")
    if (mounts[str(ROOT / offer)][1] != "tmpfs"
            or any(mounts.get(str(p), ((), ""))[0].count("ro") != 1 for p in readonly)
            or any(Path(p).exists() for p in ("/srv/bulk", "/mnt/qnap01", "/proc/1/root/srv/bulk"))):
        raise ValueError("Expected read-only staged operands and a private tmpfs output")
    for family in (socket.AF_INET, socket.AF_INET6, socket.AF_UNIX):
        try:
            with socket.socket(family):
                raise ValueError("Expected native socket confinement")
        except PermissionError:
            pass
    return {"mount": os.readlink("/proc/self/ns/mnt"), "stack": "readonly original South fixture",
            "network": os.readlink("/proc/self/ns/net"), "sockets_denied": True}


def worker(offer, smoke):
    proof = isolated(offer)
    area = ROOT / offer
    if not smoke and (os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) != 15
                      or not os.path.samestat(os.fstat(0), prior.LOCK.stat())):
        raise ValueError("Require the admitted shared lease on CPU 2")
    base = prior.module("_frozen_south", prior.checked(CORE, CORE_PIN))
    counts, activity = Counter(), Counter()
    with ExitStack() as stack:
        bootstrap = base.bootstrap

        def bind():
            ready = bootstrap()
            port = prior.module("_profiled_grid_south_export", HERE / "profiled_grid_export.py")
            stack.enter_context(prior.observed_grid("profiled", counts, activity, port))
            if smoke:
                from tools import algo08_position

                stock = prior.checked(prior.PAYLOAD / "posterior-grid-handoff.so",
                                      port.STOCK_POSTERIOR_SHA256)
                with port.handoff.grid_handoff(algo08_position, stock, lambda: False):
                    pass
            return ready

        if not smoke:
            prior.write(area / "isolation.json", proof)
        stack.enter_context(patch.object(base, "bootstrap", bind))
        base.worker(f"{offer}:integrated", area / "publication", probe=smoke)
    record = {"clocks": dict(counts), "activity": dict(activity), "isolation": proof,
              "candidate_binary_sha256": prior.LIBRARY_PIN}
    if smoke:
        print(json.dumps(record))
    else:
        prior.write(area / "callback-clocks.json", record)


def prepare():
    files, inputs = point_in_time_paths()
    from reports.ALGO08.v3.held_cfo_features_capsule import sock_filter

    resident = prior.require_resident(tuple(map(Path, inputs)))
    prior.checked(STOCK / "prediction-seal.json", STOCK_SEAL)
    prior.checked(CORE, CORE_PIN)
    ROOT.mkdir(mode=0o700)
    SHM_ROOT.mkdir(mode=0o700)
    code = ROOT / "src/reports/ALGO08/v3"
    code.mkdir(parents=True)
    for name in STAGED_CODE:
        copyfile(HERE / name, code / name)
    sock_filter(ROOT / "sockets.bpf")
    smoke = {}
    for offer in OFFERS:
        area = ROOT / offer
        (area / "tmp").mkdir(parents=True)
        folder = area / "fonts"
        folder.mkdir()
        font, = (STOCK / "fonts").glob("fontlist-*.json")
        copyfile(font, folder / font.name)
        with (ROOT / "sockets.bpf").open("rb") as descriptor:
            probe = subprocess.run(command(offer, "smoke", descriptor.fileno(), files),
                                   capture_output=True, text=True, pass_fds=(descriptor.fileno(),),
                                   timeout=12, check=False)
        prior.write(area / "smoke.json", {"rc": probe.returncode, "stdout": probe.stdout,
                                         "stderr": probe.stderr})
        if probe.returncode:
            raise ValueError(probe.stderr)
        origin, proof = map(json.loads, probe.stdout.splitlines())
        if origin["waveform_opened"] or proof["activity"] or proof["clocks"].get("calls", 0):
            raise ValueError("The South isolation check must stop before numerical work")
        smoke[offer] = proof
    prior.write(ROOT / "ready.json", {"files": files, "inputs": inputs, "resident_bytes": resident,
        "smoke": smoke, "code": {name: prior.digest(code / name) for name in STAGED_CODE},
        "seccomp_sha256": prior.digest(ROOT / "sockets.bpf")})
    print(prior.digest(ROOT / "ready.json"))


def primary_pending():
    rows = [r for r in map(json.loads, (CAMPAIGN / "rows.jsonl").read_text().splitlines())
            if r["case"] == "DS30-0218"]
    if len(rows) != 2 or any(r["admission_state"] != "pending" or r["verified_pair"] for r in rows):
        raise ValueError("Yield to the priority DS30-0218")


def admit(offer, pid, ready, event):
    area = ROOT / offer
    if event["case"] == "DS30-0218":
        raise ValueError("The priority field case owns this deferral")
    with prior.LOCK.open("rb") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prior.driver_idle(pid)
        primary_pending()
        resident = prior.require_resident(tuple(map(Path, ready["inputs"])))
        if not 0 <= time_ns() - event["unix_ns"] <= prior.FRESH_NS:
            raise ValueError("The official deferral expired")
        with (area / "worker.stdout").open("x") as out, (area / "worker.stderr").open("x") as err, (
                ROOT / "sockets.bpf").open("rb") as sock:
            argv = command(offer, "worker", sock.fileno(), ready["files"])
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            start, before_ns = monotonic(), time_ns()
            if before_ns - event["unix_ns"] > prior.FRESH_NS:
                raise ValueError("The official deferral expired before the child could start")
            with subprocess.Popen(argv, stdin=lease, stdout=out, stderr=err,
                                  pass_fds=(sock.fileno(),), start_new_session=True) as child:
                outcome = "exit"
                while True:
                    try:
                        status = child.wait(min(.25, max(0, CAP_SECONDS-(monotonic()-start))))
                        break
                    except subprocess.TimeoutExpired:
                        try:
                            primary_pending()
                        except ValueError:
                            outcome, status = "priority_yield", 125
                            break
                        if monotonic() - start >= CAP_SECONDS:
                            outcome, status = "timeout", 124
                            break
                if outcome != "exit":
                    with suppress(ProcessLookupError):
                        os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
            after = resource.getrusage(resource.RUSAGE_CHILDREN)
            end_ns = time_ns()
    clock = {"exit_code": status, "reason": outcome, "wall_s": monotonic()-start, "resident_bytes": resident,
             "cpu_s": after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
             "input_blocks": after.ru_inblock-before.ru_inblock,
             "major_faults": after.ru_majflt-before.ru_majflt,
             "gate": event, "started_unix_ns": before_ns, "finished_unix_ns": end_ns}
    prior.write(area / "clock.json", clock)
    return clock


def watch(offer, pid, pin, case):
    from reports.ALGO08.v3.profiled_grid_export_admission import observe

    area = ROOT / offer
    ready = prior.read(prior.checked(ROOT / "ready.json", pin))
    prior.checked(ROOT / "sockets.bpf", ready["seccomp_sha256"])
    for name, expected in ready["code"].items():
        prior.checked(ROOT / "src/reports/ALGO08/v3" / name, expected)
    if (area / "worker.stdout").exists():
        raise ValueError("This offer has already used its numerical attempt")
    primary_pending()
    result = observe(lambda event: admit(offer, pid, ready, event), case, seconds=WATCH_SECONDS)
    prior.write(area / f"watch-{result['watching_from']}.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "smoke", "worker", "watch"))
    parser.add_argument("--offer", choices=OFFERS)
    parser.add_argument("--driver-pid", type=int)
    parser.add_argument("--ready-pin")
    parser.add_argument("--official-case")
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "watch":
        watch(args.offer, args.driver_pid, args.ready_pin, args.official_case)
    else:
        worker(args.offer, args.action == "smoke")
