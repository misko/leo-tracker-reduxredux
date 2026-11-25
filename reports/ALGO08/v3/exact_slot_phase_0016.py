"""Prepare, admit and verify the opposite-order, acceleration-only original pair."""

import argparse
from copy import deepcopy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
from time import monotonic, process_time, time_ns

from . import short_shared_phase_0016 as phase


CASE = phase.CASE
ORDER = ("combined", "ordinary")
DONOR = Path("/tmp/leo-v3-shared-phase-0016-05")
DONOR_READY = "fc3f70aa34f67f53d0e8d5bc7aaf4ce86d036e46517a385ab56eb561eda48499"
DONOR_BUILD = "d64d94a56121b449c923705a4ce2a4c9b7fd9324757d5c5ae0a85a95804a82a0"
SHORT = "279d994ef8a666df93fae83f9f7b8c5797278ddb3dcbe229f5bfc9cb7ff502ad"
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PROTOCOL = HERE / "exact-slot-phase-0016-protocol.md"
VERIFIER = HERE / "combined_small_panel_score.py"
PREFIX = "reports/ALGO08/v3/"
SWITCH = "--reuse-prefetched-snapshots"
INDEXES = {
    (0, "windows-000003.jsonl"): (173187, "1d6c96e627299d8d201054c0c75115d316cc5f865967bfc80d0f1c3c0de78732"),
    (1, "windows-000000.jsonl"): (173244, "2ae18be4677352c146c6b0051b95094213d24abe921fbe958a5e8316961cd459"),
    (1, "windows-000003.jsonl"): (173290, "de2362f1a5c65b8ebfd15d41ead5b888a0fa2f392c4afb54cf7ddcc012d0f81e"),
}
INDEX_CAP = 36864


def build_delta(ordinary, guarded, owned, check_slots):
    phase_sources = {PREFIX + name for name in ("full_short_run.py", "eight_ms_native_receiver.py")}
    if {k: v for k, v in ordinary.items() if k not in ("native", "sources")} != {
        k: v for k, v in guarded.items() if k not in ("native", "sources")
    } or guarded["native"] != ordinary["native"] | {
        "--short-binary": dict(path=str(DONOR / "shared.so"), sha256=SHORT)
    }:
        raise ValueError("The guarded donor changed charted assets beyond the short verifier")
    a, b = ordinary["sources"], guarded["sources"]
    if a.keys() != b.keys() or {name for name in a if a[name] != b[name]} != phase_sources:
        raise ValueError("The guarded donor changed sources beyond the two recipe modules")
    slots = check_slots(ordinary, owned)
    if slots & phase_sources:
        raise ValueError("Guarded phase and buffer substitutions overlap")
    build = deepcopy(guarded)
    build["sources"].update({name: owned["sources"][name] for name in slots})
    return build, phase_sources, slots


def controller_pins(panel):
    return {file.name: panel.digest(file.read_bytes()) for file in
            (PROTOCOL, VERIFIER, Path(__file__).resolve(), Path(phase.__file__).resolve())}


def scratch(path, *, inodes=1024):
    info = path.stat()
    size = os.statvfs(path)
    receipt = dict(device=info.st_dev, free_bytes=size.f_bavail * size.f_frsize, free_inodes=size.f_favail)
    if receipt["free_bytes"] < 256 * 1024**2 or receipt["free_inodes"] < inodes:
        raise ValueError("The private scratch lacks the registered output headroom")
    return receipt


def invoke(panel, root, inputs, role, build, work, *, verify=False):
    runtime = DONOR if role == "combined" else phase.OLD_READY
    extra = [SWITCH] if role == "combined" else []
    if verify:
        extra.append("--verify")
    command = panel.command(runtime, CASE, work, inputs, "charted", extra, meter=True)
    command[command.index("--build-sha256") + 1] = build
    if role == "combined":
        command[command.index("--build") + 1] = str(root / "charted-build.json")
        mount = command.index("--remount-ro")
        command[mount:mount] = ["--ro-bind", str(root / "worker-sources"), str(DONOR / "charted" / PREFIX)]
    return command


