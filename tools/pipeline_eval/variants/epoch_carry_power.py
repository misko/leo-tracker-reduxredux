"""An independent CFO-invariant timing nomination from known pilot energy."""

import numpy as np

RATE = 10_000_000
FRAME = 13_333
FFT = 8_192
SCOUT_FRAMES = tuple((i * 15 + 3) // 7 for i in range(8))
MIN_SCORE = 0.08


def distance(a, b):
    return abs((a - b + FRAME // 2) % FRAME - FRAME // 2)


class PilotEnvelope:
    def __init__(self, template):
        if len(template) != FRAME:
            raise ValueError("expected the ordinary 10 MS/s pilot period")
        q = np.arange(FFT) * FRAME
        self.source, self.weight = q // FFT, (q % FFT) / FFT
        expected = self.resample(abs(np.asarray(template)) ** 2)
        expected -= expected.mean()
        self.gain = np.linalg.norm(expected)
        self.fourier = np.fft.rfft(expected).conj()

    def resample(self, values):
        return values[self.source] + self.weight * (
            values[(self.source + 1) % FRAME] - values[self.source]
        )

    def select(self, iq, stock):
        if len(iq) != RATE // 50 or len(stock) != 4:
            return list(stock), None
        power = np.sum(np.asarray(iq, dtype=np.float64) ** 2, axis=1)
        energy, supports = np.zeros(FRAME), np.zeros(FRAME)
        for frame in SCOUT_FRAMES:
            start = round(RATE * frame / 750)
            length = min(FRAME, len(power) - start)
            energy[:length] += power[start : start + length]
            supports[:length] += 1
        observed = self.resample(energy / supports)
        observed -= observed.mean()
        norm = np.linalg.norm(observed) * self.gain
        if norm <= 0:
            return list(stock), None
        correlation = np.fft.irfft(np.fft.rfft(observed) * self.fourier) / norm
        before, after = np.roll(correlation, 1), np.roll(correlation, -1)
        keep = (
            (correlation >= before)
            & (correlation >= after)
            & ((correlation > before) | (correlation > after))
            & (correlation >= MIN_SCORE)
        )
        peaks = np.flatnonzero(keep)
        epochs = (peaks * FRAME + FFT // 2) // FFT % FRAME
        eligible = np.array([all(distance(int(e), p) >= 5 for p in stock[:3]) for e in epochs])
        if not eligible.any():
            return list(stock), None
        score = correlation[peaks][eligible]
        chosen = int(np.argmax(score))
        epoch = int(epochs[eligible][chosen])
        return [*stock[:3], epoch], dict(epoch=epoch, correlation=float(score[chosen]))
