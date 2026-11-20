"""Pair the released and typed native detector on contiguous saved windows."""

import argparse
import ctypes as ct
import json
import os
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, thread_time_ns

import numpy as np

from ..__main__ import encoded, local_output, save_json, write
from ..variants import center_union, differential_pilot, iq_stream
from ..variants.differential_runtime_fft import FftScout
from . import differential_pilot_eval, fifth_arm
from . import native_hotpath_build as build
from .full_v5_check import _from_native, _load_case, _sha
from .glrt_reuse_eval import CLOCKS, Profile
from .pilot_kernel_eval import _windows
from .wide_regional_eval import templates

CASES = {"DS26-0197": 14, "DS29-0316": 15}
SCOUT = Path(
    "/var/tmp/leo-whole-center-union-20261119/center-union-runtime-v2/libdifferential-scout.so"
)
SCOUT_SHA = "558e5832a1e489c23bff6ec2dd3203a780b9473c7e8284c00290621ee269c4f8"
MODES = ("stock", "fifth", "absent")
ROLES = ("legacy", "reference", "hotpath")
TIMED_MODES = MODES[:2]


class Trace(ct.Structure):
    _fields_ = [
        ("hints", ct.c_int32 * 2),
        ("union_trace", center_union.Trace),
        ("stock_profile", Profile),
        *[
            (f"{stage}_{clock}_ms", ct.c_double)
            for stage in ("scout", "rank", "detector")
            for clock in ("cpu", "wall")
        ],
    ]


def freeze(work):
    release = work / "build-v1/build.json"
    iq_stream.MAX_CHUNK_PREFIX = 56 * iq_stream.MIB
    roster = {}
    for ident in CASES:
        case = _load_case(ident)
        roster[ident] = rows = []
        for segment in (0, 4):
            rows.extend(_freeze_block(work, case, ident, segment))
    for edge in ("lower", "upper"):
        for control in ("strong", "noise", "zero"):
            if control == "zero":
                sample, target = np.zeros((200000, 2, 2), dtype="<i2"), {}
            else:
                sample, target = differential_pilot_eval.synthetic(edge, control)
            filename = f"{edge}-{control}.ci16"
            write(work / filename, sample.tobytes())
            roster.setdefault(edge, []).append(
                dict(
                    name=filename.removesuffix(".ci16"),
                    file=filename,
                    edge=edge,
                    case=edge,
                    iq_sha256=_sha(work / filename),
                    status="valid",
                    kind=control,
                    target=target,
                )
            )
    save_json(
        work / "input-lock.json",
        dict(
            build_sha256=_sha(release),
            protocol_sha256=_sha(build.REPORT / "PROTOCOL.md"),
            eval_sha256=_sha(Path(__file__)),
            scout_library_sha256=_sha(fifth_arm.check(SCOUT, SCOUT_SHA)),
            roster=roster,
            cases=CASES,
        ),
    )


def _freeze_block(work, case, ident, segment):
    selected = list(range(24))
    invalid = []
    for _ in range(24):
        try:
            windows = _windows(case, segment, selected)
            break
        except iq_stream.IQReadError as error:
            marker = "missing IQ or invalid layout for sequence "
            if not str(error).startswith(marker):
                raise
            sequence = int(str(error).removeprefix(marker))
            selected.remove(sequence)
            invalid.append(
                dict(sequence=sequence, segment=segment, status="invalid", reason=str(error))
            )
    else:
        windows = ()
    rows = invalid
    for window in windows:
        if window.samples.shape != (200000, 2, 2) or window.sample_rate_hz != 10_000_000:
            rows.append(
                dict(
                    sequence=window.sequence,
                    segment=segment,
                    status="invalid",
                    reason="short or non-10-MS/s dual window",
                )
            )
            continue
        name = f"{ident}-{segment}-{window.sequence}"
        file = f"{name}.ci16"
        write(work / file, window.samples.tobytes())
        fifth_arm.check(work / file, window.iq_sha256)
        rows.append(
            dict(
                name=name,
                file=file,
                segment=segment,
                sequence=window.sequence,
                visit=int(window.acquisition["global_visit"]),
                edge=window.target["edge"],
                case=ident,
                iq_sha256=window.iq_sha256,
                status="valid",
                kind="genuine",
                manifest=case["recording"]["segments"][segment],
            )
        )
    return sorted(rows, key=lambda row: row["sequence"])


