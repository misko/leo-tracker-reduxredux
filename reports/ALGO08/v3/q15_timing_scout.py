"""Exercise a mixed Q15 FFT inside the original signed native timing scout."""

import argparse
from collections import Counter
from contextlib import ExitStack, closing
import ctypes as ct
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean, median
import subprocess
from time import process_time_ns

import numpy as np

from .anchored_phase import weak_rows
from .dense_geographic_trial import host
from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, verified
from .short_cfo_refine import signed_rows
from .timing_only_oracle import asset_for, one
from .whole_group_receiver_bound import (
    FULL_BUILD, FULL_BUILD_SHA, SHORT_BUILD, SHORT_BUILD_SHA, SHORT_SHA, SOURCE_SHA, measure, receiver,
)


HERE = Path(__file__).resolve().parent
ASSETS = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/assets")
ARMS = ("exact", "speculative", "guarded")
ORDER = (ARMS, ARMS[::-1], (ARMS[1], ARMS[0], ARMS[2]), (ARMS[2], ARMS[0], ARMS[1]))
KINDS = ("full", "short")
CALLS = dict(full=1696, short=11834)
NATIVE_SOURCE = HERE / "q15_timing_scout.inc"


class ScoutTrace(ct.Structure):
    _fields_ = [("ns", ct.c_uint64), ("score_radius", ct.c_double), ("smallest_gap", ct.c_double),
                ("epochs", ct.c_int * 12), ("tentative", ct.c_int * 12), ("fallback", ct.c_int)]

    def document(self):
        return dict(ns=self.ns, radius=self.score_radius, smallest_gap=self.smallest_gap,
                    epochs=list(self.epochs), tentative=list(self.tentative), fallback=self.fallback)


def overlay(source, implementation):
    caller = "    find_times(w, epochs);\n    Seed seeds[2 * clocks];"
    source = one(source, caller, caller.replace("find_times", "find_times_trial"))
    marker = "static double bin_hz(const TimingFirst *w, int i) {"
    return one(source, marker, implementation + "\n\n" + marker)


def build(root):
    full = json.loads(verified(FULL_BUILD, FULL_BUILD_SHA))
    short = json.loads(verified(SHORT_BUILD, SHORT_BUILD_SHA))
    flags = full["commands"][-2][:-4]
    implementation = NATIVE_SOURCE.read_text()
    outputs = {}
    for kind, link, pin in zip(KINDS, (full["commands"][-1], short["relink"]), (INSTALLED_SHA, SHORT_SHA), strict=True):
        path = root / kind
        path.mkdir()
        original = path / "released.so"
        subprocess.run([*link[:-1], original], cwd=full["cwd"], check=True)
        verified(original, pin)
        old, = [value for value in link if Path(value).name == "timing_first_receiver.o"]
        stock = verified(Path(old).with_suffix(".c"), SOURCE_SHA[kind]).decode()
        source, obj, binary = (path / name for name in ("timing_trial.c", "timing_trial.o", "trial.so"))
        source.write_text(overlay(stock, implementation))
        compile_cmd = [*flags, "-D_POSIX_C_SOURCE=200809L", "-c", source, "-o", obj]
        link_cmd = [*(obj if value == old else value for value in link[:-1]), binary]
        for command in (compile_cmd, link_cmd):
            subprocess.run(command, cwd=full["cwd"], check=True)
        outputs[kind] = dict(released=str(original), trial=str(binary), released_sha256=pin,
                             trial_sha256=sha256(binary.read_bytes()).hexdigest(),
                             source_sha256=sha256(source.read_bytes()).hexdigest(),
                             commands=[list(map(str, cmd)) for cmd in (compile_cmd, link_cmd)])
    return outputs


def native_ports(library):
    prepare, read, free = library.timing_q15_set, library.timing_q15_read, library.timing_q15_free
    prepare.argtypes, prepare.restype = (ct.c_int,), ct.c_int
    read.argtypes, read.restype = (ct.POINTER(ScoutTrace),), ct.c_int
    free.argtypes, free.restype = (), None
    return prepare, read, free


