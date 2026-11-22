"""Count the carrier FFT work a multiresolution ALGO08v3 scout could avoid."""

import argparse
import ctypes as ct
import json
import math
import subprocess
from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .receiver_benchmark import Factor, Receiver, digest, read_archive, read_simulated_prefix

V3_SHA = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
TIMING_SOURCE_SHA = "936b67cbb9af0201a7e65281756cc9c16f042ac2ad5e84201b1577131c67044a"
SPECTRUM = 4096
SUPPORT = 704
CLOCKS = 12
KEEP = 4
PUBLIC_SOUTH = "6bd1f26bfa0bedfcf3f100f8"


# Capture the frozen scores without changing nominations or downstream execution.
TRACE = """
typedef struct {
    int epoch, bins[2];
    double coarse[2], peak, scores[2];
} CarrierBoundRow;
static _Thread_local CarrierBoundRow carrier_bound_rows[2][clocks];
static _Thread_local int carrier_bound_scans;

int carrier_bound_read(CarrierBoundRow *out) {
    int scans = carrier_bound_scans;
    if (scans == 1 || scans == 2)
        memcpy(out, carrier_bound_rows, scans * sizeof(carrier_bound_rows[0]));
    carrier_bound_scans = 0;
    return scans;
}
"""


def inject_trace(source):
    before_function = "static int find_carriers("
    before_rank = "        int prev = -1;"
    after_rank = "            prev = best;"
    end = "    return used;\n}"
    for marker in (before_function, before_rank, after_rank, end):
        if source.count(marker) != 1:
            raise ValueError(f"unexpected ALGO08v3 timing code near {marker!r}")
    source = source.replace(before_function, TRACE + before_function)
    source = source.replace(before_rank, """
        CarrierBoundRow *row = carrier_bound_scans < 2
            ? &carrier_bound_rows[carrier_bound_scans][i] : NULL;
        if (row) {
            *row = (CarrierBoundRow){.epoch = epochs[i], .bins = {-1, -1}};
            double denom = fmax(energy, 1e-15);
            for (int j = 0; j < bins; ++j) {
                double value = w->power[j] / denom;
                row->peak = fmax(row->peak, value);
                if (j % 2 == 0) row->coarse[0] = fmax(row->coarse[0], value);
                if (j % 4 == 0) row->coarse[1] = fmax(row->coarse[1], value);
            }
        }
""" + before_rank)
    source = source.replace(after_rank, """
            if (row) {
                row->bins[rep] = best;
                row->scores[rep] = all[used - 1].power;
            }
""" + after_rank)
    return source.replace(end, "    ++carrier_bound_scans;\n" + end)


def build_trace(archive, work, *, instrument=inject_trace):
    manifest = json.loads((archive / "build.json").read_bytes())
    link = manifest["commands"][-1]
    work.mkdir()
    reference = work / "reference.so"
    subprocess.run([*link[:-1], reference], check=True)
    if digest(reference.read_bytes()) != V3_SHA:
        raise ValueError("the archived objects do not relink to the installed ALGO08v3 receiver")
    index, = (i for i, value in enumerate(link) if Path(value).name == "timing_first_receiver.o")
    stock = Path(link[index]).with_suffix(".c").read_bytes()
    if digest(stock) != TIMING_SOURCE_SHA:
        raise ValueError("unexpected archived timing source")
    source = work / "timing_first_receiver.c"
    source.write_text(instrument(stock.decode()))
    traces = source.with_suffix(".o")
    compiler = manifest["commands"][-2]
    subprocess.run([*compiler[:-4], "-c", source, "-o", traces], cwd=manifest["cwd"], check=True)
    link[index] = str(traces)
    output = work / "trace.so"
    subprocess.run([*link[:-1], output], check=True)
    return reference, output


@dataclass(frozen=True)
class Epoch:
    index: int
    coarse: tuple[float, float]
    peak: float
    seeds: tuple[tuple[int, float], ...]


class TraceRow(ct.Structure):
    _fields_ = [
        ("epoch", ct.c_int), ("bins", ct.c_int * 2), ("coarse", ct.c_double * 2),
        ("peak", ct.c_double), ("scores", ct.c_double * 2),
    ]


def read_trace(radio):
    read = radio.lib.carrier_bound_read
    read.argtypes = [ct.POINTER(TraceRow)]
    read.restype = ct.c_int
    rows = (TraceRow * (2 * CLOCKS))()
    count = read(rows)
    if count not in (1, 2):
        raise ValueError(f"expected one or two recorded ALGO08v3 scouts, got {count}")
    epochs = [Epoch(row.epoch, tuple(row.coarse), row.peak,
                    tuple((b, s) for b, s in zip(row.bins, row.scores, strict=True) if b >= 0))
              for row in rows[:count * CLOCKS]]
    return [epochs[start:start + CLOCKS] for start in range(0, len(epochs), CLOCKS)]


def peak_upper(coarse_power, step):
    """Bound the ideal DFT power of a 704-sample pair from a shorter grid."""
    degree = SUPPORT // 2
    anchors = SPECTRUM // step
    ehlich_zeller = 1 / math.cos(math.pi * degree / anchors) ** 2
    summation_kernel = anchors / (anchors - 2 * degree)
    return coarse_power * min(ehlich_zeller, summation_kernel)


def ranked(rows, evaluated):
    return sorted(
        ((i, ordinal, bin_id, power) for i in evaluated
         for ordinal, (bin_id, power) in enumerate(rows[i].seeds)),
        key=lambda seed: (-seed[3], seed[0], seed[1]),
    )[:KEEP]


