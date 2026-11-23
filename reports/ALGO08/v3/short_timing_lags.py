"""Measure current-window timing scouts using a fixed subset of the released lag filters."""

import argparse
import ctypes as ct
import gzip
import json
from collections import Counter
from contextlib import ExitStack, closing
from hashlib import sha256
from itertools import combinations
from pathlib import Path
from statistics import median

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import read_archive

from .mixed_aperture_receiver import PILOT_SHA, StereoSchedule, verified
from .timing_only_oracle import (
    TICKS,
    WINDOWS,
    Scout,
    asset_for,
    build,
    distance,
    one,
    overlay,
    phase_offset,
)
from .whole_group_receiver_bound import LAGS, WEAK_SHA, measure, read_dense, receiver

PUBLISHED = "ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85"
ORACLE = "0caad917eec9e02f0d1a6fa0ad57b3323175e16a429ef18053f1add2e22d10f9"
MODES = {"control": 0, "one_four": 3, "two_four": 4, "two_eight": 5}


TIMING_CLOCK = """
#include <time.h>
static _Thread_local uint64_t sparse_ticks;
static _Thread_local unsigned sparse_amount;

static inline uint64_t sparse_clock(void) {
    struct timespec clock;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &clock);
    return (uint64_t)clock.tv_sec * 1000000000 + clock.tv_nsec;
}

uint64_t sparse_timing_ticks(unsigned *amount) {
    *amount = sparse_amount;
    return sparse_ticks;
}
"""


def sparse_overlay(source):
    source = overlay(source)
    start = source.index("static void find_times(")
    end = source.index("static double bin_hz(", start)
    narrow = source[start:end]
    narrow = one(narrow, "find_times(TimingFirst *w, int *epochs)",
                 "find_sparse_times(TimingFirst *w, int *epochs, int width, int two)")
    old = "    for (int k = 0; k < lags; ++k) {"
    narrow = one(narrow, old, old + "\n        if (k != 5 && (!two || k != 6)) continue;")
    narrow = one(narrow, "k < clocks", "k < width")
    source = source[:end] + TIMING_CLOCK + narrow + source[end:]
    source = one(source, "    scoped_mode = mode;", """    scoped_mode = mode;
    sparse_ticks = 0;
    sparse_amount = 0;""")
    old = ("        n = find_scoped_carriers(w, scoped_allow[scan], scoped_size[scan],"
           " lo, hi, center, seeds);")
    return one(source, old, old + """
    } else if (scoped_mode >= 3) {
        int width = scoped_mode == 5 ? 8 : 4;
        uint64_t start = sparse_clock();
        find_sparse_times(w, epochs, width, scoped_mode >= 4);
        sparse_ticks += sparse_clock() - start;
        ++sparse_amount;
        n = find_scoped_carriers(w, epochs, width, lo, hi, center, seeds);""")


