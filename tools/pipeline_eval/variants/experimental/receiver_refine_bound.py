"""Measure the savings ceiling of exact within-scout hypothesis pruning."""

import argparse
import ctypes as ct
import json
import math
import subprocess
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from statistics import median

import numpy as np

from ..carrier_continuation import Continuation
from .receiver_benchmark import Receiver, benchmark, digest, read_archive
from .receiver_brackets import read_physical
from .receiver_build import replace
from .receiver_cfo_peak_bound import build_trace

OVERLAY = """
typedef struct {
    int epoch, gate, supported, matches;
    double hz, score, upper[4];
} RefineAuditSeed;
typedef struct {
    int count, winner, gate_stages;
    uint64_t bank_cpu_ns, bank_wall_ns;
    RefineAuditSeed seed[max_peaks];
} RefineAuditScan;

static _Thread_local int refine_audit_mode, refine_audit_count;
static _Thread_local RefineAuditScan refine_audit_scans[2];
int receiver_refine_enclosure(const float *, const float *, RefineRequest,
                              double, double, double *, double *);

int receiver_refine_audit(RefineAuditScan *out, int mode) {
    int n = refine_audit_count;
    if (out && (n == 1 || n == 2))
        memcpy(out, refine_audit_scans, n * sizeof(*out));
    refine_audit_mode = mode;
    refine_audit_count = 0;
    return n;
}

static uint64_t audit_clock(clockid_t id) {
    struct timespec tick;
    clock_gettime(id, &tick);
    return (uint64_t)tick.tv_sec * UINT64_C(1000000000) + tick.tv_nsec;
}

static int scout_gate(TimingFirst *w, const Peak *p, int *calls) {
    ++*calls;
    if (gate(w, p, 160, 0)) return 1;
    ++*calls;
    if (gate(w, p, 232, 0)) return 1;
    ++*calls;
    return gate(w, p, 0, 1) ? 2 : 0;
}
"""

BANK = """    double v[max_peaks][4];
    if (delay_refine_bank((float *)w->data, (float *)(w->pilot + first), request, done, lo, hi, v))
        return -1;"""


def inject_audit(source):
    source = ('#define _POSIX_C_SOURCE 200809L\n#include <stdint.h>\n#include <time.h>\n'
              + source)
    signature = "static int detect_lane("
    source = replace(source, signature, OVERLAY + "\n" + signature)
    source = replace(source, BANK, """    RefineAuditScan *audit = refine_audit_count < 2
        ? &refine_audit_scans[refine_audit_count++] : NULL;
    if (audit) *audit = (RefineAuditScan){.count = done, .winner = -1};
    uint64_t wall = audit_clock(CLOCK_MONOTONIC), cpu = audit_clock(CLOCK_THREAD_CPUTIME_ID);
""" + BANK + """
    if (audit) {
        audit->bank_cpu_ns = audit_clock(CLOCK_THREAD_CPUTIME_ID) - cpu;
        audit->bank_wall_ns = audit_clock(CLOCK_MONOTONIC) - wall;
    }""")
    gate = """        int why = 0;
        if (gate(w, &p, 160, 0) || gate(w, &p, 232, 0))
            why = 1;
        else if (gate(w, &p, 0, 1))
            why = 2;
        if (why) {"""
    source = replace(source, gate, """        int calls = 0;
        int why = scout_gate(w, &p, &calls);
        if (audit) audit->gate_stages += calls;
        if (why) {
            if (audit) audit->winner = best;""")
    finish = "    return 0;\n}\n\nint timing_first_detect("
    return replace(source, finish, """    if (audit && refine_audit_mode) {
        for (int i = 0; i < done; ++i) {
            double scores[4];
            Peak p = (Peak){v[i][0], v[i][1], v[i][3], (int)v[i][2]};
            int trials = 0;
            RefineAuditSeed *seed = &audit->seed[i];
            seed->epoch = request[i].epoch;
            seed->hz = request[i].hz;
            seed->score = p.score;
            seed->gate = scout_gate(w, &p, &trials) ? trials : -trials;
            seed->supported = receiver_refine_enclosure((float *)w->data,
                (float *)(w->pilot + first), request[i], lo, hi, scores, seed->upper);
            seed->matches = seed->supported && memcmp(scores, v[i], sizeof(scores)) == 0;
        }
    }
""" + finish)