def millis(start):
    return (thread_time_ns() - start[0]) / 1e6, (perf_counter_ns() - start[1]) / 1e6


def clock():
    return thread_time_ns(), perf_counter_ns()


def timed(metrics, name, elapsed):
    metrics.update(
        {f"{name}_{key}_ms": value for key, value in zip(("cpu", "wall"), elapsed, strict=True)}
    )


def public_rows(result):
    from leo.analysis.starlink.native_short_window import _ROW_COUNTS, _ROW_TIMINGS, _candidate

    if result.row_count != 2:
        raise ValueError("typed API returned invalid dual row geometry")
    rows = []
    for value in result.rows[:2]:
        if not 0 <= value.candidate_count <= 8:
            raise ValueError("typed API returned invalid candidate count")
        rows.append(
            dict(
                {k: getattr(value, k) for k in _ROW_COUNTS},
                candidates=[_candidate(c) for c in value.candidates[: value.candidate_count]],
                timings_ms={k: getattr(value, f"{k}_ms") for k in _ROW_TIMINGS},
            )
        )
    return rows


class NativeCall:
    def __init__(self, stack, path, edge):
        from leo.analysis.starlink.native_short_window import _Result

        start = clock()
        self.port = port = ct.CDLL(str(path))
        self.ctx = ct.c_void_p()
        self.out, self.trace = _Result(), Trace()
        for name, storage in (("result", self.out), ("trace", self.trace)):
            size = getattr(port, f"leo_native_hotpath_{name}_size_v1")
            size.restype = ct.c_size_t
            if size() != ct.sizeof(storage):
                raise ValueError(f"typed native {name} does not match host layout")
        create = port.leo_native_hotpath_create_v1
        create.argtypes = (ct.POINTER(ct.c_void_p),) + (ct.c_void_p,) * 4
        destroy = port.leo_native_hotpath_destroy_v1
        destroy.argtypes = (ct.c_void_p,)
        destroy.restype = None
        self.analyze = port.leo_native_hotpath_analyze_v1
        self.analyze.argtypes = (
            ct.c_void_p,
            ct.c_int,
            ct.c_void_p,
            ct.c_size_t,
            ct.POINTER(_Result),
            ct.POINTER(Trace),
        )
        refs = differential_pilot.filters(edge)
        bank = [
            np.stack([values[j] for values in refs], dtype=dtype)
            for j, dtype in enumerate(("<c8", "<f8"))
        ]
        bindings = (*templates(10_000_000, edge), *bank)
        if create(ct.byref(self.ctx), *(a.ctypes.data for a in bindings)):
            raise RuntimeError("cannot construct typed detector context")
        stack.callback(destroy, self.ctx)
        self.setup = millis(start)

    def measure(self, sample, mode):
        metrics = {}
        start = clock()
        if self.analyze(
            self.ctx,
            MODES.index(mode),
            sample.ctypes.data,
            len(sample),
            ct.byref(self.out),
            ct.byref(self.trace),
        ):
            raise RuntimeError("typed native detector returned a failure")
        typed_end = clock()
        timed(metrics, "typed", ((typed_end[0] - start[0]) / 1e6, (typed_end[1] - start[1]) / 1e6))
        rows = public_rows(self.out)
        timed(metrics, "decoded", millis(start))
        timed(metrics, "decode", millis(typed_end))
        for stage in ("scout", "rank", "detector"):
            for kind in ("cpu", "wall"):
                key = f"{stage}_{kind}_ms"
                metrics[key] = getattr(self.trace, key)
        if mode == "stock":
            metrics.update({k: getattr(self.trace.stock_profile, k) for k in CLOCKS})
        hints = list(self.trace.hints)
        trace = trace_rows(self.trace.union_trace) if mode != "stock" else None
        return rows, hints, trace, metrics


def trace_rows(trace):
    return [
        dict(
            ordinary=list(lane.ordinary[: lane.count]),
            added_epochs=lane.added_epochs,
            active_epochs=lane.active_epochs,
            stock_key_masks=dict(
                zip(
                    lane.stock_epochs[: lane.stock_epoch_count],
                    lane.stock_peak_masks[: lane.stock_epoch_count],
                    strict=True,
                )
            ),
            stock_peaks=lane.stock_peaks,
            extra_peaks=lane.extra_peaks,
            retained_stock=lane.retained_stock,
            retained_extra=lane.retained_extra,
        )
        for lane in trace.lanes
    ]


