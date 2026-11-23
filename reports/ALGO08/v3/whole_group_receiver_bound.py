"""Measure optimistic tail-energy rejection before native full-rate refinement."""

import argparse
import ctypes as ct
import json
import subprocess
from collections import Counter
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from time import process_time_ns

import numpy as np

from tools.pipeline_eval.variants.carrier_continuation import Continuation
from tools.pipeline_eval.variants.experimental.receiver_benchmark import (
    Factor,
    Receiver,
    read_archive,
)

from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, StereoSchedule, verified

BENCH = Path("/tmp/leo-algo08v2-2x-bench")
FULL_BUILD = BENCH / "receiver-fractional-exact-v1/build.json"
FULL_BUILD_SHA = "5566ddd22345982e1b7673c7d65a8ce5799ce8229275365e1e6e237ab3f0e86d"
SHORT_BUILD = Path("/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/build-receipt.json")
SHORT_BUILD_SHA = "99f912ef6c1cd57f13b081408a8cececc9bb3ea2384c517bef70f7eb34bfcfac"
SHORT_SHA = "06570a53032c770d99cc9678b8660e1bb502b71f30fc47c8b1a4a8e31bc19ba9"
WEAK_SHA = "0f025d0f5c80f5425a3c6fa90bc77a0e5628eb8cf7bc7ac7dab7fdd6c1d2e9d9"
DENSE_MANIFEST_SHA = "5ffe3ed98feb37f7f7ada44dbf34d2af9d3fcadce567fd3cdbb7e31965a02759"
SOURCE_SHA = {
    "full": "936b67cbb9af0201a7e65281756cc9c16f042ac2ad5e84201b1577131c67044a",
    "short": "a8fa28b5997ee7b4537ebaca4e41982b4976de4b00fde82011871570a616e1cc",
}
LAGS = (2, 4, 6, 11, 18, 28, 44, 74)
TIMING_EPOCHS = 3333
MODE_WIDTH = 4740
CODE_LEN = 1408
CARRIER_TAPS = 704
PARTITIONS = 8
GROUP_WIDTH = 32


TRACE_C = """
#include <time.h>
enum { trace_width = 4740, trace_epochs = 3333, trace_code = 1408 };
typedef struct {
    Sample mode[2][trace_width], code[trace_code];
    double timing_cut, carrier_cut;
    uint64_t timing_ns, carrier_ns;
    int epochs[clocks];
} GroupTrace;

static _Thread_local GroupTrace group_traces[2];
static _Thread_local int group_scans;

static uint64_t group_clock(void) {
    struct timespec clock;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &clock);
    return (uint64_t)clock.tv_sec * 1000000000 + clock.tv_nsec;
}

int whole_group_read(GroupTrace *out) {
    int scans = group_scans;
    if (scans > 0 && scans <= 2)
        memcpy(out, group_traces, scans * sizeof(*out));
    group_scans = 0;
    return scans;
}
"""


def instrument(source):
    markers = {
        'static void find_times(': TRACE_C + 'static void find_times(',
        '        epochs[k] = best;': '''        epochs[k] = best;
        if (group_scans < 2 && k == clocks - 1)
            group_traces[group_scans].timing_cut = w->time_score[best];''',
        '    find_times(w, epochs);': '''    uint64_t timing_start = group_clock();
    find_times(w, epochs);
    uint64_t carrier_start = group_clock();''',
        '    Peak peaks[max_peaks];': '''    uint64_t carrier_end = group_clock();
    if (w->stride == 4 && w->epochs == trace_epochs && w->width == trace_width &&
        w->length == trace_code && group_scans < 2) {
        GroupTrace *trace = group_traces + group_scans++;
        trace->timing_ns = carrier_start - timing_start;
        trace->carrier_ns = carrier_end - carrier_start;
        memcpy(trace->mode, w->modes, sizeof(trace->mode));
        memcpy(trace->code, w->code, sizeof(trace->code));
        memcpy(trace->epochs, epochs, sizeof(trace->epochs));
        trace->carrier_cut = -1.;
        Seed ordered[2 * clocks];
        memcpy(ordered, seeds, n * sizeof(*ordered));
        for (int k = 0; k < choices && k < n; ++k) {
            int best = 0;
            for (int j = 1; j < n; ++j)
                if (ordered[j].power > ordered[best].power)
                    best = j;
            if (k == choices - 1)
                trace->carrier_cut = ordered[best].power;
            ordered[best].power = -1.;
        }
    }
    Peak peaks[max_peaks];''',
    }
    for old, new in markers.items():
        if source.count(old) != 1:
            raise ValueError(f"Unexpected geometry at {old}")
        source = source.replace(old, new)
    return source


class Trace(ct.Structure):
    _fields_ = [
        ("mode", ct.c_float * (4 * MODE_WIDTH)), ("code", ct.c_float * (2 * CODE_LEN)),
        ("timing_cut", ct.c_double), ("carrier_cut", ct.c_double),
        ("timing_ns", ct.c_uint64), ("carrier_ns", ct.c_uint64), ("epochs", ct.c_int * 12),
    ]


