"""Price an early escalation from one-lag timing to the complete signed scout."""

import argparse
import ctypes as ct
import gzip
import json
import math
from collections import Counter
from contextlib import ExitStack, closing
from pathlib import Path
from statistics import median

from tools.pipeline_eval.variants.experimental.receiver_benchmark import read_archive

from .mixed_aperture_receiver import StereoSchedule, verified
from .short_timing_lags import (
    SparseScout,
    close_factor,
    packet,
    publication_factor,
    sparse_overlay,
    strongest,
    training,
)
from .timing_only_oracle import asset_for, build, one
from .whole_group_receiver_bound import WEAK_SHA, measure, read_dense, receiver

PEAK_RATIO = 2.0
CUTOFF_RATIO = 1.125
MODES = {"control": 0, "one": 3, "routed": 6, "readout": 8}
REPEATS = 3
DENSE_POOLS = {"short": 12.635, "full": 4.716}

DECLARATIONS = """
typedef struct { double peak[5]; int escalated; } TimingCue;
static _Thread_local TimingCue timing_cues[2];

static int cutoff_confident(const double s[5]) {
    return isfinite(s[0]) && isfinite(s[3]) && isfinite(s[4]) && s[4] > 0. &&
           s[0] > PEAK_RATIO * s[4] && s[3] > CUTOFF_RATIO * s[4];
}
"""


def gate_overlay(source):
    source = sparse_overlay(source)
    marker = "static void find_sparse_times(TimingFirst *w, int *epochs, int width, int two) {"
    decl = DECLARATIONS.replace("PEAK_RATIO", str(PEAK_RATIO))
    decl = decl.replace("CUTOFF_RATIO", str(CUTOFF_RATIO))
    signature = marker.replace("int two)", "int two, double *peaks)")
    source = one(source, marker, decl + "\n" + signature)
    start = source.index("static void find_sparse_times(")
    end = source.index("static double bin_hz(", start)
    score = "        epochs[k] = best;"
    record = score + "\n        if (peaks) peaks[k] = w->time_score[best];"
    sparse = one(source[start:end], score, record)
    source = source[:start] + sparse + source[end:]
    marker = "int timing_scope_read(ScopedRows *rows) {"
    source = one(source, marker, """
int timing_cue_read(TimingCue *out) {
    if (scoped_mode < 6 || scoped_scan < 1 || scoped_scan > 2) return -1;
    memcpy(out, timing_cues, scoped_scan * sizeof(*out));
    return scoped_scan;
}
""" + marker)
    old = """        find_sparse_times(w, epochs, width, scoped_mode >= 4);
        sparse_ticks += sparse_clock() - start;
        ++sparse_amount;
        n = find_scoped_carriers(w, epochs, width, lo, hi, center, seeds);"""
    return one(source, old, """        if (scoped_mode >= 6) {
            TimingCue *cue = timing_cues + scan;
            find_sparse_times(w, epochs, 5, 0, cue->peak);
            cue->escalated = scoped_mode == 6 && !cutoff_confident(cue->peak);
            sparse_ticks += sparse_clock() - start;
            ++sparse_amount;
            if (cue->escalated) {
                find_times(w, epochs);
                n = find_carriers(w, epochs, lo, hi, center, seeds);
            } else {
                n = find_scoped_carriers(w, epochs, 4, lo, hi, center, seeds);
            }
        } else {
            find_sparse_times(w, epochs, width, scoped_mode >= 4, NULL);
            sparse_ticks += sparse_clock() - start;
            ++sparse_amount;
            n = find_scoped_carriers(w, epochs, width, lo, hi, center, seeds);
        }""")


def confident(peaks):
    a, b, c = peaks[0], peaks[3], peaks[4]
    return (all(map(math.isfinite, (a, b, c))) and c > 0.
            and a > PEAK_RATIO * c and b > CUTOFF_RATIO * c)


def confidence(peaks):
    a, b, c = peaks[0], peaks[3], peaks[4]
    if not all(map(math.isfinite, (a, b, c))) or c <= 0:
        return 0.
    return min(a / (PEAK_RATIO * c), b / (CUTOFF_RATIO * c))


class TimingCue(ct.Structure):
    _fields_ = [("peak", ct.c_double * 5), ("escalated", ct.c_int)]


