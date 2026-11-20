"""Eliminate repeated reference FFTs and share waveform normalization."""

import subprocess
from pathlib import Path

from . import capture_batched_fft, capture_fft
from .wide_regional import replace

HEADER = Path(__file__).with_name("original_kernel_cache.h")


def kernel(source):
    source = replace(
        source,
        "enum { fft_length = 512, maximum_taps = 64 };",
        'enum { fft_length = 512, maximum_taps = 64 };\n#include "original_kernel_cache.h"',
    )
    p = source.index("    const size_t filter_cells")
    q = source.index("    /* Circular convolution", p)
    source = (
        source[:p]
        + """    int filter_ffts;
    kernel_cache_entry *ready=prepare_kernel(k,taps,&filter_ffts);
    if(!ready) { k->invalid_geometry=1; return; }
    const size_t filter_cells=(size_t)ns*nf*fft_length;
    fftwf_complex *filters=ready->filters, *input=ready->input, *spectrum=ready->spectrum,
        *inverse_input=ready->inverse_input, *output=ready->output;
    const fftwf_plan forward=ready->forward, inverse=ready->inverse;
    int common_taps=1;
    for(int s=1;s<ns;++s) if(taps[s]!=taps[0]) common_taps=0;

"""
        + source[q:]
    )
    source = replace(
        source,
        "        ++blocks;\n        for (int s",
        """        ++blocks;
        double common[fft_length];
        int available=remaining-max_taps+1;
        if(available>span) available=span;
        if(common_taps) {
            #pragma omp simd
            for(int t=0;t<available;++t) {
                const double energy=k->prefix[first+t+max_taps]-k->prefix[first+t];
                common[t]=energy>0 ? 1/sqrt(energy) : 0;
            }
        }
        for (int s""",
    )
    p = source.index("            double norm[fft_length];")
    q = source.index("            for (int f", p)
    source = (
        source[:p]
        + """            double distinct[fft_length];
            const double *norm=common_taps ? common : distinct;
            if(!common_taps) {
                #pragma omp simd
                for(int t=0;t<limit;++t) {
                    const double energy=k->prefix[first+t+taps[s]]-k->prefix[first+t];
                    distinct[t]=energy>0 ? 1/sqrt(energy) : 0;
                }
            }
            const double template_weight=ready->inverse_ref[s];
"""
        + source[q:]
    )
    source = replace(
        source,
        "                    for (int t = start[m]; t < stop[m]; ++t) {\n"
        "                        if (!norm[t]) continue;",
        "                    #pragma omp simd\n"
        "                    for (int t = start[m]; t < stop[m]; ++t) {",
    )
    source = replace(
        source,
        "(double)sqrtf(xr * xr + xi * xi) * norm[t]",
        "(double)sqrtf(xr * xr + xi * xi) * (norm[t]*template_weight)",
    )
    source = replace(
        source,
        "            fft_length, blocks, inverse_calls, ns * nf,",
        "            fft_length, blocks, inverse_calls, filter_ffts,",
    )
    p = source.index("\ncleanup:")
    return source[:p] + "\n}\n"


class PersistentGrid(capture_fft.FullGrid):
    def clear_cache(self):
        """Release prepared filter/FFTW memory when the process ends a replay."""
        port = self.library.capture_kernel_clear
        port.argtypes = ()
        port.restype = None
        port()


def build(work):
    path = work / capture_fft.SOURCE.name
    path.write_bytes(capture_fft.SOURCE.read_bytes())
    canonical = capture_fft.SOURCE.with_name("folded_bank.c")
    (work / canonical.name).write_text(kernel(capture_batched_fft.fft_bank(canonical.read_text())))
    dll = work / "original_kernel.so"
    cmd = [
        "cc",
        *capture_fft.FLAGS,
        "-march=native",
        "-fopenmp-simd",
        "-fno-math-errno",
        "-fno-trapping-math",
        "-I",
        str(HEADER.parent),
        str(path),
        "-lfftw3f",
        "-lm",
        "-o",
        str(dll),
    ]
    subprocess.run(cmd, check=True, timeout=30)
    return dll, cmd
