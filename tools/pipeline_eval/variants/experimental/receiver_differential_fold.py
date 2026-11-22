"""Audit full-aperture, phase-invariant differential pilot proposals from saved I/Q."""

import argparse
import ctypes as ct
import json
from collections import Counter
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from ..carrier_continuation import Continuation
from .receiver_benchmark import Factor, Receiver, digest, read_archive
from .receiver_cfo_peak_bound import build_trace

RATE = 2_500_000
PERIOD = 13_333
EPOCHS = 3_333
CODE = 1_408
WIDTH = EPOCHS + CODE - 1
FFT = 4_800
FRAMES = 14
LAGS = (2, 11, 28, 74)
ROW_INDICES = (np.rint(np.arange(FRAMES) * RATE / 750).astype(int)[:, None]
               + 22 + np.arange(WIDTH)[None, :])
CFO_HZ = (RATE / 4096) * np.arange(-1310, 1311)
ROTATION = np.exp(-2j * np.pi * CFO_HZ[:, None] * np.asarray(LAGS)[None, :] / RATE)
PROPOSER = ct.CFUNCTYPE(ct.c_int, ct.c_void_p, ct.c_double,
                       ct.POINTER(ct.c_int), ct.POINTER(ct.c_double))


def inject_signal(source):
    marker = "static int detect_lane("
    checkpoint = "    principal_modes(w, low);"
    end = "    double v[max_peaks][4];"
    if any(source.count(part) != 1 for part in (marker, checkpoint, end)):
        raise ValueError("unexpected ALGO08v3 detection source")
    before, tail = source.split(checkpoint)
    original, after = tail.split(end)
    buffers = "    Peak peaks[max_peaks];\n    RefineRequest request[max_peaks];\n"
    reload = "    if (center)\n        input(w, iq, lane, 0.);\n"
    if original.count(buffers) != 1 or original.count(reload) != 1:
        raise ValueError("unexpected ALGO08v3 refinement preparation")
    original = checkpoint + original.replace(buffers, "").replace(reload, "")
    seed_count = "seeds), done = 0;"
    if original.count(seed_count) != 1:
        raise ValueError("unexpected ALGO08v3 seed counter")
    original = original.replace(seed_count, "seeds);")
    original = "\n".join("    " + line for line in original.splitlines())
    before = before.replace(marker, """
typedef int (*FoldedProposer)(const Sample *, double, int *, double *);
static _Thread_local FoldedProposer folded_proposer;
static _Thread_local Sample folded_iq[2][points / 4];
static _Thread_local int folded_scans;

void differential_fold_set(FoldedProposer selected) { folded_proposer = selected; }

int differential_fold_read(Sample *out) {
    int scans = folded_scans;
    if (scans == 1 || scans == 2)
        memcpy(out, folded_iq, scans * sizeof(folded_iq[0]));
    folded_scans = 0;
    return scans;
}

""" + marker)
    body = """
    int done = 0;
    if (folded_proposer && w->stride == 4) {
        int epochs[choices];
        double hz[choices];
        done = folded_proposer(low, center, epochs, hz);
        if (done < 0 || done > choices)
            return -1;
        for (int i = 0; i < done; ++i)
            request[i] = (RefineRequest){epochs[i], hz[i]};
    } else {
        if (w->stride == 4 && folded_scans < 2) {
            memcpy(folded_iq[folded_scans], low, sizeof(folded_iq[0]));
            ++folded_scans;
        }
"""
    return before + buffers + body + original + "\n    }\n" + reload + end + after


def pilot_filters(asset):
    pilot = asset[:2 * PERIOD].view(np.complex64)
    fir = asset[4 * PERIOD:4 * PERIOD + 81]
    code = np.convolve(pilot, fir, mode="same")[88:88 + 4 * CODE:4]
    filters = []
    for lag in LAGS:
        product = code[lag:] * np.conj(code[:-lag])
        product -= product.mean()
        product /= np.linalg.norm(product)
        filters.append(np.conj(np.fft.fft(product, n=FFT)))
    return filters


