"""Fixed-coordinate late pilot measurement for ordinary native GLRT proposals."""

from dataclasses import dataclass
from math import isfinite, sqrt

import numpy as np

from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    CYCLIC_PREFIX_DURATION_S,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    edge_frequencies_hz,
    qin_edge_pilot_symbols,
)

SAMPLE_RATE_HZ = 10_000_000
SYMBOL_BLOCKS = (tuple(range(79, 142, 2)), tuple(range(199, 262, 2)))
SYMBOL_TAPS = np.arange(5, 41)
NATIVE_MARGIN = 0.025
MINIMUM_CONFIRMATION = 2.5


@dataclass(frozen=True)
class PilotEvidence:
    frames: int
    block_z: tuple[float, float]
    pooled_z: float
    passed: bool


class PilotConfirmation:
    """Compare exact and rolled pilots without adjusting epoch, CFO or rank."""

    def __init__(self, sample_rate_hz, edge, *, minimum_margin=NATIVE_MARGIN):
        if sample_rate_hz != SAMPLE_RATE_HZ:
            raise ValueError("pilot confirmation requires the recorded 10 MS/s geometry")
        self.sample_rate_hz = sample_rate_hz
        self.minimum_margin = minimum_margin
        symbols = np.asarray(SYMBOL_BLOCKS)
        symbol_samples = round(OFDM_SYMBOL_DURATION_S * sample_rate_hz)
        self.taps = (symbols[:, :, None] * symbol_samples + SYMBOL_TAPS).reshape(2, -1)
        self.component_angular = 2 * np.pi * edge_frequencies_hz(edge) / sample_rate_hz
        basis = np.exp(
            1j
            * np.outer(
                SYMBOL_TAPS - CYCLIC_PREFIX_DURATION_S * sample_rate_hz, self.component_angular
            )
        )
        states = np.stack(
            [
                qin_edge_pilot_symbols(edge, symbol_roll=roll)[symbols - 2]
                for roll in (0, CONTROL_SYMBOL_ROLL)
            ]
        )
        self.components = (states[:, :, :, None, :] * basis).reshape(2, 2, -1, basis.shape[1])
        frames = np.arange(15)
        self.frame_starts = np.rint(frames * sample_rate_hz / FRAME_RATE_HZ).astype(int)
        self.frame_phase = frames % 3  # 10 MHz / 750 Hz has denominator three.
        self.phase_offset = np.arange(3) * sample_rate_hz / FRAME_RATE_HZ - self.frame_starts[:3]

    def __call__(self, samples, rows):
        if samples.dtype != np.dtype("<i2") or samples.shape != (self.sample_rate_hz // 50, 2, 2):
            raise ValueError("pilot confirmation requires dual-CI16 and 20 ms of measured IQ")
        if tuple(row["receiver_id"] for row in rows) != (0, 1) or any(
            row["probe_start_ms"] != 0 or len(row["candidates"]) > 8 for row in rows
        ):
            raise ValueError("pilot confirmation requires the two native short-window rows")
        results = {}
        for row in rows:
            receiver = row["receiver_id"]
            cache = {}
            for rank, candidate in enumerate(row["candidates"]):
                fractional = candidate["fractional_epoch"]
                if fractional["status"] != "complete" or fractional["margin"] < self.minimum_margin:
                    continue
                key = (
                    candidate["epoch"],
                    fractional["offset_samples"],
                    fractional["tracking_cfo_hz"],
                )
                if key not in cache:
                    cache[key] = self._measure(samples[:, receiver, :], *key)
                results[receiver, rank] = cache[key]
        return results

    def _measure(self, samples, epoch, offset, cfo_hz):
        if (
            type(epoch) is not int
            or not 0 <= epoch < round(self.sample_rate_hz / FRAME_RATE_HZ)
            or not isfinite(offset)
            or abs(offset) > 1.5
            or not isfinite(cfo_hz)
        ):
            raise ValueError("pilot confirmation requires complete native fractional coordinates")
        starts = epoch + self.frame_starts
        complete = starts + self.taps[-1, -1] < len(samples)
        frame_phase = self.frame_phase[complete]

        # Generate the fractional reference at the retained raw sample times. The
        # interior taps keep it inside its own symbol for all offsets and frames.
        shifts = np.exp(-1j * np.outer(self.phase_offset + offset, self.component_angular))
        reference = np.einsum("wblc,pc->wpbl", self.components, shifts)
        reference /= np.linalg.norm(reference, axis=-1, keepdims=True)
        similarity = np.einsum("pbl,pbl->pb", reference[0].conj(), reference[1])
        steering = np.exp(2j * np.pi * cfo_hz * self.taps / self.sample_rate_hz)
        kernels = (reference * steering).conj()[:, frame_phase]

        data = samples[starts[complete, None, None] + self.taps]
        signal = data[..., 0].astype(np.complex128)
        signal.imag = data[..., 1]
        energy = np.mean(signal.real**2 + signal.imag**2, axis=-1)
        observed = np.all(energy > 0, axis=1)
        frames = int(np.count_nonzero(observed))
        if frames < 2:
            return PilotEvidence(frames, (0.0, 0.0), 0.0, False)
        correlation = np.einsum("fbl,wfbl->wfb", signal, kernels)
        power = correlation.real**2 + correlation.imag**2
        delta = (power[0, observed] - power[1, observed]) / energy[observed]
        variance = 2 * (1 - np.abs(similarity[frame_phase[observed]]) ** 2)
        block_z = delta.sum(axis=0) / np.sqrt(variance.sum(axis=0))
        first, second = map(float, block_z)
        pooled = (first + second) / sqrt(2)
        return PilotEvidence(
            frames,
            (first, second),
            pooled,
            min(first, second) > 0 and pooled >= MINIMUM_CONFIRMATION,
        )