def inject_pruning(source, *, enabled):
    source = replace(source, "static int detect_lane(", f"""
int receiver_refine_pruning __attribute__((section(".data"))) = {int(enabled)};
""" + """
int receiver_refine_prune(const float *, const float *, RefineRequest, double,
                          double, double, double *);

static int confirmation(TimingFirst *w, const Peak *p) {
    if (gate(w, p, 160, 0) || gate(w, p, 232, 0)) return 1;
    return gate(w, p, 0, 1) ? 2 : 0;
}

static int detect_lane(""")
    source = replace(source, BANK, """    double v[max_peaks][4];
    const float *x = (float *)w->data, *h = (float *)(w->pilot + first);
    if (receiver_refine_pruning && done == choices) {
        if (delay_refine_bank(x, h, request, 1, lo, hi, v)) return -1;
        Peak first_peak = (Peak){v[0][0], v[0][1], v[0][3], (int)v[0][2]};
        int why = confirmation(w, &first_peak);
        if (why) {
            *out = (TimingFirstResult){first_peak.epoch, first_peak.hz, first_peak.score, why};
            for (int i = 1; i < done; ++i) {
                int status = receiver_refine_prune(x, h, request[i], lo, hi, first_peak.score, v[i]);
                if (status == 2 && delay_refine_bank(x, h, request + i, 1, lo, hi, v + i))
                    return -1;
                if (status < 0) return -1;
                if (status == 1) {
                    memset(v[i], 0, sizeof(v[i]));
                    v[i][3] = -1.;
                } else if (v[i][3] <= first_peak.score) {
                    v[i][3] = -1.;
                }
            }
        } else if (delay_refine_bank(x, h, request + 1, done - 1, lo, hi, v + 1)) {
            return -1;
        }
        v[0][3] = -1.;
    } else if (delay_refine_bank(x, h, request, done, lo, hi, v)) {
        return -1;
    }""")
    gate = """        int why = 0;
        if (gate(w, &p, 160, 0) || gate(w, &p, 232, 0))
            why = 1;
        else if (gate(w, &p, 0, 1))
            why = 2;"""
    return replace(source, gate, """        if (p.score < 0.) break;
        int why = confirmation(w, &p);""")


def build_audit(archive, work, *, pruning=None):
    def instrument(source):
        if pruning is None:
            return inject_audit(source)
        return inject_pruning(source, enabled=pruning)

    reference, _ = build_trace(archive, work, instrument=instrument)
    manifest = json.loads((archive / "build.json").read_bytes())
    link = manifest["commands"][-1]
    timing, = (i for i, value in enumerate(link) if Path(value).name == "timing_first_receiver.o")
    delay, = (Path(value) for value in link if Path(value).name == "delay_reference.o")
    # The source that compiled into the archived PGO object was also retained.
    wrap_manifest = json.loads((delay.parent / "build.json").read_bytes())
    original, = (Path(value) for value in wrap_manifest["commands"][1]
                 if Path(value).name == "delay_product_kernel.o")
    archived = original.parent
    source = Path(__file__).with_suffix(".c").resolve()
    if digest((archived / "delay_product_kernel.c").read_bytes()) != (
            "d014fe0670ff7a926bbd302ada1f4d021fe2f488f91b32dae8b4fe1634a07f1c"):
        raise ValueError("unexpected source for the frozen ALGO08v3 block reductions")
    compiler = manifest["commands"][-2]
    bound_object = work / "enclosure.o"
    subprocess.run([compiler[0], "-I", archived, *compiler[1:-4], "-c", source,
                    "-o", bound_object], cwd=manifest["cwd"], check=True)
    link[timing] = str(work / "timing_first_receiver.o")
    output = work / ("audit.so" if pruning is None else "pruned.so")
    subprocess.run([*link[:timing], bound_object, *link[timing:-1], output], check=True)
    return reference, output


class Seed(ct.Structure):
    _fields_ = [("epoch", ct.c_int), ("gate", ct.c_int), ("supported", ct.c_int),
                ("matches", ct.c_int), ("hz", ct.c_double), ("score", ct.c_double),
                ("upper", ct.c_double * 4)]


class Scan(ct.Structure):
    _fields_ = [("count", ct.c_int), ("winner", ct.c_int), ("gate_stages", ct.c_int),
                ("bank_cpu_ns", ct.c_uint64), ("bank_wall_ns", ct.c_uint64),
                ("seed", Seed * 16)]


def read_scans(radio, *, detail=False):
    reader = radio.lib.receiver_refine_audit
    reader.argtypes = [ct.POINTER(Scan), ct.c_int]
    reader.restype = ct.c_int
    scans = (Scan * 2)()
    n = reader(scans, int(detail))
    if n not in (1, 2):
        raise ValueError(f"expected one or two instrumented scouts, found {n}")
    return scans[:n]


