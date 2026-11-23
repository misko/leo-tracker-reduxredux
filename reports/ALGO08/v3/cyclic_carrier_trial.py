"""Measure a carrier-first nonconjugate spectral comb on saved CI16 windows."""

import argparse
from collections import defaultdict
from contextlib import ExitStack
import ctypes as ct
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import subprocess
from time import process_time_ns

import numpy as np

from low_bit_pilot_screen import ADC, PERIOD, PINS, POINTS, adc, carrier_wave, rms
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver, read_archive
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical
from tools.pipeline_eval.variants.experimental.receiver_cancel_support import Coarse, timing_context


SIZES = (16384, 32768)
LINE_COUNT = 16
TOLERANCE_HZ = 4550
V3_RECEIVER = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
SOURCE = (
    Path(__file__).resolve().parents[3]
    / "tools/pipeline_eval/variants/experimental/receiver_cyclic_carrier.c"
)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def spectrum(signal):
    return np.fft.fft(signal) / len(signal)


def line_peaks(coefficients, count):
    positions = np.argsort(-abs(coefficients), kind="stable")[:count]
    signed = (positions + len(coefficients) // 2) % len(coefficients) - len(coefficients) // 2
    return signed, coefficients[positions]


def describe(signal, noise_variance):
    coeff = spectrum(signal)
    harmonics, leading = line_peaks(coeff, LINE_COUNT)
    return dict(harmonics=harmonics.tolist(), amplitude=abs(leading).tolist(),
                peak_energy_share=float(max(abs(leading)**2) / np.mean(abs(signal)**2)),
                line_energy_over_noise_variance=float(sum(abs(leading)**2) / noise_variance),
                dc_amplitude=float(abs(coeff[0])))


def pilot_lines(asset):
    exact, rolled = [carrier_wave(asset, 0, 0, rolled=kind)[:40000] for kind in (False, True)]
    # 40,000 native samples span three pilot periods. Use tick order so the DFT
    # harmonics are spaced by 750 Hz and the adjacent native lag is three ticks.
    reorder = (np.arange(40000) * pow(3, -1, 40000)) % 40000
    templates = [template[reorder] / rms(template) for template in (exact, rolled)]
    results = {}
    for name, template in zip(("exact", "rolled"), templates, strict=True):
        results[name] = dict(second=describe(template**2, 2), fourth=describe(template**4, 24))
        results[name]["lags"] = {str(lag): describe(template * np.roll(template, -3 * lag), 1)
                                 for lag in (1, 2, 4, 8, 11, 22, 44, 88, 132, 176)}
    template = results["exact"]["lags"]["1"]
    lines = np.asarray(template["harmonics"], dtype=np.intc)
    amplitudes = np.asarray(template["amplitude"])
    weights = (amplitudes**2 / sum(amplitudes**2)).astype(np.float32)
    results["frozen_lines"] = lines.tolist()
    results["frozen_weights"] = weights.tolist()
    return lines, weights, results


def build(output):
    command = ["cc", "-O3", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC", "-march=x86-64-v3",
               str(SOURCE), "-lfftw3f", "-lm", "-o", str(output)]
    subprocess.run(command, check=True)
    return dict(command=command, source_sha256=digest(SOURCE), binary_sha256=digest(output),
                compiler=subprocess.check_output(["cc", "--version"], text=True).splitlines()[0])


class Scout:
    def __init__(self, path, size):
        lib = ct.CDLL(str(path.resolve()))
        lib.cyclic_carrier_create.argtypes = [ct.c_int]
        lib.cyclic_carrier_create.restype = ct.c_void_p
        self.work = lib.cyclic_carrier_create(size)
        if self.work is None:
            raise ValueError("cyclic carrier plan allocation failed")
        self.free = lib.cyclic_carrier_free
        self.free.argtypes = [ct.c_void_p]
        self.free.restype = None
        self.use = lib.cyclic_carrier_propose
        self.use.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, *([ct.c_void_p] * 4)]
        self.use.restype = ct.c_int
        self.hz = np.empty(4, dtype=np.float64)
        self.score = np.empty(4, dtype=np.float64)

    def close(self):
        self.free(self.work)

    def measure(self, samples, lane, center, lines, weights, repeats=5):
        args = (self.work, samples.ctypes.data, lane, center, lines.ctypes.data, weights.ctypes.data,
                self.hz.ctypes.data, self.score.ctypes.data)
        durations = []
        for _ in range(repeats):
            start = process_time_ns()
            count = self.use(*args)
            durations.append(process_time_ns() - start)
            if count != len(self.hz):
                raise ValueError("unexpected proposal count")
        return dict(hz=self.hz.tolist(), scores=self.score.tolist(), cpu_ns=median(durations))