def folded_correlations(signal, filters):
    rows = signal[ROW_INDICES].astype(np.complex128)
    rows -= rows.mean(axis=1, keepdims=True)
    rows /= np.maximum(np.sqrt(np.mean(abs(rows) ** 2, axis=1, keepdims=True)), 1e-12)
    results = []
    for lag, template in zip(LAGS, filters, strict=True):
        folded = np.sum(rows[:, lag:] * np.conj(rows[:, :-lag]), axis=0)
        energy = np.r_[0., np.cumsum(abs(folded) ** 2)]
        length = CODE - lag
        normalizer = np.sqrt(np.maximum(energy[length:length + EPOCHS] - energy[:EPOCHS], 1e-20))
        correlation = np.fft.ifft(np.fft.fft(folded, n=FFT) * template)[:EPOCHS]
        results.append(correlation / normalizer)
    return np.asarray(results)


def propose(signal, filters, center):
    correlation = folded_correlations(signal, filters)
    phase_score = np.sum(abs(correlation) ** 2, axis=0)
    epochs = []
    for _ in range(12):
        index = int(np.argmax(phase_score))
        phase_score[(index + np.arange(-2, 3)) % EPOCHS] = -1
        epochs.append(index)
    score = np.real(ROTATION @ correlation[:, epochs])
    seeds = []
    for column, epoch in enumerate(epochs):
        power = score[:, column].copy()
        for _ in range(2):
            best = int(np.argmax(power))
            seeds.append((float(power[best]), 4 * epoch, float(CFO_HZ[best] + center)))
            power[abs(CFO_HZ - CFO_HZ[best]) < 10_000] = -np.inf
    seeds.sort(key=lambda row: -row[0])
    return [4 * epoch for epoch in epochs], seeds[:4]


def wrapped_distance(a, b):
    return abs((a - b + PERIOD / 2) % PERIOD - PERIOD / 2)


def coverage(factor, epochs, seeds):
    target = (factor.integer + factor.offset) % PERIOD
    phase = any(wrapped_distance(epoch, target) <= 7 for epoch in epochs)
    signed = any(wrapped_distance(epoch, target) <= 7 and abs(hz - factor.hz) <= 4550
                 for _, epoch, hz in seeds)
    return phase, signed


def corresponding_factor(factor, others):
    epoch = factor.integer + factor.offset
    return any(other.rank == factor.rank and abs(other.hz - factor.hz) <= 250
               and wrapped_distance(other.integer + other.offset, epoch) <= 2
               for other in others)


def measure(radio, iq, lane, center):
    out = (Factor * 2)()
    count = radio.run(radio.ctx, iq.ctypes.data, lane, center - 800_000, center + 800_000, out)
    if not 0 <= count <= len(out):
        raise ValueError(f"invalid receiver factor count {count}")
    return out[:count]


def proposer_callback(filters):
    @PROPOSER
    def callback(pointer, center, epochs, frequencies):
        floats = ct.cast(pointer, ct.POINTER(ct.c_float))
        low = np.ctypeslib.as_array(floats, shape=(100_000,)).view(np.complex64)
        _, seeds = propose(low, filters, center)
        for i, (_, epoch, frequency) in enumerate(seeds):
            epochs[i] = epoch
            frequencies[i] = frequency
        return len(seeds)

    return callback


