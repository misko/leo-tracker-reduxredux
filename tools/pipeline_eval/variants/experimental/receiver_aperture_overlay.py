"""Keep full-window verification around a 10 ms nonlinear nomination aperture."""

import re

from .receiver_build import replace


def timing_overlay(source):
    source = replace(source, '    points = 200000,', '    points = 200000,\n    aperture = 100000,\n    scout_frames = 7,')
    start = source.index('static void principal_modes(')
    stop = source.index('static void find_times(', start)
    source = source[:start] + re.sub(r'\bcount\b', 'scout_frames', source[start:stop]) + source[stop:]
    edits = [
        ('static void input(TimingFirst *w, const int16_t *iq, int lane, double center)',
         'static void input(TimingFirst *w, const int16_t *iq, int lane, double center, int start, int stop)'),
        ('    for (int i = 0; i < points; ++i) {\n        Sample z',
         '    for (int i = start; i < stop; ++i) {\n        Sample z'),
        ('    input(w, iq, lane, center);', '    input(w, iq, lane, center, 0, aperture);'),
        ('    if (center)\n        input(w, iq, lane, 0.);',
         '    input(w, iq, lane, 0., center ? 0 : aperture, points);'),
    ]
    for old, new in edits:
        source = replace(source, old, new)
    return source


def kernel_overlay(source):
    # This translation unit uses `samples` only in the front-end FIR. The
    # separate delay-refinement constants and all its frame loops stay intact.
    return replace(source, 'enum { samples = 200000,', 'enum { samples = 100000,')
