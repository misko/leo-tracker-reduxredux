"""Build and measure an opt-in FFTW wisdom overlay for the packed receiver."""

import argparse
import ctypes as ct
import hashlib
import json
import platform
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from unittest.mock import patch

from . import receiver_build

PACKED_SHA256 = "950c2b9412020317654fd7c79d30063e9258b70152ed9c91b4129d379ac75a13"
SHAPES = [(4800, -1), (4800, 1), (4096, -1)]
COUNTERS = (
    "estimate_calls", "wisdom_calls", "fallback_calls", "import_ns", "planning_ns", "setup_ns",
    "timing_forward_calls", "timing_backward_calls", "carrier_forward_calls",
    "timing_forward_ns", "timing_backward_ns", "carrier_forward_ns",
)


def fftw():
    return ct.CDLL("libfftw3f.so.3")


def hardware():
    cpu = Path("/proc/cpuinfo").read_text().split("\n\n", 1)[0]
    selected = ("vendor_id", "cpu family", "model", "model name", "stepping", "flags")
    signature = {key.strip(): value.strip() for key, value in
                 (line.split(":", 1) for line in cpu.splitlines() if ":" in line)
                 if key.strip() in selected}
    library = fftw()
    version = ct.string_at(ct.addressof(ct.c_char.in_dll(library, "fftwf_version"))).decode("ascii")
    fingerprint = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    return dict(machine=platform.machine(), fftw_version=version, cpu_sha256=fingerprint,
                cpu=signature.get("model name"))


def measure(seconds):
    """One bounded MEASURE pass over the production alignment and three shapes."""
    if not 0 < seconds <= 2:
        raise ValueError("FFTW planner budget must be at most two seconds per shape")
    dll = fftw()
    allocate = dll.fftwf_alloc_complex
    allocate.argtypes, allocate.restype = (ct.c_size_t,), ct.c_void_p
    plan = dll.fftwf_plan_dft_1d
    plan.argtypes = (ct.c_int, ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_uint)
    plan.restype = ct.c_void_p
    export = dll.fftwf_export_wisdom_to_string
    export.argtypes, export.restype = (), ct.c_void_p
    release, destroy = dll.fftwf_free, dll.fftwf_destroy_plan
    release.argtypes = destroy.argtypes = (ct.c_void_p,)
    release.restype = destroy.restype = None
    dll.fftwf_set_timelimit.argtypes = (ct.c_double,)
    dll.fftwf_set_timelimit.restype = None
    data = allocate(8192)
    if not data:
        raise MemoryError("FFTW planning workspace allocation failed")
    rows = []
    try:
        dll.fftwf_forget_wisdom()
        dll.fftwf_set_timelimit(seconds)
        for length, direction in SHAPES:
            cpu, wall = process_time(), perf_counter()
            transform = plan(length, data, data, direction, 0)  # FFTW_MEASURE
            rows.append(dict(length=length, direction=direction,
                             cpu_s=process_time() - cpu, elapsed_s=perf_counter() - wall))
            if not transform:
                raise ValueError("FFTW could not measure the declared transform")
            destroy(transform)
        text = export()
        if not text:
            raise ValueError("FFTW returned no wisdom")
        try:
            return dict(hardware=hardware(), plans=rows, limit_s_per_shape=seconds,
                        wisdom=ct.string_at(text).decode("ascii"))
        finally:
            release(text)
    finally:
        dll.fftwf_set_timelimit(-1)
        dll.fftwf_forget_wisdom()
        release(data)


def read_wisdom(path):
    """Select a bundle only for the runtime CPU and FFTW build that produced it."""
    if path is None:
        return None
    try:
        row = json.loads(path.read_bytes())
        if row["hardware"] != hardware() or len(row["wisdom"]) >= 65536:
            return None
        return row["wisdom"].encode("ascii")
    except (OSError, TypeError, AttributeError, ValueError, KeyError):
        return None


def configure(library, wisdom, profile=False):
    setter = library.experimental_receiver_fftw_configure
    setter.argtypes, setter.restype = (ct.c_char_p, ct.c_int), ct.c_int
    if setter(wisdom, profile) != 1:
        raise ValueError("FFTW overlay could not store the explicit wisdom configuration")


def counters(library):
    read = library.experimental_receiver_fftw_stats
    read.argtypes, read.restype = (ct.POINTER(ct.c_uint64), ct.c_uint), ct.c_uint
    values = (ct.c_uint64 * len(COUNTERS))()
    if read(values, len(values)) != len(values):
        raise ValueError("FFTW overlay returned an unexpected counter layout")
    return dict(zip(COUNTERS, values, strict=True))


def fftw_overlay(original, source, crop):
    transformed = original(source, crop)
    helper = (receiver_build.HERE / "receiver_fftw.inc").read_text()
    start = helper.index("static int prepare_fft(")
    stop = helper.index("static void release_fft(", start)
    helper = helper[:start] + '#include "receiver_fftw_wisdom.inc"\n\n' + helper[stop:]
    helper = receiver_build.replace(helper, "    fftwf_execute(w->plans[plan]);",
                                    "    execute_wisdom_profile(w, plan);")
    return "#define _POSIX_C_SOURCE 200809L\n" + receiver_build.replace(
        transformed, '#include "receiver_fftw.inc"', helper
    )


def build(output):
    output = output.resolve()
    original = receiver_build.fftw_timing
    with TemporaryDirectory(dir=output.parent) as work:
        frozen = Path(work) / "frozen.so"
        receiver_build.build(frozen, pack_stencil=True)
        if hashlib.sha256(frozen.read_bytes()).hexdigest() != PACKED_SHA256:
            raise ValueError("Packed build recipe did not reproduce frozen 950c")
        with patch.object(receiver_build, "fftw_timing",
                          lambda source, crop: fftw_overlay(original, source, crop)):
            receiver_build.build(output, pack_stencil=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "measure"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--seconds", type=float, default=1.5)
    args = parser.parse_args()
    if args.mode == "build":
        build(args.output)
    else:
        payload = (json.dumps(measure(args.seconds), sort_keys=True) + "\n").encode()
        with args.output.open("xb") as output:
            output.write(payload)


if __name__ == "__main__":
    main()
