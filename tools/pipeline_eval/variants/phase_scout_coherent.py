"""Pilot-matched coherent phase in five-tap groups at already proposed epochs."""

import numpy as np

RATE = 10_000_000
GRID = np.arange(-800_000, 800_001, 80_000)
FRAMES = np.rint(np.arange(14) * RATE / 750).astype(int)
LAGS = (1, 3)
ALL = (1 << len(GRID)) - 1


def lag_values(groups):
    z, rho = [], []
    for lag in LAGS:
        before, after = groups[..., :-lag], groups[..., lag:]
        lo, hi = (np.sum(abs(a) ** 2, axis=(-1, -2, -3)) for a in (before, after))
        cross = np.sum(after * before.conj(), axis=(-1, -2, -3))
        scale = np.sqrt(lo * hi)
        z.append(np.angle(cross))
        rho.append(np.divide(abs(cross), scale, out=np.zeros_like(scale), where=scale > 0))
    return np.stack(z, axis=-1), np.stack(rho, axis=-1)


class CoherentPilot:
    def __init__(self, template, symbol_time):
        self.taps = np.rint((2 + np.arange(12) * 26) * RATE * symbol_time).astype(int)[:, None]
        self.taps = self.taps + np.arange(40)[None, :]
        kernel = np.asarray(template)[self.taps]
        self.energy = (abs(kernel) ** 2).reshape(12, 8, 5).sum(axis=-1)
        self.reference = kernel.conj()
        rotation = np.exp(2j * np.pi * GRID[:, None, None] * self.taps[None, :, :] / RATE)
        pattern = (rotation * abs(kernel) ** 2).reshape(len(GRID), 12, 8, 5).sum(axis=-1)
        self.expected, _ = lag_values((pattern / self.energy)[..., None, :, :])

    def allocate(self, values, center):
        epochs = np.clip(center + np.arange(-1, 2), 0, round(RATE / 750) - 1)
        iq = values[
            epochs[:, None, None, None] + FRAMES[None, :, None, None] + self.taps[None, None, :, :]
        ]
        data = (iq * self.reference).reshape(len(epochs), len(FRAMES), 12, 8, 5).sum(axis=-1)
        data = data / self.energy
        splits = [lag_values(group) for group in (data, data[:, ::2], data[:, 1::2])]
        k = int(np.argmax(np.minimum(splits[1][1], splits[2][1]).min(axis=-1)))
        phase = np.stack([s[0][k] for s in splits])
        strength = np.stack([s[1][k] for s in splits])
        residual = (phase[:, None, :] - self.expected[None, :, :] + np.pi) % (2 * np.pi) - np.pi
        best = np.argmin((residual**2 * strength[:, None, :] ** 2).sum(axis=-1), axis=-1)
        measured = dict(
            epoch=int(epochs[k]),
            bins=best.tolist(),
            coherence=strength.tolist(),
            residual_rad=np.max(abs(residual[np.arange(3), best]), axis=-1).tolist(),
        )
        if strength.min() < 0.09 or np.ptp(best) > 1 or max(measured["residual_rad"]) > 0.55:
            return ALL, measured
        pivot = int(best[0])
        return sum(1 << i for i in range(max(0, pivot - 2), min(len(GRID), pivot + 3))), measured