def prepare(root):
    start = monotonic(), process_time()
    panel, old = phase.load_panel()
    phase.check_controller(panel, old)
    inputs = old["cases"][CASE]
    donor = json.loads(panel.check(DONOR / "ready.json", DONOR_READY))
    if (donor["input"] != inputs or donor["build"] != DONOR_BUILD
            or donor["identities"]["short"] != SHORT or donor["preflight"] != inputs["preflight"]["charted"]):
        raise ValueError("The qualifying trial or original enrollment changed")
    panel.check(DONOR / "shared.so", SHORT)
    ordinary = json.loads(panel.check(phase.OLD_READY / "charted-build.json", panel.CONTROL))
    phase_build = json.loads(panel.check(DONOR / "charted-build.json", DONOR_BUILD))
    owned = json.loads(panel.check(phase.OLD_READY / "trial-build.json", panel.TRIAL))
    build, phase_sources, slots = build_delta(ordinary, phase_build, owned, panel.checked_source_delta)
    ctl_held = json.loads(panel.check(phase.CHARTED / "publication-held-anchor-route.json", phase.OLD_SELECTOR))
    base, held = phase.pins(SHORT, ctl_held["receiver_recipe"])
    if donor["identities"] != dict(base=base, held=held, short=SHORT):
        raise ValueError("Held receiver recipes differ from the qualifying run")
    for source in sorted(phase_sources):
        panel.check(DONOR / "charted" / source, phase_build["sources"][source])

    # Cross-file copies are limited to already pinned private source files.
    staged_sources = {name: panel.check(phase.OLD_READY / "trial" / name, owned["sources"][name])
                      for name in slots}
    donor_sources = DONOR / "charted" / PREFIX
    before = scratch(root.parent, inodes=1024+sum(1 for _ in donor_sources.rglob("*"))+32)
    if before["device"] != DONOR.stat().st_dev or root.parent != Path("/tmp"):
        raise ValueError("Use a fresh /tmp sibling of the qualified runtime for the hardlink tree")
    root.mkdir(mode=0o700)
    shutil.copytree(donor_sources, root / "worker-sources", copy_function=os.link)
    for name, body in staged_sources.items():
        path = root / "worker-sources" / name.removeprefix(PREFIX)
        path.unlink(missing_ok=True)
        with path.open("xb") as file:
            file.write(body)
    panel.check(DONOR / (CASE + "-authority.json"), inputs["authority_sha256"])
    builds = dict(combined=panel.write(root / "charted-build.json", build), ordinary=panel.CONTROL)

    verified = {}
    for role in ORDER:
        work = panel.new_work(root / ("build-verify-" + role))
        command = invoke(panel, root, inputs, role, builds[role], work, verify=True)
        result = panel.check_command(command)
        if result != dict(schema=build["schema"], charted_commit=build["charted_commit"],
                          build_sha256=builds[role]) or (work / "publication").exists():
            raise ValueError("The build-only entry produced an unexpected result")
        verified[role] = dict(result=result, numeric_process=json.loads((work / "numeric-process.json").read_bytes()))

    residency = panel.residency(inputs["files"])
    try:
        source = panel.bounded_natural_source(residency, Path(inputs["staged"]), page=os.sysconf("SC_PAGE_SIZE"))
        eligibility = dict(status="pass", residency=source)
    except ValueError as failure:
        eligibility = dict(status="refused", reason=str(failure), residency=residency)
    finish = scratch(root)
    ready = dict(order=ORDER, inputs=inputs, builds=builds, controller=controller_pins(panel),
                 donors=dict(guarded=DONOR_BUILD, guarded_ready=DONOR_READY, owned=panel.TRIAL, short=SHORT),
                 source_changes=sorted(phase_sources | slots), identities=donor["identities"],
                 build_checks=verified, eligibility=eligibility, scratch=dict(before=before, after=finish),
                 prep_wall_s=monotonic()-start[0], prep_cpu_s=process_time()-start[1])
    return panel.write(root / "ready.json", ready)


def read_ready(root, pin):
    panel, old = phase.load_panel()
    ready = json.loads(panel.check(root / "ready.json", pin))
    if (ready["order"] != list(ORDER) or ready["inputs"] != old["cases"][CASE]
            or ready["controller"] != controller_pins(panel)):
        raise ValueError("The registered executable, order or custody changed")
    return panel, ready


