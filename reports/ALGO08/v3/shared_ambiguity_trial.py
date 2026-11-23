"""Test a shared linear span for signed-CFO and cyclic-lag pilot filters."""

import argparse
from collections import defaultdict
import ctypes as ct
import gzip
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import subprocess
from time import process_time_ns, perf_counter_ns
from zipfile import ZipFile

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
KERNEL = ROOT / "tools/pipeline_eval/variants/experimental/receiver_shared_ambiguity.c"
N, TAPS, EPOCHS, RATE = 4800, 704, 3333, 2_500_000
PERIOD = 13333
LIMIT = 800_000
ON_BINS = np.arange(-1536, 1537)
RANKS = (16, 24, 32, 48, 64, 80, 96, 128, 160, 192, 224, 256, 320, 384, 448, 512, 640, 704)
PINS = {
    "lower": "1b98937cbd87fd5f27b82e4d535512ca5ee12b33a64a6bae90e07ec041368adb",
    "upper": "eef7b89526adb80fc64cd0be61f35b7cc5edceb3eb293d72066378e751b4467c",
}


def digest(data):
    return sha256(data).hexdigest()


def build(binary):
    command = ["cc", "-O3", "-fPIC", "-shared", "-march=x86-64-v3", "-ffp-contract=off",
               str(KERNEL), "-lfftw3f", "-o", str(binary)]
    subprocess.run(command, check=True)
    return dict(command=command, library_sha256=digest(binary.read_bytes()),
                source_sha256=digest(KERNEL.read_bytes()),
                compiler=subprocess.check_output(["cc", "--version"], text=True).splitlines()[0])


class Kernel:
    def __init__(self, library, size, rows, batch):
        create = library.shared_ambiguity_create
        create.argtypes = [ct.c_int, ct.c_int, ct.c_int]
        create.restype = ct.c_void_p
        self.bank = create(size, rows, batch)
        if not self.bank:
            raise ValueError("FFTW bank setup failed")
        self.free = library.shared_ambiguity_free
        self.free.argtypes = [ct.c_void_p]
        self.free.restype = None
        self.apply = library.shared_ambiguity_run
        self.apply.argtypes = [ct.c_void_p] * 4
        self.apply.restype = ct.c_int

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.free(self.bank)

    def run(self, signal, spectra, result=None):
        output = None if result is None else result.ctypes.data
        if self.apply(self.bank, signal.ctypes.data, spectra.ctypes.data, output):
            raise ValueError("invalid native filter bank")


def load_pilot(path, pin):
    data = path.read_bytes()
    if digest(data) != pin:
        raise ValueError(f"unexpected pilot asset {path.name}")
    asset = np.frombuffer(data, dtype="<f4")
    fir = asset[4 * PERIOD:4 * PERIOD + 81].astype(np.float64)
    pilots = asset[:4 * PERIOD].view(np.complex64).reshape(2, PERIOD)
    codes = [np.convolve(pilot, fir, mode="same")[88:88 + 4 * TAPS:4] for pilot in pilots]
    return tuple(code / np.linalg.norm(code) for code in codes)


def steering(code, hz, rate=RATE):
    time = np.arange(len(code)) / rate
    return np.asarray(code)[:, None] * np.exp(2j * np.pi * time[:, None] * np.asarray(hz)[None, :])


def signed_span(code, fft_size=N, bins=ON_BINS):
    # The bank's admitted signed bins are symmetric. Its row covariance is
    # a weighted Dirichlet matrix in time; no dense frequency bank is needed.
    if not np.array_equal(bins, np.arange(bins[0], bins[-1] + 1)) or bins[0] != -bins[-1]:
        raise ValueError("expected a symmetric contiguous range of signed bins")
    tap = np.arange(len(code))
    diff = tap[:, None] - tap[None, :]
    averaging = np.sinc(len(bins) * diff / fft_size) / np.sinc(diff / fft_size)
    covariance = code[:, None] * np.conj(code[None, :]) * averaging
    means, axes = np.linalg.eigh(covariance)
    return axes[:, ::-1], np.cumsum(means[::-1]) / np.sum(abs(code)**2)


def parseval_bound(code, bins=ON_BINS, fft_size=N):
    power = np.sort(abs(code)**2)[::-1]
    return np.minimum(1., (fft_size / len(bins)) * np.cumsum(power) / np.sum(power))


def needed_rank(cumulative, required):
    indices = np.flatnonzero(np.asarray(cumulative) >= required)
    return int(indices[0] + 1) if len(indices) else None


