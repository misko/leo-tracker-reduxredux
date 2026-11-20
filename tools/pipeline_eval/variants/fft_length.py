"""Compile the complete prepared overlap-save bank at a different block length."""

import os
import subprocess

from . import capture_batched_fft, capture_fft, original_kernel
from .wide_regional import replace

LENGTHS = (64, 128, 256, 512, 1024, 2048)
RELEASED = 512


def build(work, length):
    """Vary the whole filter transform while preserving the existing coarse ABI."""
    if length not in LENGTHS:
        raise ValueError(f"unsupported prepared FFT length {length}")
    work.mkdir(parents=True)
    port = work / capture_fft.SOURCE.name
    port.write_bytes(capture_fft.SOURCE.read_bytes())
    canonical = capture_fft.SOURCE.with_name("folded_bank.c")
    source = original_kernel.kernel(capture_batched_fft.fft_bank(canonical.read_text()))
    source = replace(source, "fft_length = 512", f"fft_length = {length}")
    (work / canonical.name).write_text(source)
    library = work / f"prepared_{length}.so"
    command = [
        "cc",
        *capture_fft.FLAGS,
        "-march=native",
        "-fopenmp-simd",
        "-fno-math-errno",
        "-fno-trapping-math",
        "-I",
        str(original_kernel.HEADER.parent),
        str(port),
        "-lfftw3f",
        "-lm",
        "-o",
        str(library),
    ]
    subprocess.run(command, env=os.environ | {"TMPDIR": str(work)}, check=True, timeout=30)
    return library, command
