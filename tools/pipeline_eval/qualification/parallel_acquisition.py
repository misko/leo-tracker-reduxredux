"""Release one recorded arrivals clock to two independent bounded detector processes."""

import argparse
import os
import socket
import subprocess
from contextlib import ExitStack, contextmanager
from fcntl import LOCK_EX, LOCK_UN, flock
from hashlib import sha256
from pathlib import Path
from struct import Struct
from time import monotonic_ns, process_time_ns, sleep

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json
from ..original_receiver import peak_selector_for
from ..variants.original_kernel import PersistentGrid
from . import arrival_queue as pace
from . import capture_exact_trial, capture_release, paced_original
from . import parallel_acquisition_source as staging
from .adaptive_arrival_worker import matching_clock
from .full_v5_check import _bind_producer, _sha
from .whole_memory_chain_worker import memory

MODULE = "tools.pipeline_eval.qualification.parallel_acquisition"
WORK = Path("/var/tmp/leo-pa-20261119")
ROLES = ("wide", "original")
BUDGET_S = 350
CAPACITY = 2  # One reservation for service and one independent waiting slot.
WORD = Struct("<q")
WIDE = dict(path=str(paced_original.WIDE_LIB), sha256=paced_original.WIDE_SHA)


def resource(cpu):
    info = memory()
    if (
        info["cpus"] != [cpu]
        or info["memory.swap.current"]
        or info["memory.events.oom"]
        or info["memory.events.oom_kill"]
    ):
        raise ValueError("process violated its measured CPU or zero-swap cgroup")
    return dict(info, monotonic_ns=monotonic_ns(), process_cpu_ns=process_time_ns())


def source_input(folder):
    spec = whole_iq.read(folder / "input.json")
    ready = whole_iq.read(folder / "ready.json")
    events = pace.readgz(whole_iq.checked(folder / "events.json.gz", spec["events_sha256"]))
    members = pace.readgz(
        whole_iq.checked(folder / "members.json.gz", ready["window_ledger_sha256"])
    )
    if (
        ready["case"] != spec["case"]
        or ready["raw_recording_sha256"] != spec["raw_recording_sha256"]
        or ready["bytes"] != spec["iq_bytes"]
        or len(members) != len(events)
        or len(events) != ready["windows"]
        or spec["last_arrival_ns"] != events[-1]["arrival_ns"]
    ):
        raise ValueError("ready source does not bind the same complete arrival clock")
    return spec, ready, events, members


def sample_file(folder, ready, stack):
    stream = stack.enter_context((folder / "samples.ci16").open("rb", buffering=0))
    st = os.fstat(stream.fileno())
    if (st.st_size, st.st_dev, st.st_ino, st.st_mtime_ns) != (
        ready["bytes"],
        ready["dev"],
        ready["inode"],
        ready["mtime_ns"],
    ) or st.st_mode & 0o222:
        raise ValueError("sample source differs from the read-only authenticated staging inode")
    return stream.fileno()


@contextmanager
def occupancy(fd):
    flock(fd, LOCK_EX)
    try:
        current = WORD.unpack(os.pread(fd, WORD.size, 0))[0]
        yield current
    finally:
        flock(fd, LOCK_UN)


def offer(fd, stream, visit):
    with occupancy(fd) as pending:
        if pending == CAPACITY:
            return False
        if not 0 <= pending < CAPACITY:
            raise ValueError("invalid detector FIFO state")
        os.pwrite(fd, WORD.pack(pending + 1), 0)
        stream.sendall(WORD.pack(visit))
    return True


def complete(fd):
    with occupancy(fd) as pending:
        if not 1 <= pending <= CAPACITY:
            raise ValueError("detector finished an unreserved visit")
        os.pwrite(fd, WORD.pack(pending - 1), 0)


def receive(stream):
    word = stream.recv(WORD.size)
    if len(word) != WORD.size:
        raise RuntimeError("detector stream closed without a terminal message")
    return WORD.unpack(word)[0]


def append(stream, row):
    stream.write(encoded(row).decode() + "\n")


def assigned_roles(event, selected_rf_hz):
    if event["status"] == "invalid_capture":
        return ()
    if event["status"] != "processed" or event["center_hz"] is None:
        raise ValueError("a valid stereo arrival needs a physical RF")
    if selected_rf_hz is None:
        return ROLES
    return ("original" if event["center_hz"] == selected_rf_hz else "wide",)


