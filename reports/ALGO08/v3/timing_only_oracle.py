"""Price signed native acquisition when a timing source supplies the finalist rows."""

import argparse
import ctypes as ct
import json
import subprocess
import sys
from collections import Counter
from contextlib import ExitStack, closing
from hashlib import sha256
from pathlib import Path
from statistics import median

import numpy as np

from tools.pipeline_eval.variants.carrier_continuation import Continuation
from tools.pipeline_eval.variants.experimental.receiver_benchmark import read_archive

from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, StereoSchedule, verified
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
    read_dense,
    receiver,
)

EPOCHS, CLOCKS, FINALISTS = 3333, 12, 4
TICKS = 40000
WINDOWS = (4, 16, 64, 256, 1024)
REPEATS = 3
LABELS = ("installed", "control", "minimum", "four", "eight", "twelve")
SIZES = {"minimum": 0, "four": 4, "eight": 8, "twelve": 12}


C_LOCALS = """
typedef struct { int available, order[clocks], used[choices]; } ScopedRows;
static _Thread_local ScopedRows scoped_rows[2];
static _Thread_local int scoped_mode, scoped_scan, scoped_size[2], scoped_allow[2][clocks];

void timing_scope_set(int mode, const int *sizes, const int *epochs) {
    scoped_mode = mode;
    scoped_scan = 0;
    if (mode == 2) {
        memcpy(scoped_size, sizes, sizeof(scoped_size));
        memcpy(scoped_allow, epochs, sizeof(scoped_allow));
    }
}

int timing_scope_read(ScopedRows *rows) {
    if (scoped_mode != 1 || scoped_scan < 1 || scoped_scan > 2) return -1;
    memcpy(rows, scoped_rows, scoped_scan * sizeof(*rows));
    return scoped_scan;
}
"""


def one(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"The checked receiver source differs near {old!r}")
    return text.replace(old, new)


def overlay(source):
    start = source.index("static int find_carriers(")
    end = source.index("/* At a proposed native carrier", start)
    original = source[start:end]
    nearby = one(original, "find_carriers(TimingFirst *w, const int *epochs,",
                 "find_scoped_carriers(TimingFirst *w, const int *epochs, int epoch_count,")
    nearby = one(nearby, "i < clocks", "i < epoch_count")
    source = source[:end] + C_LOCALS + nearby + source[end:]
    old = "    int epochs[clocks];\n    find_times(w, epochs);\n    Seed seeds[2 * clocks];\n"
    old += "    int n = find_carriers(w, epochs, lo, hi, center, seeds), done = 0;"
    source = one(source, old, """    int epochs[clocks];
    Seed seeds[2 * clocks];
    int n, done = 0, scan = 0;
    if (scoped_mode) {
        scan = scoped_scan++;
        if (scan >= 2) return -1;
    }
    if (scoped_mode == 2) {
        if (scoped_size[scan] < 1 || scoped_size[scan] > clocks) return -1;
        n = find_scoped_carriers(w, scoped_allow[scan], scoped_size[scan], lo, hi, center, seeds);
    } else {
        find_times(w, epochs);
        n = find_carriers(w, epochs, lo, hi, center, seeds);
        if (scoped_mode == 1) {
            memcpy(scoped_rows[scan].order, epochs, sizeof(epochs));
            scoped_rows[scan].available = n < choices ? n : choices;
        }
    }
""")
    old = "        Seed selected = seeds[pick];"
    return one(source, old, old + """
        if (scoped_mode == 1) scoped_rows[scan].used[k] = selected.epoch / w->stride;
""")


class ScopedRows(ct.Structure):
    _fields_ = [("available", ct.c_int), ("order", ct.c_int * CLOCKS),
                ("used", ct.c_int * FINALISTS)]