def preparation_scope(panel, inputs, residency, *, page):
    staged = Path(inputs["staged"])
    files = {Path(name) for name in inputs["files"]}
    targets = {}
    for (segment, name), spec in INDEXES.items():
        path = staged / f"{staged.name}-segment-{segment:08d}" / name
        if path not in files:
            raise ValueError("The approved index is outside the enrolled custody")
        targets[str(path)] = spec
    indexes, other = [], []
    for row in residency["nonresident"]:
        if row["file"] in targets:
            if row["size"] != targets[row["file"]][0]:
                raise ValueError("An enrolled index changed extent")
            indexes.append(row)
        else:
            other.append(row)
    panel.bounded_natural_source(dict(residency, nonresident=other), staged, page=page)
    missing = sum(((row["size"]+page-1)//page)*page-row["res"] for row in indexes)
    if not 0 <= missing <= INDEX_CAP:
        raise ValueError("The sealed index preparation exceeds 36,864 nonresident bytes")
    return targets if missing else {}, missing


def same_local_swap():
    active = [line.split()[:2] for line in Path("/proc/swaps").read_text().splitlines()[1:]]
    if active != [["/swap.img", "file"]] or Path("/swap.img").stat().st_dev != Path("/").stat().st_dev:
        raise ValueError("Index preparation requires the verified local root swap file")
    root_device = subprocess.check_output(["findmnt", "-n", "-o", "SOURCE", "-T", "/swap.img"], text=True).strip()
    leaves = subprocess.check_output(["lsblk", "-s", "-nlpo", "NAME,TYPE", root_device], text=True).splitlines()
    disks = [line.split()[0] for line in leaves if line.split()[-1] == "disk"]
    if disks != ["/dev/nvme0n1"]:
        raise ValueError("The enrolled swap device is not the independent root NVMe")
    return dict(file="/swap.img", root_device=root_device, physical=disks[0])


def read_index(panel, path, size, pin):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW), "rb") as file:
        first = os.fstat(file.fileno())
        if first.st_dev != Path("/dev/shm").stat().st_dev or first.st_size != size:
            raise ValueError("Prepared index is not its signed private tmpfs extent")
        body = file.read(size+1)
        last = os.fstat(file.fileno())
    if (len(body) != size or panel.digest(body) != pin or first.st_ino != last.st_ino
            or first.st_size != last.st_size or first.st_mtime_ns != last.st_mtime_ns
            or first.st_ctime_ns != last.st_ctime_ns):
        raise ValueError("Prepared index failed signed snapshot verification")
    return dict(path=path, bytes=size, sha256=pin)


def prepare_indexes(root, pin, pid):
    from .profiled_grid_export_admission import observe

    panel, ready = read_ready(root, pin)
    inputs = ready["inputs"]
    intent = root / "index-preparation-intent.json"
    result = root / "index-preparation.json"
    if intent.exists() or result.exists() or any((root / role).exists() for role in ORDER):
        raise ValueError("The one-time index preparation is spent or a raw arm already started")
    panel.check(panel.DRIVER, panel.DRIVER_PIN)
    swap = same_local_swap()
    preparation_scope(panel, inputs, panel.residency(inputs["files"]), page=os.sysconf("SC_PAGE_SIZE"))

    def launch(event):
        with panel.LOCK.open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            before = panel.residency(inputs["files"])
            targets, missing = preparation_scope(panel, inputs, before, page=os.sysconf("SC_PAGE_SIZE"))
            panel.driver_window(event, pid, 0, CASE, pending_0218=False)
            panel.write(intent, dict(event=event, targets=targets, missing_page_bytes=missing, swap=swap,
                                     before=before, ready_sha256=pin))
            start, cpu, usage = monotonic(), process_time(), resource.getrusage(resource.RUSAGE_SELF)
            receipts, failure = [], None
            try:
                for path, (size, digest) in targets.items():
                    receipts.append(read_index(panel, path, size, digest))
            except (OSError, ValueError) as error:
                failure = str(error)
            after = resource.getrusage(resource.RUSAGE_SELF)
            clock = dict(wall_s=monotonic()-start, cpu_s=process_time()-cpu, major_faults=after.ru_majflt-usage.ru_majflt,
                         minor_faults=after.ru_minflt-usage.ru_minflt, input_blocks=after.ru_inblock-usage.ru_inblock,
                         finished_unix_ns=time_ns())
        observed = panel.residency(inputs["files"])
        try:
            panel.bounded_natural_source(observed, Path(inputs["staged"]), page=os.sysconf("SC_PAGE_SIZE"))
        except ValueError as error:
            failure = failure or str(error)
        report = dict(status="refused" if failure else "ready", reason=failure, after=observed,
                      reads=receipts, read_clock=clock, event=event, lease_and_preparation_completed_unix_ns=time_ns())
        return report | dict(receipt_sha256=panel.write(result, report))

    return observe(launch, None)