def schedule(seeds, mode):
    """Simulate strict certification against an already confirmed incumbent."""
    winner, half_blocks, gate_stages, pruned = None, 0, 0, []
    for i, row in enumerate(seeds):
        score, gate, upper = row["score"], row["gate"], row["upper"]
        if mode is not None and winner is not None and upper is not None:
            half_blocks += 1
            if upper[mode] < seeds[winner]["score"]:
                pruned.append(i)
                continue
            half_blocks += 1
        else:
            half_blocks += 2
        if winner is None or score > seeds[winner]["score"]:
            gate_stages += abs(gate)
            if gate > 0:
                winner = i
    return dict(winner=winner, half_blocks=half_blocks, gate_stages=gate_stages, pruned=pruned)


def first_then_ranked(seeds):
    """Count the prototype's fixed first-candidate cutline and gate order."""
    n = len(seeds)
    if not n:
        return dict(winner=None, half_blocks=0, gate_stages=0, pruned=[])
    first = seeds[0]
    winner = 0 if first["gate"] > 0 else None
    attempts, pruned = abs(first["gate"]), []
    cutline = first["score"] if winner is not None else -math.inf
    for i, row in enumerate(seeds[1:], 1):
        if row["upper"] is not None and row["upper"][0] < cutline:
            pruned.append(i)
    remaining = sorted(range(1, n), key=lambda i: -seeds[i]["score"])
    for i in remaining:
        row = seeds[i]
        if row["score"] <= cutline:
            break
        attempts += abs(row["gate"])
        if row["gate"] > 0:
            winner = i
            break
    return dict(winner=winner, half_blocks=2*n-len(pruned), gate_stages=attempts, pruned=pruned)


def scan_detail(scan):
    winner = None if scan.winner < 0 else scan.winner
    seeds = []
    for seed in scan.seed[:scan.count]:
        if seed.supported and not seed.matches:
            raise ValueError("single-request matrix changed frozen refinement score or location")
        upper = [value if math.isfinite(value) else None for value in seed.upper]
        if seed.supported and any(value is not None and value < seed.score for value in upper):
            raise ValueError("measured stock score does not fit its enclosure")
        seeds.append(dict(epoch=seed.epoch, hz=seed.hz, score=seed.score, gate=seed.gate,
                          upper=upper if seed.supported and all(value is not None for value in upper)
                          else None))
    schedules = {key: schedule(seeds, mode) for key, mode in
                 [("even_triangle", 0), ("even_restricted", 1), ("odd_triangle", 2),
                  ("odd_restricted", 3), ("sequential_full", None)]}
    schedules["first_then_ranked"] = first_then_ranked(seeds)
    if any(result["winner"] != winner for result in schedules.values()):
        raise ValueError("refinement pruning or rank schedule changed a frozen scout winner")
    return dict(winner=winner, gate_stages=scan.gate_stages, seeds=seeds, schedules=schedules)


def measure(rows, reference, instrumented, assets, repeats):
    timings, profiles, details = [], [], []
    with ExitStack() as close:
        radios = {}
        for edge in sorted({row["edge"] for row, _ in rows}):
            pilot = np.fromfile(assets / f"{edge}.f32", dtype="<f4")
            if pilot.shape != (133413,):
                raise ValueError("invalid receiver pilot asset")
            for arm, binary in enumerate((reference, instrumented)):
                radio = Receiver(binary, pilot)
                close.callback(radio.close)
                radios[edge, arm] = radio

        for repeat in range(repeats + 1):
            detail = repeat == repeats
            continuation = {}
            time_cpu, time_wall, profile_cpu, profile_wall = Counter(), Counter(), Counter(), Counter()
            # Set the mode once per distinct loaded file, then clear traces per lane.
            radio = next(radio for (_, arm), radio in radios.items() if arm == 1)
            radio.lib.receiver_refine_audit(None, int(detail))
            for index, (row, iq) in enumerate(rows):
                target, a = row["target"], row["acquisition"]
                rf = a["actual_if_center_hz"] + target["lnb_lo_hz"]
                center = target["rf_center_hz"] - rf
                for lane in (0, 1):
                    result, selection, measured = {}, {}, []
                    first = (repeat + index + lane) % 2
                    for arm in (first, 1-first):
                        radio = radios[row["edge"], arm]
                        factors, cpu, wall = radio.timed(iq, lane, center)
                        result[arm] = factors
                        time_cpu[arm] += cpu
                        time_wall[arm] += wall
                        history = continuation.setdefault((arm, row["case"]), Continuation())
                        selection[arm] = history.select(dict(
                            receiver_id=lane, channel=target["channel"], actual_rf_hz=rf,
                            valid_start_counter=a["sample_start"],
                            candidates=[radio.criteria(*factor) for factor in factors],
                        ))
                        if arm == 1:
                            for pass_id, scan in enumerate(read_scans(radio, detail=detail)):
                                profile_cpu[pass_id] += scan.bank_cpu_ns
                                profile_wall[pass_id] += scan.bank_wall_ns
                                if detail:
                                    measured.append(scan_detail(scan))
                    if result[0] != result[1] or selection[0] != selection[1]:
                        raise ValueError(f"trace changed a factor or continuation at {row['key']} lane {lane}")
                    if detail:
                        details.append(dict(window=row["key"], iq_sha256=row["sha256"], lane=lane,
                                            factors=result[0], continuation=selection[0], scans=measured))
            if not detail:
                timings.append(dict(cpu_ns=[time_cpu[i] for i in (0, 1)],
                                    wall_ns=[time_wall[i] for i in (0, 1)]))
                profiles.append(dict(cpu_ns=[profile_cpu[i] for i in (0, 1)],
                                     wall_ns=[profile_wall[i] for i in (0, 1)]))
    return dict(timings=timings, profiles=profiles, lanes=details, summary=summarize(details, timings, profiles))