def template_screen(assets):
    """Rank lag masks by worst ideal timing peak-to-sidelobe ratio across signed CFOs."""
    all_scores = []
    epoch = 201
    samples = np.arange(4 * 4740 + 80) + 48 - 4 * epoch
    for edge in PILOT_SHA:
        asset = asset_for(assets, edge)
        pilot = asset[:2 * 13333].view(np.complex64)
        fir = asset[4 * 13333:4 * 13333 + 81]
        synthesis = asset[4 * 13333 + 81:].view(np.complex64)
        waveform = np.convolve(pilot, fir, "same")[88:88 + 4 * 1408:4]
        for cfo in (-750000, -400000, 0, 400000, 750000):
            phased = synthesis[(3 * samples) % TICKS] * np.exp(2j * np.pi * cfo * samples / 1e7)
            mode = np.convolve(phased, fir, "valid")[::4]
            scores = []
            for lag in LAGS:
                code = waveform[lag:] * waveform[:-lag].conj()
                code -= code.mean()
                code /= np.linalg.norm(code)
                measured = mode[lag:] * mode[:-lag].conj()
                prefix = np.r_[0, np.cumsum(abs(measured) ** 2)]
                energy = prefix[len(code):len(code) + 3333] - prefix[:3333]
                filt = np.fft.fft(measured, 4800) * np.fft.fft(code, 4800).conj()
                scores.append(abs(np.fft.ifft(filt)[:3333]) ** 2 / np.maximum(energy, 1e-20))
            all_scores.append(scores)
    surfaces = np.asarray(all_scores)
    out = {}
    for order in (1, 2):
        contrast = []
        for indices in combinations(range(len(LAGS)), order):
            score = surfaces[:, indices, :].sum(axis=1)
            peak = score[:, epoch - 2:epoch + 3].max(axis=1)
            side = np.maximum(score[:, :epoch - 2].max(axis=1), score[:, epoch + 3:].max(axis=1))
            contrast.append((float(min(peak / side)), [LAGS[i] for i in indices]))
        out[str(order)] = sorted(contrast, reverse=True)
    if out["1"][0][1] != [28] or out["2"][0][1] != [28, 44]:
        raise ValueError("The template-screened lags differ from the preselected masks")
    return out


def publication_factor(row):
    if len(row["candidates"]) > 1:
        raise ValueError("Expected the mixed packet to retain one factor per lane")
    if not row["candidates"]:
        return None
    f = row["candidates"][0]
    return tuple(f[field] for field in (
        "candidate_rank", "integer_epoch_sample", "fractional_epoch_offset_samples",
        "fractional_tracking_cfo_hz", "fractional_exact_score", "fractional_control_score",
    ))


def strongest(factors):
    return max(factors, key=lambda a: (a[4] - a[5], -a[0]), default=None)


def packet(path):
    document = json.loads(verified(path, PUBLISHED))
    probes = document["source"]["probes"]
    rows = {(row["valid_start_counter"], row["receiver_id"]): row for row in probes}
    if len(rows) != len(probes) or len(probes) != 13530:
        raise ValueError("Expected the complete original mixed packet")
    return rows


def oracle_species(prior, full_packet):
    """Separate true published winning rows from verified and unconfirmed nominees."""
    results = Counter()
    rows = [r for r in prior["dense"]["rows"] if r["kind"] == r["scheduled"]]
    current = {(r["sample"], r["antenna"]): r for r in rows}
    history = {}
    for row in rows:
        stamp, antenna = row["sample"], row["antenna"]
        peer = current[stamp, 1 - antenna]
        published = full_packet[stamp, antenna]
        published_factor = publication_factor(published)
        factors = [tuple(f) for f in row["factors"]]
        if (published["actual_rf_hz"], published["edge"], published_factor) != (
            row["rf"], row["edge"], strongest(factors),
        ):
            raise ValueError("The timing-only oracle prefix differs from the full mixed packet")
        key = antenna, row["edge"], row["rf"], row["generation"], published["channel"]
        recent = [old for old in history.get(key, ()) if 0 < stamp - old["sample"] <= 20_000_000]
        hints = [phase_offset(f, old["sample"], stamp)
                 for old in (*recent, peer) for f in old["factors"]]
        factor_cells = {}
        for f in factors:
            nominated = sorted(set(row["scopes"][f[0]][1]))
            factor_phase = phase_offset(f, stamp, stamp)
            cell = min(nominated, key=lambda e: distance(e, [factor_phase]))
            if distance(cell, [factor_phase]) <= 7:
                factor_cells[f[0], cell] = "published" if f == published_factor else "unselected"
            else:
                results["factor_without_nearby_coarse_row"] += 1
        positive = published_factor is not None
        results["positive_lanes" if positive else "empty_lanes"] += 1
        if not hints:
            results["donorless_positive_lanes" if positive else "donorless_empty_lanes"] += 1
        for rank, (_, nominees) in enumerate(row["scopes"]):
            for cell in set(nominees):
                group = factor_cells.get((rank, cell), "other_on_positive" if positive else "empty")
                results[group + "/total"] += 1
                nearest = distance(cell, hints)
                for radius in WINDOWS:
                    results[f"{group}/{radius}/missed"] += nearest > radius
        history[key] = (*recent[-1:], row)
    return dict(results)


