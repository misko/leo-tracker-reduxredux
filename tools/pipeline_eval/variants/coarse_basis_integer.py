"""Quantize the proposed reconstruction while keeping the complete aperture and grid."""

import ctypes as ct
import subprocess
from pathlib import Path
from time import process_time_ns

import numpy as np

from .capture_fft import FLAGS

SOURCE = Path(__file__).with_suffix(".c")


class QuantizedReconstruction:
    def __init__(self, library, source):
        flags = Path("/proc/cpuinfo").read_text().split("flags", 1)[-1].splitlines()[0].split()
        if not {"avx2", "avx_vnni", "fma"} <= set(flags):
            raise RuntimeError("quantized reconstruction requires AVX2, FMA and AVX-VNNI")
        dll = ct.CDLL(str(library))
        self.fold = dll.fold_integer_basis
        p, n = ct.c_void_p, ct.c_int
        self.fold.argtypes = (p, n, n, ct.c_float, p, p, p, p, n, n, p, n, n, p, n, n, p)
        self.fold.restype = None
        self.source = source
        coef = source.coefficient
        if coef.shape[1] != 20:
            raise ValueError("quantized reconstruction requires rank 20")
        self.norm = np.maximum(abs(coef.real).max(axis=1), abs(coef.imag).max(axis=1)) / 127
        scaled = np.divide(
            coef, self.norm[:, None], out=np.zeros_like(coef), where=self.norm[:, None] != 0
        )
        re, im = (np.rint(x).astype(np.int8) for x in (scaled.real, scaled.imag))
        matrix = np.empty((len(coef), 2, 20, 2), dtype=np.int8)
        matrix[:, 0, :, 0], matrix[:, 0, :, 1] = re, -im
        matrix[:, 1, :, 0], matrix[:, 1, :, 1] = im, re
        self.packed = matrix.reshape(len(coef), 2, 40).view(np.int32)
        self.bias = (-128 * matrix.sum(axis=(2, 3))).astype(np.int32)

    def score(self, samples, prefix):
        source = self.source
        values, norm, valid, scores, support, receipt = source.responses(samples, prefix)
        clock = process_time_ns()
        tile = 512
        max_step = 0.0
        clipped = 0
        for first in range(0, valid, tile):
            block = values[:, first : min(first + tile, valid)].view(np.float32)
            largest = max(float(block.max()), -float(block.min()))
            scale = np.float32(126.999 / largest if largest > 0 else 1.0)
            max_step = max(max_step, 1 / float(scale))
            clipped += int(largest * float(scale) > 127)
            self.fold(
                block.ctypes.data,
                values.shape[1],
                block.shape[1] // 2,
                scale,
                self.packed.ctypes.data,
                self.bias.ctypes.data,
                self.norm.ctypes.data,
                norm.ctypes.data,
                first,
                valid,
                source.starts.ctypes.data,
                len(source.starts),
                source.lanes,
                source.frames.ctypes.data,
                len(source.frames),
                source.epochs,
                scores.ctypes.data,
            )
        np.divide(scores, support, out=scores, where=support != 0)
        receipt.update(
            reconstruct_fold_ns=process_time_ns() - clock,
            largest_quantization_step=max_step,
            response_reconstruction_clipped_tiles=clipped,
        )
        return scores, receipt


def build(library):
    command = ["cc", *FLAGS, "-march=native", "-mavxvnni", str(SOURCE), "-lm", "-o", str(library)]
    subprocess.run(command, check=True, timeout=30)
    return command
