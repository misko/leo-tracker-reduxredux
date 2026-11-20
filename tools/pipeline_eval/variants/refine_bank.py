"""Fused pairwise GLRT correlation on the original capture-era sample grid."""

import ctypes
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np

SOURCE = Path(__file__).with_suffix(".c")
FLAGS = ("-std=c11", "-O3", "-march=native", "-ffp-contract=off", "-shared", "-fPIC")
RATE = 10_000_000
SAMPLES = 200_000
GLRT_SIZE = 512
TAPS = 44
OFFSET = 2 * TAPS
STOP = 66 * TAPS
RELATIVE = np.arange(OFFSET, STOP)
SYMBOL_STARTS = RELATIVE[::TAPS]
FRAME_BASE = np.array([round(f * (RATE / 750)) for f in range(15)])
EPOCHS = round(RATE / 750)
LANCZOS = np.arange(-7, 9)


def compile_bank(library):
    subprocess.run(["cc", *FLAGS, str(SOURCE), "-lm", "-o", str(library)], check=True)


@lru_cache(maxsize=512)
def _frequency_grid(epoch):
    starts = epoch + FRAME_BASE
    starts = starts[starts + STOP <= SAMPLES]
    times = (starts[:, None] + SYMBOL_STARTS + (TAPS - 1) / 2) / RATE
    step = float(np.median(np.diff(times, axis=1)))
    return np.fft.fftfreq(GLRT_SIZE, d=step)


def _integer_spectrum(correlations):
    transformed = np.fft.fft(correlations, n=128, axis=2)
    autocorrelation = np.fft.ifft(np.sum(np.abs(transformed) ** 2, axis=1), axis=1)
    packed = np.zeros((len(correlations), GLRT_SIZE), dtype=np.complex128)
    packed[:, :64] = autocorrelation[:, :64]
    packed[:, -63:] = autocorrelation[:, -63:]
    spectrum = np.fft.fft(packed, axis=1).real
    ceiling = np.sum(np.sum(np.abs(correlations), axis=2) ** 2, axis=1)
    normalized = np.divide(
        spectrum, ceiling[:, None], out=np.zeros_like(spectrum), where=ceiling[:, None] > 0,
    )
    best = np.argmax(normalized, axis=1)
    return normalized[np.arange(len(correlations)), best], best


