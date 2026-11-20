"""Exercise the original full and timed peer-retry branches on chronological saved IQ."""

import argparse
import json
import subprocess
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch
from uuid import uuid4

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json
from ..variants.original_kernel import PersistentGrid
from ..variants.retry_cadence import RetryCadence
from ..variants.selective_capture import visit_pairs
from . import field_exact_waveform as field
from .capture_detector_replay import scan_capture_window
from .full_v5_check import _sha

CASES = ("DS26-0237", "DS29-0082")
CPUS = (12, 16)
MODES = ("full", "miss", "hit")
ROUNDS = 2
VISITS = 64
LIMIT = 720
REPORT = field.REPORT.parents[1] / "retry-and-transfer/cadence-waveform"
WORK = Path("/var/tmp/leo-cadence-waveform-20261119-A")
MODULE = "tools.pipeline_eval.qualification.cadence_waveform"
base = field.base


def choose_spans(ident, chunks, excluded, count):
    """Select one complete physical chunk per half by hash and valid coverage."""

    def score(span):
        return sha256(encoded([ident, "retry-cadence-waveform-v1", span])).digest()

    result = []
    for half in (0, 1):
        candidates = [
            s
            for s in chunks
            if (s[3] + s[1] >= count // 2) == bool(half)
            and s[2] - s[1] == VISITS
            and sum(v not in excluded for v in range(s[3] + s[1], s[3] + s[2])) >= VISITS // 2
        ]
        result.append(min(candidates, key=score))
    return result


def freeze(work, cpus):
    from . import retry_cadence_trial as schedules
    from .fresh_replay_results import sealed

    if work.exists() or (REPORT / "plan.json").exists():
        raise FileExistsError("choose a new waveform experiment scope")
    fine = sealed(field.PANEL, "qualification-lock.json", field.PANEL_SHA)
    fine_lock = whole_iq.read(
        whole_iq.checked(field.PANEL / "input-lock.json", fine["files"]["input-lock.json"])
    )
    work.mkdir(mode=0o755)
    REPORT.mkdir(exist_ok=True)
    files = {}
    for ident, cpu in zip(CASES, cpus, strict=True):
        doc, primary, lock, _ = schedules.sources(ident)
        cfg = fine_lock["cases"][ident]
        if (
            (cfg["root"], cfg["edge"], cfg["input_manifest"], cfg["archive_sha256"])
            != (
                lock["producer"],
                lock["capture"]["edge"],
                lock["capture"]["input_manifest_sha256"],
                lock["original"]["native"]["sha256"],
            )
            or lock["python_sha256"] != fine_lock["python_sha256"]
            or any(fine_lock["libs"][k] != v for k, v in lock["libraries"].items())
        ):
            raise ValueError("the exact shared fine kernel was qualified on another producer")
        chunks = sorted(s for _, _, spans in lock["workers"] for s in spans)
        excluded = {r["visit"]: r for r in doc["provenance"]["excluded_windows"]}
        clocks = doc["delivery_clocks"]
        spans = choose_spans(ident, chunks, excluded, len(clocks))
        scope = {visit for _, a, b, base_id in spans for visit in range(base_id + a, base_id + b)}
        bindings = dict(
            full=dict(visit_pairs(doc["source"]["probes"])),
            primary=dict(visit_pairs(primary["source"]["probes"])),
        )
        refs = {
            str(v): dict(
                delivery_clock=clocks[v],
                excluded=excluded.get(v),
                **{mode: rows.get(v) for mode, rows in bindings.items()},
            )
            for v in sorted(scope)
        }
        sources = lock["sources"] | fine_lock["sources"] | cfg["sources"]
        sources.update(
            {
                str(p): _sha(p)
                for p in (
                    Path(__file__),
                    Path(RetryCadence.observed.__code__.co_filename),
                    REPORT / "PROTOCOL.md",
                )
            }
        )
        for p, d in sources.items():
            whole_iq.checked(Path(p), d)
        lock.update(
            cpus=[cpu],
            spans=spans,
            libraries=fine_lock["libs"],
            sources={p: d for p, d in sources.items() if Path(p).stat().st_mode & 0o004},
            reference=refs,
            reference_parent=schedules.PARENTS[ident],
        )
        path = work / f"{ident}.json"
        save_json(path, lock)
        path.chmod(0o644)
        files[path.name] = _sha(path)
        print(ident, "CPU", cpu, "spans", spans, flush=True)
    plan = dict(
        cases=list(CASES),
        cpus=list(cpus),
        rounds=ROUNDS,
        modes=list(MODES),
        interval_ns=2_000_000_000,
        initial_state="cold per mode, round and span",
        files=files,
    )
    for p in (work / "plan.json", REPORT / "plan.json"):
        save_json(p, plan)
        p.chmod(0o644)


def configure(work, ident):
    local = work / "plan.json"
    plan = whole_iq.read(whole_iq.checked(local, _sha(REPORT / local.name)))
    name = f"{ident}.json"
    lock = whole_iq.read(whole_iq.checked(work / name, plan["files"][name]))
    for name, digest in lock["sources"].items():
        whole_iq.checked(Path(name), digest)
    whole_iq.checked(Path(lock["python"]), lock["python_sha256"])
    libs = {k: whole_iq.checked(Path(v["path"]), v["sha256"]) for k, v in lock["libraries"].items()}
    return plan, lock, libs


@contextmanager
def dispatch(detector, timer, rf, now):
    """Reuse the freshly evaluated primary object when the online timer blocks."""
    evaluate = detector._evaluate_probe
    primary, attempts = {}, []

    def attempt(*args, acquisition_config, **kwargs):
        receiver = kwargs["receiver_id"]
        anchors = len(acquisition_config.anchor_symbols)
        if anchors == 12 and receiver not in primary:
            result = evaluate(*args, acquisition_config=acquisition_config, **kwargs)
            primary[receiver] = result
            return result
        gate = args[1].glrt64_margin_gate
        if (
            anchors != 22
            or set(primary) != {0, 1}
            or attempts
            or primary[receiver].has_fractional_detection(gate)
            or not primary[1 - receiver].has_fractional_detection(gate)
        ):
            raise ValueError("the installed scanner did not follow the original peer retry")
        if rf is None:
            raise ValueError("a physical retry requires the measured RF")
        key = (receiver, rf)
        run = timer is None or timer.allows(key, now)
        cost, hit = 0, None
        result = primary[receiver]
        if run:
            before = process_time_ns()
            result = evaluate(*args, acquisition_config=acquisition_config, **kwargs)
            hit = result.has_fractional_detection(gate)
            cost = process_time_ns() - before
            if timer is not None:
                timer.observed(key, now, hit)
        attempts.append(dict(receiver=receiver, executed=run, hit=hit, cpu_ns=cost))
        return result

    with patch.object(detector, "_evaluate_probe", attempt):
        yield primary, attempts


def measure(detector, window, now, timer, policy, grid):
    actual_if = window.acquisition.get("actual_if_center_hz")
    rf = float(actual_if + window.target["lnb_lo_hz"]) if actual_if is not None else None
    grid.calls.clear()
    with dispatch(detector, timer, rf, now) as (primary, attempts):
        wall, cpu = perf_counter_ns(), process_time_ns()
        status, probes = scan_capture_window(window, (0, 1), policy)
        timing = dict(cpu_ns=process_time_ns() - cpu, wall_ns=perf_counter_ns() - wall)
    if status.status not in ("processed", "invalid_capture"):
        raise ValueError("unexpected installed capture status")
    valid = status.status == "processed"
    wide = sum(r["anchors"] == 22 for r in grid.calls)
    narrow = sum(r["anchors"] == 12 for r in grid.calls)
    executed = any(a["executed"] for a in attempts)
    if (
        set(primary) != ({0, 1} if valid else set())
        or narrow + wide != len(grid.calls)
        or not all(r["applied"] for r in grid.calls)
        or (valid and not 2 <= narrow <= 4)
        or (not valid and narrow)
        or wide not in (range(1, 3) if executed else (0,))
    ):
        raise ValueError("dense-grid execution differs from the real online retry decision")
    return dict(
        status=status.status,
        probes=probes,
        attempts=attempts,
        **timing,
        primary_grids=narrow,
        wide_grids=wide,
    )


def worker(work, ident):
    from leo.analysis.starlink import acquisition
    from leo.scanner import fast_scan_detector
    from leo.storage import short_window

    plan, lock, libs = configure(work, ident)
    policy = base.policy_for(lock)
    start = base.resources.memory()
    if start["cpus"] != lock["cpus"]:
        raise ValueError("the waveform worker is outside its assigned CPU")
    grid = PersistentGrid(libs["prepared"])
    fine = field.fine_for(lock, libs["fine"])
    verified, observed = [], []
    member = short_window.ShortWindowReader._member

    def stream(reader, name, size, digest):
        if any(q.payload_relative_path == name for q in reader.manifest.chunks):
            path = short_window.confined_path(reader.path, reader.path / name, must_exist=True)
            return base.resources.AuthenticatedMember(path, size, digest, verified)
        return member(reader, name, size, digest)

    before = perf_counter_ns()
    try:
        with ExitStack() as scope:
            scope.enter_context(base.exact.refiners(libs))
            scope.enter_context(field.selector_waveform.selector(lock))
            scope.enter_context(grid.route(acquisition, base.exact.starts.screen_module()))
            scope.enter_context(fine.route())
            scope.enter_context(patch.object(short_window.ShortWindowReader, "_member", stream))
            for span, (segment, first, stop, offset) in enumerate(lock["spans"]):
                source = base.open_span(lock, segment, first, stop)
                timers = [{m: RetryCadence(m) for m in MODES[1:]} for _ in range(ROUNDS)]
                previous, closed = -1, len(verified)
                for window in source.windows():
                    visit = window.acquisition["global_visit"]
                    rt = json.loads(window.acquisition["retune_receipt"])
                    clock = rt["host_delivery_clock"]
                    now = clock["monotonic_ns"]
                    ref = lock["reference"][str(visit)]
                    if (
                        clock != ref["delivery_clock"]
                        or now < previous
                        or visit != window.sequence + offset
                        or window.target["edge"] != lock["capture"]["edge"]
                    ):
                        raise ValueError("raw delivery clock or physical recording changed")
                    previous = now
                    for round_id, by_mode in enumerate(timers):
                        turn = (window.sequence - first + round_id) % len(MODES)
                        for order, mode in enumerate(MODES[turn:] + MODES[:turn]):
                            result = measure(
                                fast_scan_detector, window, now, by_mode.get(mode), policy, grid
                            )
                            observed.append(
                                dict(
                                    span=span,
                                    visit=visit,
                                    round=round_id,
                                    order=order,
                                    mode=mode,
                                    iq_sha256=window.iq_sha256,
                                    **result,
                                )
                            )
                    if (window.sequence - first) % 8 == 7:
                        print(f"{ident} span {span} through visit {visit}", flush=True)
                if len(verified) != closed + 1:
                    raise ValueError("selected physical chunk did not authenticate")
    finally:
        grid.clear_cache()
    if len(observed) != len(lock["reference"]) * len(MODES) * ROUNDS:
        raise ValueError("waveform work did not span the entire interleaved roster")
    print(
        "cadence-waveform: "
        + encoded(
            dict(
                id=ident,
                start=start,
                end=base.resources.memory(),
                records=observed,
                elapsed_ns=perf_counter_ns() - before,
                plan_sha256=_sha(work / "plan.json"),
                authenticated_compressed_bytes=verified,
                fine={k: getattr(fine, k) for k in field.FINE_COUNTERS},
            )
        ).decode(),
        flush=True,
    )


def run(work):
    jobs = []
    with ExitStack() as scope:
        for ident in CASES:
            _, lock, _ = configure(work, ident)
            unit = f"leo-cadence-waveform-{ident.lower()}-{uuid4().hex[:8]}"
            env = dict(PYTHONPATH=f"{lock['producer']}:{field.base.ROOT}")
            env.update(field.base.recording.SINGLE_THREAD)
            args = base.service(
                unit,
                LIMIT,
                [
                    "taskset",
                    "-c",
                    str(lock["cpus"][0]),
                    "sudo",
                    "-n",
                    "-u",
                    "leo",
                    "--",
                    "env",
                    *(f"{k}={v}" for k, v in env.items()),
                    lock["python"],
                    "-Bu",
                    "-m",
                    MODULE,
                    "worker",
                    str(work),
                    ident,
                ],
            )
            log = scope.enter_context((work / f"{ident}.log").open("xb"))
            proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
            scope.callback(base.stop_if_running, proc, unit)
            jobs.append((ident, proc, args))
        save_json(work / "launch.json", {ident: args for ident, _, args in jobs})
        exits = {key: proc.wait(timeout=LIMIT + 25) for key, proc, _ in jobs}
    save_json(work / "exits.json", exits)
    if any(exits.values()):
        raise RuntimeError(f"saved-IQ cadence worker failed: {exits}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "worker"))
    parser.add_argument("work", type=local_output, nargs="?", default=WORK)
    parser.add_argument("case", choices=CASES, nargs="?")
    parser.add_argument("--cpus", nargs=2, type=int, default=CPUS)
    args = parser.parse_args()
    if args.action == "freeze":
        if len(set(args.cpus)) != len(CASES):
            parser.error("assign a distinct core to each case")
        freeze(args.work, args.cpus)
    elif args.action == "run":
        run(args.work)
    elif args.case is not None:
        worker(args.work, args.case)
    else:
        parser.error("worker requires a case")


if __name__ == "__main__":
    main()