def frequency_projections(code, basis, bins=ON_BINS):
    """Per-rank retained powers on quarter-bin offsets outside the training grid."""
    oversample = 4
    grid = oversample * N
    freqs = np.arange(bins[0] * oversample, bins[-1] * oversample + 1)
    off_grid = freqs[freqs % oversample != 0]
    hold = off_grid % grid
    cumulative = np.zeros(len(hold))
    minima, rows = [], {}
    # Reuse blocks of transform scratch rather than storing the full FFT matrix.
    for begin in range(0, basis.shape[1], 24):
        coeffs = np.conj(basis[:, begin:begin + 24].T) * code
        projections = np.fft.ifft(coeffs, n=grid, axis=1)[:, hold] * grid
        for i, contribution in enumerate(abs(projections)**2, begin + 1):
            cumulative += contribution
            minima.append(float(np.min(cumulative)))
            if i in RANKS:
                rows[i] = dict(minimum=float(np.min(cumulative)), median=float(np.median(cumulative)),
                               p10=float(np.quantile(cumulative, .1)))
    return rows, minima


def saved_factors(receipt_path, index_path):
    blob = receipt_path.read_bytes()
    with ZipFile(index_path) as archive:
        index = archive.read("index.json")
    weak_edges = {row["key"]: row["edge"] for row in json.loads(index)["visits"]}
    receipt = json.loads(gzip.decompress(blob))["groups"]
    cases = defaultdict(list)
    for group, values in receipt.items():
        counts = [0, 0]
        for change in values["checks"]["nominal_refine_2"]["altered"]:
            edge = "lower" if group == "dense" else weak_edges[change["key"]]
            for factor in change["reference"]:
                counts[factor[0]] += 1
                cases[edge].append(dict(group=group, key=change["key"], lane=change["lane"],
                                        rank=factor[0], hz=factor[3], margin=factor[4] - factor[5]))
        if counts != values["baseline_factors_by_rank"]:
            raise ValueError("saved directed receipt lacks the original factor inventory")
    return cases, dict(directed_sha256=digest(blob), index_sha256=digest(index))


def factor_span(code, basis, factors, rank):
    target = steering(code, [row["hz"] for row in factors])
    projection = basis[:, :rank].conj().T @ target
    power = np.sum(abs(projection)**2, axis=0)
    return [dict(row, retained_power=float(value)) for row, value in zip(factors, power, strict=True)]


def timed(library, spectra, signal, rank, batch):
    with Kernel(library, signal.size, rank, batch) as bank:
        bank.run(signal, spectra)
        cpu, wall = [], []
        cycles = 12 if rank < 128 else 6
        run = bank.apply
        args = bank.bank, signal.ctypes.data, spectra.ctypes.data, None
        for _ in range(5):
            a, b = process_time_ns(), perf_counter_ns()
            for _ in range(cycles):
                run(*args)
            cpu.append((process_time_ns() - a) / cycles / 1e6)
            wall.append((perf_counter_ns() - b) / cycles / 1e6)
    return dict(cpu_ms=cpu, wall_ms=wall, median_cpu_ms=median(cpu), median_wall_ms=median(wall))


def native_identity(library, basis, spectra, signal):
    rows = 3
    lag = (0, 17, EPOCHS - 1, N - 3)
    expected = np.asarray([
        [np.vdot(template, signal[(np.arange(TAPS) + epoch) % N]) for epoch in lag]
        for template in basis.T[:rows]
    ])
    errors = {}
    for batch in (False, True):
        output = np.empty((rows, N), dtype=np.complex64)
        with Kernel(library, N, rows, batch) as bank:
            bank.run(signal, spectra, output)
        observed = output[:, lag] / N
        np.testing.assert_allclose(observed, expected, atol=3e-6, rtol=3e-6)
        errors[str(batch)] = float(np.max(abs(observed - expected)))
    return errors


def synthetic_leakage(code, control, basis, rank):
    # The known cell is used only for measuring leakage; the filter bank does
    # not receive the selected weak carrier as a search input.
    span = basis[:, :rank]
    records = []
    for strong_hz, weak_hz, timing_offset in ((-745321, -742970, 0), (135323, 139723, 2),
                                              (743211, -628817, 3), (-546789, 334021, 32)):
        reference = steering(code, [weak_hz])[:, 0]
        rival = steering(code, [strong_hz])[:, 0]
        dilated = np.zeros(2 * TAPS, np.complex128)
        dilated[timing_offset:timing_offset + TAPS] = rival
        aligned = dilated[:TAPS]
        limited = span @ (span.conj().T @ reference)
        weak = .1 * reference
        noise_free_raw = aligned + weak
        rolled = .1 * steering(control, [weak_hz])[:, 0]
        records.append(dict(
            strong_hz=strong_hz, weak_hz=weak_hz, strong_delay_samples=timing_offset,
            full_band_weak_response=float(abs(np.vdot(reference, weak))),
            projected_weak_response=float(abs(np.vdot(limited, weak))),
            exact_strong_leakage=float(abs(np.vdot(reference, aligned))),
            projected_strong_leakage=float(abs(np.vdot(limited, aligned))),
            exact_raw_response=float(abs(np.vdot(reference, noise_free_raw))),
            projected_raw_response=float(abs(np.vdot(limited, noise_free_raw))),
            exact_rolled_control=float(abs(np.vdot(reference, rolled))),
            projected_rolled_control=float(abs(np.vdot(limited, rolled))),
        ))
    return records


