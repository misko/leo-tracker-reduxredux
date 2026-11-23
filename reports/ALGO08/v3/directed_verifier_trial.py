"""Replay exact and directed waveform checks with explicitly supplied proposals."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as ct
import json
import math
from pathlib import Path
from random import Random
from statistics import median, quantiles
import subprocess
import sys
from time import perf_counter_ns, process_time_ns

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import Factor, Receiver, digest, read_archive
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical
from tools.pipeline_eval.variants.experimental.receiver_cfo_peak_bound import TIMING_SOURCE_SHA, V3_SHA
from tools.pipeline_eval.variants.experimental.receiver_tracking import agree, measured_epoch
from tools.pipeline_eval.variants.carrier_continuation import Continuation

from .receiver_refine_pgo_trial import train


ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "tools/pipeline_eval/variants/experimental"
PERIOD = 13333
MODES = {"decode": 0, "refine": 1, "fixed_exact": 2, "fixed_guard": 3}


class Timing(ct.Structure):
    _fields_ = [("epoch", ct.c_double), ("hz", ct.c_double), ("score", ct.c_double),
                ("confirmation", ct.c_int)]


class Trace(ct.Structure):
    _fields_ = [("timing", Timing), ("sample", ct.c_int)]


class Seed(ct.Structure):
    _fields_ = [("epoch", ct.c_int), ("sample", ct.c_int), ("coarse_epoch", ct.c_double),
                ("offset", ct.c_double), ("hz", ct.c_double)]


class Cost(ct.Structure):
    _fields_ = [*((field, ct.c_uint64) for field in ("refine_ns", "gate_ns", "cancel_ns", "load_ns", "verify_ns")),
                *((field, ct.c_uint) for field in ("gates", "cancellations", "verifies"))]


def replace_once(source, left, right):
    if source.count(left) != 1:
        raise ValueError(f"unexpected archived source at {left!r}")
    return source.replace(left, right, 1)


def overlay_timing(source):
    start, end = source.index("static int gate("), source.index("static void input(")
    original = source[start:end]
    ci16 = replace_once(original, "static int gate(TimingFirst *w, const Peak *p, int start_symbol, int early)",
                        "static int gate_ci16(TimingFirst *w, const Peak *p, int start_symbol, int early, "
                        "const int16_t *iq, int lane)")
    ci16 = replace_once(ci16, "Sample z = multiply(w->data[offset + j], rotation[j]);", """
                const int16_t *pair = iq + 4 * (offset + j) + 2 * lane;
                Sample z = multiply((Sample){pair[0], pair[1]}, rotation[j]);""")
    mark = "static int detect_lane("
    source = replace_once(source, mark, ci16 + (CODE / "receiver_directed_timing.inc").read_text() + "\n" + mark)
    mark = "    *out = (TimingFirstResult){0};"
    source = replace_once(source, mark, mark + """
    int directed_scan = directed_stamp++;
    if (directed_scan < 2) directed_trace[directed_scan] = (DirectedTrace){0};
