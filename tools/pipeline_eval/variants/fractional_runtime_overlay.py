"""Bind the exact fractional interpolation experiment to frozen wave8 source."""

from pathlib import Path

HEADER = Path(__file__).with_name("fractional_runtime.h")
MARKER = "static double sinc(double x) { return x == 0 ? 1 : sin(TAU*0.5*x)/(TAU*0.5*x); }"
PREPARE = (
    "            for (int k = begin; k < end; ++k) {\n                double complex received = 0;"
)
CACHE = "    double previous_fraction = NAN, weights[16], normalizer = 0;"
TAIL = "                /* Omit only the common unit-magnitude frame phase. */"


def overlay(source):
    if any(source.count(marker) != 1 for marker in (MARKER, CACHE, PREPARE, TAIL)):
        raise ValueError("frozen fractional GLRT source binding changed")
    source = source.replace(MARKER, MARKER + '\n#include "fractional_runtime.h"')
    source = source.replace(CACHE, "    leo_fractional_runtime filter = {.fraction = NAN};")
    first = source.index(PREPARE)
    last = source.index(TAIL, first)
    return (
        source[:first]
        + """            int base = 0, one_binade = 0;
            if (!integer) {
                base = leo_fractional_runtime_base(&filter,start+begin,offset);
                one_binade = leo_fractional_one_binade(start+begin,start+end);
            }
            for (int k = begin; k < end; ++k) {
                double complex received;
                if (integer) received = w->samples[start+k+integer_offset];
                else {
                    if (!one_binade && k != begin)
                        base = leo_fractional_runtime_base(&filter,start+k,offset);
                    received = leo_fractional_runtime_dot(&filter,w->samples+base-7);
                    ++base;
                }
"""
        + source[last:]
    )