def wall_budget_rank(clocks, lane_budget, fixed, scouts):
    fits = [rank for rank, timings in clocks.items()
            if scouts * min(row["median_cpu_ms"] for row in timings.values()) + fixed <= lane_budget]
    return max(fits, default=0)


def measure(args, library):
    prior = json.loads(args.low_bit.read_bytes())
    budget, fixed = prior["budget"], prior["downstream"]["guarded_fixed_oracle_ms_per_dense_lane"]
    cold = budget["cold_cpu_callback_budget_ms_per_lane"]
    warm = budget["projected_warm_callback_budget_ms_per_lane"]
    scouts = prior["dense_scouts_per_lane"]
    factors, lineage = saved_factors(args.directed, args.weak_index)
    results = {}
    for edge, pin in PINS.items():
        code, rolled = load_pilot(args.assets / f"{edge}.f32", pin)
        basis, mean = signed_span(code)
        parseval = parseval_bound(code)
        projections, off_bin_min = frequency_projections(code, basis)
        spectra = np.ascontiguousarray(np.fft.fft(basis.T, n=N, axis=1), dtype=np.complex64)
        signal = np.zeros(N, dtype=np.complex64)
        for lag, hz, power in ((723, -247931., 1.), (2871, 389111., .1)):
            signal[lag:lag + TAPS] += power * steering(code, [hz])[:, 0]
        errors = native_identity(library, basis, spectra, signal)
        clocks = {r: {arm: timed(library, spectra, signal, r, batch)
                      for arm, batch in (("sequential", False), ("batched", True))} for r in RANKS}
        fits = {
            f"{name}_with_guarded_oracle": wall_budget_rank(clocks, limit, fixed, scouts)
            for name, limit in (("cold_cpu", cold), ("warm_transfer", warm))
        }
        fits.update({f"{name}_free_downstream": wall_budget_rank(clocks, limit, 0., scouts)
                     for name, limit in (("cold_cpu", cold), ("warm_transfer", warm))})
        quality = {
            str(fraction): dict(parseval_rank_floor=needed_rank(parseval, fraction),
                                optimal_mean_rank_floor=needed_rank(mean, fraction),
                                off_grid_minimum_rank_for_optimal_mean_basis=needed_rank(off_bin_min, fraction))
            for fraction in (.5, .9)
        }
        admitted = fits["warm_transfer_with_guarded_oracle"]
        generous = fits["warm_transfer_free_downstream"]
        powers_of_two = 4096
        if EPOCHS + TAPS - 1 > powers_of_two:
            raise ValueError("optional shorter transform would alias the supported correlations")
        short_spectra = np.ascontiguousarray(np.fft.fft(basis.T, n=powers_of_two, axis=1), dtype=np.complex64)
        short_signal = np.ascontiguousarray(signal[:powers_of_two])
        sensitivity_ranks = sorted({
            admitted, generous, quality["0.5"]["optimal_mean_rank_floor"],
            quality["0.9"]["parseval_rank_floor"], quality["0.9"]["optimal_mean_rank_floor"],
        } - {0})
        short_clocks = {r: {arm: timed(library, short_spectra, short_signal, r, batch)
                            for arm, batch in (("sequential", False), ("batched", True))}
                        for r in sensitivity_ranks}
        results[edge] = dict(
            budget_ranks=fits, quality_ranks=quality, clocks=clocks, identity_error=errors,
            shorter_fft_clocks=short_clocks,
            coverage_by_rank={r: dict(optimal_mean=float(mean[r - 1]), parseval_upper=float(parseval[r - 1]),
                                     held_quarter_bin=projections[r]) for r in RANKS},
            saved_factors_at_warm_budget=factor_span(code, basis, factors[edge], admitted),
            saved_factors_at_free_downstream=factor_span(code, basis, factors[edge], generous),
            synthetic_leakage_at_warm_budget=synthetic_leakage(code, rolled, basis, admitted),
        )
    return dict(cold_cpu_budget_ms_per_lane=cold, warm_transfer_budget_ms_per_lane=warm,
                guarded_oracle_ms_per_lane=fixed, scouts_per_dense_lane=scouts,
                held_out_factor_lineage=lineage, pilot_asset_sha256=PINS, by_edge=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("binary", "assets", "low_bit", "directed", "weak_index"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    built = build(args.binary)
    result = measure(args, ct.CDLL(str(args.binary.resolve())))
    print(json.dumps(dict(build=built, **result), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