""")
    source = replace_once(source, "            *out = (TimingFirstResult){p.epoch, p.hz, p.score, why};", """
            *out = (TimingFirstResult){p.epoch, p.hz, p.score, why};
            if (directed_scan < 2) directed_trace[directed_scan] = (DirectedTrace){*out, p.sample};""")
    return '#include "receiver_directed.h"\n' + source


def build(args):
    if digest(args.installed.read_bytes()) != V3_SHA:
        raise ValueError("installed detector differs")
    archived = json.loads((args.archive / "build.json").read_bytes())
    original = archived["commands"][-1]
    history = json.loads(args.history.read_bytes())["build"]["builds"]["packed"]
    compiler = subprocess.check_output(["cc", "--version"], text=True).splitlines()[0]
    if compiler != archived["compiler"]:
        raise ValueError("archived compiler differs")
    timing, verifier = (next(Path(v) for v in original if Path(v).name == name)
                        for name in ("timing_first_receiver.o", "portable_verifier.o"))
    pins = {timing.with_suffix(".c"): TIMING_SOURCE_SHA,
            verifier.with_suffix(".c"): archived["verifier_source_sha256"]}
    for path, pin in pins.items():
        if digest(path.read_bytes()) != pin:
            raise ValueError(f"unexpected archived source {path}")
    args.work.mkdir()
    timing_text = args.work / timing.with_suffix(".c").name
    timing_text.write_text(overlay_timing(timing.with_suffix(".c").read_text()))
    verifier_text = args.work / verifier.with_suffix(".c").name
    verifier_text.write_text('#include "receiver_directed.h"\n' + verifier.with_suffix(".c").read_text()
                             + (CODE / "receiver_directed_verify.inc").read_text())
    flags = archived["commands"][-2][:-4]
    new_verifier = args.work / verifier.name
    helper = args.work / "receiver_directed.o"
    commands = []
    for source, obj in ((verifier_text, new_verifier), (CODE / "receiver_directed.c", helper)):
        command = [*flags, "-I", str(CODE), "-c", str(source), "-o", str(obj)]
        subprocess.run(command, cwd=archived["cwd"], check=True)
        commands.append(command)
    archived["commands"][-1] = [
        *(str(new_verifier) if item == str(verifier) else item for item in original[:-2]),
        str(helper), *original[-2:],
    ]
    for i in (0, 2):
        history["commands"][i][-4:-4] = ["-I", str(CODE)]
    def additional_training(binary):
        command = [sys.executable, "-m", "reports.ALGO08.v3.directed_verifier_trial",
                   "train-directed", str(binary), str(args.assets)]
        return json.loads(subprocess.check_output(command))

    arm, receipt = train(args.work, archived, history, args, additional_training=additional_training)
    return arm, dict(compiler=compiler, installed_sha256=V3_SHA, build=receipt, extra_commands=commands,
                     verifier_source_sha256=digest(verifier_text.read_bytes()),
                     verifier_object_sha256=digest(new_verifier.read_bytes()),
                     native_source_sha256=digest((CODE / "receiver_directed.c").read_bytes()))


def tuple_factor(factor):
    return tuple(getattr(factor, field) for field, _ in Factor._fields_)


class Directed:
    def __init__(self, receiver, asset):
        lib = receiver.lib
        lib.directed_create.argtypes = [ct.c_void_p]
        lib.directed_create.restype = ct.c_void_p
        self.ctx = lib.directed_create(asset.ctypes.data)
        if not self.ctx:
            raise ValueError("directed receiver setup failed")
        self.free = lib.directed_free
        self.free.argtypes = [ct.c_void_p]
        self.free.restype = None
        self.run = lib.directed_run
        self.run.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.POINTER(Seed), ct.c_int,
                             ct.c_double, ct.c_double, ct.c_int, ct.POINTER(Factor), ct.POINTER(Cost)]
        self.run.restype = ct.c_int
        self.read_trace = lib.directed_timing_trace
        self.read_trace.argtypes = [ct.POINTER(Trace)]
        self.read_trace.restype = ct.c_int

    def close(self):
        self.free(self.ctx)

    def trace(self):
        out = (Trace * 2)()
        count = self.read_trace(out)
        if count not in (1, 2):
            raise ValueError(f"expected one or two original scouts, saw {count}")
        return [t for t in out[:count] if t.timing.confirmation]

    def timed(self, samples, lane, center, seeds, mode, *, full_load=False):
        if not seeds:
            return (), 0, 0, Cost()
        proposals, out, cost = (Seed * len(seeds))(*seeds), (Factor * 2)(), Cost()
        values = self.ctx, samples.ctypes.data, lane, proposals, len(seeds), center - 800000, center + 800000
        wall, cpu = perf_counter_ns(), process_time_ns()
        count = self.run(*values, MODES[mode] | (8 if full_load else 0), out, cost)
        cpu, wall = process_time_ns() - cpu, perf_counter_ns() - wall
        if not 0 <= count <= 2:
            raise ValueError(f"invalid directed verifier result {count}")
        return tuple(map(tuple_factor, out[:count])), cpu, wall, cost


def seed(epoch, hz):
    wrapped = epoch % PERIOD
    nearest = round(wrapped)
    return Seed(nearest % PERIOD, nearest % PERIOD, wrapped, wrapped - nearest, hz)


def strict_seed(scouter, factor_by_rank, rank):
    p = scouter.timing
    f = factor_by_rank.get(rank)
    return Seed(round(p.epoch) % PERIOD, scouter.sample, p.epoch, f[2] if f else 0., p.hz)


def external_seeds(factors, center, rng, stressed):
    phase_jitter, hz_jitter = (3., 1200.) if stressed else (1., 400.)
    clamp = lambda hz: max(center - 800000, min(center + 800000, hz))
    proposed = [seed(measured_epoch(f) + rng.uniform(-phase_jitter, phase_jitter),
                     clamp(f[3] + rng.uniform(-hz_jitter, hz_jitter))) for f in sorted(factors)]
    phase = measured_epoch(factors[0]) if factors else rng.uniform(0., PERIOD)
    hz = factors[0][3] if factors else center + rng.uniform(-700000., 700000.)
    sign = rng.choice((-1., 1.))
    # Near-frequency false nominations, a shifted pilot and a blind signed cell.
    decoys = [
        seed(phase, clamp(hz + sign * 1700.)),
        seed(phase + 44, clamp(hz + sign * 750.)),
        seed(phase + 23, clamp(hz - sign * 10000.)),
        seed(phase + 972, clamp(center + rng.uniform(-760000., 760000.))),
    ]
    return (proposed + decoys)[:4], decoys


def train_directed(binary, assets):
    # Reuse the pinned, site-free waveform controls from the installed recipe.
    sys.path.insert(0, str(ROOT / "reports/ALGO08/single-core-2x"))
    from receiver_compiler_trial import training_rows
    from tools.pipeline_eval.qualification import waveform_site_model as waveform

    pulses = waveform.pulse_bank()
    outcomes = Counter()
    rng = Random(17322)
    for edge, record in training_rows():
        samples = waveform.iq(record, dict(sample_rate_truth_hz=waveform.RATE), pulses[edge])
        asset = np.fromfile(assets / f"{edge}.f32", dtype="<f4")
        detector = Receiver(binary, asset)
        direct = Directed(detector, asset)
        try:
            for lane in (0, 1):
                reference, _, _ = detector.timed(samples, lane, 0.)
                direct.trace()
                proposed, decoys = external_seeds(reference, 0., rng, False)
                for mode in MODES:
                    measured, _, _, _ = direct.timed(samples, lane, 0., proposed[:2], mode)
                    outcomes[mode] += len(measured)
                direct.timed(samples, lane, 0., decoys, "decode")
        finally:
            direct.close()
            detector.close()
    return outcomes


def compare(reference, candidate):
    rem = list(candidate)
    hits = Counter()
    deltas = []
    for original in reference:
        match = next((f for f in rem if agree(original, f)), None)
        if match is not None:
            hits[original[0]] += 1
            rem.remove(match)
            deltas.append([abs(math.remainder(measured_epoch(original) - measured_epoch(match), PERIOD)),
                           *(abs(a - b) for a, b in zip(original[3:], match[3:], strict=True))])
    return hits, len(rem), deltas


def clock_summary(values):
    if not values:
        return None
    p95 = quantiles(values, n=20, method="inclusive")[-1] if len(values) > 1 else values[0]
    return dict(mean=sum(values) / len(values) / 1e6, median=median(values) / 1e6, p95=p95 / 1e6)


def continuation(histories, row, lane, factors):
    target, acq = row["target"], row["acquisition"]
    history = histories.setdefault(row["case"], Continuation())
    _, choice, _ = history.select(dict(
        receiver_id=lane, channel=target["channel"], actual_rf_hz=acq["actual_if_center_hz"] + target["lnb_lo_hz"],
        valid_start_counter=acq["sample_start"], candidates=[Receiver.criteria(*f) for f in factors],
    ))
    return factors[choice] if choice is not None else None


def evaluate(lanes, scenario, mode, budget, repeats, *, full_load=False):
    cpu, wall, positive, negative = [], [], [], []
    totals, hits, stages, maxima = Counter(), Counter(), Counter(), [0.] * 4
    altered = []
    baseline_history, candidate_history = {}, {}
    for repeat in range(repeats):
        order = lanes if repeat % 2 == 0 else reversed(lanes)
        for case in order:
            row, radio, iq, lane, center, reference, proposals = case
            seeds = proposals[scenario][:budget]
            actual, elapsed_cpu, elapsed_wall, timing = radio.timed(
                iq, lane, center, seeds, mode, full_load=full_load)
            cpu.append(elapsed_cpu)
            wall.append(elapsed_wall)
            (positive if reference else negative).append(elapsed_cpu)
            stages.update({key: getattr(timing, key) for key, _ in Cost._fields_})
            if repeat:
                continue
            old = continuation(baseline_history, row, lane, reference)
            new = continuation(candidate_history, row, lane, actual)
            totals.update(reference_selected=int(old is not None), candidate_selected=int(new is not None),
                          matching_selected=int(old is not None and new is not None and agree(old, new)))
            matched, unmatched, errors = compare(reference, actual)
            hits.update(matched)
            totals.update(lanes=1, byte_equal_lanes=int(reference == actual), extra=unmatched,
                          total_returned=len(actual), empty_returns=int(not reference and bool(actual)),
                          all_factors_matched=int(len(reference) == sum(matched.values()) and not unmatched))
            for d in errors:
                maxima = list(map(max, zip(maxima, d, strict=True)))
            if reference != actual:
                altered.append(dict(key=row["key"], lane=lane, matched=sum(matched.values()), extra=unmatched,
                                    reference=reference, candidate=actual))
    return dict(cpu_ms=clock_summary(cpu), wall_ms=clock_summary(wall),
                positive_cpu_ms=clock_summary(positive), negative_cpu_ms=clock_summary(negative),
                mean_stages_ms={key.removesuffix("_ns"): value / max(1, len(cpu)) / 1e6
                                for key, value in stages.items() if key.endswith("_ns")},
                native_stage_counts={key: value for key, value in stages.items() if not key.endswith("_ns")},
                counts=totals, matching_by_rank=[hits[0], hits[1]], maximum_deltas=maxima, altered=altered)


def measure(rows, installed, candidate, assets, repeats):
    with ExitStack() as stack:
        radios = {}
        for edge in {row["edge"] for row, _ in rows}:
            asset = np.fromfile(assets / f"{edge}.f32", dtype="<f4")
            if len(asset) != 133413:
                raise ValueError("unexpected pilot asset shape")
            control, trace = (Receiver(binary, asset) for binary in (installed, candidate))
            direct = Directed(trace, asset)
            for item in (control, trace, direct):
                stack.callback(item.close)
            radios[edge] = control, trace, direct
        lanes, base_cpu, base_wall, baseline = [], [], [], Counter()
        rng = Random(17321)
        strict_fixed = []
        for row, iq in rows:
            center = (row["target"]["rf_center_hz"] - row["target"]["lnb_lo_hz"]
                      - row["acquisition"]["actual_if_center_hz"])
            control, trace, direct = radios[row["edge"]]
            for lane in (0, 1):
                reference, cpu, wall = control.timed(iq, lane, center)
                base_cpu.append(cpu)
                base_wall.append(wall)
                baseline.update(f[0] for f in reference)
                if trace.timed(iq, lane, center)[0] != reference:
                    raise ValueError("traced receiver changed installed factors")
                scouts = direct.trace()
                factor_by_rank = {f[0]: f for f in reference}
                strict = [strict_seed(s, factor_by_rank, rank) for rank, s in enumerate(scouts)]
                nominal, decoys = external_seeds(reference, center, rng, False)
                stress, _ = external_seeds(reference, center, rng, True)
                proposals = dict(strict=strict, oracle=(strict + decoys)[:4], nominal=nominal,
                                 stress=stress, negatives=decoys)
                item = row, direct, iq, lane, center, reference, proposals
                lanes.append(item)
                if strict and len(strict) == len(reference):
                    strict_fixed.append(item)
        outcomes = {"strict_decode": evaluate(lanes, "strict", "decode", 4, repeats),
                    "strict_decode_full_load": evaluate(lanes, "strict", "decode", 4, repeats, full_load=True),
                    "strict_fixed_exact": evaluate(strict_fixed, "strict", "fixed_exact", 4, repeats),
                    "strict_fixed_guard": evaluate(strict_fixed, "strict", "fixed_guard", 4, repeats)}
        for label, mode in (("oracle", "decode"), ("oracle", "fixed_exact"), ("oracle", "fixed_guard"),
                            ("nominal", "decode"), ("nominal", "refine"),
                            ("nominal", "fixed_exact"), ("nominal", "fixed_guard"), ("stress", "refine"),
                            ("negatives", "fixed_guard")):
            for size in (1, 2, 4):
                key = f"{label}_{mode}_{size}"
                outcomes[key] = evaluate(lanes, label, mode, size, repeats)
                if label == "negatives" and mode == "fixed_guard":
                    continue
                # Keep detailed discrepancy records for strict checks and the primary two-seed alternatives.
                if size != 2:
                    del outcomes[key]["altered"]
        before, after = outcomes["strict_decode_full_load"], outcomes["strict_decode"]
        if before["altered"] != after["altered"] or before["counts"] != after["counts"]:
            raise ValueError("partial verifier load changed the traced replay")
    return dict(lanes=len(lanes), off_center_lanes=sum(case[4] != 0. for case in lanes),
                baseline_factors_by_rank=[baseline[0], baseline[1]],
                input_digests=[(row["key"], row["sha256"]) for row, _ in rows],
                installed_cpu_ms=clock_summary(base_cpu), installed_wall_ms=clock_summary(base_wall),
                strict_fixed_paired_lanes=len(strict_fixed), checks=outcomes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("archive", "history", "work", "installed", "assets", "weak", "binding", "bulk"):
        parser.add_argument(key, type=lambda value: Path(value).resolve())
    parser.add_argument("--repeats", type=int, choices=range(1, 5), default=3)
    args = parser.parse_args()
    binary, compiled = build(args)
    groups = {"weak": list(read_archive(args.weak, 18)), "dense": list(read_physical(args.binding, args.bulk, 48))}
    print(json.dumps(dict(build=compiled, repeats=args.repeats, groups={
        label: measure(rows, args.installed, binary, args.assets, args.repeats) for label, rows in groups.items()
    }), indent=2, allow_nan=False))


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "train-directed":
        print(json.dumps(train_directed(*map(Path, sys.argv[2:]))))
    else:
        main()