def qualification(library):
    test = library.timing_q15_test_transform
    test.argtypes, test.restype = (ct.c_void_p, ct.c_int), ct.c_double
    random = np.random.default_rng(4502)
    data = random.normal(size=(4800, 2)).astype(np.float32).view(np.complex64).ravel()
    expected = (np.fft.fft(data), data.size * np.fft.ifft(data))
    transforms = []
    for inverse, target in enumerate(expected):
        work = data.copy()
        bound = test(work.ctypes.data, inverse)
        observed = float(np.max(np.abs(work - target)))
        if not 0. < observed <= bound:
            raise ValueError("Mixed transform failed signed natural bin order, direction or amplitude")
        transforms.append(dict(backward=bool(inverse), maximum_complex_error=observed, absolute_q15_bound=bound))
    zero = np.zeros(4800, np.complex64)
    assert test(zero.ctypes.data, 0) == 0. and not zero.any()
    zero[-1] = np.nan
    assert test(zero.ctypes.data, 0) == -1.
    choose = library.timing_q15_test_peaks
    choose.argtypes = (ct.c_void_p, ct.c_int, ct.c_int, ct.POINTER(ct.c_int), ct.c_int, ct.c_double)
    choose.restype = ct.c_int
    scores = np.array([8., 1., 2., 5., 4., 1., 0., 8.])
    peaks = (ct.c_int * 2)()
    assert choose(scores.ctypes.data, scores.size, 1, peaks, len(peaks), 0.01) == 0 and list(peaks) == [0, 3]
    scores = np.array([8., 1., 2., 5., 4., 1., 0., 7.])
    assert choose(scores.ctypes.data, scores.size, 1, peaks, len(peaks), 0.01) == 1 and list(peaks) == [0, 3]
    return dict(transforms=transforms, zero=True, nonfinite=True, tie_and_wrap=True)


def aperture(row):
    return "full" if row["mode"] == "full" else "short"


def run_lane(engines, row, mode):
    kind = aperture(row)
    installed, engine, prepare, read = engines[kind, row["edge"]]
    if mode is None:
        return measure(installed, row["iq"], row["lane"], row["tune"])
    if prepare(ARMS.index(mode)):
        raise ValueError("The low-precision timing plan is unavailable on this host")
    factors, exact, elapsed = measure(engine, row["iq"], row["lane"], row["tune"])
    trace = (ScoutTrace * 2)()
    count = read(trace)
    if not 1 <= count <= (2 if kind == "full" else 1):
        raise ValueError("A signed native lane must have one primary and at most one full residual scout")
    return dict(factors=factors, native_bytes=exact.hex(), cpu_ns=elapsed, scouts=[t.document() for t in trace[:count]])


def comparison(reference, alternative):
    objectives = Counter()
    if len(reference["scouts"]) != len(alternative["scouts"]):
        objectives["changed_scout_count"] += 1
    for index, (a, b) in enumerate(zip(reference["scouts"], alternative["scouts"])):
        stage = "primary" if index == 0 else "residual"
        objectives.update({stage+"_scouts": 1, stage+"_ordered_peak_changes": int(a["epochs"] != b["epochs"]),
                           stage+"_unordered_peak_changes": int(set(a["epochs"]) != set(b["epochs"])),
                           stage+"_exact_fallback": int(bool(b["fallback"]))})
        if b["fallback"] == 2:
            objectives[stage+"_ambiguous_tentative_peak_changes"] += a["epochs"] != b["tentative"]
    for rank in (0, 1):
        label = "primary" if rank == 0 else "secondary"
        left = [r for r in reference["factors"] if r[0] == rank]
        right = [r for r in alternative["factors"] if r[0] == rank]
        objectives.update({label+"_reference_factors": len(left), label+"_alternative_factors": len(right),
                           label+"_factor_changes": int(left != right)})
    objectives["any_factor_bytes_changed"] = int(reference["native_bytes"] != alternative["native_bytes"])
    return objectives


