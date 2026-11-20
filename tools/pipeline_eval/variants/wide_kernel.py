"""Restrict native interpolation batching to the authenticated wide detector overlay."""

from pathlib import Path

HEADER = Path(__file__).with_name("wide_kernel_fractional.h")


def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError("wide kernel patch lacks a unique source anchor")
    return source.replace(old, new)


def overlay(source, *, trace=False):
    marker = '#include "fractional_runtime.h"'
    diagnostic = "\n#define LEO_WIDE_KERNEL_TRACE 1" if trace else ""
    source = replace(source, marker, marker + diagnostic + '\n#include "wide_kernel_fractional.h"')
    marker = "    leo_fractional_runtime filter = {.fraction = NAN};"
    source = replace(
        source,
        marker,
        marker
        + """
#if LEO_WIDE_KERNEL_AVX2
    const int batchable = !integer && w->wide_regional && __builtin_cpu_supports("avx2");
#endif""",
    )
    marker = (
        "            for (int k = begin; k < end; ++k) {\n                double complex received;"
    )
    source = replace(
        source,
        marker,
        """#if LEO_WIDE_KERNEL_AVX2
            double complex received_block[64];
            const int batch = batchable && one_binade && end-begin <= 64;
            if (batch) leo_wide_fractional_block(&filter,w->samples+base-7,end-begin,"""
        """received_block);
            else if (batchable) LEO_WIDE_KERNEL_COUNT(2,end-begin);
#endif
""" + marker,
    )
    marker = "                if (integer) received = w->samples[start+k+integer_offset];"
    return replace(
        source,
        marker,
        marker
        + """
#if LEO_WIDE_KERNEL_AVX2
                else if (batch) received = received_block[k-begin];
#endif""",
    )
