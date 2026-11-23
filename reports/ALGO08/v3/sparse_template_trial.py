"""Bound sparse exact-template time taps and measure the full-aperture signed spectral floor."""

import argparse
import ctypes as ct
import json
import math
from pathlib import Path
from statistics import median
import subprocess
from time import perf_counter_ns, process_time_ns

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import digest

from .low_bit_pilot_screen import POINTS, adc
from .scout_readout_trial import ACQUISITION, ACQUISITION_SHA, PILOT_SHA, check_machine
from .short_signed_trial import verified


PERIOD = 13333
RATE = 10000000
BINS = np.arange(-16000, 16001, dtype=np.intc)
LINE_COUNTS = (16, 32, 64, 128)
TAP_COUNTS = (16, 32, 64, 128, 256)
SCOUTS_PER_LANE = 148 / 96
OPTIMISTIC_OPS_PER_SECOND = 24e9
GUARDED_ORACLE_MS_PER_LANE = .368
SECONDS_HISTORICAL_WARM_DETECTIONS = 52.70
SECONDS_HISTORICAL_WARM_TARGET_ACQUISITION = 24.68


def digest_file(path):
    return digest(path.read_bytes())


def frequencies(asset, stride):
    sig = asset[4 * PERIOD + 81:].view(np.complex64)
    reference = sig[(3 * np.arange(0, POINTS, stride)) % 40000]
    return np.fft.fft(reference), reference


def upper_row(power, size):
    ordered = np.argsort(-power, kind="stable")
    selected = ordered[:size]
    return np.ascontiguousarray(selected, dtype=np.intc)


def minimum_subset(power, share):
    full = power.sum()
    if not full > 0:
        raise ValueError("Expected nonzero pilot template power")
    return np.searchsorted(np.cumsum(np.sort(power)[::-1]), share * full) + 1