def close_factor(a, b):
    """One finder per scan with signed CFO and circular fractional arrival tolerance."""
    phase_a, phase_b = a[1] + a[2], b[1] + b[2]
    delta = abs((phase_a - phase_b + 6666.5) % 13333 - 6666.5)
    return a[0] == b[0] and delta <= 2 and abs(a[3] - b[3]) <= 250


class SparseScout(Scout):
    def __init__(self, path, asset, kind):
        super().__init__(path, asset, kind)
        self.ticks = self.radio.lib.sparse_timing_ticks
        self.ticks.argtypes, self.ticks.restype = [ct.POINTER(ct.c_uint)], ct.c_uint64

    def evaluate(self, iq, antenna, center, mode):
        self.set(mode, None, None)
        factors, exact, cpu = measure(self.radio, iq, antenna, center)
        scouts = ct.c_uint()
        elapsed = self.ticks(ct.byref(scouts))
        return dict(factors=factors, exact=exact, cpu=cpu, timing=elapsed, scouts=scouts.value)


def training(library, kind, assets, modes=MODES):
    """Exercise the profiling variants using both edges, pilot and noise, without saved RF."""
    rng = np.random.default_rng(4841)
    indices = np.arange(200000)
    report = Counter()
    for edge in PILOT_SHA:
        asset = asset_for(assets, edge)
        pilot = asset[4 * 13333 + 81:].view(np.complex64)
        with closing(SparseScout(library, asset, kind)) as scout:
            for strength, center in ((80, -50000), (500, 60000), (1500, 0), (0, 0)):
                iq = rng.normal(0, 19, (len(indices), 2, 2)).astype(np.int16)
                for antenna in (0, 1):
                    x = strength * pilot[(3 * indices - 2215 - 3201 * antenna) % TICKS]
                    x = x * np.exp(2j * np.pi * (-250000 + 381000 * antenna) * indices * 1e-7)
                    iq[:, antenna, 0] += np.rint(x.real).astype(np.int16)
                    iq[:, antenna, 1] += np.rint(x.imag).astype(np.int16)
                    for label, mode in modes.items():
                        report[label] += len(scout.evaluate(iq, antenna, center, mode)["factors"])
    return dict(report)


def audit(rows, builds, assets, published=None):
    schedule = StereoSchedule(full_coverage=True)
    outputs = []
    with ExitStack() as stack:
        engines = {}
        for index, (row, iq) in enumerate(rows):
            event, target, edge = row["acquisition"], row["target"], row["edge"]
            _, selected = schedule.visit(edge, target, event)
            kind = "short" if selected == "short_primary" else "full"
            key = edge, kind
            if key not in engines:
                stock_path, candidate_path, _ = builds[kind]
                asset = asset_for(assets, edge)
                stock = stack.enter_context(closing(receiver(stock_path, asset, kind)))
                narrow = stack.enter_context(closing(SparseScout(candidate_path, asset, kind)))
                engines[key] = stock, narrow
            stock, narrow = engines[key]
            center = target["rf_center_hz"] - target["lnb_lo_hz"] - event["actual_if_center_hz"]
            for antenna in (0, 1):
                exact, blob, ns = measure(stock, iq, antenna, center)
                reference = strongest(exact)
                if published is not None:
                    bound = published[event["sample_start"], antenna]
                    if reference != publication_factor(bound):
                        raise ValueError("The active detector disagrees with its sealed packet")
                label_order = tuple(MODES)
                statistics = []
                for repeat in range(3):
                    rotate = (index + antenna + repeat) % len(label_order)
                    arms = {}
                    for label in label_order[rotate:] + label_order[:rotate]:
                        run = narrow.evaluate(iq, antenna, center, MODES[label])
                        factors, raw = run["factors"], run.pop("exact")
                        run["changed_bytes"] = raw != blob
                        if label == "control" and run["changed_bytes"]:
                            raise ValueError("The same-build control changed signed factor bytes")
                        run["changed_factor"] = strongest(factors) != reference
                        run["missing_factors"] = sum(
                            not any(close_factor(f, g) for g in factors) for f in exact
                        )
                        run["added_factors"] = sum(
                            not any(close_factor(f, g) for g in exact) for f in factors
                        )
                        run["lost_selection"] = reference is not None and not any(
                            close_factor(reference, g) for g in factors
                        )
                        arms[label] = run
                    statistics.append(arms)
                outputs.append(dict(key=row["key"], lane=antenna, kind=kind, iq=row["sha256"],
                                    reference=exact, installed_ns=ns, arms=statistics))
    return outputs


