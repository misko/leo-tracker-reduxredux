"""Measure and retain FFTW wisdom for the unchanged 21-row inverse batch."""

import ctypes as ct
import json
import os
import subprocess

from . import original_kernel

LIBRARY = "libfftw3f.so.3"
COUNT = 21


def measure(length):
    dll = ct.CDLL(LIBRARY)
    pointer, integer = ct.c_void_p, ct.c_int
    alloc = dll.fftwf_alloc_complex
    alloc.argtypes, alloc.restype = (ct.c_size_t,), pointer
    forward, inverse = dll.fftwf_plan_dft_1d, dll.fftwf_plan_many_dft
    forward.argtypes = (integer, pointer, pointer, integer, ct.c_uint)
    inverse.argtypes = (
        integer,
        ct.POINTER(integer),
        integer,
        pointer,
        pointer,
        integer,
        integer,
        pointer,
        pointer,
        integer,
        integer,
        integer,
        ct.c_uint,
    )
    forward.restype = inverse.restype = pointer
    export = dll.fftwf_export_wisdom_to_string
    export.argtypes, export.restype = (), pointer
    release, destroy = dll.fftwf_free, dll.fftwf_destroy_plan
    release.argtypes = destroy.argtypes = (pointer,)
    dll.fftwf_forget_wisdom()
    first, second = alloc(COUNT * length), alloc(COUNT * length)
    if not first or not second:
        raise MemoryError("FFTW workspace allocation failed")
    plans = []
    try:
        plans.extend(
            (
                forward(length, first, second, -1, 0),
                inverse(
                    1,
                    ct.byref(integer(length)),
                    COUNT,
                    first,
                    None,
                    1,
                    length,
                    second,
                    None,
                    1,
                    length,
                    1,
                    0,
                ),
            )
        )
        if not all(plans):
            raise ValueError("FFTW measure failed for the requested complete batch")
        memory = export()
        if not memory:
            raise ValueError("FFTW did not export any wisdom")
        try:
            return ct.string_at(memory).decode("ascii")
        finally:
            release(memory)
    finally:
        for plan in plans:
            if plan:
                destroy(plan)
        release(first)
        release(second)
        dll.fftwf_forget_wisdom()


def build(work, base, wisdom):
    work.mkdir()
    for name in ("capture_fft.c", "folded_bank.c"):
        (work / name).write_bytes((base / name).read_bytes())
    header = original_kernel.HEADER.read_text()
    start = header.index("    target->forward=fftwf_plan_dft_1d")
    stop = header.index("    if(!target->forward || !target->inverse)", start)
    header = (
        header[:start]
        + """    char *prior=NULL;
    unsigned plan_mode=FFTW_ESTIMATE;
    if(nf==21) {
        prior=fftwf_export_wisdom_to_string();
        if(!prior) goto error;
        fftwf_forget_wisdom();
        fftwf_import_wisdom_from_string("""
        + json.dumps(wisdom)
        + """);
        plan_mode=FFTW_WISDOM_ONLY;
    }
"""
        + header[start:stop].replace("FFTW_ESTIMATE", "plan_mode")
        + """    if(prior) {
        fftwf_forget_wisdom();
        fftwf_import_wisdom_from_string(prior);
        fftwf_free(prior);
    }
"""
        + header[stop:]
    )
    (work / original_kernel.HEADER.name).write_text(header)
    binary = work / "prepared_measured.so"
    command = [
        "cc",
        *original_kernel.capture_fft.FLAGS,
        "-march=native",
        "-fopenmp-simd",
        "-fno-math-errno",
        "-fno-trapping-math",
        str(work / "capture_fft.c"),
        "-lfftw3f",
        "-lm",
        "-o",
        str(binary),
    ]
    subprocess.run(command, env=os.environ | {"TMPDIR": str(work)}, timeout=30, check=True)
    return binary, command