class LegacyCall:
    def __init__(self, stack, edge):
        from leo.analysis.starlink.native_short_window import NativeShortWindow

        start = clock()
        args = templates(10_000_000, edge)
        opts = dict(sample_rate_hz=10_000_000, fractional_epoch=True)
        self.ordinary = stack.enter_context(NativeShortWindow(str(build.STOCK), *args, **opts))
        native = stack.enter_context(NativeShortWindow(str(build.UNION), *args, **opts))
        self.union = center_union.UnionCall(native)
        self.scout = stack.enter_context(FftScout(fifth_arm.check(SCOUT, SCOUT_SHA), edge))
        self.setup = millis(start)

    def measure(self, sample, mode):
        metrics = {}
        start = clock()
        hints, trace = [-1, -1], None
        if mode == "stock":
            out = self.ordinary.analyze(sample, include_timings=True)
        else:
            if mode == "fifth":
                before = clock()
                surface = self.scout.surface(sample)
                timed(metrics, "scout", millis(before))
                before = clock()
                lists = [
                    (i, [float(row[x]) for x in i])
                    for row in surface
                    for i in [differential_pilot.ranked_centers(row)]
                ]
                hints = [centers[0] if centers else -1 for centers, _ in lists]
                timed(metrics, "rank", millis(before))
            out, details = self.union(sample, [h if h >= 0 else None for h in hints], timings=True)
            trace = legacy_trace(details)
        total = millis(start)
        timed(metrics, "decoded", total)
        metrics["detector_cpu_ms"] = out["detector_cpu_ms"]
        metrics["interface_cpu_ms"] = (
            total[0]
            - out["detector_cpu_ms"]
            - metrics.get("scout_cpu_ms", 0)
            - metrics.get("rank_cpu_ms", 0)
        )
        return out["rows"], hints, trace, metrics


def legacy_trace(details):
    output = []
    for lane in details:
        keys = {}
        for epoch, bin_index in lane["stock_peak_keys"]:
            keys[epoch] = keys.get(epoch, 0) | 1 << bin_index
        # Zero-peak epochs carry no science and are omitted in either port.
        row = {k: v for k, v in lane.items() if k not in {"stock_peak_keys", "selected"}}
        row["stock_key_masks"] = keys
        output.append(row)
    return output


def worker(work, role, edge, arm):
    lock = json.loads((work / "input-lock.json").read_bytes())
    release = fifth_arm.check(work / "build-v1/build.json", lock["build_sha256"])
    receipt = json.loads(release.read_bytes())
    with ExitStack() as stack:
        if role == "legacy":
            ctx = LegacyCall(stack, edge)
        else:
            root = release.parent / role
            for name, digest in receipt["libraries"][role].items():
                fifth_arm.check(root / name, digest)
            ctx = NativeCall(stack, root / build.LIBRARY, edge)
            path = str(root / build.DETECTOR)
            maps = Path("/proc/self/maps").read_text()
            if (
                path not in maps
                or str(
                    release.parent
                    / ("reference" if role == "hotpath" else "hotpath")
                    / build.DETECTOR
                )
                in maps
            ):
                raise ValueError("shared-library resolution did not bind this role's detector")
        print(json.dumps(dict(setup=ctx.setup, memory=memory())), flush=True)
        last = None
        for line in sys.stdin:
            fixture, mode = json.loads(line)
            if fixture != last:
                file = fifth_arm.check(work / fixture["file"], fixture["iq_sha256"])
                sample = np.fromfile(file, dtype="<i2").reshape(200000, 2, 2)
                last = fixture
            rows, hints, trace, metrics = ctx.measure(sample, mode)
            if trace:
                for lane in trace:
                    lane["stock_key_masks"] = {
                        k: v for k, v in lane["stock_key_masks"].items() if v
                    }
            for stage in (
                "proposal",
                "proposal_fold",
                "proposal_correlation",
                "proposal_ranking",
                "coarse",
                "fine_fft",
                "fractional_epoch",
                "glrt",
            ):
                metrics[f"{stage}_cpu_ms"] = sum(r["timings_ms"][stage] for r in rows)
            payload = fifth_arm.science(rows)
            before = clock()
            blob = encoded(payload)
            timed(metrics, "json", millis(before))
            positives = [
                [
                    c
                    for i, row in enumerate(rx["candidates"])
                    if (c := _from_native(i, row)) and c["passed_fractional_margin_gate"]
                ]
                for rx in rows
            ]
            result = dict(
                payload_sha256=sha256(blob).hexdigest(),
                hints=hints,
                trace=trace,
                candidate_count=[r["candidate_count"] for r in rows],
                positives=positives,
                json_bytes=len(blob),
                timings=metrics,
                memory=memory(),
            )
            print(json.dumps(result), flush=True)


