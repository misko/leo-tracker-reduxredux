"""Batch consecutive exact-pilot integer GLRT correlations at unchanged epochs."""

from textwrap import dedent, indent

from .receiver_build import replace


def verifier_overlay(source):
    start = source.index('        if (w->integer_hz != cfo) {')
    end = source.index('        const int32_t zero', start)
    setup = source[start:end]
    source = replace(source, setup, '        prepare_integer_rotation(w, cfo);\n')
    helpers = ('static void prepare_integer_rotation(PortableVerifier *w, double cfo) {\n'
               + indent(dedent(setup), '    ') + '}\n\n#include "receiver_stencil_verify.inc"\n\n')
    source = replace(source, 'static int glrt(', helpers + 'static int glrt(')
    scout = ('    double freq = out->acquired_hz;\n'
             '    int first_epoch = diagnostics ? 0 :\n'
             '        packed_integer_stencil(w, epoch, freq, out->exact_grid, &out->flags);\n'
             '    for (int k = first_epoch; k < 5; ++k) {')
    return replace(source, '    double freq = out->acquired_hz;\n'
                   '    for (int k = 0; k < 5; ++k) {', scout)