class GateScout(SparseScout):
    def __init__(self, path, asset, kind):
        super().__init__(path, asset, kind)
        self.cue = self.radio.lib.timing_cue_read
        self.cue.argtypes, self.cue.restype = [ct.POINTER(TimingCue)], ct.c_int

    def evaluate(self, iq, antenna, center, mode):
        run = super().evaluate(iq, antenna, center, mode)
        if mode < 6:
            return run
        traces = (TimingCue * 2)()
        scans = self.cue(traces)
        if scans != run["scouts"] or not 1 <= scans <= 2:
            raise ValueError("The timing cue did not trace every reached scout")
        cues = []
        for scan in traces[:scans]:
            if mode == MODES["routed"] and bool(scan.escalated) == confident(scan.peak):
                raise ValueError("The native cue and diagnostic decision differ")
            peaks = [value if math.isfinite(value) else None for value in scan.peak]
            cues.append(dict(peaks=peaks, confidence=confidence(scan.peak),
                             escalated=bool(scan.escalated)))
        run["cue"] = cues
        return run


def compare(rows, builds, assets, publication=None):
    schedule = StereoSchedule(full_coverage=True)
    results = []
    with ExitStack() as stack:
        engines = {}
        for index, (row, iq) in enumerate(rows):
            a, t, edge = row["acquisition"], row["target"], row["edge"]
            _, chosen = schedule.visit(edge, t, a)
            kind = "short" if chosen == "short_primary" else "full"
            key = edge, kind
            if key not in engines:
                stock, trial, _ = builds[kind]
                asset = asset_for(assets, edge)
                pinned = stack.enter_context(closing(receiver(stock, asset, kind)))
                candidate = stack.enter_context(closing(GateScout(trial, asset, kind)))
                engines[key] = pinned, candidate
            pinned, candidate = engines[key]
            center = t["rf_center_hz"] - t["lnb_lo_hz"] - a["actual_if_center_hz"]
            for antenna in (0, 1):
                exact, blob, stock_cpu = measure(pinned, iq, antenna, center)
                published = strongest(exact)
                if publication is not None and published != publication_factor(
                    publication[a["sample_start"], antenna],
                ):
                    raise ValueError("The dense pinned detector differs from its released packet")
                timing = []
                labels = tuple(MODES)
                for repeat in range(REPEATS):
                    shift = (index + antenna + repeat) % len(labels)
                    arms = {}
                    for label in labels[shift:] + labels[:shift]:
                        trace = candidate.evaluate(iq, antenna, center, MODES[label])
                        current = trace["factors"]
                        trace["exact_hex"] = trace.pop("exact").hex()
                        trace["changed_bytes"] = trace["exact_hex"] != blob.hex()
                        trace["changed_published"] = strongest(current) != published
                        trace["missing_published"] = published is not None and not any(
                            close_factor(f, published) for f in current
                        )
                        arms[label] = trace
                    if arms["control"]["changed_bytes"]:
                        raise ValueError("The same-build full call changed the pinned signed bytes")
                    if arms["one"]["exact_hex"] != arms["readout"]["exact_hex"]:
                        raise ValueError("The fifth readout modified the one-lag detector")
                    timing.append(arms)
                results.append(dict(case=row["case"], key=row["key"], iq=row["sha256"],
                                    lane=antenna, kind=kind, stock_cpu=stock_cpu,
                                    stock=exact, arms=timing))
    return results


def separability(samples):
    """Count optimistic false escalations required to cover all changed observations."""
    output = {}
    for index, key in ((1, "signed_bytes"), (2, "published")):
        failures = [sample[0] for sample in samples if sample[index]]
        cut = max(failures, default=None)
        if cut is None:
            output[key] = None
            continue
        safe = [sample[0] for sample in samples if not sample[index]]
        output[key] = dict(max_bad=cut, min_bad=min(failures),
                           safe_median=median(safe) if safe else None,
                           false_escalations=sum(value <= cut for value in safe),
                           safe=len(safe), bad=len(failures))
    return output


def attribution(rows):
    counts = Counter()
    samples = []
    for row in rows:
        runs = row["arms"][0]
        raw, routed = runs["readout"], runs["routed"]
        flag = any(cue["escalated"] for cue in routed["cue"])
        counts.update(lanes=1, one_changes=raw["changed_bytes"],
                      one_published_changes=raw["changed_published"],
                      routed_changes=routed["changed_bytes"],
                      routed_published_changes=routed["changed_published"],
                      routed_missing=routed["missing_published"], escalated_lanes=flag,
                      false_escalations=flag and not raw["changed_bytes"],
                      false_publication_escalations=flag and not raw["changed_published"])
        for idx, cue in enumerate(routed["cue"]):
            counts["raw_escalated" if idx == 0 else "residual_escalated"] += cue["escalated"]
            counts["raw_scouts" if idx == 0 else "residual_scouts"] += 1
            counts["escalated_scouts_on_byte_exact_lanes"] += (
                cue["escalated"] and not raw["changed_bytes"]
            )
        samples.append((min(c["confidence"] for c in raw["cue"]), raw["changed_bytes"],
                        raw["changed_published"]))
    clocks = {label: [] for label in MODES}
    oracle_retry = []
    for repeat in range(REPEATS):
        for label in MODES:
            clocks[label].append(sum(row["arms"][repeat][label]["cpu"] for row in rows))
        oracle_retry.append(sum(row["arms"][repeat]["control"]["cpu"] for row in rows
                                if row["arms"][repeat]["routed"]["changed_bytes"]))
    return dict(counts, median_cpu_ns={k: median(ticks) for k, ticks in clocks.items()},
                routed_oracle_retry_ns=median(oracle_retry), separability=separability(samples))


