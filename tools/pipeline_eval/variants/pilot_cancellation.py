"""Training-only Qin acquisition and subtraction with a disjoint holdout."""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from . import frame_coherence as recurrence

RATE = recurrence.RATE
FRAME = recurrence.FRAME
SAMPLES = recurrence.SAMPLES
SPLIT = SAMPLES // 2
PERIOD = RATE / 750
STEPS = np.arange(-950, 951, 10, dtype=float)
FRACTIONS = (0, -1, 1)
ALIAS_HZ = RATE / 44
STRIDE = 4
BLOCK = 64
FFT_BINS = 8192
BASE_CENTERS = 4
EXTRA_CENTERS = 8
EPOCH_TOLERANCE = 2
CFO_TOLERANCE = 1000
FRAME_OFFSETS = np.rint(np.arange(-1, 16) * PERIOD).astype(int)
FRAME_NUMBERS = np.arange(-1, 16)


@dataclass(frozen=True)
class Pilot:
    epoch: int
    third: int
    cfo_hz: float
    center_rank: int
    power: float
    amplitude: complex

    @property
    def phase(self):
        return self.epoch + self.third / 3


@dataclass(frozen=True)
class Evidence:
    frames: int
    excess: float
    repeated: int
    coherent_power: float
    amplitude_ratio: float
    phase_error_rad: float
    transfer: float
    contrast_blocks: tuple[float, float]

    @property
    def coded(self):
        return (
            self.frames >= 4
            and self.repeated >= 3
            and self.excess >= 5
            and min(self.contrast_blocks) > 0
        )