def sidelobe(correlation, period, exclude):
    values = abs(correlation)**2 / abs(correlation[0])**2
    # Array lags wrap modulo the periodic visit support.
    max_lag = int(period // 2)
    return float(max(values[exclude+1:max_lag+1].max(), values[-max_lag:-exclude].max()))


def lines_audit(spectrum, stride):
    power = abs(spectrum)**2
    active = np.flatnonzero(np.fft.fftshift(power) > power.max() * 1e-6)
    active = (active + (power.size + 1)//2) % power.size
    if not len(active):
        raise ValueError("Expected nonzero pilot spectrum")
    period = RATE / stride / 750
    rows = {}
    for count in LINE_COUNTS:
        uniform_count = min(count, len(active))
        for arm, mask in (("energy", upper_row(power, count)),
                          ("uniform", active[len(active)*np.arange(uniform_count)//uniform_count])):
            selected = np.zeros_like(power)
            selected[mask] = power[mask]
            rows.setdefault(arm, {})[count] = dict(
                retained=float(selected.sum()/power.sum()),
                largest_sidelobe_power=sidelobe(np.fft.ifft(selected), period, math.ceil(8/stride)),
                spectral_bins=np.asarray(mask).tolist())
    return dict(subset=rows, lines_for_half_energy=int(minimum_subset(power, .5)),
                lines_for_90_percent_energy=int(minimum_subset(power, .9)),
                lines_above_threshold=len(active))


def taps_audit(asset, stride):
    exact = asset[:2 * PERIOD].view(np.complex64)
    if stride == 4:
        fir = asset[4 * PERIOD:4 * PERIOD+81]
        exact = np.convolve(exact, fir, mode="same")
    aperture = exact[88:88 + 2816:stride]
    power = abs(aperture)**2
    rows = {}
    for count in TAP_COUNTS:
        selected = upper_row(power, count)
        uniform = len(aperture)*np.arange(count)//count
        rows[count] = dict(top_energy=float(power[selected].sum()/power.sum()),
                           uniform=float(power[uniform].sum()/power.sum()))
    return dict(taps=len(aperture), retained=rows, taps_for_half_energy=int(minimum_subset(power, .5)),
                taps_for_90_percent_energy=int(minimum_subset(power, .9)))


def direct_bound():
    epochs, frame_cells, coherent_cells = 1667, 357, len(BINS)
    frames = 14
    grid = {}
    for name, carriers, accumulations in (("independent_frame", frame_cells, frames),
                                          ("coherent_20_ms", coherent_cells, 1)):
        cells = epochs * carriers
        grid[name] = dict(epochs=epochs, carriers=carriers, cells=cells, accumulations=accumulations,
                          min_one_hypothetical_operation_per_cell_ms_per_scout=(
                              1000*cells*accumulations / OPTIMISTIC_OPS_PER_SECOND),
                          min_four_sign_products_ms_per_scout=(
                              4000*cells*accumulations / OPTIMISTIC_OPS_PER_SECOND))
    return dict(grid=grid, rectangular_half_50_hz_bin_power=float(np.sinc(.5)**2),
                sixteen_dot_float_minimum_comb_vectors=math.ceil(len(BINS)/16)*16)


def budgets():
    split = json.loads(verified(ACQUISITION, ACQUISITION_SHA))
    native = sum(row["cpu_s"] for row in split["detector_groups"].values())
    outside = split["outside_detector_cpu_s"]
    lanes = split["ordered_probes"]
    cold = (native - outside) / 2
    warm = SECONDS_HISTORICAL_WARM_TARGET_ACQUISITION - (SECONDS_HISTORICAL_WARM_DETECTIONS - native)
    comparison = {}
    for name, allowance in (("cold_cpu", cold), ("warm_elapsed_projection", warm)):
        callback_ms = 1000*allowance/lanes
        comparison[name] = dict(complete_callback_ms_per_lane=callback_ms,
                                free_confirmation_ms_per_scout=callback_ms/SCOUTS_PER_LANE,
                                guarded_oracle_ms_per_scout=(callback_ms-GUARDED_ORACLE_MS_PER_LANE)
                                / SCOUTS_PER_LANE)
    return dict(source_sha256=ACQUISITION_SHA, admitted_lanes=lanes, scout_rate=SCOUTS_PER_LANE,
                guarded_oracle_ms_per_lane=GUARDED_ORACLE_MS_PER_LANE, comparison=comparison)


class Comb:
    def __init__(self, outside, stride):
        self.lib = ct.CDLL(str(outside))
        self.lib.sparse_template_create.argtypes = [ct.c_int]
        self.lib.sparse_template_create.restype = ct.c_void_p
        self.free = self.lib.sparse_template_free
        self.free.argtypes = [ct.c_void_p]
        self.free.restype = None
        self.call = self.lib.sparse_template_comb
        self.call.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_void_p, ct.c_void_p,
                              ct.c_int, ct.c_void_p]
        self.call.restype = ct.c_int
        self.work = self.lib.sparse_template_create(stride)
        if not self.work:
            raise ValueError("Unable to create full-visit FFT")
        self.score = np.empty(len(BINS), dtype=np.float32)

    def close(self):
        self.free(self.work)

    def measure(self, iq, lane, lines, weights):
        start, wall = process_time_ns(), perf_counter_ns()
        result = self.call(self.work, iq.ctypes.data, lane, lines.ctypes.data, weights.ctypes.data,
                           len(lines), self.score.ctypes.data)
        cpu, elapsed = process_time_ns()-start, perf_counter_ns()-wall
        if result:
            raise ValueError("Invalid native pilot comb call")
        return cpu, elapsed


def planted_samples(asset, rng, kind):
    template = asset[4 * PERIOD + 81:].view(np.complex64)
    iq = np.empty((POINTS, 2, 2), dtype="<i2")
    samples = np.arange(POINTS)
    for lane, (phase, hz) in enumerate(((3037, -631300), (8893, 492150))):
        wave = template[(3*samples-phase) % 40000] * np.exp(2j*np.pi*hz*samples/RATE)
        wave /= np.sqrt(np.mean(abs(wave)**2))
        if kind == "noise":
            wave[:] = 0
        noise = (rng.normal(size=POINTS)+1j*rng.normal(size=POINTS)) / np.sqrt(2)
        values = adc(2000*(wave + .35*noise))
        iq[:, lane, 0], iq[:, lane, 1] = values.real, values.imag
    return iq


def ranked(scores):
    copied = scores.copy()
    result = []
    for _ in range(4):
        bin_ = int(np.argmax(copied))
        result.append(int(BINS[bin_]*50))
        copied[max(0, bin_-10):min(len(BINS), bin_+11)] = -np.inf
    return result


def run_edge(path, asset, rng):
    inputs = {tag: planted_samples(asset, rng, tag) for tag in ("planted", "noise")}
    result = {}
    for stride in (1, 4):
        spectrum, _ = frequencies(asset, stride)
        power = abs(spectrum)**2
        description = lines_audit(spectrum, stride)
        description["taps"] = taps_audit(asset, stride)
        comb = Comb(path, stride)
        try:
            scores, elapsed, hits = {}, {}, {}
            for repeat in range(9):
                labels = (0, *LINE_COUNTS)
                labels = labels[repeat % len(labels):] + labels[:repeat % len(labels)]
                for count in labels:
                    lines = upper_row(power, count)
                    weights = np.ascontiguousarray(power[lines] / power.sum(), dtype=np.float32)
                    for lane in (0, 1):
                        cpu, wall = comb.measure(inputs["planted"], lane, lines, weights)
                        scores.setdefault(count, []).append(cpu)
                        elapsed.setdefault(count, []).append(wall)
                        if not repeat and count:
                            hits.setdefault(count, {})[f"planted_{lane}"] = ranked(comb.score)
                            comb.measure(inputs["noise"], lane, lines, weights)
                            hits[count][f"noise_{lane}"] = ranked(comb.score)
            result[stride] = dict(
                geometry=description, planted_expected_hz=[-631300, 492150], cpu_ns=scores, wall_ns=elapsed,
                estimates_hz=hits, median_cpu_ms={k: median(v)/1e6 for k, v in scores.items()})
        finally:
            comb.close()
    return dict(screens=result, synthetic_iq_sha256={key: digest(iq.tobytes()) for key, iq in inputs.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=lambda path: Path(path).resolve())
    parser.add_argument("assets", type=lambda path: Path(path).resolve())
    args = parser.parse_args()
    state = check_machine()
    args.work.mkdir()
    source = Path(__file__).with_name("sparse_template_comb.c").resolve()
    path = args.work / "comb.so"
    cmd = ["cc", "-O3", "-std=c11", "-march=x86-64-v3", "-Wextra", "-Wall", "-Werror", "-ffp-contract=off",
           "-fPIC", "-shared", str(source), "-lfftw3f", "-o", str(path)]
    subprocess.run(cmd, check=True)
    rng = np.random.default_rng(686050322)
    edges = {edge: run_edge(path, np.frombuffer(verified(args.assets / f"{edge}.f32", sha), dtype="<f4"), rng)
             for edge, sha in PILOT_SHA.items()}
    print(json.dumps(dict(native_machine=state, build=cmd, source_sha256=digest_file(source),
                          binary_sha256=digest_file(path), asset_sha256=PILOT_SHA, pilot_edges=edges,
                          direct=direct_bound(), budgets=budgets()),
                     indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
