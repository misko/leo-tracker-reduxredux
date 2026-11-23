"""Bound fixed timing-subspace energy from the actual native lag filters."""

import argparse
import ctypes as ct
from fractions import Fraction
from hashlib import sha256
from itertools import accumulate
import json
from pathlib import Path
import re
from statistics import median
import subprocess
from time import process_time_ns

import numpy as np


HERE = Path(__file__).resolve().parent
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
NATIVE_ARCHIVE = Path("/dev/shm/leo-v3-whole-group-native")
FULL = NATIVE_ARCHIVE / "full/stock.so"
SHORT = NATIVE_ARCHIVE / "short/stock.so"
BENCH = Path("/tmp/leo-algo08v2-2x-bench")
FULL_SOURCE = BENCH / "spectral-vectors-combined-v1/packed/timing_first_receiver.c"
SHORT_SOURCE = Path("/var/tmp/leo-short-signed-02/short/timing_first_receiver.c")
CARRIER_SOURCE = Path("/tmp/leo-algo08v2-2x/tools/pipeline_eval/variants/experimental/receiver_carrier_eligibility.inc")
NATIVE = {"full": (FULL, "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"),
          "short": (SHORT, "06570a53032c770d99cc9678b8660e1bb502b71f30fc47c8b1a4a8e31bc19ba9")}
SOURCES = {FULL_SOURCE: "936b67cbb9af0201a7e65281756cc9c16f042ac2ad5e84201b1577131c67044a",
           SHORT_SOURCE: "a8fa28b5997ee7b4537ebaca4e41982b4976de4b00fde82011871570a616e1cc",
           CARRIER_SOURCE: "75c5ed5cf04aea90087175117774e267b8685256c286edbefd4bc13ad37d9bff"}
PILOTS = {"lower": "1b98937cbd87fd5f27b82e4d535512ca5ee12b33a64a6bae90e07ec041368adb",
          "upper": "eef7b89526adb80fc64cd0be61f35b7cc5edceb3eb293d72066378e751b4467c"}
ORACLE = Path("/dev/shm/leo-v3-timing-oracle-corrected.json")
ORACLE_SHA = "0caad917eec9e02f0d1a6fa0ad57b3323175e16a429ef18053f1add2e22d10f9"
FFT_CLOCK = Path("/dev/shm/leo-v3-fft-lanes-native.json")
FFT_SHA = "7246950b055aff2323b4539208e0d7e45924e132d67a33880245dc77a77243d7"
LAGS = (2, 4, 6, 11, 18, 28, 44, 74)
EPOCHS, MODE_WIDTH, FILTER_SIZE = 3333, 4740, 4800
TARGET = Fraction(349, 100)
FREQUENT_RANKS = (1, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 1536, 2048, 2560, 3000, 3333)
RETENTION = ("0.50", "0.90", "0.99")


EXPORT = """
_Static_assert(sizeof(Sample) == 2 * sizeof(float), "interleaved samples required");
int read_timing_filters(const struct TimingFirst *w, float *out, int length) {
    if (!w || w->stride != 4 || w->rate != 2500000 || w->epochs != 3333 ||
        w->width != 4740 || w->length != 1408 || w->correlation_size != 4800 ||
        length != 2 * 8 * w->correlation_size || !w->filters)
        return 0;
    memcpy(out, w->filters, length * sizeof(float));
    return 1;
}
"""


def checked(path, expected):
    body = path.read_bytes()
    if sha256(body).hexdigest() != expected:
        raise ValueError(f"Pinned source, asset or receipt changed at {path}")
    return body


