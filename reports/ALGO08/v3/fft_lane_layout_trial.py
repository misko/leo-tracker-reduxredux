"""Benchmark sample-major independent FFTW batches on authentic receiver arrays."""

import argparse
import ctypes as ct
import json
import subprocess
from collections import Counter, defaultdict
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from statistics import median
from time import process_time_ns

import numpy as np

from tools.pipeline_eval.variants.carrier_continuation import Continuation
from tools.pipeline_eval.variants.experimental.receiver_benchmark import read_archive

from .mixed_aperture_receiver import INSTALLED_SHA, verified
from .timing_only_oracle import asset_for, one
from .whole_group_receiver_bound import (
    FULL_BUILD,
    FULL_BUILD_SHA,
    SHORT_BUILD,
    SHORT_BUILD_SHA,
    SHORT_SHA,
    SOURCE_SHA,
    WEAK_SHA,
    history_row,
    measure,
    receiver,
)

REPEATS = 5
STAGES = (("lag_forward", 4800, 0, 8), ("lag_inverse", 4800, 1, 8),
          ("carrier_forward", 4096, 0, 24))

TRACE = """
enum { trace_max = 48, trace_width = 4800 };
static _Thread_local Sample observed[2][3][trace_max * trace_width];
static _Thread_local int trace_count[2][3], trace_active;

void observe_fft_start(void) {
    memset(trace_count, 0, sizeof(trace_count));
    trace_active = 1;
}

void observe_fft_stop(void) { trace_active = 0; }

const Sample *observe_fft_read(int side, int type, int *used) {
    if (side < 0 || side > 1 || type < 0 || type > 2) return NULL;
    *used = trace_count[side][type];
    return observed[side][type];
}

static inline void observe_fft(const TimingFirst *w, int side, int n, int backwards) {
    if (!trace_active || (n != 4800 && n != 4096)) return;
    int type = n == 4096 ? 2 : !!backwards;
    int entry = trace_count[side][type]++;
    if (entry < trace_max)
        memcpy(observed[side][type] + entry * n, w->scratch, n * sizeof(Sample));
}
"""


def observe(source):
    marker = "static void transform(TimingFirst *w, int n, int backward) {"
    source = one(source, marker, TRACE + "\n" + marker)
    old = "    if (transform_large(w, n, backward)) return;"
    source = one(source, old, """    observe_fft(w, 0, n, backward);
    if (transform_large(w, n, backward)) {
        observe_fft(w, 1, n, backward);
        return;
    }""")
    old = "            fftwf_execute(w->plans[timing_backward]);"
    return one(source, old, """            observe_fft(w, 0, w->correlation_size, 1);
            fftwf_execute(w->plans[timing_backward]);
            observe_fft(w, 1, w->correlation_size, 1);""")


def assemble(work):
    full = json.loads(verified(FULL_BUILD, FULL_BUILD_SHA))
    short = json.loads(verified(SHORT_BUILD, SHORT_BUILD_SHA))
    work.mkdir()
    binaries, pins = {}, {}
    for kind, link, expected in (
        ("full", full["commands"][-1], INSTALLED_SHA),
        ("short", short["relink"], SHORT_SHA),
    ):
        sub = work / kind
        sub.mkdir()
        stock = sub / "stock.so"
        subprocess.run([*link[:-1], stock], cwd=full["cwd"], check=True)
        verified(stock, expected)
        position, = (i for i, arg in enumerate(link)
                     if Path(arg).name == "timing_first_receiver.o")
        original = verified(Path(link[position]).with_suffix(".c"), SOURCE_SHA[kind]).decode()
        c_path = sub / "timing_first_receiver.c"
        c_path.write_text(observe(original))
        obj = c_path.with_suffix(".o")
        subprocess.run([*full["commands"][-2][:-4], "-c", c_path, "-o", obj],
                       cwd=full["cwd"], check=True)
        trace = sub / "trace.so"
        subprocess.run([*link[:position], obj, *link[position + 1:-1], trace],
                       cwd=full["cwd"], check=True)
        binaries[kind] = stock, trace
        pins[kind] = dict(stock=expected, trace=sha256(trace.read_bytes()).hexdigest())
    library = work / "kernel.so"
    c_path = Path(__file__).with_name("fft_lane_layout.c")
    subprocess.run(["cc", "-O3", "-std=c11", "-fPIC", "-shared", "-Wall", "-Werror",
                    "-D_POSIX_C_SOURCE=200809L", c_path, "-o", library, "-lfftw3f"], check=True)
    pins["kernel"] = sha256(library.read_bytes()).hexdigest()
    return binaries, library, pins


def wire(function, arguments, result):
    function.argtypes, function.restype = arguments, result
    return function


def capture(trace, stage, length):
    read = wire(trace.lib.observe_fft_read, [ct.c_int, ct.c_int, ct.POINTER(ct.c_int)],
                ct.POINTER(ct.c_float))
    result = []
    for side in (0, 1):
        count = ct.c_int()
        pointer = read(side, stage, ct.byref(count))
        if not pointer or not 1 <= count.value <= 48:
            raise ValueError("Unexpected transform input count")
        values = np.ctypeslib.as_array(pointer, shape=(count.value, length, 2)).copy()
        result.append(values)
    if result[0].shape != result[1].shape:
        raise ValueError("Transform input and output counts differ")
    return result