def build(root):
    full = json.loads(verified(FULL_BUILD, FULL_BUILD_SHA))
    short = json.loads(verified(SHORT_BUILD, SHORT_BUILD_SHA))
    builds = {}
    for kind, link, expected in (
        ("full", full["commands"][-1], INSTALLED_SHA),
        ("short", short["relink"], SHORT_SHA),
    ):
        work = root / kind
        work.mkdir(parents=True)
        stock, trace = work / "stock.so", work / "trace.so"
        subprocess.run([*link[:-1], stock], cwd=full["cwd"], check=True)
        verified(stock, expected)
        index, = (i for i, value in enumerate(link)
                  if Path(value).name == "timing_first_receiver.o")
        source = verified(Path(link[index]).with_suffix(".c"), SOURCE_SHA[kind]).decode()
        c_path = work / "timing_first_receiver.c"
        c_path.write_text(instrument(source))
        obj = c_path.with_suffix(".o")
        subprocess.run([*full["commands"][-2][:-4], "-D_POSIX_C_SOURCE=200809L",
                        "-c", c_path, "-o", obj],
                       cwd=full["cwd"], check=True)
        relink = link[:index] + [str(obj)] + link[index + 1:-1]
        subprocess.run([*relink, trace], cwd=full["cwd"], check=True)
        builds[kind] = (stock, trace)
    return builds


def prefix_energy(values):
    complex_ = values.astype(np.complex128, copy=False)
    return np.r_[0., np.cumsum(complex_.real ** 2 + complex_.imag ** 2)]


def prunable_cells(upper, cutline, group_width=GROUP_WIDTH):
    """Count complete blocks below the cutline. Early rejection requires strict order."""
    upper = np.asarray(upper)
    safe = np.isfinite(upper) & np.isfinite(cutline) & (upper < cutline)
    end = len(safe) // group_width * group_width
    groups = safe[:end].reshape(-1, group_width).all(axis=1)
    return group_width * int(np.count_nonzero(groups)) + (len(safe) - end) * int(safe[end:].all())


def timing_tail_floor(modes, code):
    """Drop the magnitude of all prefix correlations to grant a free zero prefix."""
    output = np.zeros((PARTITIONS, TIMING_EPOCHS))
    e = np.arange(TIMING_EPOCHS)
    for lag in LAGS:
        products = np.sum(modes[:, lag:] * modes[:, :-lag].conj(), axis=0)
        reference = code[lag:] * code[:-lag].conj()
        reference -= reference.mean(dtype=np.complex128).astype(np.complex64)
        x, h = prefix_energy(products), prefix_energy(reference)
        length = len(reference)
        head = np.arange(PARTITIONS) * length // PARTITIONS
        if h[-1] > 0:
            energy = x[e + length]
            all_x = np.maximum(energy - x[e], 1e-20)
            output += ((h[-1] - h[head]) / h[-1])[:, None] * (energy - x[e + head[:, None]]) / all_x
    return output


def carrier_tail_floor(modes, code, epochs):
    """The two-mode tail is independent of signed CFO, so it bounds the whole row."""
    x = np.sum([prefix_energy(mode) for mode in modes], axis=0)
    h = prefix_energy(code[:CARRIER_TAPS])
    e = np.asarray(epochs)
    stop = x[e + CARRIER_TAPS]
    all_x = np.maximum(stop - x[e], 1e-15)
    head = np.arange(PARTITIONS) * CARRIER_TAPS // PARTITIONS
    return (h[-1] - h[head])[:, None] * (stop - x[e + head[:, None]]) / all_x


def opportunities(trace):
    mode = np.ctypeslib.as_array(trace.mode).view(np.complex64).reshape(2, MODE_WIDTH)
    code = np.ctypeslib.as_array(trace.code).view(np.complex64)
    timing = timing_tail_floor(mode, code)
    carrier = carrier_tail_floor(mode, code, list(trace.epochs))
    return dict(
        timing=[prunable_cells(row, trace.timing_cut) for row in timing],
        timing_individual=[prunable_cells(row, trace.timing_cut, 1) for row in timing],
        carrier=[prunable_cells(row, trace.carrier_cut, 1) for row in carrier],
        cuts=[trace.timing_cut, trace.carrier_cut],
        stage_cpu_ns=[trace.timing_ns, trace.carrier_ns],
    )


def read_dense(directory, visits=24):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support
    from leo.storage.fast_scan import FastSegmentSource

    scope = dict(path=str(directory), manifest_digest="sha256:" + DENSE_MANIFEST_SHA)
    source = FastSegmentSource(scope, stop_sequence=visits)
    policy = FastScanPolicyV2()
    lanes = tuple(source.receiver_ids)
    if lanes != (0, 1):
        raise ValueError("Expected the original stereo ordering")
    for window in source.windows():
        acq, target = window.acquisition, window.target
        supported = valid_window_support(
            acq, window.sample_rate_hz, window.samples.shape, lanes, policy,
        )
        if not supported:
            continue
        yield dict(case="DS30-0008", key=f"DS30-0008:{acq['global_visit']}", edge=target["edge"],
                   acquisition=acq, target=target, sha256=window.iq_sha256), window.samples


