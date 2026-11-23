"""Price the short detector's remaining coarse-CFO template preparation."""

import argparse
from collections import OrderedDict
import ctypes as ct
import gzip
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
from struct import pack
import subprocess
from tempfile import TemporaryDirectory

from .mixed_aperture_receiver import PILOT_SHA
from .scout_readout_trial import check_machine


HERE = Path(__file__).resolve().parent
SHORT_SOURCE = "944d8a9bfee130f8f12e22098ced20195464783e521ced9172c039cadb198ba2"
SHORT_BINARY = "06570a53032c770d99cc9678b8660e1bb502b71f30fc47c8b1a4a8e31bc19ba9"
PINS = {
    "short-signed.json.gz": "cb369f55ceaaced0ddc87ff7c9bdff48b6cb78ea4ee7eff8ebf7754983b7234d",
    "refine-bound-audit.json.gz": "a0a1e7f3eb9b923fa0aef18164c6b81175ab21a15282f1816492556f51037cb7",
    "scout-readout.json.gz": "5d1998cee0e16165f2c355059d28b4b96f2486cc9297e7c55d760d4784f34431",
    "dense-full-short-raw.json.gz": "51521b26848532823922cc43a198b7f91d59d3f1d81e155e5862b04b53193f38",
}
FLAGS = ("-shared", "-fPIC", "-O3", "-std=c11", "-fopenmp-simd", "-ffp-contract=off",
         "-fno-math-errno", "-fno-strict-aliasing", "-ffunction-sections", "-fdata-sections")
NATIVE = r"""
static uint64_t cpu_ns(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &now)) abort();
    return (uint64_t)now.tv_sec * 1000000000 + now.tv_nsec;
}

static volatile double sink;
uint64_t price(const float *asset, const double *keys, size_t count, int repeats) {
    RefineRotation slots[4];
    double sum = 0;
    uint64_t start = cpu_ns();
    for (int repeat = 0; repeat < repeats; ++repeat)
        for (size_t i = 0; i < count; ++i) {
            RefineRotation *slot = &slots[i % 4];
            prepare_refine_rotation(asset + 2 * 88, keys[i], slot);
            sum += slot->real[i % pilot] + slot->imag[(i + 256) % pilot] + slot->energy;
            /* Keep all prepared coefficients as observable memory. */
            __asm__ volatile("" : : "m"(*slot) : "memory");
        }
    sink = sum;
    return cpu_ns() - start;
}

int equal_energy(const float *asset, double a, double b) {
    RefineRotation first, second;
    prepare_refine_rotation(asset + 2 * 88, a, &first);
    prepare_refine_rotation(asset + 2 * 88, b, &second);
    return memcmp(&first.energy, &second.energy, sizeof(double)) == 0 &&
           memcmp(first.real, second.real, sizeof first.real) != 0;
}
"""