def memory():
    with Path("/proc/self/status").open() as stream:
        return int(next(line for line in stream if line.startswith("VmHWM:")).split()[1])


@contextmanager
def start_worker(work, role, edge, arm):
    args = [
        sys.executable,
        "-m",
        __name__.replace("__main__", "tools.pipeline_eval.qualification.native_hotpath_eval"),
        "worker",
        str(work),
        role,
        edge,
        arm,
    ]
    env = os.environ | {
        name: "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    }
    with subprocess.Popen(
        args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env, text=True, bufsize=1
    ) as proc:
        try:
            initial = proc.stdout.readline()
            if not initial:
                raise RuntimeError(f"{role} failed before the first call")
            yield proc, json.loads(initial)
        finally:
            proc.stdin.close()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def call(proc, fixture, mode):
    proc.stdin.write(json.dumps((fixture, mode)) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("benchmark worker failed during a paired visit")
    return json.loads(line)


def comparable(results):
    return len({r["payload_sha256"] for r in results.values()}) == 1 and all(
        r["hints"] == results["legacy"]["hints"] and r["trace"] == results["legacy"]["trace"]
        for r in results.values()
    )


def run(work, ident):
    path = work / "input-lock.json"
    lock = json.loads(path.read_bytes())
    if _sha(Path(__file__)) != lock["eval_sha256"]:
        raise ValueError("runner changed after inputs were sealed")
    if os.sched_getaffinity(0) != {CASES[ident]}:
        raise ValueError("pin all matched workers to their single fixed core")
    primary = [f for f in lock["roster"][ident] if f["status"] == "valid"]
    edge = primary[0]["edge"]
    assert all(f["edge"] == edge for f in primary)
    rows = []
    with ExitStack() as stack:
        workers = {
            role: stack.enter_context(start_worker(work, role, edge, ident)) for role in ROLES
        }
        for role in ROLES:
            for mode in TIMED_MODES:
                call(workers[role][0], primary[0], mode)
        for i, fixture in enumerate([*primary, *lock["roster"][edge]]):
            schedule = TIMED_MODES if fixture["kind"] == "genuine" else MODES
            measured = {}
            for mode in schedule:
                measured[mode] = ar = []
                for rep in range(3):
                    offset = (i + rep) % len(ROLES)
                    outcome = {
                        r: call(workers[r][0], fixture, mode)
                        for r in ROLES[offset:] + ROLES[:offset]
                    }
                    if not comparable(outcome):
                        raise ValueError(
                            f"full science or support mismatch: {fixture['name']} {mode}"
                        )
                    ar.append(outcome)
            if "absent" in measured and any(
                x["hotpath"]["payload_sha256"] != y["hotpath"]["payload_sha256"]
                for x, y in zip(measured["stock"], measured["absent"], strict=True)
            ):
                raise ValueError("absent-hint mode differed from stock")
            rows.append(dict(fixture=fixture, modes=measured))
            if i % 12 == 0:
                print(ident, i, fixture["name"], flush=True)
                save_json(work / f"{ident}-progress.json", rows)
    save_json(
        work / f"{ident}-measured.json",
        dict(
            rows=rows,
            source_lock_sha256=_sha(path),
            core=CASES[ident],
            start={role: setup for role, (_, setup) in workers.items()},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "run", "worker"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("role", nargs="?")
    parser.add_argument("edge", nargs="?")
    parser.add_argument("arm", nargs="?")
    args = parser.parse_args()
    if args.mode == "freeze":
        freeze(args.work)
    elif args.mode == "run":
        run(args.work, args.role)
    else:
        worker(args.work, args.role, args.edge, args.arm)
