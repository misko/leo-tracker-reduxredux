"""CFO-free pilot predictor for 20 ms CI16 at 2.5 MS/s.

One instance per worker: scratch buffers are reused and are not thread-safe.
The C kernel is explicitly supplied; there is no compilation or fallback at
runtime. The published cutoff is qualified on the two saved 2.5 MS/s scans.
"""

from __future__ import annotations

import ctypes
from pathlib import Path

import numpy as np

from leo.analysis.starlink import templates
from leo.analysis.starlink.pilot_predictor_bank import prepare_bank


def native_library_path() -> Path:
    """Return the installed kernel, failing explicitly if it was not built."""
    from leo.analysis.starlink import _native_acquisition

    return Path(_native_acquisition.__file__)


def pilot_period(edge: str, roll: int = 0) -> np.ndarray:
    """Sample three frames exactly, avoiding rounded samples per frame."""
    if edge not in ("lower", "upper"):
        raise ValueError("edge must be lower or upper")
    ticks = (3 * np.arange(10000)) % 10000
    symbols = ticks // 33
    valid = (symbols >= 2) & (symbols < 302)
    local = (ticks[valid] - symbols[valid] * 33) / 7500000
    coefficients = templates.qin_edge_pilot_symbols(edge, symbol_roll=roll)
    frequencies = templates.edge_frequencies_hz(edge)
    values = np.zeros(10000, complex)
    values[valid] = np.sum(
        coefficients[symbols[valid] - 2]
        * np.exp(
            2j
            * np.pi
            * (local[:, None] - templates.CYCLIC_PREFIX_DURATION_S)
            * frequencies[None, :]
        ),
        axis=1,
    ) / np.sqrt(8)
    return values


class PilotPredictor:
    """Exact lag-one score with one inverse FFT per receiver.

    Only the exact template needs a full timing search. The control is evaluated
        directly at the winning epoch, preserving the reference score definition.
    """

    def __init__(self, library: str | Path, edge: str, receivers: int = 2):
        if receivers not in (1, 2):
            raise ValueError("receivers must be 1 or 2")
        exact, control = pilot_period(edge), pilot_period(edge, 17)
        bank = prepare_bank(exact, control, (1,))
        self._transform = bank.transforms[0, 0].conj()
        self._inverse_norm = 1 / np.sqrt(bank.energies[0])
        self._control = control * np.roll(control, 1).conj()
        self._control -= self._control.mean()
        self._library = ctypes.CDLL(str(Path(library).resolve()))
        self._kernel = self._library.fast8_fold_ci16
        self._kernel.argtypes = [
            np.ctypeslib.ndpointer(dtype=np.int16, flags="C_CONTIGUOUS"),
            ctypes.c_int,
            np.ctypeslib.ndpointer(dtype=np.complex128, flags="C_CONTIGUOUS"),
            np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS"),
        ]
        self._kernel.restype = ctypes.c_int
        self.receivers = receivers
        self._fold = np.empty((receivers, 10000), dtype=np.complex128)
        self._energy = np.empty(receivers, dtype=np.float64)

    def score_ci16(self, iq: np.ndarray) -> list[dict[str, float | int]]:
        """Score contiguous, native-endian signed CI16; no IQ conversion."""
        if (
            iq.dtype != np.dtype(np.int16)
            or iq.shape != (50000, self.receivers, 2)
            or not iq.flags.c_contiguous
        ):
            raise ValueError("requires contiguous native CI16 shaped (50000, receivers, 2)")
        if self._kernel(iq, self.receivers, self._fold, self._energy) != 0:
            raise RuntimeError("native folding failed")
        numerators = np.abs(np.fft.ifft(np.fft.fft(self._fold, axis=1) * self._transform, axis=1))
        normalized = numerators * self._inverse_norm[0]
        epochs = normalized.argmax(axis=1)
        result = []
        for rx, epoch in enumerate(epochs):
            if self._energy[rx] <= 0:
                result.append({"margin": 0.0, "exact": 0.0, "control": 0.0, "epoch_sample": 0})
                continue
            scale = 1 / np.sqrt(self._energy[rx])
            exact = float(normalized[rx, epoch] * scale)
            # Circularly shifted control without allocating np.roll(control).
            split = int(epoch)
            folded = self._fold[rx]
            if split:
                dot = np.vdot(self._control[-split:], folded[:split]) + np.vdot(
                    self._control[:-split], folded[split:]
                )
            else:
                dot = np.vdot(self._control, folded)
            control = float(abs(dot) * self._inverse_norm[1, epoch] * scale)
            result.append(
                {
                    "margin": exact - control,
                    "exact": exact,
                    "control": control,
                    "epoch_sample": int(epoch),
                }
            )
        return result