def summary(rows):
    groups = {"mixed": rows}
    for kind in ("short", "full"):
        groups[kind] = [row for row in rows if row["kind"] == kind]
    for case in sorted({row["case"] for row in rows}):
        groups[case] = [row for row in rows if row["case"] == case]
    return {name: attribution(group) for name, group in groups.items() if group}


def axes(row):
    scores = [cue["peaks"] for cue in row["arms"][0]["readout"]["cue"]]
    return tuple(min(values[i] / values[4] if values[i] is not None and values[4] else 0.
                     for values in scores) for i in (0, 3))


def hindsight_rectangles(rows, pools):
    """Grant both tuned thresholds, advance knowledge of the residual, and free routing."""
    features = [(row, *axes(row)) for row in rows]
    failures = [(p, q) for row, p, q in features if row["arms"][0]["one"]["changed_bytes"]]
    boundaries = [-math.inf, *sorted({p for p, _ in failures})]
    best = None
    for peak in boundaries:
        cutoff = max((q for p, q in failures if p > peak), default=-math.inf)
        spend = [(row, p <= peak or q <= cutoff) for row, p, q in features]
        false = sum(full and not row["arms"][0]["one"]["changed_bytes"] for row, full in spend)
        saving = 0.
        for aperture, cost in pools.items():
            used = [(row, full) for row, full in spend if row["kind"] == aperture]
            stock = median(sum(row["arms"][k]["control"]["cpu"] for row, _ in used)
                           for k in range(REPEATS))
            paid = median(sum(row["arms"][k]["control" if full else "one"]["cpu"]
                              for row, full in used) for k in range(REPEATS))
            saving += (1 - paid / stock) * cost
        if best is None or saving > best["gross_saved_s"]:
            best = dict(peak=peak if math.isfinite(peak) else None,
                        cutoff=cutoff if math.isfinite(cutoff) else None,
                        false_escalations=false, gross_saved_s=saving)
    return best


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(required=True, dest="mode")
    bench = modes.add_parser("bench")
    for name in ("work", "assets", "weak", "dense", "packet"):
        bench.add_argument(name, type=lambda value: Path(value).resolve())
    feedback = modes.add_parser("train")
    feedback.add_argument("library", type=Path)
    feedback.add_argument("kind", choices=("full", "short"))
    feedback.add_argument("assets", type=Path)
    analyze = modes.add_parser("analyze")
    analyze.add_argument("receipt", type=Path)
    args = parser.parse_args()
    if args.mode == "train":
        print(json.dumps(training(args.library, args.kind, args.assets, MODES)))
        return
    if args.mode == "analyze":
        data = args.receipt.read_bytes()
        if args.receipt.suffix == ".gz":
            data = gzip.decompress(data)
        print(json.dumps(hindsight_rectangles(json.loads(data)["dense"]["rows"], DENSE_POOLS)))
        return
    verified(args.weak, WEAK_SHA)
    reference = packet(args.packet)
    builds = build(args.work, args.assets, source_overlay=gate_overlay,
                   extra_flags=("-D_POSIX_C_SOURCE=200809L",),
                   worker="reports.ALGO08.v3.precarrier_timing_gate")
    weak = compare(read_archive(args.weak, 18), builds, args.assets)
    dense = compare(read_dense(args.dense, 48), builds, args.assets, reference)
    if len(weak) != 36 or len(dense) != 96:
        raise ValueError("The saved matched lane counts changed")
    result = dict(rule=dict(peak=PEAK_RATIO, cutoff=CUTOFF_RATIO),
                  builds={k: v[-1] for k, v in builds.items()},
                  weak=dict(rows=weak, metrics=summary(weak)),
                  dense=dict(rows=dense, metrics=summary(dense)))
    print(json.dumps(result, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