class Scout:
    def __init__(self, path, asset, kind):
        self.radio = receiver(path, asset, kind)
        self.set = self.radio.lib.timing_scope_set
        self.set.argtypes = [ct.c_int, ct.POINTER(ct.c_int), ct.POINTER(ct.c_int)]
        self.set.restype = None
        self.read = self.radio.lib.timing_scope_read
        self.read.argtypes, self.read.restype = [ct.POINTER(ScopedRows)], ct.c_int

    def close(self):
        self.radio.close()

    def capture(self, iq, antenna, center):
        self.set(1, None, None)
        factors, exact, _ = measure(self.radio, iq, antenna, center)
        rows = (ScopedRows * 2)()
        count = self.read(rows)
        if count not in (1, 2):
            raise ValueError(f"Expected a primary and optional residual trace, got {count}")
        result = [(list(row.order), list(row.used[:row.available])) for row in rows[:count]]
        return factors, exact, result

    def run(self, iq, antenna, center, rows, size=None):
        if size is None:
            self.set(0, None, None)
        else:
            scopes = [scope_order(order, required, size) for order, required in rows]
            counts = (ct.c_int * 2)(*map(len, scopes))
            payload = (ct.c_int * (2 * CLOCKS))()
            for scan, scope in enumerate(scopes):
                payload[scan * CLOCKS:scan * CLOCKS + len(scope)] = scope
            self.set(2, counts, payload)
        return measure(self.radio, iq, antenna, center)


def scope_order(order, required, size):
    """Subset the original row order so equal carrier powers keep the same first seed."""
    locked = set(required)
    if not locked or len(locked) > FINALISTS or not locked.issubset(order):
        raise ValueError("The original finalists require at least one valid timing row")
    if size and not len(locked) <= size <= CLOCKS:
        raise ValueError("The oracle cannot admit fewer rows than the finalists require")
    if size:
        for epoch in order:
            if len(locked) >= size:
                break
            locked.add(epoch)
    return [epoch for epoch in order if epoch in locked]


def asset_for(assets, edge):
    return np.frombuffer(verified(assets / f"{edge}.f32", PILOT_SHA[edge]), dtype="<f4")


def train(library, kind, assets):
    """Site-free signal, overlap and noise paths exercise both dispatch arms for GCC."""
    random = np.random.default_rng(31577)
    samples = np.arange(200000)
    output = Counter()
    for edge in PILOT_SHA:
        asset = asset_for(assets, edge)
        pilot = asset[4 * 13333 + 81:].view(np.complex64)
        with closing(Scout(library, asset, kind)) as scout:
            for case, center in enumerate((0, 50000, -60000, 0)):
                iq = random.normal(0, 18, (len(samples), 2, 2)).astype(np.int16)
                for antenna in (0, 1):
                    if case != 3:
                        x = 1600 * pilot[(3 * samples - 2400 - 1569 * antenna) % TICKS]
                        x = x * np.exp(2j * np.pi * (-350000 + 195000 * antenna) * samples * 1e-7)
                        if case == 2:
                            y = 360 * pilot[(3 * samples - 5833) % TICKS]
                            x += y * np.exp(2j * np.pi * 312000 * samples * 1e-7)
                        iq[:, antenna, 0] += np.rint(x.real).astype(np.int16)
                        iq[:, antenna, 1] += np.rint(x.imag).astype(np.int16)
                    _, exact, rows = scout.capture(iq, antenna, center)
                    for size in (None, *SIZES.values()):
                        _, current, _ = scout.run(iq, antenna, center, rows, size)
                        if current != exact:
                            raise ValueError("Synthetic training changed native factor bytes")
                    output["lanes"] += 1
                    output["scouts"] += len(rows)
    return dict(output)


