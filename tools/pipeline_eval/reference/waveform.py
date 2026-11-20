"""Frozen Qin waveform control extracted from the earlier bounded IQ probe."""


import math
import time

import numpy as np

from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame


FREQUENCY_PERIOD = 1 / 4.4e-6
PHASE_PERIOD_US = 1e6 / 750


def wrap(value, period):
    return (value + period / 2) % period - period / 2


RATE = 10_000_000
FRAME_SAMPLES = round(RATE / 750)
PROBE_SAMPLES = RATE // 50
FFT_SIZE = 512
PROPOSALS = 8
REFINE_SAMPLES = 4
MARGIN = 0.10
TAPS = np.arange(2, 66)[:, None] * 44 + np.arange(44)
ALIASES = np.arange(-2, 3)
ALIAS_ROTATION = np.exp(-2j * np.pi * np.outer(ALIASES, np.arange(44)) / 44)
BINS_HZ = np.fft.fftfreq(FFT_SIZE) * FREQUENCY_PERIOD


def source_phase(counter):
    return ((counter * 750) % RATE) / RATE * PHASE_PERIOD_US


def phase_at(epoch, counter):
    return (source_phase(counter) + epoch * 1e6 / RATE) % PHASE_PERIOD_US


class PilotBank:
    """Shared two-lag FFT proposals and exact-versus-rolled 64-symbol pilot scores."""

    def __init__(self, edge):
        template = np.asarray(qin_edge_pilot_frame(RATE, edge), np.complex128)
        control = np.asarray(qin_edge_pilot_frame(RATE, edge, symbol_roll=CONTROL_SYMBOL_ROLL), np.complex128)
        self.reference = np.stack((template[TAPS], control[TAPS])).conj()
        self.lag_references = []
        for lag in (4, 20):
            feature = np.roll(template, -lag) * template.conj()
            feature -= feature.mean()
            self.lag_references.append((lag, np.fft.fft(feature).conj(), np.linalg.norm(feature)))

    def coarse(self, x):
        folds = np.rint(np.arange(math.floor(x.size * 750 / RATE) - 1) * RATE / 750).astype(int)
        folds = folds[:, None] + np.arange(FRAME_SAMPLES)[None, :]
        scores = np.zeros(FRAME_SAMPLES)
        for lag, template_fft, template_norm in self.lag_references:
            feature = (x[folds + lag] * x[folds].conj()).mean(axis=0)
            feature -= feature.mean()
            scale = np.linalg.norm(feature) * template_norm
            if scale > 0.:
                scores += np.abs(np.fft.ifft(np.fft.fft(feature) * template_fft)) / scale
        return scores

    def search(self, x, counter, gates=None):
        start = time.perf_counter()
        proposal = self.coarse(x)
        coarse = time.perf_counter()
        epoch_grid = np.arange(FRAME_SAMPLES)
        phases = phase_at(epoch_grid, counter)
        if gates is not None:
            possible = np.zeros(FRAME_SAMPLES, dtype=bool)
            for gate in gates:
                possible |= np.abs(wrap(phases - gate.phase_us, PHASE_PERIOD_US)) <= gate.half_us
            proposal[~possible] = -np.inf
        epochs = set()
        for _ in range(PROPOSALS):
            peak = int(proposal.argmax())
            if not np.isfinite(proposal[peak]):
                break
            epochs.update(int(ep) for ep in (peak + np.arange(-REFINE_SAMPLES, REFINE_SAMPLES+1)) % FRAME_SAMPLES)
            proposal[(peak + np.arange(-12, 13)) % FRAME_SAMPLES] = -np.inf

        frame_starts = np.rint(np.arange(15) * RATE / 750).astype(int)
        best = None
        cells = 0
        tested_epochs = 0
        for epoch in sorted(epochs):
            use = None
            if gates is not None:
                use = np.zeros(FFT_SIZE, dtype=bool)
                for gate in gates:
                    if abs(wrap(phases[epoch] - gate.phase_us, PHASE_PERIOD_US)) <= gate.half_us:
                        use |= np.abs(wrap(BINS_HZ - gate.frequency, FREQUENCY_PERIOD)) <= gate.half_hz
                if not use.any():
                    continue
            starts = frame_starts[frame_starts + epoch + TAPS[-1, -1] < x.size]
            if len(starts) < 2:
                continue
            samples = x[starts[:, None, None] + epoch + TAPS[None, :, :]]
            z = np.einsum("fst,kst,at->kafs", samples, self.reference, ALIAS_ROTATION, optimize=True)
            ceiling = np.sum(np.sum(abs(z), axis=-1)**2, axis=-1)
            if use is None:
                hz = BINS_HZ
                spectrum = np.fft.fft(z, n=FFT_SIZE, axis=-1)
            else:
                hz = BINS_HZ[use]
                steering = np.exp(-2j * np.pi * np.outer(np.arange(TAPS.shape[0]), hz) / FREQUENCY_PERIOD)
                spectrum = z @ steering
            power = np.sum(abs(spectrum)**2, axis=-2)
            norm = np.divide(power, ceiling[:, :, None], out=np.zeros_like(power), where=ceiling[:, :, None] > 0.)
            arg = np.argmax(norm[0], axis=-1)
            exact = norm[0, np.arange(ALIASES.size), arg]
            control = np.max(norm[1], axis=-1)
            margin = exact - control
            alias = int(np.argmax(margin))
            cells += 2 * ALIASES.size * hz.size
            tested_epochs += 1
            if best is None or margin[alias] > best["margin"]:
                best = dict(epoch_sample=epoch, phase_us=float(phases[epoch]), cfo_hz=float(hz[arg[alias]]),
                            alias_cfo_hz=float(hz[arg[alias]] + ALIASES[alias] * FREQUENCY_PERIOD),
                            exact=float(exact[alias]), control=float(control[alias]), margin=float(margin[alias]),
                            frames=len(starts), passed=bool(margin[alias] >= MARGIN))
        return dict(winner=best, tested_epochs=tested_epochs, scored_epoch_alias_cfo_cells=cells,
                    coarse_wall_ms=1000 * (coarse - start), total_wall_ms=1000 * (time.perf_counter() - start))