def inspect(rows, libraries, assets):
    signals, inputs, stats = defaultdict(list), [], defaultdict(Counter)
    with ExitStack() as stack:
        detectors, histories = {}, {}
        for row, iq in rows:
            edge = row["edge"]
            target, event = row["target"], row["acquisition"]
            center = target["rf_center_hz"] - target["lnb_lo_hz"] - event["actual_if_center_hz"]
            inputs.append((row["key"], row["sha256"], edge))
            for kind, paths in libraries.items():
                key = kind, edge
                if key not in detectors:
                    asset = asset_for(assets, edge)
                    stock, trace = (receiver(path, asset, kind) for path in paths)
                    stack.callback(stock.close)
                    stack.callback(trace.close)
                    detectors[key] = stock, trace
                stock, trace = detectors[key]
                chron = row["case"], kind
                if chron not in histories:
                    histories[chron] = Continuation(), Continuation()
                for lane in (0, 1):
                    control, expected, _ = measure(stock, iq, lane, center)
                    trace.lib.observe_fft_start()
                    test, observed, _ = measure(trace, iq, lane, center)
                    trace.lib.observe_fft_stop()
                    if expected != observed:
                        raise ValueError(f"Trace changed output on {row['key']} lane {lane}")
                    original, modified = histories[chron]
                    chosen = original.select(history_row(control, row, lane))
                    if chosen != modified.select(history_row(test, row, lane)):
                        raise ValueError("Trace changed independent continuation state")
                    stats[kind].update(lanes=1, primary=sum(f[0] == 0 for f in control),
                                       residual=sum(f[0] == 1 for f in control),
                                       selected=chosen[1] is not None)
                    for stage, (name, length, _, per_scout) in enumerate(STAGES):
                        before, after = capture(trace, stage, length)
                        if len(before) not in (per_scout, 2 * per_scout):
                            raise ValueError("The released transform count differs")
                        for i in range(len(before) // per_scout):
                            part = slice(i * per_scout, (i + 1) * per_scout)
                            signals[kind, name, i].append((before[part], after[part]))
    return signals, dict(inputs=inputs, factors=stats)


def grouped(tensors, width):
    """Batch the same operator from adjacent lane sequences in chronological order."""
    values = np.asarray(tensors)
    length = len(values) // width * width
    _, count, n, coords = values.shape
    views = values[:length].reshape(length // width, width, count, n, coords)
    return np.ascontiguousarray(views.transpose(0, 2, 1, 3, 4).reshape(-1, width, n, coords))


def prototype(library, tensors, length, backward, lanes):
    scalar = ct.c_void_p
    create = wire(library.fft_lane_create, [ct.c_int, ct.c_int, ct.c_int], scalar)
    free = wire(library.fft_lane_free, [scalar], None)
    plan = wire(library.fft_lane_plan, [scalar, ct.c_int], scalar)
    free_plan = wire(library.fft_lane_plan_free, [scalar], None)
    args = [scalar, scalar, scalar, ct.c_int, ct.c_int, ct.POINTER(ct.c_uint64)]
    evaluate = wire(library.fft_lane_measure, args, None)
    raw, expected = (grouped(part, lanes) for part in zip(*tensors, strict=True))
    if not len(raw):
        return None
    start = process_time_ns()
    ctx = create(length, lanes, backward)
    creation = process_time_ns() - start
    if not ctx:
        raise ValueError("The native FFTW plan could not be created")
    stages, plans, changes = [[], []], [], []
    try:
        for arm in (0, 1):
            ptr = plan(ctx, arm)
            if not ptr:
                raise ValueError("FFTW did not return a plan description")
            plans.append(ct.string_at(ptr).decode())
            free_plan(ptr)
        out = [np.empty_like(expected), np.empty_like(expected)]
        for repeat in range(REPEATS):
            for arm in (repeat % 2, 1 - repeat % 2):
                ns = (ct.c_uint64 * 2)()
                evaluate(ctx, raw.ctypes.data, out[arm].ctypes.data, len(raw), arm, ns)
                stages[arm].append(list(ns))
        for values in out:
            diffs = values.view("u4") != expected.view("u4")
            changes.append(dict(transforms=int(diffs.any(axis=(2, 3)).sum()),
                                components=int(diffs.sum()),
                                maximum=float(np.max(np.abs(values - expected)))))
    finally:
        free(ctx)
    if changes[0]["components"]:
        raise ValueError("Standalone scalar FFT differs from the exact captured receiver outputs")
    return dict(groups=len(raw), lanes=lanes, plans=plans, plan_cpu_ns=creation, changes=changes,
                clocks=stages, total_cpu_ns=[median(t[1] for t in arm) for arm in stages],
                kernel_cpu_ns=[median(t[0] for t in arm) for arm in stages])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("work", "assets", "weak"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    verified(args.weak, WEAK_SHA)
    paths, kernel, pins = assemble(args.work)
    signals, info = inspect(read_archive(args.weak, 8), paths, args.assets)
    if len(info["inputs"]) != 8:
        raise ValueError("Expected eight bounded saved stereo inputs")
    library = ct.CDLL(str(kernel))
    bounds = {}
    for kind, name, scan in signals:
        _, n, backward, _ = next(stage for stage in STAGES if stage[0] == name)
        for width in (2, 4, 8):
            result = prototype(library, signals[kind, name, scan], n, backward, width)
            bounds[f"{kind}/{name}/{scan}/{width}"] = result
    print(json.dumps(dict(identity=pins, evidence=info, batches=bounds), ensure_ascii=True,
                     separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