def summarize(rows):
    stats = {}
    for label in MODES:
        for kind in ("mixed", "full", "short"):
            scope = [row for row in rows if kind == "mixed" or row["kind"] == kind]
            stats[label, kind] = {}
            for field in ("cpu", "timing", "scouts", "changed_bytes", "changed_factor",
                          "missing_factors", "added_factors", "lost_selection"):
                stats[label, kind][field] = [sum(r["arms"][i][label][field] for r in scope)
                                             for i in range(3)]
            retry_cpu = [sum(r["arms"][i]["control"]["cpu"] for r in scope
                             if r["arms"][i][label]["changed_factor"]) for i in range(3)]
            stats[label, kind]["publication_oracle_retry_cpu"] = retry_cpu
            early_cpu = []
            for i in range(3):
                cost = 0
                for row in scope:
                    arm = row["arms"][i][label]
                    if arm["changed_factor"]:
                        cost += arm["timing"] + row["arms"][i]["control"]["cpu"]
                    else:
                        cost += arm["cpu"]
                early_cpu.append(cost)
            stats[label, kind]["publication_oracle_preflight_cpu"] = early_cpu
    return {"/".join(key): {name: median(values) for name, values in entry.items()}
            for key, entry in stats.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(required=True, dest="mode")
    bench = modes.add_parser("bench")
    for name in ("work", "assets", "weak", "dense", "packet", "prior"):
        bench.add_argument(name, type=lambda value: Path(value).resolve())
    feedback = modes.add_parser("train")
    feedback.add_argument("library", type=Path)
    feedback.add_argument("kind", choices=("full", "short"))
    feedback.add_argument("assets", type=Path)
    args = parser.parse_args()
    if args.mode == "train":
        print(json.dumps(training(args.library, args.kind, args.assets)))
        return
    published = packet(args.packet)
    raw = gzip.decompress(args.prior.read_bytes())
    if sha256(raw).hexdigest() != ORACLE:
        raise ValueError("The first-phase oracle receipt has changed")
    classifications = oracle_species(json.loads(raw), published)
    verified(args.weak, WEAK_SHA)
    template = template_screen(args.assets)
    libraries = build(args.work, args.assets, source_overlay=sparse_overlay,
                      extra_flags=("-D_POSIX_C_SOURCE=200809L",),
                      worker="reports.ALGO08.v3.short_timing_lags")
    weak = audit(read_archive(args.weak, 18), libraries, args.assets)
    dense = audit(read_dense(args.dense, 48), libraries, args.assets, published)
    print(json.dumps(dict(template=template, classifications=classifications,
                          builds={key: value[-1] for key, value in libraries.items()},
                          weak=dict(rows=weak, summary=summarize(weak)),
                          dense=dict(rows=dense, summary=summarize(dense))),
                     separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