def build_accessor(root):
    texts = {path: checked(path, pin).decode() for path, pin in SOURCES.items()}
    code = texts[FULL_SOURCE]
    declaration = re.search(r"struct TimingFirst \{.*?\n\};", code, re.S).group()
    if declaration not in texts[SHORT_SOURCE]:
        raise ValueError("The released full and short context layouts differ")
    sample = re.search(r"typedef struct \{\s+float re, im;\s+\} Sample;", code).group()
    carrier = re.search(r"typedef struct \{.*?\} CarrierEligibility;", texts[CARRIER_SOURCE], re.S).group()
    generated = "\n".join(("#include <stdint.h>\n#include <string.h>\n#include <fftw3.h>",
                            "enum { bins = 4096 };", sample, carrier, declaration, EXPORT))
    source, binary = root / "layout.c", root / "layout.so"
    source.write_text(generated)
    command = ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-fPIC", "-shared", source, "-o", binary]
    start = process_time_ns()
    subprocess.run(command, check=True, timeout=15)
    reader = ct.CDLL(str(binary)).read_timing_filters
    reader.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int]
    reader.restype = ct.c_int
    return reader, dict(command=list(map(str, command)), issuer_cpu_ns=process_time_ns() - start,
                        source_sha256=sha256(source.read_bytes()).hexdigest(), binary_sha256=sha256(binary.read_bytes()).hexdigest())


def read_filters(reader, library, asset):
    library.timing_first_create.argtypes = [ct.c_int, ct.c_void_p, ct.c_void_p]
    library.timing_first_create.restype = ct.c_void_p
    library.timing_first_free.argtypes = [ct.c_void_p]
    library.timing_first_free.restype = None
    start = process_time_ns()
    handle = library.timing_first_create(4, asset.ctypes.data, asset[4 * 13333:].ctypes.data)
    if not handle:
        raise ValueError("Failed to construct the original timing context")
    try:
        bank = np.empty((len(LAGS), FILTER_SIZE), dtype=np.complex64)
        if not reader(handle, bank.ctypes.data, bank.size * 2):
            raise ValueError("Unsupported original timing context dimensions")
    finally:
        library.timing_first_free(handle)
    return bank, process_time_ns() - start


def mantissa_units(bits):
    """Magnitude in units of 2**-149, exactly, for a finite IEEE binary32."""
    exp, frac = (bits >> 23) & 255, bits & ((1 << 23) - 1)
    if exp == 255:
        raise ValueError("A stored native multiplier is nonfinite")
    return ((1 << 23) + frac) << (exp - 1) if exp else frac


def exact_powers(bank):
    if bank.dtype != np.complex64 or bank.ndim != 2:
        raise ValueError("Expected the original binary32 interleaved multiplier bank")
    components = np.ascontiguousarray(bank).view(np.uint32).reshape((*bank.shape, 2))
    return [[mantissa_units(int(re)) ** 2 + mantissa_units(int(im)) ** 2 for re, im in row]
            for row in components]


def energy_envelope(powers, epochs, widths):
    """Exact upper fractions for every common output rank of the valid lag stack."""
    size = len(powers[0])
    if (len(powers) != len(widths) or not 0 < epochs <= size
            or any(len(row) != size for row in powers)
            or any(not size - epochs < w <= size for w in widths)):
        raise ValueError("Invalid finite circulant restrictions")
    # Both the captured power bound and this retained trace lower bound have the same 1/N scale.
    trace = sum((epochs + w - size) * sum(row) for w, row in zip(widths, powers, strict=True))
    if trace <= 0:
        raise ValueError("A nonzero timing bank is required")
    spectral = sorted(map(sum, zip(*powers, strict=True)), reverse=True)
    prefix = tuple(accumulate(spectral, initial=0))
    spectral.append(0)
    ceiling = []
    for rank in range(epochs + 1):
        q, rem = divmod(rank * size, epochs)
        ceiling.append(min(trace, epochs * prefix[q] + rem * spectral[q]))
    rank_lower = max(0, max(sum(v != 0 for v in row) - (size - epochs) - (size - width)
                              for row, width in zip(powers, widths, strict=True)))
    return trace, ceiling, rank_lower


def summarize(powers, widths, cost):
    denominator, envelope, rank = energy_envelope(powers, EPOCHS, widths)
    levels = {}
    for retained in RETENTION:
        fraction = Fraction(retained)
        levels[retained] = next(i for i, q in enumerate(envelope)
                                if q * fraction.denominator >= denominator * fraction.numerator)
    keys = set(FREQUENT_RANKS) | {cost["rank_cap_one_dot"], cost["rank_cap_all_lags"],
                                cost["rank_cap_one_dot_after_forwards"], cost["rank_cap_all_lags_after_forwards"]}
    return dict(algebraic_rank_lower=rank, required_rank_lower=levels,
                upper_power_fraction={str(r): envelope[r] / denominator for r in sorted(keys)},
                exact_trace_lower_numerator=str(denominator), power_unit="2^-298 before 1/N scaling")