def watch(root, pin, role, pid):
    from .profiled_grid_export_admission import observe

    panel, ready = read_ready(root, pin)
    inputs = ready["inputs"]
    work = root / role
    if work.exists():
        raise ValueError("The cell's only launched attempt has already been used")
    preparation = root / "index-preparation.json"
    last_finish = 0
    if (root / "index-preparation-intent.json").exists():
        prep = json.loads(preparation.read_bytes())
        if prep["status"] != "ready":
            raise ValueError("The single approved index preparation failed")
        last_finish = prep["lease_and_preparation_completed_unix_ns"]
    if role == "ordinary":
        previous = root / "combined"
        clock = json.loads((previous / "process.json").read_bytes())
        if clock["exit_code"] or clock["timed_out"] or not (previous / "verified.json").is_file():
            raise ValueError("Require the successful, independently verified first cell")
        last_finish = clock["finished_unix_ns"]
    elif (root / "ordinary").exists():
        raise ValueError("The enrolled order is combined first")
    panel.check(panel.DRIVER, panel.DRIVER_PIN)
    scratch(root)
    panel.source_before(inputs, True)

    def launch(event):
        with panel.LOCK.open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            before = panel.source_before(inputs, True)
            panel.driver_window(event, pid, last_finish, CASE, pending_0218=False)
            panel.new_work(work)
            command = ["/usr/bin/taskset", "-c", "2", "/usr/bin/ionice", "-c2", "-n7",
                       *invoke(panel, root, inputs, role, ready["builds"][role], work)]
            panel.write(work / "launch.json", dict(command=command, event=event, before=before, ready_sha256=pin))
            process = panel.paired.child(command, work, panel.CAP_SECONDS[CASE], lock.fileno())
            panel.write(work / "process.json", process)
        after = panel.residency(inputs["files"])
        panel.write(work / "source-after.json", after)
        return dict(status="completed_one_child", process=process, event=event, before=before, after=after)

    return observe(launch, None)


def verify_publication(root, pin, role):
    panel, ready = read_ready(root, pin)
    work = root / role
    spec = importlib.util.spec_from_file_location("exact_slot_phase_verifier", VERIFIER)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    clock = json.loads((work / "process.json").read_bytes())
    answer = verifier.checked_publication(work, "charted", CASE, ready["inputs"], clock,
                                          build_pin=ready["builds"][role], allow_snapshot_witness=True)
    return panel.write(work / "verified.json", answer)


def verify(root, pin, role):
    panel, _ = read_ready(root, pin)
    work = root / role
    command = [panel.paired.PYTHON, "-B", "-m", __spec__.name, "verify-child", root, "--pin", pin, "--role", role]
    before, start = resource.getrusage(resource.RUSAGE_CHILDREN), monotonic()
    child = subprocess.run(command, cwd=REPO, env=panel.paired.environment(work),
                           capture_output=True, text=True, check=False, timeout=30)
    duration, after = monotonic()-start, resource.getrusage(resource.RUSAGE_CHILDREN)
    meter = dict(wall_s=duration, cpu_s=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                 major_faults=after.ru_majflt-before.ru_majflt, minor_faults=after.ru_minflt-before.ru_minflt,
                 input_blocks=after.ru_inblock-before.ru_inblock, exit_code=child.returncode,
                 verified_sha256=child.stdout.strip() if child.returncode == 0 else None)
    if child.returncode:
        meter["stderr"] = child.stderr
    return panel.write(work / "verify-process.json", meter)


def compare(ordinary, combined, control_packet, trial_packet, enroll, identities):
    packet = phase.packet_delta(control_packet, trial_packet, enroll)
    if packet["lanes"] != dict(anchor=186, short=1240) or packet["positives"] != dict(anchor=74, short=432):
        raise ValueError("The enrolled 20/8 opportunity schedule changed")
    native_before, native_after = (item["receiver_audit"]["native"] for item in (ordinary, combined))
    excluded = {"native_cpu_ns", "native_wall_ns", "short_primary_sha256"}
    if ({key: value for key, value in native_before.items() if key not in excluded} !=
            {key: value for key, value in native_after.items() if key not in excluded}
            or native_after["short_primary_sha256"] != SHORT
            or dict(ordinary["recipe"], shortened_sha256=SHORT) != combined["recipe"]
            or any(ordinary["prefetch"][key] != combined["prefetch"][key]
                   for key in ("submitted", "submitted_bytes"))):
        raise ValueError("Ordinary aperture, held recipe or charged lookahead changed")
    science = phase.science(ordinary, combined)
    if any(science["numeric_max_abs_delta"].values()) or not all(row["bytes_identical"] for row in science["media"]):
        raise ValueError("Exact ordinary scientific products or PNG bytes changed")
    return dict(packet=packet, science=science, identities=identities)