def summarize(rows):
    result = {}
    for label, testrows in (("all", rows), *((mode, [row for row in rows if row["kind"] == mode]) for mode in KINDS)):
        if not testrows:
            continue
        summary = {}
        for arm in ARMS:
            clocks, audits = [], Counter()
            for index in range(len(ORDER)):
                records = [row["tests"][index] for row in testrows]
                clocks.append(dict(scout_cpu_ns=sum(sum(s["ns"] for s in r[arm]["scouts"]) for r in records),
                                   lane_cpu_ns=sum(r[arm]["cpu_ns"] for r in records)))
                if index == 0:
                    for record in records:
                        audits.update(comparison(record["exact"], record[arm]))
            summary[arm] = dict(raw=dict(audits), clocks=clocks,
                                **{key: median(v[key] for v in clocks) for key in clocks[0]})
        result[label] = dict(lanes=len(testrows), arms=summary)
    return result


def panel(engines, rows):
    records = []
    for number, row in enumerate(rows):
        _, installed, _ = run_lane(engines, row, None)
        records.append(dict(key=row["key"], lane=row["lane"], kind=aperture(row), edge=row["edge"],
                            installed=installed.hex(), tests=[{} for _ in ORDER]))
    for i, order in enumerate(ORDER):
        for arm in order:
            for record, row in zip(records, rows, strict=True):
                record["tests"][i][arm] = run_lane(engines, row, arm)
    for record in records:
        for trial in record["tests"]:
            if trial["exact"]["native_bytes"] != record["installed"]:
                raise ValueError("The profiled-as-is scout differs from the released signed factor bytes")
            if trial["guarded"]["native_bytes"] != record["installed"]:
                raise ValueError("The tested guarded complete scout changed signed factor bytes")
    return dict(rollups=summarize(records), rows=records)


def run(root):
    machine = host()
    if root.absolute() != root.resolve() or not root.is_relative_to("/dev/shm"):
        raise ValueError("Use new report output on tmpfs")
    root.mkdir()
    native = build(root)
    rate = subprocess.check_output(["ldd", str(root / "full/trial.so")], text=True).splitlines()
    with ExitStack() as resources:
        engines, setup, synthetic = {}, {}, {}
        for kind, builds in native.items():
            for edge in PILOT_SHA:
                asset = asset_for(ASSETS, edge)
                installed = resources.enter_context(closing(receiver(Path(builds["released"]), asset, kind)))
                experiment = resources.enter_context(closing(receiver(Path(builds["trial"]), asset, kind)))
                prepare, read, free = native_ports(experiment.lib)
                if edge == "lower":
                    start = process_time_ns()
                    if prepare(1):
                        raise ValueError("The native Q15 fallback study requires one working AVX2 mixed plan")
                    setup[kind] = process_time_ns() - start
                    resources.callback(free)
                    synthetic[kind] = qualification(experiment.lib)
                engines[kind, edge] = (installed, experiment, prepare, read)
        dense, signed = signed_rows("dense")
        weak, staged = weak_rows()
        results = {name: panel(engines, rows) | dict(source=evidence)
                   for name, rows, evidence in (("dense", dense, signed), ("weak", weak, staged))}
    dense = results["dense"]["rollups"]
    forecasts = {}
    for arm in ("speculative", "guarded"):
        forecasts[arm] = dict(nominal_dense_scout_cpu_delta_s=sum(
            CALLS[kind] * (dense[kind]["arms"]["exact"]["scout_cpu_ns"] - dense[kind]["arms"][arm]["scout_cpu_ns"])
            / dense[kind]["lanes"] / 1e9 for kind in KINDS))
    result = dict(panels=results, forecasts=forecasts, results_are_sensor_stage_only=True, host=machine,
                  whole_recordings=0, original_waveform_opens=0, paired_order=ORDER, native=native,
                  setup_cpu_ns=setup, synthetic=synthetic, libraries=rate,
                  pins={path.name: sha256(path.read_bytes()).hexdigest()
                        for path in (Path(__file__), NATIVE_SOURCE, HERE / "q15-timing-scout-protocol.md")})
    with (root / "result.json").open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    run(cli.parse_args().root)