def admit(event, role, selected_rf_hz, fd, stream):
    if event["status"] == "invalid_capture":
        return "invalid_capture"
    if role not in assigned_roles(event, selected_rf_hz):
        return "unassigned"
    return "queued" if offer(fd, stream, event["visit"]) else "dropped_busy"


def publisher(work, folder):
    spec, ready, events, members = source_input(folder)
    plan = whole_iq.read(work / "plan.json")
    cpu = plan["cpus"]["publisher"]
    selected_rf_hz = plan.get("routing", {}).get("selected_rf_hz")
    startup = resource(cpu)
    stage_group = ready["end"]["cgroup"]
    with ExitStack() as stack:
        sample_file(folder, ready, stack)
        output = stack.enter_context((work / "source.jsonl").open("x", buffering=1))
        streams, counters = {}, {}
        for role in ROLES:
            listener = stack.enter_context(socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET))
            listener.bind(str(work / f"{role}.sock"))
            listener.listen(1)
            listener.settimeout(20)
            streams[role] = listener
            counter = stack.enter_context((work / f"{role}.count").open("xb+", buffering=0))
            counter.write(WORD.pack(0))
            counters[role] = counter.fileno()
        for role, listener in streams.items():
            stream, _ = listener.accept()
            streams[role] = stack.enter_context(stream)
            stream.settimeout(20)
            if receive(stream) != 0:
                raise ValueError("detector did not report its fully configured barrier")
        source_before = staging.spool.charge(stage_group)
        before = resource(cpu)
        origin = monotonic_ns() + 50_000_000
        for stream in streams.values():
            stream.sendall(WORD.pack(origin))
        save_json(work / "clock-start.json", dict(origin_ns=origin, before=before))
        for due, item in zip(events, members, strict=True):
            visit = due["visit"]
            target_ns = origin + due["arrival_ns"]
            sleep_ns = target_ns - monotonic_ns()
            if sleep_ns > 0:
                sleep(sleep_ns / pace.NS)
            if (
                due["delivery_clock"] != item["clock"]
                or due["sample_start"] != item["acquisition"]["sample_start"]
                or due["sample_end"] != item["acquisition"]["sample_end"]
                or visit != int(item["acquisition"]["global_visit"])
            ):
                raise ValueError("released physical event disagrees with the staged clock ledger")
            released = monotonic_ns() - origin
            outcomes = {}
            for role, stream in streams.items():
                outcomes[role] = dict(
                    admission=admit(due, role, selected_rf_hz, counters[role], stream),
                    offered_ns=monotonic_ns() - origin,
                )
            append(output, dict(visit=visit, released_ns=released, outcomes=outcomes))
        for stream in streams.values():
            stream.sendall(WORD.pack(-1))
        after = resource(cpu)
        source_after = staging.spool.charge(stage_group)
    save_json(
        work / "source-resources.json",
        dict(
            startup=startup,
            start=before,
            end=after,
            origin_ns=origin,
            last_release_ns=released,
            stage_charge=dict(start=source_before, end=source_after),
        ),
    )