def build(root, assets):
    full = json.loads(verified(FULL_BUILD, FULL_BUILD_SHA))
    short = json.loads(verified(SHORT_BUILD, SHORT_BUILD_SHA))
    builds = {}
    for kind, link, expected in (
        ("full", full["commands"][-1], INSTALLED_SHA),
        ("short", short["relink"], SHORT_SHA),
    ):
        work = root / kind
        feedback = work / "feedback"
        feedback.mkdir(parents=True)
        stock = work / "stock.so"
        subprocess.run([*link[:-1], stock], cwd=full["cwd"], check=True)
        verified(stock, expected)
        old, = (value for value in link if Path(value).name == "timing_first_receiver.o")
        source = verified(Path(old).with_suffix(".c"), SOURCE_SHA[kind]).decode()
        c_path = work / "timing_first_receiver.c"
        c_path.write_text(overlay(source))
        obj = c_path.with_suffix(".o")
        relink = [str(obj) if arg == old else arg for arg in link[1:-1]
                  if not arg.startswith("-fprofile-use") and arg != "-fno-profile-values"]
        receipt = dict(source=sha256(c_path.read_bytes()).hexdigest(), stock=expected)
        for phase in ("generate", "use"):
            binary = work / f"{phase}.so"
            profile = [f"-fprofile-{phase}={feedback}", "-fno-profile-values"]
            guard = []
            if phase == "use":
                guard = ["-Werror=missing-profile", "-Werror=coverage-mismatch"]
            cc = full["commands"][-2]
            subprocess.run([*cc[:-4], *profile, *guard, "-c", c_path, "-o", obj],
                           cwd=full["cwd"], check=True)
            subprocess.run([cc[0], *profile, *relink, binary], cwd=full["cwd"], check=True)
            if phase == "generate":
                command = [sys.executable, "-BPs", "-m", "reports.ALGO08.v3.timing_only_oracle",
                           "train", str(binary), kind, str(assets)]
                result = subprocess.check_output(command, text=True)
                receipt["training"] = json.loads(result)
        receipt["trial"] = sha256(binary.read_bytes()).hexdigest()
        builds[kind] = (stock, binary, receipt)
    return builds


def total_cpu(runs):
    totals = Counter(dict.fromkeys(LABELS, 0))
    for row in runs:
        totals.update(row)
    return dict(totals)


def audit(rows, builds, assets):
    status, details, factors, selected = Counter(), [], Counter(), Counter()
    schedule = StereoSchedule(full_coverage=True)
    with ExitStack() as stack:
        radios, histories, exact_history = {}, {}, {}
        for index, (row, iq) in enumerate(rows):
            a, t, edge = row["acquisition"], row["target"], row["edge"]
            center = t["rf_center_hz"] - t["lnb_lo_hz"] - a["actual_if_center_hz"]
            _, scheduled = schedule.visit(edge, t, a)
            scheduled = "short" if scheduled == "short_primary" else "full"
            for kind, (stock_path, trial_path, _) in builds.items():
                key = edge, kind
                if key not in radios:
                    asset = asset_for(assets, edge)
                    stock = stack.enter_context(closing(receiver(stock_path, asset, kind)))
                    trial = stack.enter_context(closing(Scout(trial_path, asset, kind)))
                    radios[key] = stock, trial
                stock, trial = radios[key]
                for antenna in (0, 1):
                    nominations, exact, scopes = trial.capture(iq, antenna, center)
                    times = []
                    for repeat in range(REPEATS):
                        start = (index + antenna + repeat) % len(LABELS)
                        ordered = LABELS[start:] + LABELS[:start]
                        clocks = {}
                        for label in ordered:
                            if label == "installed":
                                measured = measure(stock, iq, antenna, center)
                            else:
                                measured = trial.run(iq, antenna, center, scopes, SIZES.get(label))
                            value, bytes_, clocks[label] = measured
                            if bytes_ != exact:
                                status[kind, label] += 1
                            if repeat == 0:
                                hist_key = row["case"], kind, label
                                history = histories.setdefault(hist_key, Continuation())
                                choice = history.select(history_row(value, row, antenna))
                                if label == "installed":
                                    selected[kind] += choice[1] is not None
                                lane_key = kind, antenna, row["key"]
                                if exact_history.setdefault(lane_key, choice) != choice:
                                    status[kind, label, "continuation"] += 1
                        times.append(clocks)
                    factors.update(f"{kind}-{value[0]}" for value in nominations)
                    details.append(dict(kind=kind, scheduled=scheduled, key=row["key"],
                                        recording=row["case"], sample=a["sample_start"], edge=edge,
                                        rf=a["actual_if_center_hz"] + t["lnb_lo_hz"],
                                        generation=a.get("generation"), antenna=antenna,
                                        iq=row["sha256"], factors=nominations, scopes=scopes,
                                        clocks=times))
    return dict(rows=details, factors=dict(factors), selected=dict(selected),
                changes={"/".join(key): value for key, value in status.items()})