def compare(rows, paths, assets):
    by_rank = [Counter(), Counter()]
    selections = Counter()
    histories = {}
    inputs = []
    samples = np.zeros((2, 50_000), dtype=np.complex64)
    misses = []
    with ExitStack() as stack:
        radios_by_edge = {}
        for row, iq in rows:
            edge = row["edge"]
            if edge not in radios_by_edge:
                asset = np.fromfile(assets / f"{edge}.f32", dtype="<f4")
                radios = [Receiver(path, asset) for path in paths]
                for radio in radios:
                    stack.callback(radio.close)
                read = radios[1].lib.differential_fold_read
                read.argtypes = [ct.c_void_p]
                read.restype = ct.c_int
                select = radios[1].lib.differential_fold_set
                select.argtypes = [PROPOSER]
                select.restype = None
                filters = pilot_filters(asset)
                radios_by_edge[edge] = (radios, read, select, filters, proposer_callback(filters))
            radios, read, select, filters, callback = radios_by_edge[edge]
            target, acquisition = row["target"], row["acquisition"]
            center = (target["rf_center_hz"] - target["lnb_lo_hz"]
                      - acquisition["actual_if_center_hz"])
            inputs.append((row["key"], row["sha256"]))
            for lane in (0, 1):
                control, traced = (measure(radio, iq, lane, center) for radio in radios)
                if list(map(bytes, control)) != list(map(bytes, traced)):
                    raise ValueError(f"trace changed v3 factors at {row['key']} lane {lane}")
                scans = read(samples.ctypes.data)
                if scans not in (1, 2):
                    raise ValueError(f"trace recorded {scans} scout passes")
                proposals = [propose(signal, filters, center) for signal in samples[:scans]]
                select(callback)
                try:
                    shadow = measure(radios[1], iq, lane, center)
                finally:
                    select(PROPOSER())
                chosen = []
                for arm, factors in enumerate((control, shadow)):
                    history = histories.setdefault((row["case"], arm), Continuation())
                    _, selected, _ = history.select(dict(
                        receiver_id=lane, channel=target["channel"],
                        actual_rf_hz=acquisition["actual_if_center_hz"] + target["lnb_lo_hz"],
                        valid_start_counter=acquisition["sample_start"],
                        candidates=[dict(candidate_rank=f.rank, fractional_tracking_cfo_hz=f.hz,
                                         fractional_margin=f.exact - f.control) for f in factors],
                    ))
                    chosen.append(factors[selected:selected + 1] if selected is not None else [])
                selections["reference"] += len(chosen[0])
                selections["shadow"] += len(chosen[1])
                selections["missing"] += sum(not corresponding_factor(f, chosen[1])
                                             for f in chosen[0])
                selections["added"] += sum(not corresponding_factor(f, chosen[0])
                                           for f in chosen[1])
                for counter in by_rank[:scans]:
                    counter["scouts"] += 1
                for factor in shadow:
                    counter = by_rank[factor.rank]
                    counter["shadow_factors"] += 1
                    counter["added_factors"] += not corresponding_factor(factor, control)
                for factor in control:
                    phase, signed = coverage(factor, *proposals[factor.rank])
                    matched = corresponding_factor(factor, shadow)
                    counter = by_rank[factor.rank]
                    counter.update(factors=1, phase_supported=int(phase),
                                   signed_supported=int(signed), verified_missed=int(not matched))
                    if not signed:
                        misses.append((row["key"], lane, factor.rank, factor.integer,
                                       factor.hz, factor.exact - factor.control, phase, matched))
    return dict(inputs=inputs, counts=by_rank, selections=selections, misses=misses)


def main():
    from .receiver_brackets import read_physical

    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "work", "assets", "weak", "dense", "bulk"):
        parser.add_argument(name, type=lambda value: Path(value).resolve())
    args = parser.parse_args()
    paths = build_trace(args.archive, args.work, instrument=inject_signal)
    result = dict(trace=digest(paths[1].read_bytes()),
                  weak=compare(read_archive(args.weak, 18), paths, args.assets),
                  dense=compare(read_physical(args.dense, args.bulk, 24), paths, args.assets))
    if [len(result[name]["inputs"]) for name in ("weak", "dense")] != [18, 24]:
        raise ValueError("unexpected saved weak and dense test slice sizes")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