def score(root, pin):
    from .anchor_exposure import enroll

    panel, ready = read_ready(root, pin)
    records, packets, selectors, clocks = {}, {}, {}, {}
    for role in ORDER:
        work = root / role
        verifier = json.loads((work / "verify-process.json").read_bytes())
        if verifier["exit_code"] or not verifier["verified_sha256"]:
            raise ValueError("Both fresh verifiers must have exited successfully")
        row = records[role] = json.loads(panel.check(work / "verified.json", verifier["verified_sha256"]))
        output = work / "publication"
        (packet,) = (output / "fast-scan-automatic-work").glob("*/detections.json")
        packets[role] = json.loads(panel.check(packet, row["native_sha256"]))
        selectors[role] = json.loads((work / "publication-held-anchor-route.json").read_bytes())
        path = output / "prefetch-snapshots.json"
        if role == "combined":
            witness = row["slots"] = json.loads(path.read_bytes())
            build = json.loads(panel.check(root / "charted-build.json", ready["builds"][role]))
            slot_pins = {name: build["sources"][PREFIX + name] for name in
                         ("prefetch_snapshots.py", "legacy_snapshot_reuse.py")}
            if (witness["native_sha256"] != row["native_sha256"] or witness["statistics"] != row["prefetch"]
                    or witness["source_sha256"] != slot_pins or len(witness["slots"]) != 2
                    or not all(slot.get("reuses", 0) > 0 for slot in witness["slots"])):
                raise ValueError("The paid combined arm did not use its qualified slots")
        elif path.exists():
            raise ValueError("The ordinary arm emitted an unexpected private slot witness")
        clocks[role] = dict(raw=row["process"], worker=row["numeric_process"], verification=verifier,
                            through_verified_wall_s=row["process"]["elapsed_s"]+verifier["wall_s"],
                            through_verified_cpu_s=row["numeric_process"]["cpu_s"]+verifier["cpu_s"])
    before, after = (selectors[role] for role in ("ordinary", "combined"))
    ids = ready["identities"]
    if (after["choice"]["route"] != "unfiltered" or after["choice"]["route"] != before["choice"]["route"]
            or after["parent_detector_sha256"] != "sha256:"+ids["base"]
            or after["detector_recipe_sha256"] != "sha256:"+ids["held"]
            or any(before[key] != after[key] for key in ("observed", "selected", "refinement_calls", "would_refine",
                                                        "would_refine_by_radio", "would_refine_stereo_visits"))):
        raise ValueError("Held history or continuation changed")
    result = compare(records["ordinary"], records["combined"], packets["ordinary"], packets["combined"],
                     enroll, ids)
    return panel.write(root / "score.json", result | dict(publications=records, clocks=clocks, ready_sha256=pin))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "prepare-indexes", "watch", "verify", "verify-child", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--pin")
    parser.add_argument("--role", choices=ORDER)
    parser.add_argument("--pid", type=int)
    args = parser.parse_args()
    if os.sched_getaffinity(0) != {3} or os.nice(0) < 15:
        parser.error("Use low-priority CPU3 for the controller and verifier")
    if args.action != "prepare" and not args.pin:
        parser.error("Supply the qualified ready pin")
    if args.action in ("watch", "verify", "verify-child") and not args.role:
        parser.error("Supply its enrolled role")
    if args.action in ("prepare-indexes", "watch") and not args.pid:
        parser.error("Supply the live official driver PID")
    if args.action == "prepare":
        result = prepare(args.root)
    elif args.action == "prepare-indexes":
        result = json.dumps(prepare_indexes(args.root, args.pin, args.pid))
    elif args.action == "watch":
        result = json.dumps(watch(args.root, args.pin, args.role, args.pid))
    elif args.action == "verify":
        result = verify(args.root, args.pin, args.role)
    elif args.action == "verify-child":
        result = verify_publication(args.root, args.pin, args.role)
    else:
        result = score(args.root, args.pin)
    print(result)


if __name__ == "__main__":
    main()