class RefinementBank:
    """Use the same scorer with shared input work inside one immutable window."""

    def __init__(self, library, producer):
        dll = ctypes.CDLL(str(Path(library).resolve()))

        def array(dtype):
            return np.ctypeslib.ndpointer(dtype=dtype, flags="C_CONTIGUOUS")

        z, i, d = (array(dtype) for dtype in (np.complex128, np.int32, np.float64))
        n = ctypes.c_int
        self.integer_correlation = dll.correlated_integer
        self.integer_correlation.argtypes = [z, i, n, n, i, z, z, z, z, z]
        self.integer_correlation.restype = None
        self.fractional_correlation = dll.correlated_fractional
        self.fractional_correlation.argtypes = [z, i, n, i, d, z, z, z, z, z]
        self.fractional_correlation.restype = None
        self.producer = producer
        self.original_integer = producer.conditioned_glrt64_scores
        self.original_fractional = producer.conditioned_glrt64_score
        self.templates = {}
        self.compatible = self._matches_runtime_arithmetic()
        self.reset()

    def reset(self):
        self.values = None
        self.scores = {}
        self.receipts = []

    def _templates(self, edge):
        edge = self.producer.StarlinkEdge(edge)
        if edge not in self.templates:
            frame = self.producer.qin_edge_pilot_frame
            self.templates[edge] = tuple(np.ascontiguousarray(
                frame(RATE, edge, symbol_roll=roll)[OFFSET:STOP].conj(), dtype=np.complex128,
            ) for roll in (0, self.producer.CONTROL_SYMBOL_ROLL))
        return self.templates[edge]

    def _matches_runtime_arithmetic(self):
        # The NumPy baseline and AVX2 dispatch can differ on fused products.
        # Verify the installed reduction against this binary before using it.
        rng = np.random.default_rng(15097)
        values, rotation, reference = (np.ascontiguousarray(
            rng.standard_normal(STOP - OFFSET) + 1j * rng.standard_normal(STOP - OFFSET)
        ) for _ in range(3))
        starts = np.zeros((1, 1), dtype=np.int32)
        exact = np.empty((1, 1, 64), dtype=np.complex128)
        control = np.empty_like(exact)
        self.integer_correlation(values, starts, 1, 1, starts.ravel(), rotation,
                                 reference, reference, exact, control)
        expected = np.sum((reference * (values * rotation)).reshape(64, TAPS), axis=1)
        return np.array_equal(exact.ravel(), expected)

    def _score(self, exact, control, residual, acquired):
        return self.producer._score(
            self.producer.PilotMethod.GLRT64, float(exact), float(control),
            float(residual), float(acquired),
        )

    def _supported(self, samples, rate, size):
        return (
            self.compatible and rate == RATE and type(size) is int and size == GLRT_SIZE
            and isinstance(samples, np.ndarray) and samples.shape == (SAMPLES,)
            and samples.dtype == np.complex128 and samples.flags.c_contiguous
        )

    def integer(self, samples, sample_rate_hz, *, epoch_samples, acquired_cfo_hz,
                edge="lower", glrt_size=GLRT_SIZE):
        epochs = np.asarray(epoch_samples)
        frequencies = np.asarray(acquired_cfo_hz, dtype=float)
        if not (
            self._supported(samples, sample_rate_hz, glrt_size)
            and epochs.ndim == frequencies.ndim == 1 and len(epochs) == len(frequencies)
            and np.issubdtype(epochs.dtype, np.integer)
            and np.all((epochs >= 0) & (epochs < EPOCHS))
            and np.isfinite(frequencies).all()
        ):
            return self.original_integer(
                samples, sample_rate_hz, epoch_samples=epoch_samples,
                acquired_cfo_hz=acquired_cfo_hz, edge=edge, glrt_size=glrt_size,
            )
        source = self.producer.StarlinkEdge(edge)
        if self.values is not samples:
            self.values, self.scores = samples, {}
        keys = tuple((source, int(ep), float(cfo)) for ep, cfo in zip(
            epochs, frequencies, strict=True,
        ))
        needed = tuple(dict.fromkeys(key for key in keys if key not in self.scores))
        if needed:
            unique_ep = np.array([key[1] for key in needed])
            unique_cfo = np.array([key[2] for key in needed])
            starts = unique_ep[:, None] + FRAME_BASE
            starts = starts[:, :int(np.max(np.sum(starts + STOP <= SAMPLES, axis=1)))]
            starts = np.where(starts + STOP <= SAMPLES, starts + OFFSET, -1).astype(np.int32)
            distinct, indices = np.unique(unique_cfo, return_inverse=True)
            rotation = np.exp(-2j * np.pi * distinct[:, None] * RELATIVE[None, :] / RATE)
            exact = np.zeros((*starts.shape, 64), dtype=np.complex128)
            control = np.zeros_like(exact)
            self.integer_correlation(
                samples, starts, *starts.shape, indices.astype(np.int32), rotation,
                *self._templates(source), exact, control,
            )
            exact_scores, best = _integer_spectrum(exact)
            control_scores, _ = _integer_spectrum(control)
            scores = zip(needed, exact_scores, control_scores, best, strict=True)
            for key, e, c, bin_index in scores:
                self.scores[key] = self._score(e, c, _frequency_grid(key[1])[bin_index], key[2])
            self.receipts.append(dict(
                kind="integer", evaluated=len(needed), reused=len(keys) - len(needed),
                rotation_rows=len(distinct), aperture_array_bytes=sum(a.nbytes for a in (
                    starts, indices, rotation, exact, control,
                )),
            ))
        return tuple(self.scores[key] for key in keys)

    def fractional(self, samples, sample_rate_hz, *, epoch_sample, acquired_cfo_hz, edge="lower",
                   glrt_size=GLRT_SIZE, fractional_epoch_offset_samples=0.0):
        offset = fractional_epoch_offset_samples
        if not (
            self._supported(samples, sample_rate_hz, glrt_size)
            and isinstance(epoch_sample, (int, np.integer)) and 0 <= epoch_sample < EPOCHS
            and np.isfinite(acquired_cfo_hz) and np.isfinite(offset)
            and abs(offset) <= 2.5 and abs(offset - round(offset)) > 2e-10
        ):
            return self.original_fractional(
                samples, sample_rate_hz, epoch_sample=epoch_sample, acquired_cfo_hz=acquired_cfo_hz,
                edge=edge, glrt_size=glrt_size, fractional_epoch_offset_samples=offset,
            )
        starts = epoch_sample + FRAME_BASE
        continuous_start = starts + OFFSET + offset
        left, right = self.producer.fractional_take_bounds(offset)
        valid = (continuous_start >= left) & (starts + STOP - 1 + offset < SAMPLES - right)
        invalid = np.flatnonzero(~valid)
        if invalid.size:
            starts = starts[:invalid[0]]
        phases = starts[:, None] + RELATIVE[None, :] + offset
        if not len(phases):
            return self._score(0.0, 0.0, 0.0, acquired_cfo_hz)
        base = np.floor(phases).astype(np.int32)
        fractions, weight_rows = np.unique(phases - base, return_inverse=True)
        distance = fractions[:, None] - LANCZOS
        weights = np.sinc(distance) * np.sinc(distance / 8)
        weights /= np.sum(weights, axis=1, keepdims=True)
        rotation = np.exp(-2j * np.pi * acquired_cfo_hz * phases / RATE)
        exact = np.empty((len(starts), 64), dtype=np.complex128)
        control = np.empty_like(exact)
        left_indexes = base + LANCZOS[0]
        self.fractional_correlation(
            samples, left_indexes.astype(np.int32), len(starts), weight_rows.astype(np.int32),
            weights, rotation, *self._templates(edge), exact, control,
        )
        times = (phases[:, ::TAPS] + (TAPS - 1) / 2) / RATE
        correlation = self.producer._SymbolCorrelations
        (exact_score, residual), (control_score, _) = self.producer._glrt_pair(
            correlation(exact, np.empty(0), times), correlation(control, np.empty(0), times),
            size=GLRT_SIZE,
        )
        self.receipts.append(dict(
            kind="fractional", evaluated=1, interpolated_samples=phases.size,
            weight_rows=len(weights), aperture_array_bytes=sum(a.nbytes for a in (
                phases, base, weight_rows, weights, left_indexes, rotation, exact, control, times,
            )),
        ))
        return self._score(exact_score, control_score, residual, acquired_cfo_hz)
