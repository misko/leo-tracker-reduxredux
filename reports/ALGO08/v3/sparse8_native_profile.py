"""Bounded exact-factor stage profile of the installed sparse 8 ms primary."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as ct
import gzip
from hashlib import sha256
import json
import mmap
import os
from pathlib import Path
from statistics import median
import subprocess
from time import process_time_ns


HERE = Path(__file__).resolve().parent
PROFILE = HERE / "sparse8_profile_clock.h"
SPARSE = Path("/tmp/leo-v3-short-rank-transfer-DS30-0016-01/sparse")
BASE = Path("/var/tmp/leo-v3-eight-ms-build-padded/8ms")
RECIPE_SOURCE = Path("/tmp/leo-algo08v2-2x")
TRAIN_ROOT = Path("/var/tmp/leo-v3-eight-ms-primary")
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
OPERANDS = Path("/tmp/leo-ds30-partial-window-attestation01")
ORIGINAL = "c5b57b0602e81a6a85c14caf648eb12341f098d09915b4d3f705094ed309574c"
STOCK = {
    "build-receipt.json": "b2324c7cfe3c60eecd59a98eda6b8d508c46e01df6ac81375db2f5f500493a30",
    "timing_first_receiver.c": "10d8ec75ac2d6e820dd9cee184b2825b8d6510a465bbb8bfa38fc782126daea5",
    "timing_first_receiver.o": "b56bf27134e8f55be937ed1120db404e73b0ea944309a9cb468f7d39806223c4",
    "timing_first_receiver.gcda": "478669aa2cdd57de93479c527b8582901f0be76b348ade716ffc03db62024398",
    "two_carrier_receiver.c": "6f21e36a55caa489f5992a3fbae6006c2af549c30753b7053fae926d0cefb48e",
    "two_carrier_receiver.o": "90e6b9af8a0c9de5160016e0eba606f4e0ead8678576c24523138b72c0a3b5a2",
}
PILOTS = {"lower": "1b98937cbd87fd5f27b82e4d535512ca5ee12b33a64a6bae90e07ec041368adb",
           "upper": "eef7b89526adb80fc64cd0be61f35b7cc5edceb3eb293d72066378e751b4467c"}
CUSTODY = {"DS30-0163": "f97a78dc990d406237a1c896c1c26d7ce04ce8162722a61b2d01c98ca8c5dd6e",
           "DS30-0419": "7c50973d2ccc1b16dd59c0019aafb90306b406a94f3f4144e306e339e71fb19c"}
FIELD = "6edf7f54ff0689eb27712cad780d7539a9fa8dc7f95c3d7dd379641580225eeb"
TRAINER = "c63b849fb630d33fee53d8011b1766891b7e3c9038295334275135055dc443ac"
TRAIN_ROWS = "a43fe596d806cf29079a1b909a993e6128d4ff0e96862ed6ccfdce01b60a14ec"
SPARSE_INCLUDE = "de3c7140eaa7435065f75c96f977788c0a20f53d7adfe9863e5cd1acc5e72a2c"
STAGES = ("input_mix", "fir", "frame_modes", "lag_timing", "carrier_grid", "seed_setup", "full_rate_refine",
          "pilot_confirm", "verifier_load", "verifier", "other")
ARMS = ("installed", "clock_off", "clock_on")
REPEATS = 6
THREADS = ("OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def digest(data):
    return sha256(data).hexdigest()


def checked(path, expected):
    data = path.read_bytes()
    if digest(data) != expected:
        raise ValueError(f"Archived input differs: {path}")
    return data


def one(text, old, replacement):
    if text.count(old) != 1:
        raise ValueError(f"Native stage boundary changed at {old!r}")
    return text.replace(old, replacement, 1)


def timing_source(source):
    marker = "static int detect_lane(TimingFirst *w"
    before, after = source.split(marker, 1)
    after = one(after, "    if (!resident) input(w, iq, lane, center);",
                "    if (!resident) { input(w, iq, lane, center); } sparse8_mark(s_input);")
    for anchor, stage in (
            ("    principal_modes(w, low);", "s_modes"),
            ("    find_times(w, epochs);", "s_lag"),
            ("    int n = find_carriers(w, epochs, lo, hi, center, seeds), done = 0;", "s_carrier"),
    ):
        after = one(after, anchor, anchor + f" sparse8_mark({stage});")
    for anchor, stage in (
            ("    principal_modes(w, low);", "s_fir"),
            ("    double v[max_peaks][4];", "s_seed"),
            ("    for (int k = 0; k < done; ++k)\n        peaks[k]", "s_bank"),
            ("    return 0;\n}\n\nint timing_first_detect", "s_confirm"),
    ):
        after = one(after, anchor, f"    sparse8_mark({stage}); " + anchor.lstrip())
    return before + marker + after


def wrapper_source(source):
    marker = "int cancellation_primary_factors("
    before, after = source.split(marker, 1)
    after = one(after, "    TimingFirstResult scouts[2]", "    sparse8_begin(); TimingFirstResult scouts[2]")
    after = one(after, "    if (!scouts[0].confirmation)", "    sparse8_mark(s_other); if (!scouts[0].confirmation)")
    after = one(after, "    TwoCarrierPeak peaks[2];",
                "    sparse8_mark(s_load); TwoCarrierPeak peaks[2];")
    after = one(after, "    return verify_peaks(r, scouts, peaks, out, 1);",
                "    int count = verify_peaks(r, scouts, peaks, out, 1); sparse8_mark(s_verify); return count;")
    return before + marker + after


def build(root):
    recipe = json.loads(checked(BASE/"build-receipt.json", STOCK["build-receipt.json"]))
    command = recipe["relink"]
    original = SPARSE/"use.so"
    checked(original, ORIGINAL)
    for part in command:
        if part.endswith(".o"):
            path = Path(part)
            pin = STOCK.get(path.name) if path.name == "two_carrier_receiver.o" else recipe["short_object_sha256"][path.name]
            checked(path, pin)
    names = ("timing_first_receiver", "two_carrier_receiver")
    content = {name: checked(base/(name+".c"), STOCK[name+".c"]).decode()
               for name, base in zip(names, (SPARSE, BASE), strict=True)}
    checked(SPARSE/"timing_first_receiver.o", STOCK["timing_first_receiver.o"])
    original_profile = SPARSE/"feedback"/str((SPARSE/"timing_first_receiver.gcda")).lstrip("/")
    checked(original_profile, STOCK[original_profile.name])
    checked(RECIPE_SOURCE/"tools/pipeline_eval/variants/experimental/receiver_sparse_carriers.inc", SPARSE_INCLUDE)
    trainer = TRAIN_ROOT/"reports/ALGO08/single-core-2x/receiver_mixer_profile_trial.py"
    checked(trainer, TRAINER)
    calls = []

    def execute(args, **kwargs):
        row = list(map(str, args))
        calls.append(row)
        return subprocess.run(row, cwd=RECIPE_SOURCE/"native/algo08v2", check=True, **kwargs)

    def link(path, objects, flags=()):
        execute([command[0], *flags, *[objects.get(Path(part).name, part) for part in command[3:-1]], path])

    control = root/"exact.so"
    link(control, {"timing_first_receiver.o": SPARSE/"timing_first_receiver.o"})
    checked(control, ORIGINAL)
    system_flags = recipe["compile"][:-4] + ["-D_POSIX_C_SOURCE=200809L", "-include", PROFILE]
    traced = root/"trace.so"
    objects = {}
    for name, edit in zip(names, (timing_source, wrapper_source), strict=True):
        cfile, obj = (root/(name+suffix) for suffix in (".c", ".o"))
        cfile.write_text(edit(content[name]))
        objects[obj.name] = obj
    timing, wrapper = (objects[name+".o"] for name in names)
    execute([*system_flags, "-DSPARSE8_CLOCK_IMPLEMENTATION", "-c", wrapper.with_suffix(".c"), "-o", wrapper])
    feedback = root/"feedback"
    feedback.mkdir()
    generate = [f"-fprofile-generate={feedback}", "-fno-profile-values"]
    execute([*system_flags, *generate, "-c", timing.with_suffix(".c"), "-o", timing])
    training = root/"train.so"
    link(training, objects, generate)
    paths = (TRAIN_ROOT, TRAIN_ROOT/"src", RELEASE/"src", RELEASE)
    env = os.environ | {k: "1" for k in THREADS} | {"PYTHONPATH": os.pathsep.join(map(str, paths))}
    train = execute([RELEASE/"venv/bin/python", "-B", trainer, "train", training, RELEASE/"assets"],
                    capture_output=True, env=env)
    episodes = json.loads(train.stdout)
    if digest(json.dumps(episodes, sort_keys=True, separators=(",", ":")).encode()) != TRAIN_ROWS:
        raise ValueError("The instrumented trainer did not reproduce the released PGO call outcomes")
    execute([*system_flags, f"-fprofile-use={feedback}", "-fno-profile-values", "-Werror=coverage-mismatch",
             "-Werror=missing-profile", "-c", timing.with_suffix(".c"), "-o", timing])
    link(traced, objects)
    receipt = dict(archived_sha256=STOCK, exact_sha256=ORIGINAL, trace_sha256=digest(traced.read_bytes()),
                   generated_sha256={name: digest((root/(name+".c")).read_bytes()) for name in names},
                   clock_source_sha256=digest(PROFILE.read_bytes()), commands=calls,
                   train_sha256=TRAIN_ROWS, trainer_source_sha256=TRAINER, sparse_include_sha256=SPARSE_INCLUDE)
    (root/"build.json").write_text(json.dumps(receipt, sort_keys=True))


class Factor(ct.Structure):
    _fields_ = [("rank", ct.c_int), ("integer", ct.c_int)] + [
        (key, ct.c_double) for key in ("offset", "hz", "exact", "control")]


class Receiver:
    def __init__(self, library, pilot, tracing):
        self.lib = lib = ct.CDLL(str(library))
        lib.two_carrier_create.argtypes = (ct.c_void_p,)
        lib.two_carrier_create.restype = ct.c_void_p
        lib.two_carrier_free.argtypes = (ct.c_void_p,)
        lib.two_carrier_free.restype = None
        self.ctx = lib.two_carrier_create(pilot)
        if not self.ctx:
            raise MemoryError("The native 8 ms receiver failed to initialize")
        self.call = lib.cancellation_primary_factors
        self.call.argtypes = (ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double, ct.POINTER(Factor))
        self.call.restype = ct.c_int
        self.tracing = tracing
        if tracing:
            lib.sparse8_enable.argtypes = (ct.c_int,)
            lib.sparse8_enable.restype = None
            lib.sparse8_collect.argtypes = (ct.POINTER(ct.c_uint64),)
            lib.sparse8_collect.restype = None

    def close(self):
        self.lib.two_carrier_free(self.ctx)

    def run(self, data, lane, center, clock):
        if self.tracing:
            self.lib.sparse8_enable(clock)
        out = (Factor*2)()
        t0 = process_time_ns()
        count = self.call(self.ctx, data, lane, center-800000., center+800000., out)
        elapsed = process_time_ns()-t0
        if count not in (0, 1) or count and out[0].rank != 0:
            raise ValueError("The real 8 ms ABI must emit no factor or one primary")
        ticks = (ct.c_uint64*len(STAGES))()
        if self.tracing:
            self.lib.sparse8_collect(ticks)
            if not clock and sum(ticks) or clock and not 0 < sum(ticks) <= elapsed:
                raise ValueError("Exclusive stage clocks do not nest within the matched callback")
        return bytes(out)[:count*ct.sizeof(Factor)], [elapsed, *ticks]


def fixture(case, stack):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support

    root = OPERANDS/case
    meta = json.loads(checked(root/"visits.json", CUSTODY[case]))
    file = root/meta["verified_file"]["name"]
    if (file.name != "verified.ci16" or file.resolve(strict=True) != file or file.stat().st_dev != Path("/tmp").stat().st_dev
            or meta["case"] != case or meta["schema"] != "leo.research.detached-original-prefix-visits.v1"
            or meta["sample_rate_hz"] != 10_000_000 or meta["receiver_ids"] != [0, 1]):
        raise ValueError("Only previously attested local scratch operands are admitted")
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", file], text=True).strip() != "tmpfs":
        raise ValueError("Require source operands resident in tmpfs")
    resident, size = map(int, subprocess.check_output(
        ["fincore", "--bytes", "--noheadings", "--output", "RES,SIZE", file], text=True).split())
    if resident < size or size != meta["verified_file"]["bytes"]:
        raise ValueError("An enrolled operand is unavailable without faulting cold data")
    fd = stack.enter_context(file.open("rb"))
    data = stack.enter_context(mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_COPY))
    if len(data) != meta["verified_file"]["bytes"] or "sha256:"+digest(data) != meta["verified_file"]["sha256"]:
        raise ValueError("Detached operand bytes fail the paired signed seal")
    base = ct.addressof(ct.c_char.from_buffer(data))
    policy = FastScanPolicyV2()
    offset = 0
    cadence = Counter()
    published = Counter()
    rows = []
    past = None
    for visit, item in enumerate(meta["windows"]):
        signed = item["signed_row"]
        acq, target = signed["acquisition"], item["target"]
        raw_bytes = item["decoded_bytes"]
        window_shape = (signed["sample_count"], 2, 2)
        if (visit != item["sequence"] or visit != signed["sequence"] or visit != acq["global_visit"]
                or item["decoded_offset_bytes"] != offset or raw_bytes != signed["sample_count"]*8
                or signed["receiver_count"] != 2 or item["receiver_ids"] != [0, 1] or item["sha256"] != signed["iq_sha256"]
                or "sha256:"+digest(data[offset:offset+raw_bytes]) != item["sha256"]
                or signed["target_id"] != target["target_id"] or past is not None and acq["sample_start"] < past):
            raise ValueError("A detached visit no longer matches its complete original signed observation")
        past = acq["sample_end"]
        start = base + offset
        offset += raw_bytes
        if not valid_window_support(acq, 10_000_000, window_shape, (0, 1), policy):
            published["excluded"] += 1
            continue
        edge = target["edge"]
        stream = (edge, target["channel"], acq["actual_if_center_hz"]+target["lnb_lo_hz"])
        slot = cadence[stream]
        cadence[stream] += 1
        if slot % 8 == 0:
            published["anchor"] += 1
            continue
        if window_shape != (200000, 2, 2):
            raise ValueError("Expected exact unmodified stereo support for the primary ABI")
        center = target["rf_center_hz"]-target["lnb_lo_hz"]-acq["actual_if_center_hz"]
        rows.append((visit, edge, center, start, item["sha256"]))
        published["short"] += 1
    first_complete = meta["stop"]["sequence"]
    if offset != len(data) or sum(published.values()) != first_complete:
        raise ValueError("Detached visit count or exact decoded extent changed")
    return rows, dict(visits_sha256=CUSTODY[case], bytes=len(data), sample_sha256=meta["verified_file"]["sha256"],
                      roster=dict(published), first_complete_issued=first_complete)


def summarize(rows):
    out = {}
    for label in ("all", "empty", "positive"):
        selected = [row for row in rows if label == "all" or bool(row["factor_hex"]) == (label == "positive")]
        n = len(selected)
        if not n:
            continue
        panels = {arm: [sum(row["rounds"][r][arm][0] for row in selected)/n for r in range(REPEATS)] for arm in ARMS}
        stages = {stage: median(sum(row["rounds"][r]["clock_on"][i] for row in selected)/n
                                 for r in range(REPEATS)) for i, stage in enumerate(STAGES, 1)}
        out[label] = dict(lanes=n, per_lane_cpu_ns={arm: median(x) for arm, x in panels.items()},
                          per_repeat_cpu_ns=panels, exclusive_per_lane_cpu_ns=stages)
    return out


def field_totals():
    path = HERE/"measurements/first30-empty-call-roof.json.gz"
    return json.loads(gzip.decompress(checked(path, FIELD)))["modes"]


def profile(root):
    cpu, nice = list(os.sched_getaffinity(0)), os.nice(0)
    io = subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip()
    threads = {name: os.environ.get(name) for name in THREADS}
    if cpu != [2] or nice < 15 or "prio 7" not in io or set(threads.values()) != {"1"}:
        raise RuntimeError("Expected one low-priority CPU2 receiver slot")
    build_receipt = json.loads((root/"build.json").read_bytes())
    checked(root/"exact.so", ORIGINAL)
    checked(root/"trace.so", build_receipt["trace_sha256"])
    outputs, custody = {}, {}
    with ExitStack() as stack:
        engines = {}
        for case in CUSTODY:
            rows, custody[case] = fixture(case, stack)
            results = []
            for visit, edge, center, data, source_pin in rows:
                if edge not in engines:
                    pilot = ct.create_string_buffer(checked(RELEASE/"assets"/(edge+".f32"), PILOTS[edge]))
                    engines[edge] = {arm: Receiver(root/("exact.so" if arm == "installed" else "trace.so"), pilot,
                                                   arm != "installed") for arm in ARMS}
                    for engine in engines[edge].values():
                        stack.callback(engine.close)
                for lane in (0, 1):
                    expected = None
                    rounds = []
                    for repeat in range(REPEATS):
                        phase = (visit+lane+repeat) % len(ARMS)
                        order = ARMS[phase:]+ARMS[:phase]
                        if repeat >= len(ARMS):
                            order = order[::-1]
                        sample = {}
                        for arm in order:
                            factor, sample[arm] = engines[edge][arm].run(data, lane, center, arm == "clock_on")
                            if expected is None:
                                expected = factor
                            if factor != expected:
                                raise ValueError(f"Installed or traced factor mismatch at {(case, visit, lane, arm)}")
                        rounds.append(sample)
                    results.append(dict(visit=visit, lane=lane, center_hz=center, source_sha256=source_pin,
                                        factor_hex=expected.hex(), rounds=rounds))
            outputs[case] = dict(rows=results, summary=summarize(results))
    data = dict(host=dict(cpu=cpu, nice=nice, io=io, threads=threads), build=build_receipt, cases=outputs, custody=custody,
                first30_native=field_totals(), benchmark_repeats=REPEATS, backing_reads=0, solver_calls=0)
    print(json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("build", "profile"))
    cli.add_argument("output", type=lambda path: Path(path).resolve())
    args = cli.parse_args()
    if args.mode == "build":
        args.output.mkdir()
        build(args.output)
    else:
        profile(args.output)
