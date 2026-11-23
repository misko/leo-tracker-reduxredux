"""Benchmark two original independent antenna inputs behind one native FFT batch."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as ct
import json
from pathlib import Path
from statistics import median
from struct import Struct
import subprocess
from time import perf_counter_ns, process_time_ns

import numpy as np

from tools.pipeline_eval.variants.carrier_continuation import Continuation
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Factor, Receiver, digest, read_archive
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical
from tools.pipeline_eval.variants.experimental.receiver_cfo_peak_bound import TIMING_SOURCE_SHA, V3_SHA

from .scout_readout_trial import PILOT_SHA, check_machine
from .short_signed_trial import verified


HERE = Path(__file__).resolve().parent
CARRIER_SOURCE_SHA = "4f3326eee5522f02ee05a236f22a41fc1af5bb0f21b6e3fe337711a66226f5f7"
METHODS = ("installed", "scalar_dispatch", "scalar_two_dispatches", "paired_fft")
WIRE = Struct("=ii4d")
REPEATS = 5


def exact_helpers(stock):
    """Copy the pinned stock decisions into entrypoints for the grouped transform path."""
    time_begin = "    int radius = (int)nearbyint(6. / w->stride);"
    time_rank = stock[stock.index(time_begin):stock.index("\nstatic double bin_hz(")]
    carrier_begin = "        int prev = -1;"
    carrier_end = "\n    }\n    return used;\n}"
    begin = stock.index(carrier_begin, stock.index("static int find_carriers("))
    carrier_rank = stock[begin:stock.index(carrier_end, begin)].replace("epochs[i]", "epoch")
    finish_begin = "    Peak peaks[max_peaks];"
    finish = stock[stock.index(finish_begin, stock.index("static int detect_lane(")):
                   stock.index("\nint timing_first_detect(")]
    return (
        stock + "\nstatic void stereo_rank_times(TimingFirst *w, int *epochs) {\n" + time_rank +
        "\nstatic int stereo_rank_carriers(TimingFirst *w, int epoch, const uint16_t *eligible, "
        "int eligible_count, int minimum_gap, double energy, Seed *all, int used) {\n" +
        carrier_rank + "\n    return used;\n}\n" +
        "\nstatic int stereo_finish_search(TimingFirst *w, const int16_t *iq, int lane, double lo, double hi, "
        "double center, TimingFirstResult *out, Seed *seeds, int n) {\n    int done = 0;\n" + finish
    )


def build(archive, work, installed):
    check_machine()
    verified(installed, V3_SHA)
    manifest = json.loads((archive / "build.json").read_bytes())
    compiler_version = subprocess.check_output(["cc", "--version"], text=True).splitlines()[0]
    if compiler_version != manifest["compiler"]:
        raise ValueError("The archived compiler version differs")
    link = manifest["commands"][-1]
    work.mkdir()
    reference = work / "relinked.so"
    subprocess.run([*link[:-1], reference], check=True)
    verified(reference, V3_SHA)
    objects = link.copy()
    commands, pins = [], {}
    for component, pin, overlay, helper in (
        ("timing_first_receiver", TIMING_SOURCE_SHA, "stereo_fft_timing.inc", exact_helpers),
        ("two_carrier_receiver", CARRIER_SOURCE_SHA, "stereo_fft_pair.inc", lambda src: src),
    ):
        index, = (i for i, name in enumerate(link) if Path(name).name == component + ".o")
        stock = Path(link[index]).with_suffix(".c")
        source = work / (component + ".c")
        appended = HERE / overlay
        source.write_text(helper(verified(stock, pin).decode()) + "\n" + appended.read_text())
        compiler = manifest["commands"][-2]
        compiled = source.with_suffix(".o")
        command = [*compiler[:-4], "-Wall", "-Werror", "-c", str(source), "-o", str(compiled)]
        subprocess.run(command, cwd=manifest["cwd"], check=True)
        commands.append(command)
        objects[index] = str(compiled)
        pins[component] = dict(stock=pin, appended=digest(appended.read_bytes()), injected=digest(source.read_bytes()))
    output = work / "stereo_fft.so"
    subprocess.run([*objects[:-1], output], check=True)
    receipt = dict(relinked_sha256=V3_SHA, binary_sha256=digest(output.read_bytes()),
                   source_sha256=pins, compiler=compiler_version, commands=commands, pgo=False,
                   driver_sha256=digest(Path(__file__).read_bytes()))
    (work / "build.json").write_text(json.dumps(receipt, indent=2))


def factor_values(rows, count):
    return tuple(tuple(getattr(row, name) for name, _ in Factor._fields_) for row in rows[:count])


def factor_bytes(factors):
    return b"".join(WIRE.pack(*factor) for factor in factors)


class StereoReceiver:
    def __init__(self, library, asset, paired):
        self.radio = ct.CDLL(str(library))
        create = self.radio.stereo_receiver_create
        create.argtypes, create.restype = [ct.c_void_p, ct.c_int], ct.c_void_p
        self.close = self.radio.stereo_receiver_free
        self.close.argtypes, self.close.restype = [ct.c_void_p], None
        self.run = self.radio.stereo_receiver_run
        self.run.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_double, ct.c_double, ct.c_uint,
                             ct.POINTER(Factor * 2), ct.POINTER(ct.c_int), ct.POINTER(ct.c_int)]
        self.run.restype = ct.c_int
        self.probe = self.radio.stereo_receiver_probe
        self.probe.argtypes = [ct.c_void_p, ct.c_int, ct.c_void_p, ct.c_void_p]
        self.probe.restype = ct.c_int
        size = self.radio.stereo_receiver_bytes
        size.argtypes, size.restype = [ct.c_void_p], ct.c_size_t
        start = process_time_ns(), perf_counter_ns()
        self.context = create(asset.ctypes.data, paired)
        self.create_clocks_ns = (process_time_ns()-start[0], perf_counter_ns()-start[1])
        if self.context is None:
            raise ValueError("Could not allocate stereo FFT workspace")
        self.bytes = size(self.context)

    def timed(self, iq, center, mask=3):
        out, count, paths = ((Factor * 2) * 2)(), (ct.c_int * 2)(), (ct.c_int * 4)()
        start = process_time_ns(), perf_counter_ns()
        status = self.run(self.context, iq.ctypes.data, center-800000, center+800000, mask, out, count, paths)
        timing = process_time_ns()-start[0], perf_counter_ns()-start[1]
        if status or any(not 0 <= n <= 2 for n in count):
            raise ValueError("Invalid stereo receiver state")
        return [factor_values(rows, n) for rows, n in zip(out, count, strict=True)], timing, tuple(paths)

    def diagnostic(self):
        rng = np.random.default_rng(2008)
        result = {}
        for plan, n in enumerate((4800, 4800, 4096)):
            a = rng.normal(size=(2, n, 2)).astype(np.float32)
            b = np.empty((4, n, 2), np.float32)
            if self.probe(self.context, plan, a.ctypes.data, b.ctypes.data):
                raise ValueError("FFT array diagnostic failed")
            scalar, paired = b[:2], b[2:]
            result[str(plan)] = dict(transform_size=n, exact_bytes=scalar.tobytes() == paired.tobytes(),
                                     same_floats=int(np.sum(scalar == paired)),
                                     max_abs=float(np.max(abs(scalar-paired))))
        return result


def measured(stock, trial, method, iq, center, mask=3):
    if method not in ("installed", "scalar_two_dispatches"):
        return trial.timed(iq, center, mask)
    factors, cpu, wall = [(), ()], 0, 0
    for lane in (0, 1):
        if mask & (1 << lane):
            if method == "installed":
                factors[lane], ticks, elapsed = stock.timed(iq, lane, center)
            else:
                found, (ticks, elapsed), _ = trial.timed(iq, center, 1 << lane)
                factors[lane] = found[lane]
            cpu += ticks
            wall += elapsed
    return factors, (cpu, wall), (0, 0, 0, 0)


def continuation(histories, row, lane, factors):
    target, capture = row["target"], row["acquisition"]
    history = histories.setdefault(row["case"], Continuation())
    probe = dict(receiver_id=lane, channel=target["channel"],
                 actual_rf_hz=capture["actual_if_center_hz"] + target["lnb_lo_hz"],
                 valid_start_counter=capture["sample_start"], candidates=[Receiver.criteria(*f) for f in factors])
    return history.select(probe), tuple((key, tuple(values)) for key, values in history.by_lane.items())


def cohort(stereo, installed, binary, assets):
    output, differences, init, checks = [], {}, {}, {}
    singleton_cpu = {arm: [] for arm in METHODS}
    with ExitStack() as closer:
        radios = {}
        for edge in sorted({row["edge"] for row, _ in stereo}):
            asset = np.frombuffer(verified(assets / f"{edge}.f32", PILOT_SHA[edge]), dtype="<f4")
            start = process_time_ns(), perf_counter_ns()
            stock = Receiver(installed, asset)
            stock_clock = process_time_ns()-start[0], perf_counter_ns()-start[1]
            closer.callback(stock.close)
            stock.lib.two_carrier_bytes.argtypes = [ct.c_void_p]
            stock.lib.two_carrier_bytes.restype = ct.c_size_t
            radios[edge] = {"installed": stock}
            init[edge] = {"installed": dict(bytes=stock.lib.two_carrier_bytes(stock.ctx), cpu_wall_ns=stock_clock)}
            for name in ("scalar_dispatch", "paired_fft"):
                radio = StereoReceiver(binary, asset, name == "paired_fft")
                closer.callback(radio.close, radio.context)
                radios[edge][name] = radio
                init[edge][name] = dict(bytes=radio.bytes, cpu_wall_ns=radio.create_clocks_ns)
            radios[edge]["scalar_two_dispatches"] = radios[edge]["scalar_dispatch"]
            checks[edge] = radios[edge]["paired_fft"].diagnostic()
        for repeat in range(REPEATS):
            histories = {arm: {} for arm in METHODS}
            timings = {arm: ([], []) for arm in METHODS}
            paths = Counter()
            for i, (row, iq) in enumerate(stereo):
                radio = radios[row["edge"]]
                target, acq = row["target"], row["acquisition"]
                center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
                records = {}
                order = METHODS if (i+repeat) % 2 else METHODS[::-1]
                for name in order:
                    factors, (cpu, wall), path = measured(radio["installed"], radio[name], name, iq, center)
                    timings[name][0].append(cpu)
                    timings[name][1].append(wall)
                    records[name] = [(factor_bytes(fs), continuation(histories[name], row, lane, fs))
                                     for lane, fs in enumerate(factors)]
                    if name == "paired_fft":
                        paths.update(dict(zip(("paired_primary", "paired_residual", "one_residual", "one_request"),
                                              path, strict=True)))
                for name in METHODS[1:]:
                    for lane, (stock, trial) in enumerate(zip(records["installed"], records[name], strict=True)):
                        if stock != trial:
                            differences[(name, row["key"], lane)] = dict(
                                stock=stock[0].hex(), trial=trial[0].hex(),
                                continuation_state_and_selection_equal=stock[1:] == trial[1:])
                if i < 6:
                    for mask in (1, 2):
                        singles = {name: measured(radio["installed"], radio[name], name, iq, center, mask)
                                   for name in order}
                        expected = singles["installed"][0]
                        for name, (found, (cpu, _), path) in singles.items():
                            if list(map(factor_bytes, found)) != list(map(factor_bytes, expected)):
                                raise ValueError("Singleton must reproduce the installed antenna")
                            if name == "paired_fft" and path[3] != 1:
                                raise ValueError("Singleton failed to use the original scalar dispatcher")
                            singleton_cpu[name].append(cpu)
            output.append(dict(clocks={name: dict(cpu_s=sum(sets[0])/1e9, wall_s=sum(sets[1])/1e9,
                                                   median_stereo_cpu_ms=median(sets[0])/1e6)
                                      for name, sets in timings.items()}, paths=paths))
    return dict(visits=len(stereo), inputs=[(row["key"], row["sha256"]) for row, _ in stereo],
                initialization=init, transform_checks=checks, repeats=output,
                differences=[dict(arm=key[0], visit=key[1], lane=key[2], **value)
                             for key, value in differences.items()],
                singleton_cpu_ms={arm: median(values)/1e6 for arm, values in singleton_cpu.items()})


def measure(work, installed, assets, weak, binding, bulk, cohort_name):
    worker = check_machine()
    metadata = json.loads((work / "build.json").read_bytes())
    candidate = work / "stereo_fft.so"
    verified(installed, V3_SHA)
    verified(candidate, metadata["binary_sha256"])
    visits = read_archive(weak, 18) if cohort_name == "weak" else read_physical(binding, bulk, 48)
    result = cohort(list(visits), installed, candidate, assets)
    print(json.dumps(dict(cohort=cohort_name, build=metadata, worker=worker, **result), indent=2, allow_nan=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    build_cli, run_cli = (sub.add_parser(action) for action in ("build", "measure"))
    for interface, fields in ((build_cli, ("archive", "work", "installed")),
                              (run_cli, ("work", "installed", "assets", "weak", "binding", "bulk"))):
        for field in fields:
            interface.add_argument(field, type=lambda value: Path(value).resolve())
    run_cli.add_argument("cohort_name", choices=("weak", "dense"))
    args = vars(parser.parse_args())
    (build if args.pop("action") == "build" else measure)(**args)