def clock_summary(detail):
    totals = [total_cpu(row["clocks"][i] for row in detail) for i in range(REPEATS)]
    ns = {label: median(row[label] for row in totals) for label in LABELS}
    return dict(lanes=len(detail), median_cpu_ns=ns, repeats_cpu_ns=totals)


def phase_offset(factor, donor_start, query_start):
    """Advance the absolute epoch into the current visit using fixed 40000-third wraps."""
    epoch = round(3 * (factor[1] + factor[2]))
    return ((donor_start - query_start) * 3 + epoch) % TICKS


def distance(epoch, hypotheses):
    return min((abs((3 * (4 * epoch) - phase + TICKS // 2) % TICKS - TICKS // 2) / 3
                for phase in hypotheses), default=float("inf"))


def scoped_bins(hypotheses, radius):
    width = radius * 3
    bins = set()
    for phase in hypotheses:
        for shifted in (phase - TICKS, phase, phase + TICKS):
            low = max(0, -((width - shifted) // 12))
            high = min(EPOCHS - 1, (shifted + width) // 12)
            bins.update(range(low, high + 1))
    return bins


def support(rows):
    past = {}
    current = {(r["key"], r["antenna"]): r for r in rows}
    output = Counter()
    for row in rows:
        output["lanes"] += 1
        peer = current[row["key"], 1 - row["antenna"]]
        key = (row["recording"], row["antenna"], row["edge"], row["rf"], row["generation"])
        older = [old for old in past.get(key, ())
                 if 0 < row["sample"] - old["sample"] <= 20_000_000]
        hypotheses = {
            "past": [phase_offset(f, old["sample"], row["sample"])
                     for old in older for f in old["factors"]],
            "peer": [phase_offset(f, peer["sample"], row["sample"]) for f in peer["factors"]],
        }
        hypotheses["union"] = hypotheses["past"] + hypotheses["peer"]
        needed = [set(scope[1]) for scope in row["scopes"]]
        output["scouts"] += len(needed)
        output["required_rows"] += sum(map(len, needed))
        for name, hints in hypotheses.items():
            output[f"{name}/lanes_with_hints"] += bool(hints)
            distances = [distance(epoch, hints) for required in needed for epoch in required]
            for radius in WINDOWS:
                start = f"{name}/{radius}"
                output[start + "/rows"] += sum(d <= radius for d in distances)
                output[start + "/lanes"] += all(d <= radius for d in distances)
                output[start + "/searched_bins"] += len(scoped_bins(hints, radius))
        past[key] = (*older[-1:], row)
    return dict(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(required=True, dest="mode")
    bench = modes.add_parser("bench")
    for field in ("work", "assets", "weak", "dense"):
        bench.add_argument(field, type=lambda value: Path(value).resolve())
    synthetic = modes.add_parser("train")
    synthetic.add_argument("library", type=Path)
    synthetic.add_argument("kind", choices=("full", "short"))
    synthetic.add_argument("assets", type=Path)
    args = parser.parse_args()
    if args.mode == "train":
        print(json.dumps(train(args.library, args.kind, args.assets)))
        return
    verified(args.weak, WEAK_SHA)
    builds = build(args.work, args.assets)
    tests = {"weak": audit(read_archive(args.weak, 18), builds, args.assets),
             "dense": audit(read_dense(args.dense, 48), builds, args.assets)}
    if [len(panel["rows"]) for panel in tests.values()] != [72, 192]:
        raise ValueError("Unexpected weak or dense saved slice")
    for panel in tests.values():
        all_rows = panel["rows"]
        panel["aperture_cpu"] = {kind: clock_summary([r for r in all_rows if r["kind"] == kind])
                                 for kind in ("full", "short")}
        mixed = [r for r in all_rows if r["scheduled"] == r["kind"]]
        panel["mixed_cpu"] = clock_summary(mixed)
        panel["mixed_support"] = support(mixed)
    result = dict(builds={kind: item[-1] for kind, item in builds.items()}, **tests)
    print(json.dumps(result, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
