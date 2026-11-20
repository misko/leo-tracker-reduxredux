"""Find pilot timing with three code products on the original sampling grid."""

import ctypes as ct
from contextlib import AbstractContextManager
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import differential_pilot as dp
from .wide_regional import replace

LAGS = (44, 88, 132)
SOURCE = Path(__file__).with_name("differential_runtime_fft.c")
ENTRY = "leo_multilag_scout_v1"


def overlay(source):
    """Reuse the compiled adjacent-symbol feed and FFT plans at three displacements."""
    source = replace(
        source,
        "static void center_products(fftwf_complex *out, const int16_t *data, int lane)",
        "static double center_products(fftwf_complex *out, const int16_t *data, int lane,\n"
        "                              int displacement, int count, int measure_energy)",
    )
    source = replace(source, "i < pairs", "i < count", count=2)
    source = replace(source, "2 * receivers * lag", "2 * receivers * displacement")
    source = replace(
        source,
        "real_sum / pairs, mean_imag = imag_sum / pairs",
        "real_sum / count, mean_imag = imag_sum / count",
    )
    source = replace(
        source,
        "    for (int i = 0; i < count; ++i) {\n        out[i][0] -= mean_real;",
        "    double total = 0.;\n"
        "    for (int i = 0; i < count; ++i) {\n        out[i][0] -= mean_real;",
    )
    source = replace(
        source,
        "        out[i][1] -= mean_imag;\n    }",
        """        out[i][1] -= mean_imag;
        if (measure_energy) {
            double re = out[i][0], im = out[i][1];
            total += re * re + im * im;
        }
    }
    return total;""",
    )
    source = replace(
        source,
        "static void fold_lane(scout_context *s)",
        "static void fold_lane(scout_context *s, int count)",
    )
    source = replace(source, "pairs - start", "count - start")
    source = replace(
        source,
        "center_products(s->products, data, lane);",
        "center_products(s->products, data, lane, lag, pairs, 0);",
    )
    source = replace(source, "fold_lane(s);", "fold_lane(s, pairs);")
    entire = source[source.index("void leo_differential_scout(scout_context") :]
    loop = entire[entire.index("        for (int control") :].rsplit("    }\n}", 1)[0]
    loop = replace(loop, "filters + control * branches * fft", "bank + control * branches * fft")
    loop = replace(
        loop,
        """                float a = hypotf(s->work[i][0] / fft, s->work[i][1] / fft);
                double power = (a * a) / energy[control * frame + i];
                if (control) lane_scores[i] -= power;
                else lane_scores[i] = power;""",
        """                const double norm = sqrt(reference[control * frame + i] * data_energy);
                float *z = out + 2 * ((lane * nlags * 2 + k * 2 + control) * frame + i);
                z[0] = norm > 0 ? s->work[i][0] / (fft * norm) : 0.f;
                z[1] = norm > 0 ? s->work[i][1] / (fft * norm) : 0.f;""",
    )
    return (
        source
        + f"""
void {ENTRY}(scout_context *s, const int16_t *data,
    const fftwf_complex *filters, const double *energy, float *out)
{{
    enum {{ nlags = 3 }};
    for (int lane = 0; lane < receivers; ++lane) for (int k = 0; k < nlags; ++k) {{
        const int displacement = lag * (k + 1);
        const int count = times - displacement;
        const double data_energy = center_products(s->products, data, lane, displacement, count, 1);
        fold_lane(s, count);
        const fftwf_complex *bank = filters + k * 2 * branches * fft;
        const double *reference = energy + k * 2 * frame;
{loop}    }}
}}
"""
    )


def product_filter(edge, roll, lag):
    waves, active = dp.phase_templates(edge, roll)
    valid = active[:, lag:] & active[:, :-lag]
    products = waves[:, lag:] * waves[:, :-lag].conj()
    mean = np.sum(products, axis=-1, dtype=np.complex128, keepdims=True) / valid.sum(
        axis=-1, keepdims=True
    )
    kernels = np.zeros_like(waves)
    kernels[:, :-lag] = np.where(valid, products - mean, 0)
    ends = dp.SAMPLES - lag
    epochs = np.arange(dp.FRAME)
    prefix = np.pad(np.cumsum(abs(kernels) ** 2, axis=-1, dtype=np.float64), ((0, 0), (1, 0)))
    energy = np.zeros(dp.FRAME)
    for residue, start in dp.STARTS:
        lo = np.clip(-start - epochs, 0, dp.FRAME)
        hi = np.clip(ends - start - epochs, 0, dp.FRAME)
        energy += prefix[residue, hi] - prefix[residue, lo]
    return np.fft.fft(kernels, n=dp.FFT, axis=-1).conj(), energy


@lru_cache(maxsize=2)
def filters(edge):
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL

    pairs = [[product_filter(edge, roll, lag) for roll in (0, CONTROL_SYMBOL_ROLL)] for lag in LAGS]
    return (
        np.asarray([[f for f, _ in p] for p in pairs], dtype="<c8"),
        np.asarray([[v for _, v in p] for p in pairs], dtype="<f8"),
    )


def score(response):
    exact, control = response[:, :, 0], response[:, :, 1]
    a = abs(exact)
    unit = np.divide(exact, a, where=a > 0, out=np.zeros_like(exact))
    first = unit[:, 0].conj()
    squared = first * first
    agreement = 0.75 + 0.125 * (squared * (unit[:, 1] + first * unit[:, 2])).real
    return (a * a).sum(axis=1) * agreement - (abs(control) ** 2).sum(axis=1)


class MultilagScout(AbstractContextManager):
    """Callable drop-in scout for the existing full-support fifth-center ABI."""

    def __init__(self, library, edge):
        self.edge = edge
        self.port = ct.CDLL(str(library))
        self.kernel = getattr(self.port, ENTRY)
        self.kernel.argtypes = [ct.c_void_p] * 5
        self.kernel.restype = None
        create = self.port.leo_differential_scout_create
        create.restype = ct.c_void_p
        create.argtypes = []
        self.close = self.port.leo_differential_scout_destroy
        self.close.argtypes = [ct.c_void_p]
        self.close.restype = None
        self.filters, self.energy = filters(edge)
        self.native = create()
        if not self.native:
            raise MemoryError("could not allocate multilag FFTW workspace")
        self.response = np.empty((2, len(LAGS), 2, dp.FRAME), dtype="<c8")

    def surface(self, samples):
        if samples.shape != (dp.SAMPLES, 2, 2) or samples.dtype != np.dtype("<i2"):
            raise ValueError("expected a dual-RX 20 ms CI16 short window")
        if not self.native:
            raise RuntimeError("the multilag scout context is closed")
        sample = np.ascontiguousarray(samples)
        self.kernel(
            self.native,
            sample.ctypes.data,
            self.filters.ctypes.data,
            self.energy.ctypes.data,
            self.response.ctypes.data,
        )
        return score(self.response)

    def __call__(self, samples, edge):
        if self.edge != edge:
            raise ValueError("the multilag scout is bound to its pilot edge")
        return [
            (rank, [float(row[i]) for i in rank])
            for row in self.surface(samples)
            for rank in [dp.ranked_centers(row, capacity=1)]
        ]

    def __exit__(self, *exc):
        if self.native:
            self.close(self.native)
            self.native = None
