"""Add covariance diagnostics to the otherwise frozen packed receiver build."""

from unittest.mock import patch

from . import receiver_build


def overlay(text):
    edits = (
        (
            'static Sample multiply(Sample a, Sample b) {',
            '#include "receiver_covariance_probe.inc"\n\n'
            'static Sample multiply(Sample a, Sample b) {',
        ),
        (
            '    memset(w->modes, 0, 2 * w->width * sizeof(Sample));',
            '    if (covariance_record(covariance)) return;\n'
            '    memset(w->modes, 0, 2 * w->width * sizeof(Sample));',
        ),
        (
            '    double center = (lo + hi) / 2;\n    input(w, iq, lane, center);',
            '    covariance_probe.prefix_start = covariance_cpu_ns();\n'
            '    double center = (lo + hi) / 2;\n    input(w, iq, lane, center);',
        ),
        (
            '    principal_modes(w, low);',
            '    covariance_probe.skipped = 0;\n'
            '    covariance_probe.covariance_start = covariance_cpu_ns();\n'
            '    principal_modes(w, low);\n'
            '    if (covariance_probe.skipped) return 0;',
        ),
    )
    for original, diagnostic in edits:
        text = receiver_build.replace(text, original, diagnostic)
    return '#define _POSIX_C_SOURCE 200809L\n' + text


def build_probe(output):
    stock_timing = receiver_build.fftw_timing

    def diagnostic_timing(text, crop):
        return overlay(stock_timing(text, crop))

    with patch.object(receiver_build, "fftw_timing", diagnostic_timing):
        receiver_build.build(output, pack_stencil=True)