def verified(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Unexpected archived asset {path}")
    return data


def lane_keys(seeds):
    if len(seeds) > 4:
        raise ValueError("Trace exceeds the native four-request path")
    frequencies = {pack("=d", seed["hz"]): seed["hz"] for seed in seeds if 4 <= seed["epoch"] < 13329}
    return frequencies


def count_reuse(rows, capacity):
    banks = {}
    hits = writes = 0
    for edge, keys in rows:
        bank = banks.setdefault(edge, OrderedDict())
        for key in keys:
            if key in bank:
                hits += 1
                bank.move_to_end(key)
            else:
                writes += 1
                bank[key] = None
                if capacity is not None and len(bank) > capacity:
                    bank.popitem(last=False)
    return dict(hits=hits, misses=writes, keys=hits+writes)


def panel_keys(audit, observed, short):
    short_by_identity = {(item["key"], item["lane"], item["input_sha256"]): item["edge"]
                         for item in short["detail"]}
    center_by_identity = {(item["key"], item["lane"], item["digest"]): item["center_hz"]
                          for item in observed["rows"]}
    if len(short_by_identity) != len(audit["lanes"]) or len(center_by_identity) != len(audit["lanes"]):
        raise ValueError("Archives differ in signed lane coverage")
    rows, centers = [], set()
    for lane in audit["lanes"]:
        identity = lane["window"], lane["lane"], lane["iq_sha256"]
        centers.add(center_by_identity[identity])
        rows.append((short_by_identity[identity], lane_keys(lane["scans"][0]["seeds"])))
    return rows, sorted(centers)


def build(source, output):
    text = verified(source, SHORT_SOURCE).decode()
    bounds = text.index("static void prepare_refine_rotation"), text.index("static int finish_refine")
    (rotation_type,) = [line for line in text.splitlines() if line.endswith("} RefineRotation;")]
    fragment = rotation_type + "\n" + text[bounds[0]:bounds[1]]
    preface = ('#define _POSIX_C_SOURCE 200809L\n#include <math.h>\n#include <stdint.h>\n'
               '#include <stdlib.h>\n#include <string.h>\n#include <time.h>\n'
               'enum {pilot=2816, frames=8};\n')
    (constant,) = [line for line in text.splitlines() if line.startswith("static const double tau")]
    wrapper = output / "prepare.c"
    wrapper.write_text(preface + constant + "\n" + fragment + NATIVE)
    library = output / "prepare.so"
    command = ["cc", *FLAGS, str(wrapper), "-lm", "-o", str(library)]
    subprocess.run(command, check=True)
    lib = ct.CDLL(str(library))
    lib.price.argtypes = [ct.c_void_p, ct.POINTER(ct.c_double), ct.c_size_t, ct.c_int]
    lib.price.restype = ct.c_uint64
    lib.equal_energy.argtypes = [ct.c_void_p, ct.c_double, ct.c_double]
    lib.equal_energy.restype = ct.c_int
    return lib, dict(command=command, compiler=subprocess.check_output(["cc", "--version"], text=True).splitlines()[0],
                     fragment_sha256=sha256(fragment.encode()).hexdigest(),
                     binary_sha256=sha256(library.read_bytes()).hexdigest())


def run(source, short_binary, assets, out):
    host = check_machine()
    verified(short_binary, SHORT_BINARY)
    blobs = {name: json.loads(gzip.decompress(verified(HERE / "measurements" / name, pin))) for name, pin in PINS.items()}
    audit = blobs["refine-bound-audit.json.gz"]
    observation = blobs["scout-readout.json.gz"]["groups"]
    short = blobs["short-signed.json.gz"]["groups"]
    panels, primary = {}, {}
    for panel in ("dense", "weak"):
        rows, centers = panel_keys(audit[panel], observation[panel], short[panel])
        primary[panel] = rows
        panels[panel] = dict(lanes=len(rows), mixer_centers_hz=centers,
                             reuse={str(c): count_reuse(rows, c) for c in (16, 64, None)})
    dense_keys = sorted({freq for _, keys in primary["dense"] for freq in keys.values()})
    if any(hz / (2_500_000 / 4096) != round(hz / (2_500_000 / 4096)) for hz in dense_keys):
        raise ValueError("The timing panel must use zero-center actual coarse bins")
    frequency = (ct.c_double * len(dense_keys))(*dense_keys)
    trials = {edge: [] for edge in PILOT_SHA}
    with TemporaryDirectory(prefix="leo-short-shared-prep-") as scratch:
        lib, recipe = build(source, Path(scratch))
        buffers = {edge: ct.create_string_buffer(verified(assets / (edge + ".f32"), pin))
                   for edge, pin in PILOT_SHA.items()}
        for buffer in buffers.values():
            if not lib.equal_energy(buffer, dense_keys[0], dense_keys[-1]):
                raise ValueError("Pilot energy changed with CFO or rotations were identical")
            lib.price(buffer, frequency, len(frequency), 2)
        reps = 32
        for repeat in range(5):
            order = list(buffers) if repeat % 2 == 0 else list(reversed(buffers))
            for edge in order:
                trials[edge].append(lib.price(buffers[edge], frequency, len(frequency), reps) / (reps * len(frequency)))
    raw = blobs["dense-full-short-raw.json.gz"]
    call_count = raw["candidate"]["recipe"]["receiver_audit"]["native"]["native_calls"]["short_primary"]
    process = raw["process"]["cpu_s"]
    half = raw["baseline"]["clocks"]["cpu_s"] / 2
    greatest = max(median(times) for times in trials.values())
    result = dict(machine=host, build=recipe, trials_ns_per_rotation=trials, panels=panels, keys_timed=len(dense_keys),
                  short_binary_sha256=SHORT_BINARY, short_source_sha256=SHORT_SOURCE, receipt_sha256=PINS,
                  pilot_sha256=PILOT_SHA, repeats=reps, actual_dense_short_calls=call_count,
                  dense_all_preparation_ceiling_s=greatest*4*call_count/1e9, dense_gap_s=process-half)
    with out.open("x") as file:
        json.dump(result, file, sort_keys=True, indent=2, allow_nan=False)
        file.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "short_binary", "assets", "out"):
        parser.add_argument(key, type=Path)
    run(**vars(parser.parse_args()))
