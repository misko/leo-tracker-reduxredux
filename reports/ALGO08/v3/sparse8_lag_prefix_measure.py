"""One quiet-slot sparse8 callback comparison on the two detached signed fixtures."""

import argparse
from collections import Counter, deque
from contextlib import ExitStack
import ctypes as ct
import fcntl
import json
import os
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from statistics import median
import subprocess
import sys
from time import monotonic, process_time_ns, sleep

from . import sparse8_native_profile as sparse


CASES = {"DS30-0163": (36, 10), "DS30-0419": (6, 4)}
NAMES = ("control", "candidate")
REPEATS = 6
LIMIT_S = 12


def book(build, pin):
    data = json.loads(sparse.checked(build / "build.json", pin))
    arms = data["arms"]
    if (arms["control"]["sha256"]["library"] != sparse.ORIGINAL or set(arms) != set(NAMES)
            or any(x["training_sha256"] != sparse.TRAIN_ROWS or x["training_calls"] != 32 for x in arms.values())):
        raise ValueError("Require faithful separately trained PGO arms and an exact installed control")
    bodies = {}
    for case in CASES:
        origin = sparse.OPERANDS / case
        meta = json.loads(sparse.checked(origin / "visits.json", sparse.CUSTODY[case]))
        if meta["verified_file"]["name"] != "verified.ci16":
            raise ValueError("Unexpected waveform topology")
        bodies[case] = origin / "verified.ci16"
    libraries = {key: Path(arms[key]["paths"]["library"]) for key in NAMES}
    assets = {edge: build / "assets" / (edge + ".f32") for edge in sparse.PILOTS}
    return arms, bodies, libraries, assets


def allowed_inputs(event, params, bodies):
    if event in ("socket.connect", "socket.getaddrinfo"):
        raise ValueError("Detached short callback trial is offline")
    if event != "open" or not isinstance(params[0], (str, bytes, os.PathLike)):
        return
    path = Path(os.path.abspath(os.fsdecode(params[0])))
    if (path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01")
            or path.suffix in (".ci16", ".zst", ".tle") and path not in bodies):
        raise ValueError(f"Detached short callback trial cannot open backing input {path}")
    if path in bodies and params[2] & (os.O_WRONLY | os.O_RDWR):
        raise ValueError("Use the private detached original bytes read-only")


def runtime_footprint(bodies, libraries, assets):
    paths = [*bodies.values(), *libraries.values(), *assets.values()]
    device = Path("/tmp").stat().st_dev
    if any(p.resolve(strict=True) != p or p.stat().st_dev != device for p in paths):
        raise ValueError("Detached input, immutable DSOs and pilot assets must be in tmpfs")
    rows = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,PAGES,SIZE,FILE",
                                               *paths]))["fincore"]
    if len(rows) != len(paths) or any(row["res"] < row["size"] for row in rows):
        raise ValueError("The detached fixture and its native setup must be fully resident")
    return rows


def summary(records):
    def section(rows):
        batches = []
        for round_ in range(REPEATS):
            batch = [row for row in rows if row["round"] == round_]
            if batch:
                parts = {key: sum(r["cpu_ns"][key] for r in batch) / len(batch) for key in NAMES}
                batches.append(dict(round=round_, lanes=len(batch), **parts))
        return dict(total_pairs=len(rows), rounds=batches,
                    median_cpu_ns={key: median(r[key] for r in batches) for key in NAMES} if batches else {},
                    median_paired_saving_ns=median(r["control"] - r["candidate"] for r in batches) if batches else None)

    return {outcome: dict(all_orders=section(rows),
                          by_first={arm: section([r for r in rows if r["first"] == arm]) for arm in NAMES})
            for outcome, rows in (("all", records), ("positive", [r for r in records if r["factor_hex"]]),
                                  ("empty", [r for r in records if not r["factor_hex"]]))}


def measure(arms, libraries, assets, began):
    pilot, results = {}, {}
    for edge, path in assets.items():
        payload = sparse.checked(path, sparse.PILOTS[edge])
        pilot[edge] = ct.create_string_buffer(payload)
    with ExitStack() as stack:
        engines = {}
        for name, path in libraries.items():
            sparse.checked(path, arms[name]["sha256"]["library"])
            for edge, asset in pilot.items():
                instance = sparse.Receiver(path, ct.addressof(asset), False)
                stack.callback(instance.close)
                engines[name, edge] = instance
        for case, expected in CASES.items():
            visits, custody = sparse.fixture(case, stack)
            rows, unique = [], {}
            for repeat in range(REPEATS):
                for index, (visit, edge, center, address, window_sha) in enumerate(visits):
                    for lane in (0, 1):
                        order = NAMES if (repeat + index + lane) % 2 == 0 else NAMES[::-1]
                        factor, cpu = {}, {}
                        for arm in order:
                            result, clock = engines[arm, edge].run(address, lane, center, False)
                            factor[arm], cpu[arm] = result.hex(), clock[0]
                        if factor["control"] != factor["candidate"]:
                            raise ValueError(f"Native signed factor differs at {case} visit {visit}, lane {lane}")
                        wire = factor["control"]
                        if unique.setdefault((visit, lane), wire) != wire:
                            raise ValueError("An original lane shifted across independent matched repeats")
                        rows.append(dict(round=repeat, visit=visit, lane=lane, first=order[0], cpu_ns=cpu,
                                         factor_hex=wire, original_window_sha256=window_sha))
            if (len(unique), sum(bool(wire) for wire in unique.values())) != expected:
                raise ValueError("The original signed short-lane schedule or positivity changed")
            results[case] = dict(custody=custody, rows=rows, summary=summary(rows))
    return dict(cases=results, duration_s=monotonic()-began)