def cost_model():
    oracle = json.loads(checked(ORACLE, ORACLE_SHA))["dense"]
    fft = json.loads(checked(FFT_CLOCK, FFT_SHA))["batches"]
    lags = len(LAGS)
    lanes = 11_834 + 1_696
    gross = 0
    for mode, total in (("full", Fraction(4716, 1000)), ("short", Fraction(12635, 1000))):
        times = oracle["aperture_cpu"][mode]["median_cpu_ns"]
        gross += total * Fraction(times["control"] - times["four"], times["control"])
    support = oracle["mixed_support"]
    scouts_per_lane = Fraction(support["scouts"], support["lanes"])
    headroom = (gross - TARGET) / lanes
    per_scout = headroom / scouts_per_lane
    fwd = fft["short/lag_forward/0/2"]
    forward_ns = median(v[0] for v in fwd["clocks"][0]) / (fwd["groups"] * fwd["lanes"])
    without_forwards = max(0.0, float(per_scout) - lags * forward_ns * 1e-9)
    rate = 4 * 6_000_000_000
    return dict(gross_four_row_cpu_s=float(gross), required_cpu_s=float(TARGET), dense_lanes=lanes,
                scouts_per_lane=float(scouts_per_lane), extra_per_lane_us=float(headroom * 1e6),
                extra_per_scout_us=float(per_scout * 1e6), measured_short_4800_forward_ns=forward_ns,
                eight_forwards_per_scout_us=lags * forward_ns / 1000, per_scout_after_eight_forwards_us=without_forwards * 1e6,
                optimistic_complex_products_s=rate, rank_cap_one_dot=int(per_scout * rate / EPOCHS),
                rank_cap_all_lags=int(per_scout * rate / EPOCHS / lags),
                rank_cap_one_dot_after_forwards=int(without_forwards * rate / EPOCHS),
                rank_cap_all_lags_after_forwards=int(without_forwards * rate / EPOCHS / lags))


def run(root):
    from .dense_geographic_trial import host

    machine = host()
    if root.absolute() != root.resolve() or not root.is_relative_to("/dev/shm"):
        raise ValueError("Use fresh tmpfs output for the bounded native study")
    root.mkdir()
    reader, build = build_accessor(root)
    cost = cost_model()
    widths = [MODE_WIDTH - lag for lag in LAGS]
    runs = {}
    for aperture, (path, pin) in NATIVE.items():
        checked(path, pin)
        library = ct.CDLL(str(path))
        for edge, pilot_pin in PILOTS.items():
            asset = np.frombuffer(checked(RELEASE / f"assets/{edge}.f32", pilot_pin), dtype="<f4")
            bank, prepare_ns = read_filters(reader, library, asset)
            start = process_time_ns()
            matrices = exact_powers(bank)
            combined = summarize(matrices, widths, cost)
            individual = [dict(lag=lag, **summarize([row], [width], cost))
                          for lag, row, width in zip(LAGS, matrices, widths, strict=True)]
            runs[f"{aperture}/{edge}"] = dict(bank_sha256=sha256(bank.tobytes()).hexdigest(),
                preparation_cpu_ns=prepare_ns, bound_cpu_ns=process_time_ns()-start, shared=combined, per_lag=individual)
    result = dict(host=machine, build=build, costs=cost, runs=runs, lags=LAGS, active_epochs=EPOCHS,
                  fft_size=FILTER_SIZE, mode_width=MODE_WIDTH, valid_product_widths=widths,
                  receipt_bindings=dict(oracle=ORACLE_SHA, fft_clock=FFT_SHA),
                  runtime_sources={str(path): pin for path, pin in SOURCES.items()},
                  native_libraries={k: pin for k, (_, pin) in NATIVE.items()}, pilots=PILOTS,
                  protocol_sha256=sha256((HERE / "timing-rank-ceiling-protocol.md").read_bytes()).hexdigest(),
                  driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), raw_recordings_opened=0,
                  dense_decompositions=0)
    with (root / "rank-ceiling.json").open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    run(parser.parse_args().root)