def summarize(details, timings, profiles):
    passes = [Counter(), Counter()]
    modes = [{}, {}]
    for row in details:
        for pass_id, scan in enumerate(row["scans"]):
            n = len(scan["seeds"])
            passes[pass_id].update(scouts=1, hypotheses=n, half_blocks=2*n,
                                  stock_gate_stages=scan["gate_stages"],
                                  confirmed=int(scan["winner"] is not None),
                                  clairvoyant_omitted=(n - 1) if scan["winner"] is not None else 0)
            for name, result in scan["schedules"].items():
                modes[pass_id].setdefault(name, Counter()).update(
                    pruned=len(result["pruned"]), half_blocks=result["half_blocks"],
                    gate_stages=result["gate_stages"])
    return dict(
        lanes=len(details), scouts=passes, schedules=modes,
        factor_ranks=dict(Counter(factor[0] for lane in details for factor in lane["factors"])),
        selected=sum(row["continuation"][1] is not None for row in details),
        factor_digest=digest(json.dumps([(row["window"], row["lane"], row["factors"],
                                          row["continuation"]) for row in details]).encode()),
        reference_native_cpu_ns=median(row["cpu_ns"][0] for row in timings),
        reference_native_wall_ns=median(row["wall_ns"][0] for row in timings),
        bank_cpu_ns=median(sum(row["cpu_ns"]) for row in profiles),
        bank_wall_ns=median(sum(row["wall_ns"]) for row in profiles),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("work", type=Path)
    parser.add_argument("assets", type=Path)
    parser.add_argument("weak", type=Path)
    parser.add_argument("binding", type=Path)
    parser.add_argument("bulk", type=Path)
    parser.add_argument("--dense-visits", type=int, choices=range(1, 65), default=48)
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=3)
    parser.add_argument("--pruning", action="store_true")
    args = parser.parse_args()
    reference, instrumented = build_audit(args.archive, args.work,
                                          pruning=True if args.pruning else None)
    if args.pruning:
        _, disabled = build_audit(args.archive, args.work.with_name(args.work.name + "-off"),
                                  pruning=False)
    weak = list(read_archive(args.weak, 18))
    dense = list(read_physical(args.binding, args.bulk, args.dense_visits))
    if not weak or not dense:
        raise ValueError("expected nonempty weak and dense waveform slices")
    def run(rows):
        if args.pruning:
            pairs = dict(v3_on=(reference, instrumented), off_on=(disabled, instrumented))
            results = {name: benchmark(pair, rows, args.assets, args.repeats)
                       for name, pair in pairs.items()}
            for evidence in results.values():
                if evidence["changed"] or evidence["changed_continuation"] or len(
                        set(evidence["factor_digests"])) != 1:
                    raise ValueError("pruning changed ordered factors or continuation")
            return results
        return measure(rows, reference, instrumented, args.assets, args.repeats)

    result = dict(reference_sha256=digest(reference.read_bytes()),
                  candidate_sha256=digest(instrumented.read_bytes()),
                  weak=run(weak), dense=run(dense))
    if args.pruning:
        result["disabled_sha256"] = digest(disabled.read_bytes())
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
