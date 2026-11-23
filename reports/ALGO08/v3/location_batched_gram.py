"""Prepare four independent likelihoods with one SIMD row traversal."""

import ctypes as ct
from pathlib import Path
import subprocess

import numpy as np

REPEATS = 5
ARMS = ("c0", "fitted_c")


def candidate_source(original):
    from tools.pipeline_eval.variants.algo08_posterior_handoff import replace

    original = replace(original, "int nb_run_posterior(", "int nb_run_posterior_batch(")
    original = replace(original, "int *exported) {", "int *exported,const double *prepared) {")
    marker = "    /* Current group Gram/RHS, fused over actual active columns. */"
    original = replace(
        original, marker, "    if (prepared) {\n"
        "        memcpy(matrix, prepared, ((l->mats ? l->mats : 1)+l->total)*sizeof(double));\n"
        "    } else {\n" + marker,
    )
    original = replace(original, "    for(int g=0;g<k;g++)rate[g]=alpha[g];",
                       "    }\n    for(int g=0;g<k;g++)rate[g]=alpha[g];")
    return original + "\n" + Path(__file__).with_suffix(".inc").read_text()


def build(out):
    from leo.analysis.localization_v4 import native_bound
    from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff

    out.mkdir()
    stock = out / "stock.so"
    handoff.build(stock)
    source = out / "location-batch.c"
    binary = out / "location-batch.so"
    source.write_text(candidate_source(stock.with_suffix(".c").read_text()))
    command = ["cc", *native_bound.FLAGS, "-Wall", "-Wextra", "-Werror", str(source),
               "-lm", "-o", str(binary)]
    subprocess.run(command, check=True, timeout=30)
    return binary, command


class BatchGram:
    def __init__(self, binary):
        self.lib = ct.CDLL(str(binary))
        self.width = self.lib.nb_batch_width
        self.width.argtypes, self.width.restype = [ct.c_void_p], ct.c_int
        self.prepare = self.lib.nb_prepare_four
        self.prepare.argtypes = [ct.c_void_p]*6
        self.prepare.restype = ct.c_int
        self.fit = self.lib.nb_run_posterior_batch
        self.fit.restype = ct.c_int

    def batch(self, layout, points, sigma, groups):
        if len(points) != 4:
            raise ValueError("Expected four complete points in the same layout")
        width = self.width(layout)
        if width < 1:
            raise ValueError("Missing eligible native layout")
        out = np.empty((4, width))
        response, design = zip(*points, strict=True)
        yp = (ct.c_void_p*4)(*(a.ctypes.data for a in response))
        up = (ct.c_void_p*4)(*(a.ctypes.data for a in design))
        if self.prepare(layout, yp, up, sigma.ctypes.data, groups.ctypes.data, out.ctypes.data):
            raise ValueError("The checked four-location row pass failed")
        return out