def receiver(path, asset, kind):
    engine = Receiver(path, asset)
    if kind == "short":
        primary = engine.lib.cancellation_primary_factors
        primary.argtypes, primary.restype = engine.run.argtypes, engine.run.restype
        engine.run = primary
    return engine


def measure(engine, iq, lane, tune):
    out = (Factor * 2)()
    call = (engine.ctx, iq.ctypes.data, lane, tune - 800000, tune + 800000, out)
    then = process_time_ns()
    n = engine.run(*call)
    cpu = process_time_ns() - then
    if not 0 <= n <= 2:
        raise ValueError(f"Invalid factor count {n}")
    rows = tuple(tuple(getattr(factor, key) for key, _ in Factor._fields_) for factor in out[:n])
    return rows, bytes(out)[:n * ct.sizeof(Factor)], cpu


def history_row(factors, row, lane):
    target, acquisition = row["target"], row["acquisition"]
    return dict(receiver_id=lane, channel=target["channel"],
                actual_rf_hz=acquisition["actual_if_center_hz"] + target["lnb_lo_hz"],
                valid_start_counter=acquisition["sample_start"], candidates=[
                    dict(candidate_rank=rank, fractional_tracking_cfo_hz=hz,
                         fractional_margin=exact - control)
                    for rank, _, _, hz, exact, control in factors
                ])


def audit(rows, builds, assets):
    outputs = []
    factor_counts, continuation_counts = Counter(), Counter()
    schedule = StereoSchedule(full_coverage=True)
    with ExitStack() as stack:
        radios, histories = {}, {}
        for index, (row, iq) in enumerate(rows):
            target, acquisition = row["target"], row["acquisition"]
            center = (target["rf_center_hz"] - target["lnb_lo_hz"]
                      - acquisition["actual_if_center_hz"])
            edge = row["edge"]
            _, scheduled = schedule.visit(edge, target, acquisition)
            if edge not in radios:
                asset_bytes = verified(assets / f"{edge}.f32", PILOT_SHA[edge])
                asset = np.frombuffer(asset_bytes, dtype="<f4")
                radios[edge] = {}
                for kind, paths in builds.items():
                    stock, traced = (receiver(path, asset, kind) for path in paths)
                    stack.callback(stock.close)
                    stack.callback(traced.close)
                    read = traced.lib.whole_group_read
                    read.argtypes, read.restype = [ct.POINTER(Trace)], ct.c_int
                    radios[edge][kind] = (stock, traced, read)
            for lane in (0, 1):
                for kind, (stock, traced, read) in radios[edge].items():
                    factors, stock_bytes, stock_time = measure(stock, iq, lane, center)
                    traced_factors, traced_bytes, traced_time = measure(traced, iq, lane, center)
                    if stock_bytes != traced_bytes:
                        raise ValueError(f"Trace changed {kind} factors at {row['key']}/{lane}")
                    buffer = (Trace * 2)()
                    scans = read(buffer)
                    if scans not in range(1, 3 if kind == "full" else 2):
                        raise ValueError(f"Unexpected {kind} scout count {scans}")
                    histories.setdefault((kind, row["case"]), (Continuation(), Continuation()))
                    original, other = histories[kind, row["case"]]
                    selected = original.select(history_row(factors, row, lane))
                    if selected != other.select(history_row(traced_factors, row, lane)):
                        raise ValueError(f"Trace changed {kind} continuation at {row['key']}")
                    factor_counts.update(f"{kind}-{factor[0]}" for factor in factors)
                    continuation_counts[kind] += selected[1] is not None
                    outputs.append(dict(
                        kind=kind, index=index, key=row["key"], iq=row["sha256"], lane=lane,
                        scheduled="short" if scheduled == "short_primary" else "full",
                        stock_cpu_ns=stock_time, traced_cpu_ns=traced_time,
                        scans=[opportunities(item) for item in buffer[:scans]],
                    ))
    return dict(data=outputs, factors=factor_counts, continuation=continuation_counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("work", "assets", "weak", "dense"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    verified(args.weak, WEAK_SHA)
    builds = build(args.work)
    controls = {
        "weak": audit(read_archive(args.weak, 18), builds, args.assets),
        "dense": audit(read_dense(args.dense), builds, args.assets),
    }
    if [len(controls[name]["data"]) for name in controls] != [72, 96]:
        raise ValueError("The saved panels do not have 18 and 24 admitted stereo visits")
    pins = {kind: [sha256(path.read_bytes()).hexdigest() for path in pair]
            for kind, pair in builds.items()}
    print(json.dumps(dict(builds=pins, **controls), separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