def timing_order(rows, raw):
    """Prioritize nearby raw-pass winners for residual search, with wrap."""
    if raw is None:
        return list(range(len(rows)))
    period = 3333
    raw_epochs = [raw[i].index for i, *_ in ranked(raw, range(len(raw)))]

    def priority(i):
        for rank, epoch in enumerate(raw_epochs):
            delta = abs(epoch - rows[i].index)
            if min(delta, period - delta) <= 2:
                return rank
        return KEEP

    return sorted(range(len(rows)), key=priority)


def audit_scout(rows, step, order, initial):
    """Reveal whole epochs until no remaining upper bound reaches the cutline."""
    upper = []
    for row in rows:
        value = peak_upper(row.coarse[step // 2 - 1], step)
        # The audit uses rounded full FFT outputs as stand-ins for mathematical anchors.
        # Never count a measured violation as an opportunity to avoid exact work.
        upper.append(value if math.isfinite(value) and value >= row.peak else math.inf)
    done = order[:initial]
    pending = order[initial:]
    coarse = len(pending)
    for i in sorted(pending, key=lambda j: -upper[j]):
        winners = ranked(rows, done)
        if len(winners) == KEEP and upper[i] < winners[-1][3]:
            break
        done.append(i)
    if ranked(rows, done) != ranked(rows, range(len(rows))):
        raise ValueError("the measured envelope omitted an exact ranked carrier seed")
    return Counter(scouts=1, epochs=len(rows), coarse=coarse, full=len(done),
                   bounds_failed=sum(math.isinf(value) for value in upper))


def compare(rows, reference, instrumented, assets):
    from ..carrier_continuation import Continuation

    scans = [dict(), dict()]
    records = []
    factor_counts = Counter()
    histories = {}
    fields = tuple(name for name, _ in Factor._fields_)
    with ExitStack() as stack:
        radios = {}
        for row, samples in rows:
            edge = row["edge"]
            if edge not in radios:
                pilot = np.fromfile(assets / f"{edge}.f32", dtype="<f4")
                radios[edge] = (Receiver(reference, pilot), Receiver(instrumented, pilot))
                for radio in radios[edge]:
                    stack.callback(radio.close)
            target, acquisition = row["target"], row["acquisition"]
            lo_hz, if_hz = target["lnb_lo_hz"], acquisition["actual_if_center_hz"]
            rf_hz = if_hz + lo_hz
            center = target["rf_center_hz"] - lo_hz - if_hz
            for lane in (0, 1):
                stock, traced = radios[edge]
                by_arm = []
                for radio in (stock, traced):
                    out = (Factor * 2)()
                    count = radio.run(radio.ctx, samples.ctypes.data, lane,
                                      center - 800000, center + 800000, out)
                    if not 0 <= count <= len(out):
                        raise ValueError(f"invalid ALGO08v3 factor count {count}")
                    factors = out[:count]
                    by_arm.append((b"".join(map(bytes, factors)),
                                   [tuple(getattr(f, name) for name in fields) for f in factors]))
                if by_arm[0][0] != by_arm[1][0]:
                    raise ValueError(f"overlay changed factor bytes for {row['key']} lane {lane}")
                trace = read_trace(traced)
                history = []
                for arm, (_, values) in enumerate(by_arm):
                    continuation = histories.setdefault((row["case"], arm), Continuation())
                    history.append(continuation.select(dict(
                        receiver_id=lane, channel=target["channel"], actual_rf_hz=rf_hz,
                        valid_start_counter=acquisition["sample_start"],
                        candidates=[stock.criteria(*factor) for factor in values],
                    )))
                if history[0] != history[1]:
                    raise ValueError(f"overlay changed continuation for {row['key']} lane {lane}")
                for index, scout in enumerate(trace):
                    timing = timing_order(scout, None)
                    strategies = {"bounds-first": (timing, 0), "timing-first": (timing, 2)}
                    if index == 1:
                        strategies["raw-hint-first"] = (timing_order(scout, trace[0]), 2)
                    for step in (2, 4):
                        for start, (order, initial) in strategies.items():
                            key = f"{SPECTRUM // step}-{start}"
                            counts = audit_scout(scout, step, order, initial)
                            scans[index].setdefault(key, Counter()).update(counts)
                factors = by_arm[0][1]
                factor_counts.update(factor[0] for factor in factors)
                records.append((row["key"], row["sha256"], lane, factors, history[0]))
    return dict(lanes=len(records), factor_ranks=dict(factor_counts),
                selection_count=sum(row[-1][1] is not None for row in records),
                outputs_sha256=digest(json.dumps(records, sort_keys=True).encode()),
                inputs=sorted({(row[0], row[1]) for row in records}),
                primary=scans[0], residual=scans[1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archived_build", "work", "assets", "weak_archive", "public_panel"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    reference, instrumented = build_trace(args.archived_build, args.work)
    weak = compare(read_archive(args.weak_archive, 18), reference, instrumented, args.assets)
    # Only the sparse southern member is scored. The saved panel reader authenticates I/Q.
    south_rows = ((row, iq) for row, iq in read_simulated_prefix(args.public_panel, 40)
                  if row["case"] == PUBLIC_SOUTH)
    south = compare(south_rows, reference, instrumented, args.assets)
    if (weak["lanes"], south["lanes"]) != (36, 80):
        raise ValueError("expected the 18 weak-carrier slots and the 40-visit public south prefix")
    print(json.dumps(dict(reference=V3_SHA, instrumented=digest(instrumented.read_bytes()),
                          weak=weak, south=south), indent=2))


if __name__ == "__main__":
    main()
