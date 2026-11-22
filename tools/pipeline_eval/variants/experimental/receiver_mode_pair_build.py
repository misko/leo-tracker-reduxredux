"""Pack a pair of frame covariance entries with the pinned reduction order."""

from pathlib import Path
import platform
from types import SimpleNamespace
from unittest.mock import patch

from . import receiver_build
from .receiver_build import replace


def timing(source):
    source = replace(source, "/* Cyclic Jacobi rotations on",
                     '#include "receiver_mode_pair.inc"\n\n/* Cyclic Jacobi rotations on')
    source = replace(source, "    double complex covariance[count][count] = {0}, axis[count][count] = {0};",
                     "    double complex covariance[count][count] = {0}, axis[count][count] = {0};\n"
                     '    const int paired = __builtin_cpu_supports("avx2");')
    original = """        for (int other = 0; other <= f; ++other) {
            const Sample *b = w->frames + other * w->width;
            float re = 0.f, im = 0.f;
#pragma omp simd reduction(+ : re, im)
            for (int i = 0; i < w->width; ++i) {
                re += a[i].re * b[i].re + a[i].im * b[i].im;
                im += a[i].im * b[i].re - a[i].re * b[i].im;
            }
            covariance[f][other] = re + I * im;
            covariance[other][f] = re - I * im;
        }"""
    alternate = """        int other = 0;
        if (paired) {
            for (; other < f; other += 2) {
                const Sample *b = w->frames + other * w->width;
                Sample values[2];
                covariance_two(a, b, b + w->width, w->width, values);
                store_covariance(covariance, f, other, values[0]);
                store_covariance(covariance, f, other + 1, values[1]);
            }
        }
        for (; other <= f; ++other)
            store_covariance(covariance, f, other, covariance_dot(a, w->frames + other * w->width, w->width));"""
    return replace(source, original, alternate)


def overlay(build):
    def composed(output, **recipe):
        if platform.machine() != "x86_64" or recipe.get("avx2"):
            raise ValueError("The paired covariance requires the generic x86-64 Float32 reduction")
        compile_source = receiver_build.subprocess.run

        def compile_paired(command, **kwargs):
            if "-c" in command:
                path = Path(command[command.index("-c") + 1])
                if path.name == "timing_first_receiver.c":
                    path.write_text(timing(path.read_text()))
            return compile_source(command, **kwargs)

        with patch.object(receiver_build, "subprocess", SimpleNamespace(run=compile_paired)):
            return build(output, **recipe)

    return composed