def difference(a_phase, a_hz, b_phase, b_hz):
    phase_delta = (a_phase - b_phase + PERIOD / 2) % PERIOD - PERIOD / 2
    hz_delta = a_hz - b_hz
    alias_delta = (hz_delta + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2
    return phase_delta, hz_delta, alias_delta


def relationship(a_phase, a_hz, b_phase, b_hz):
    phase, hz, alias = difference(a_phase, a_hz, b_phase, b_hz)
    if abs(phase) > EPOCH_TOLERANCE or abs(alias) > CFO_TOLERANCE:
        return "distinct"
    return "literal" if abs(hz) <= CFO_TOLERANCE else "alias"


def comparable(a, b):
    phase, _, alias = difference(a.phase, a.cfo_hz, b.phase, b.cfo_hz)
    return abs(phase) <= 44 and abs(alias) <= 2 * CFO_TOLERANCE


@lru_cache(maxsize=2)
def banks(edge):
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

    # One high-rate array serves every epoch and rounded 750 Hz frame residue.
    return tuple(
        qin_edge_pilot_frame(3 * RATE, edge, symbol_roll=roll) for roll in (0, CONTROL_SYMBOL_ROLL)
    )


@lru_cache(maxsize=18)
def waves(edge, third, stride, rolled):
    phase_residue = np.asarray((0, 1, -1))
    offsets = np.arange(0, FRAME, stride)
    location = 3 * offsets - phase_residue[:, None] - third
    reference = banks(edge)[rolled]
    valid = (location >= 0) & (location < len(reference))
    return np.where(valid, reference.take(location, mode="clip"), 0)


def view(epoch, lo, hi):
    starts = epoch + FRAME_OFFSETS
    complete = (starts >= lo) & (starts + FRAME <= hi)
    return starts[complete], FRAME_NUMBERS[complete] % 3


def scout(samples, edge):
    exact, control = recurrence.filters(edge)
    folded = np.zeros((3, FRAME), dtype=np.complex64)
    for i, start in enumerate(recurrence.STARTS):
        later = start + recurrence.LAG
        if later + FRAME > SPLIT:
            break
        folded[i % 3] += samples[start : start + FRAME].conj() * samples[later : later + FRAME]
    energy = np.sum(abs(folded) ** 2, axis=-1)
    folded -= np.mean(folded, axis=-1, keepdims=True)
    spectrum = np.fft.fft(folded, n=recurrence.FFT, axis=-1)
    a = recurrence.circular_prompt(spectrum, exact)
    b = recurrence.circular_prompt(spectrum, control)
    surface = np.sum((abs(a) ** 2 - abs(b) ** 2) / np.maximum(energy[:, None], 1), axis=0)
    centers = recurrence.ranked_centers(surface, BASE_CENTERS + EXTRA_CENTERS)
    return [(epoch, float(surface[epoch])) for epoch in centers]


def lane_values(samples):
    if samples.shape != (SAMPLES, 2, 2) or samples.dtype != np.dtype("<i2"):
        raise ValueError("expected 20 ms of dual-CI16 at 10 MS/s")
    result = np.empty((2, SAMPLES), dtype=np.complex64)
    result.real, result.imag = samples[:, :, 0].T, samples[:, :, 1].T
    return result


def training_spectrum(samples, edge, epoch):
    starts, residues = view(epoch, 0, SPLIT)
    reference = waves(edge, 0, STRIDE, False)[residues]
    offsets = np.arange(0, FRAME, STRIDE)
    signal = samples[starts[:, None] + offsets]
    product = signal * reference.conj()
    spectrum = np.fft.fft(product, n=FFT_BINS, axis=-1)
    energy = np.sum(abs(signal) ** 2)
    return np.sum(abs(spectrum) ** 2, axis=0) / max(float(energy), 1)


def fit(samples, edge, epoch, cfo_hz, center_rank):
    starts, residues = view(epoch, 0, SPLIT)
    offsets = np.arange(0, FRAME, STRIDE)
    tap_times = starts[:, None] + offsets
    data = samples[tap_times] * np.exp(-2j * np.pi * cfo_hz * tap_times / RATE)
    references = np.stack([waves(edge, third, STRIDE, False)[residues] for third in FRACTIONS])
    products = (data * references.conj()).reshape(len(FRACTIONS), len(starts), -1)
    padded = (-products.shape[-1]) % BLOCK
    products = np.pad(products, ((0, 0), (0, 0), (0, padded)))
    reduced = products.reshape(len(FRACTIONS), len(starts), -1, BLOCK).sum(axis=-1)
    midpoints = starts[:, None] + (np.arange(reduced.shape[-1]) * BLOCK + BLOCK / 2) * STRIDE
    correction = np.exp(-2j * np.pi / RATE * STEPS[:, None] * midpoints.reshape(-1))
    scores = np.einsum("fc,kc->fk", reduced.reshape(len(FRACTIONS), -1), correction)
    energy = np.sum(abs(references) ** 2, axis=(1, 2))
    powers = abs(scores) ** 2 / energy[:, None]
    i, j = np.unravel_index(np.argmax(powers), powers.shape)
    exact_data = data * np.exp(-2j * np.pi * STEPS[j] * tap_times / RATE)
    amplitude = np.sum(exact_data * references[i].conj()) / energy[i]
    return Pilot(
        epoch,
        FRACTIONS[i],
        float(cfo_hz + STEPS[j]),
        center_rank,
        float(powers[i, j] / max(float(np.mean(abs(data) ** 2)), 1)),
        complex(amplitude),
    )


def discover(samples, edge, centers, lo_hz, hi_hz, *, rank_start=0, exclude=None):
    frequencies = np.fft.fftfreq(FFT_BINS, d=STRIDE / RATE)
    use = (frequencies >= lo_hz) & (frequencies <= hi_hz)
    found = []
    for rank, (center, _) in enumerate(centers, start=rank_start):
        epochs = [(center + move) % FRAME for move in (0, -1, 1)]
        spectra = np.stack([training_spectrum(samples, edge, epoch) for epoch in epochs])
        spectra[:, ~use] = 0
        if exclude is not None:
            for i, epoch in enumerate(epochs):
                phase, _, alias = difference(epoch, frequencies, exclude.phase, exclude.cfo_hz)
                if abs(phase) <= 45:
                    spectra[i, abs(alias) <= 2950] = 0
        for _ in range(2):
            row, bin_index = np.unravel_index(np.argmax(spectra), spectra.shape)
            if spectra[row, bin_index] <= 0:
                break
            hz = frequencies[bin_index]
            spectra[:, abs(frequencies - hz) <= 1950] = 0
            candidate = fit(samples, edge, epochs[row], hz, rank)
            if lo_hz <= candidate.cfo_hz <= hi_hz and (
                exclude is None or not comparable(exclude, candidate)
            ):
                found.append(candidate)
    return sorted(found, key=lambda candidate: -candidate.power)


def correlation(samples, edge, pilot, lo, hi):
    starts, residues = view(pilot.epoch, lo, hi)
    offsets = np.arange(0, FRAME, STRIDE)
    time = starts[:, None] + offsets
    signal = samples[time] * np.exp(-2j * np.pi * pilot.cfo_hz * time / RATE)
    a = waves(edge, pilot.third, STRIDE, False)[residues]
    b = waves(edge, pilot.third, STRIDE, True)[residues]
    energy = np.mean(abs(signal) ** 2, axis=-1)
    energy = np.maximum(energy, 1.0)
    phase = np.sum(a.conj() * signal, axis=-1)
    scale = np.sum(abs(a) ** 2, axis=-1)
    normalized = abs(phase) ** 2 / (scale * energy)
    rolled = abs(np.sum(b.conj() * signal, axis=-1)) ** 2 / (np.sum(abs(b) ** 2, axis=-1) * energy)
    delta = normalized - rolled
    return phase, scale, energy, delta


def evidence(samples, edge, pilot, lo=SPLIT, hi=SAMPLES):
    phase, scale, energy, delta = correlation(samples, edge, pilot, lo, hi)
    coherence = phase.sum()
    prediction = pilot.amplitude * scale.sum()
    interference = np.sum(energy * scale)
    transfer = 2 * np.real(coherence * prediction.conjugate()) - abs(prediction) ** 2
    ratio = coherence / prediction if prediction else 0j
    half = len(delta) // 2
    return Evidence(
        len(delta),
        float(delta.sum() / np.sqrt(2 * len(delta))),
        int(np.count_nonzero(delta > 1)),
        float(abs(coherence) ** 2 / interference),
        float(abs(ratio)),
        float(np.angle(ratio)),
        float(transfer / max(abs(coherence) ** 2, 1)),
        (float(delta[:half].sum()), float(delta[half:].sum())),
    )


def render(edge, pilot, *, shift=0, frame_rotation=None):
    values = np.zeros(SAMPLES, dtype=np.complex64)
    starts = pilot.epoch + FRAME_OFFSETS + shift
    reference = waves(edge, pilot.third, 1, False)
    for i, (start, residue) in enumerate(zip(starts, FRAME_NUMBERS % 3, strict=True)):
        lo, hi = max(start, 0), min(start + FRAME, SAMPLES)
        if lo >= hi:
            continue
        rotation = 1 if frame_rotation is None else frame_rotation[i]
        wave = reference[residue, lo - start : hi - start]
        values[lo:hi] = (
            wave
            * pilot.amplitude
            * rotation
            * np.exp(2j * np.pi * pilot.cfo_hz * np.arange(lo, hi) / RATE)
        )
    return values