def take(output, build, pin):
    from ds30_paired_evaluation import quiet_window, storage_sample
    from . import empty_lane_directed_replay as admission
    from . import empty_lane_directed_watch as watch

    if os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) < 15:
        raise ValueError("Only the low-priority CPU2 worker may execute a comparison")
    arms, bodies, libraries, assets = book(build, pin)
    sys.addaudithook(lambda event, params: allowed_inputs(event, params, set(bodies.values())))
    event, deferred = admission.prefix.occupied()
    if not deferred or watch.FIELD_SLEEP_S - event["age_s"] < LIMIT_S + 5:
        admission.prefix.write(output, dict(admitted=False, reason="no-fresh-field-deferral", event=event))
        return 75
    with admission.LOCK.open("r") as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            admission.prefix.write(output, dict(admitted=False, reason="lease-in-use"))
            return 75
        quiet, storage = quiet_window()
        before = runtime_footprint(bodies, libraries, assets)
        event, deferred = admission.prefix.occupied()
        if not quiet or not deferred:
            admission.prefix.write(output, dict(admitted=False, reason="ordinary-quiet-recheck", event=event,
                                                storage_before=storage, residency=before))
            return 75
        usage, start, cpu = getrusage(RUSAGE_SELF), monotonic(), process_time_ns()
        result = measure(arms, libraries, assets, start)
        final_usage = getrusage(RUSAGE_SELF)
        admission.prefix.write(output, dict(admitted=True, build_sha256=pin, event=event, storage_before=storage,
                                            storage_after=storage_sample(), before=before,
                                            after=runtime_footprint(bodies, libraries, assets),
                                            measured_cpu_ns=process_time_ns()-cpu,
                                            measured_input_blocks=final_usage.ru_inblock-usage.ru_inblock,
                                            measured_major_faults=final_usage.ru_majflt-usage.ru_majflt, **result))
    return 0


def wait(output, build, pin):
    from ds30_paired_evaluation import storage_sample
    from . import empty_lane_directed_replay as admission
    from . import empty_lane_directed_watch as watch

    _, bodies, libraries, assets = book(build, pin)
    samples, counts, last = deque(maxlen=4), Counter(), {}
    deadline = monotonic()+180.
    while monotonic() < deadline:
        event, fresh = admission.prefix.occupied()
        storage = storage_sample()
        rolling = next((pair for earlier in reversed(samples) if (pair := watch.rolling_window(earlier, storage))), None)
        samples.append(storage)
        busy = fresh and watch.lock_present(admission.LOCK, Path("/proc/locks").read_text())
        reason = watch.eligible(event, fresh, storage, busy, rolling)
        sample = dict(event=event, storage=storage, rolling=rolling, lease_busy=busy)
        if reason is None:
            residency = runtime_footprint(bodies, libraries, assets)
            if monotonic() >= deadline:
                break
            argv = ["/usr/bin/time", "-f", "elapsed=%e user=%U system=%S rss_kib=%M input_blocks=%I exit=%x",
                    "-o", str(output / "process.txt"), "timeout", "-k", "1s", f"{LIMIT_S}s",
                    sys.executable, "-B", "-m", "reports.ALGO08.v3.sparse8_lag_prefix_measure", "take",
                    str(output / "native.json"), str(build), pin]
            result = subprocess.run(argv, capture_output=True, text=True)
            admission.prefix.write(output / "watch.json", dict(launched=True, exit=result.returncode, **sample,
                                                residency=residency, polls=dict(counts), stdout=result.stdout,
                                                stderr=result.stderr))
            return result.returncode
        counts[reason] += 1
        last[reason] = sample
        sleep(max(0., min(1., deadline-monotonic())))
    admission.prefix.write(output / "watch.json", dict(launched=False, polls=dict(counts), last_refusals=last))
    return 75


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("take", "watch"))
    parser.add_argument("output", type=Path)
    parser.add_argument("build", type=Path)
    parser.add_argument("build_sha256")
    args = parser.parse_args()
    if args.stage == "watch":
        args.output.mkdir()
        sys.exit(wait(args.output, args.build, args.build_sha256))
    sys.exit(take(args.output, args.build, args.build_sha256))