def hit(expected, proposed):
    return next((rank for rank, hz in enumerate(proposed, 1)
                 if abs(hz - expected) <= TOLERANCE_HZ), None)


def white_noise_line_power(signal_power_ratio, products, response):
    """Optimistic coherent pilot energy over proper white noise at known delay and CFO."""
    hann_independent_products = 2 * products / 3
    return hann_independent_products * signal_power_ratio**2 * response


def lag_one_noise_model(asset_details):
    response = asset_details["exact"]["lags"]["1"]["line_energy_over_noise_variance"]
    return {str(size): {str(snr): white_noise_line_power(10 ** (snr / 10), size, response)
                        for snr in (-15, -10, -6, 0)} for size in (*SIZES, POINTS // 2)}


def resume_stock_scan(receiver, context, asset, iq, lane, center, residual, scratch):
    primary = Coarse()
    if receiver.lib.timing_first_detect(context, iq.ctypes.data, lane, center - 800_000,
                                        center + 800_000, ct.byref(primary)):
        raise ValueError("installed first scout failed")
    if not primary.confirmation:
        return False
    synthesis = asset.ctypes.data + asset.itemsize * (4 * PERIOD + 81)
    if receiver.lib.pilot_cancel(iq.ctypes.data, residual.ctypes.data, lane, synthesis,
                                 scratch.ctypes.data, primary.epoch, primary.hz):
        raise ValueError("installed signed cancellation failed")
    if not np.array_equal(iq[:, 1 - lane], residual[:, 1 - lane]):
        raise ValueError("signed subtraction changed the other lane")
    return True


def physical(rows, installed, assets, scouts):
    detail = []
    residual = np.empty((POINTS, 2, 2), dtype="<i2")
    scratch = np.empty(80000, dtype="<f4")
    with ExitStack() as stack:
        radios = {}
        for edge, (asset, lines, weights, _) in assets.items():
            radio = Receiver(installed, asset)
            stack.callback(radio.close)
            ctx = timing_context(radio, asset)
            stack.callback(radio.lib.timing_first_free, ctx)
            radios[edge] = radio, ctx, asset, lines, weights
        for row, samples in rows:
            edge, target, acq = row["edge"], row["target"], row["acquisition"]
            radio, ctx, asset, lines, weights = radios[edge]
            center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
            for lane in (0, 1):
                factors, stock_cpu, _ = radio.timed(samples, lane, center)
                reached = resume_stock_scan(radio, ctx, asset, samples, lane, center, residual, scratch)
                expected = {factor[0]: factor for factor in factors}
                if not reached and expected:
                    raise ValueError("installed factors exist without first-pass confirmation")
                scans = []
                for rank, signal in enumerate((samples, residual) if reached else (samples,)):
                    factor = expected.get(rank)
                    measures = {}
                    for size, scout in scouts.items():
                        measured = scout.measure(signal, lane, center, lines, weights)
                        measured["match_rank"] = None if factor is None else hit(factor[3], measured["hz"])
                        measures[str(size)] = measured
                    scans.append(dict(factor=factor, measures=measures))
                detail.append(dict(key=row["key"], input_sha256=row["sha256"], edge=edge, lane=lane,
                                   center_hz=center, installed_cpu_ns=stock_cpu, scans=scans))
    return detail


def control_samples(asset):
    rng = np.random.default_rng(20261123)
    noise = (rng.normal(size=POINTS) + 1j * rng.normal(size=POINTS)) / np.sqrt(2)
    for rolled in (False, True):
        for orientation in (-1, 1):
            hz = 775_321 * orientation
            for phase in (3071, 7023):
                wave = carrier_wave(asset, phase, hz, rolled=rolled)
                for snr in (None, -6):
                    plant = wave if snr is None else wave * 10 ** (snr / 20) + noise
                    yield dict(kind="rolled" if rolled else "exact", hz=hz, tick=phase,
                               snr_db=snr), plant
    cw = np.exp(2j * np.pi * 430771 * np.arange(POINTS) / ADC)
    yield dict(kind="noise", hz=None), noise
    yield dict(kind="cw", hz=None), cw


def controls(assets, scouts):
    iq = np.zeros((POINTS, 2, 2), dtype="<i2")
    rows = []
    for edge, (asset, lines, weights, _) in assets.items():
        for label, plant in control_samples(asset):
            quantized = adc(2500 * plant)
            iq[:, 0, 0], iq[:, 0, 1] = quantized.real, quantized.imag
            observations = {}
            for size, scout in scouts.items():
                measured = scout.measure(iq, 0, 0, lines, weights)
                measured["match_rank"] = None if label["hz"] is None else hit(label["hz"], measured["hz"])
                observations[str(size)] = measured
            rows.append(dict(edge=edge, **label, observations=observations))
    return rows


def summarize(data):
    by_edge = defaultdict(lambda: defaultdict(list))
    for row in data:
        for rank, scan in enumerate(row["scans"]):
            by_edge[row["edge"]][rank].append(scan)
    result = {}
    for size in SIZES:
        key = str(size)
        groups = []
        for edge, ranks in sorted(by_edge.items()):
            for rank, scans in sorted(ranks.items()):
                hits = [scan["measures"][key]["match_rank"] for scan in scans]
                groups.append(dict(edge=edge, rank=rank, scans=len(scans),
                                   factors=sum(scan["factor"] is not None for scan in scans),
                                   covered={str(k): sum(h is not None and h <= k for h in hits)
                                            for k in (1, 2, 4)},
                                   slots_without_matching_factor=sum(
                                       sum(abs(hz - scan["factor"][3]) > TOLERANCE_HZ
                                           for hz in scan["measures"][key]["hz"])
                                       if scan["factor"] is not None else 4 for scan in scans),
                                   mean_cpu_ms=sum(scan["measures"][key]["cpu_ns"] for scan in scans)
                                   / len(scans) / 1e6))
        proposal_ns = sum(scan["measures"][key]["cpu_ns"] for row in data for scan in row["scans"])
        fallback = [row for row in data if any(scan["factor"] is not None
                    and scan["measures"][key]["match_rank"] is None for scan in row["scans"])]
        fallback_ns = sum(row["installed_cpu_ns"] for row in fallback)
        per_lane_ms = len(data) * 1e6
        result[key] = dict(groups=groups, lanes=len(data), mean_scout_cpu_ms_per_lane=proposal_ns / per_lane_ms,
                           installed_ms_per_lane=sum(row["installed_cpu_ns"] for row in data) / per_lane_ms,
                           oracle_fallback_lanes=len(fallback), scout_plus_oracle_fallback_ms_per_lane=(
                               proposal_ns + fallback_ns) / per_lane_ms)
    return result


def trial(native, installed, pilot_dir, weak, dense, bulk, output):
    if digest(installed) != V3_RECEIVER:
        raise ValueError("installed v3 receiver pin mismatch")
    assets = {}
    for edge, expected in PINS.items():
        path = pilot_dir / f"{edge}.f32"
        if digest(path) != expected:
            raise ValueError(f"{edge} pilot pin mismatch")
        coefficients = np.fromfile(path, dtype="<f4")
        assets[edge] = coefficients, *pilot_lines(coefficients)
    with ExitStack() as stack:
        scouts = {size: Scout(native, size) for size in SIZES}
        for scout in scouts.values():
            stack.callback(scout.close)
        rows = dict(weak=physical(read_archive(weak, 18), installed, assets, scouts),
                    dense=physical(read_physical(dense, bulk, 24), installed, assets, scouts))
        if [len(rows[key]) for key in ("weak", "dense")] != [36, 48]:
            raise ValueError("unexpected saved-window coverage")
        data = dict(raw=rows, cohorts={key: summarize(value) for key, value in rows.items()},
                    controls=controls(assets, scouts), installed_sha256=V3_RECEIVER,
                    scout_sha256=digest(native), source_sha256=digest(SOURCE),
                    runner_sha256=digest(Path(__file__)),
                    assets={edge: value[-1] for edge, value in assets.items()}, asset_sha256=PINS,
                    ideal_known_line_power={edge: lag_one_noise_model(value[-1])
                                            for edge, value in assets.items()},
                    weak_sha256=digest(weak), dense_binding_sha256=digest(dense))
    with output.open("x") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="command", required=True)
    builder = commands.add_parser("build")
    builder.add_argument("output", type=Path)
    audit = commands.add_parser("trial")
    for name in ("native", "installed", "pilot_dir", "weak", "dense", "bulk", "output"):
        audit.add_argument(name, type=Path)
    args = vars(cli.parse_args())
    if args.pop("command") == "build":
        print(json.dumps(build(**args), indent=2))
    else:
        trial(**args)