def worker(work, folder, role):
    import numpy as np

    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import VerifiedFastWindow, analyze_window

    spec, ready, events, members = source_input(folder)
    plan = whole_iq.read(work / "plan.json")
    cpu = plan["cpus"][role]
    selected_rf_hz = plan.get("routing", {}).get("selected_rf_hz")
    startup = resource(cpu)
    capture = spec["capture"]
    policy = FastScanPolicyV2()
    producer = capture_release.producer(capture["case"], capture)
    bound = _bind_producer(capture["case"], producer, policy)
    with ExitStack() as stack:
        if role == "wide":
            detector = pace.build_native(capture, "control", dict(control=WIDE), stack)

            def process(frame):
                return pace.native_visit(frame, analyze_window, detector, policy)
        else:
            from leo.analysis.starlink import acquisition

            libraries = {
                name: whole_iq.checked(Path(row["path"]), row["sha256"])
                for name, row in plan["original_libraries"].items()
            }
            grid = PersistentGrid(libraries["prepared"])
            stack.callback(grid.clear_cache)
            stack.enter_context(capture_exact_trial.refiners(libraries))
            stack.enter_context(grid.route(acquisition, capture_exact_trial.starts.screen_module()))
            stack.enter_context(peak_selector_for(dict(plan, producer=spec["producer"])))

            def process(frame):
                return paced_original.original_visit(frame, analyze_window, policy, grid, True)

        source = sample_file(folder, ready, stack)
        output = stack.enter_context((work / f"{role}.jsonl").open("x", buffering=1))
        stream = stack.enter_context(socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET))
        endpoint = work / f"{role}.sock"
        until = monotonic_ns() + 20 * pace.NS
        while True:
            try:
                stream.connect(str(endpoint))
                break
            except (FileNotFoundError, ConnectionRefusedError):
                if monotonic_ns() >= until:
                    raise
                sleep(0.025)
        counter = stack.enter_context((work / f"{role}.count").open("r+b", buffering=0))
        before = resource(cpu)
        stream.sendall(WORD.pack(0))
        origin = receive(stream)
        last = -1
        while (visit := receive(stream)) != -1:
            start = monotonic_ns() - origin
            item = members[visit]
            shape = staging.spool.SHAPE
            width = staging.spool.WINDOW_BYTES
            payload = os.pread(source, width, width * visit)
            if len(payload) != width or sha256(payload).hexdigest() != item["iq_sha256"][7:]:
                raise ValueError("worker visit bytes differ from the authenticated recording")
            window = VerifiedFastWindow(
                item["sequence"],
                item["iq_sha256"],
                item["acquisition"],
                item["target"],
                np.frombuffer(payload, dtype="<i2").reshape(shape),
                sample_rate_hz=item["sample_rate_hz"],
            )
            frame = item["segment"], window, item["bracket"], item["clock"]
            matching_clock(frame, events[visit])
            if visit <= last or role not in assigned_roles(events[visit], selected_rf_hz):
                raise ValueError("detector received an invalid or reordered FIFO admission")
            packet, (native_wall, native_cpu) = process(frame)
            finish = monotonic_ns() - origin
            complete(counter.fileno())
            append(
                output,
                dict(
                    visit=visit,
                    start_ns=start,
                    finish_ns=finish,
                    native_wall_ns=native_wall,
                    native_cpu_ns=native_cpu,
                    packet=packet,
                ),
            )
            last = visit
        after = resource(cpu)
    save_json(
        work / f"{role}-resources.json",
        dict(startup=startup, start=before, end=after, origin_ns=origin, producer=bound),
    )


def launch(case_id, work, folder, *, cpus=None, prefix="leo-parallel", routing=None, selector=None):
    spec, _, events, _ = source_input(folder)
    if (
        spec["case"] != case_id
        or _sha(Path(spec["python"])) != spec["python_sha256"]
        or events[-1]["arrival_ns"] / pace.NS > BUDGET_S - 15
    ):
        raise ValueError("case, interpreter, or full recorded-clock limit changed")
    _, own = staging.original_reference(case_id)
    _, qualified = staging.original_reference("DS26-0237")
    libraries = dict(own["libraries"], prepared=qualified["libraries"]["prepared"])
    for row in [WIDE, *libraries.values()]:
        whole_iq.checked(Path(row["path"]), row["sha256"])
    work.mkdir(mode=0o755, parents=True)
    if cpus is None:
        cpus = staging.CPUS[case_id]
    if len(set(cpus)) != 3 or spec["cpu"] != cpus[2]:
        raise ValueError("publisher and source must share one core distinct from both workers")
    units = {role: f"{prefix}-{case_id.lower()}-{role}.service" for role in (*ROLES, "publisher")}
    extra = {} if routing is None else dict(routing=routing, peak_selector=selector)
    save_json(
        work / "plan.json",
        dict(
            original_libraries=libraries,
            wide_library=WIDE,
            units=units,
            cpus=dict(zip((*ROLES, "publisher"), cpus, strict=True)),
            scope=(
                "exclusive physical RF routing"
                if routing
                else "complete concurrent recorded-clock dual acquisition"
            ),
            waiting_slots=CAPACITY - 1,
            time_limit_s=BUDGET_S,
            memory_max=whole_iq.MEMORY,
            memory_swap_max=0,
            **extra,
        ),
    )
    for role, cpu in zip((*ROLES, "publisher"), cpus, strict=True):
        action, args = ("publisher", ()) if role == "publisher" else ("worker", (role,))
        subprocess.run(
            staging.service(
                units[role],
                whole_iq.MEMORY,
                BUDGET_S,
                cpu,
                spec["producer"],
                spec["python"],
                MODULE,
                action,
                work,
                folder,
                *args,
            ),
            check=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "publisher", "worker"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("folder", type=local_output)
    parser.add_argument("argument", nargs="?")
    args = parser.parse_args()
    if args.action == "launch":
        launch(args.argument, args.work, args.folder)
    elif args.action == "publisher":
        publisher(args.work, args.folder)
    else:
        worker(args.work, args.folder, args.argument)
