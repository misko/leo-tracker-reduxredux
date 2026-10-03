"""Receiver-band-limited known-pilot likelihoods for native low-rate IQ.

Unknown complex amplitude is eliminated independently in each frame. The
statistic is the mean normalized matched projection across independent frames.
Its white-noise likelihood interpretation is approximate for receiver noise;
empirical randomized-sequence controls are reported, not a claimed analytic PFA.
No storage, transport, or instrument dependencies belong in this module.
"""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy import fft, signal

from leo.analysis.starlink.templates import (
    CYCLIC_PREFIX_DURATION_S,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    edge_frequencies_hz,
    qin_edge_pilot_symbols,
)
from leo.contracts.partial_band import PartialBandCandidateV1, PartialBandConfigurationV1


def frame_partition(seed: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Split whole frames, independent of data, with persisted reproducibility."""
    order = np.random.default_rng(seed).permutation(14)
    return tuple(sorted(map(int, order[:7]))), tuple(sorted(map(int, order[7:])))


@lru_cache(maxsize=256)
def _replica_geometry(configuration_json, edge, fractional_sample, control, first_symbol):
    cfg = PartialBandConfigurationV1.model_validate_json(configuration_json)
    fs, high = cfg.sample_rate_hz, cfg.synthesis_rate_hz
    factor = high // fs
    count = round(cfg.symbol_count * OFDM_SYMBOL_DURATION_S * fs)
    guard = cfg.filter_taps // factor + 2
    t = (
        (np.arange(-guard * factor, (count + guard) * factor) / high)
        + first_symbol * OFDM_SYMBOL_DURATION_S
        + fractional_sample / fs
    )
    symbols = np.floor(t / OFDM_SYMBOL_DURATION_S + 1e-10).astype(int)
    local = t - symbols * OFDM_SYMBOL_DURATION_S - CYCLIC_PREFIX_DURATION_S
    states = qin_edge_pilot_symbols(edge)
    if control:
        states = states[np.random.default_rng(cfg.control_seed).permutation(300)]
    valid = (symbols >= 2) & (symbols < 302)
    base = np.zeros(t.size, np.complex128)
    base[valid] = np.sum(
        states[symbols[valid] - 2]
        * np.exp(2j * np.pi * local[valid, None] * edge_frequencies_hz(edge)[None, :]),
        axis=1,
    ) / np.sqrt(8)
    taps = signal.firwin(
        cfg.filter_taps, cfg.filter_cutoff_hz, fs=high, window=("kaiser", cfg.filter_kaiser_beta)
    )
    for array in (t, base, taps):
        array.flags.writeable = False
    return t, base, taps, factor, guard, count


def filtered_replicas(
    cfos_hz: np.ndarray,
    *,
    edge: str,
    configuration: PartialBandConfigurationV1,
    fractional_sample: float = 0.0,
    control: bool = False,
    first_symbol: int | None = None,
) -> np.ndarray:
    """Shift, filter with neighboring-symbol context, then sample.

    fractional_sample is integer sample time minus true frame epoch, in native
    samples. The selected 64-symbol interval is NOT zero padded before filtering.
    """
    t, base, taps, factor, guard, count = _replica_geometry(
        configuration.model_dump_json(),
        edge,
        round(fractional_sample, 10),
        control,
        configuration.first_symbol if first_symbol is None else first_symbol,
    )
    shifted = base[None, :] * np.exp(2j * np.pi * np.asarray(cfos_hz)[:, None] * t)
    native = signal.resample_poly(shifted, 1, factor, axis=1, window=taps)
    selected = native[:, guard : guard + count]
    norms = np.linalg.norm(selected, axis=1)
    if np.any(norms <= 1e-12):
        raise ValueError("pilot template has no observable energy")
    return np.asarray(selected / norms[:, None], np.complex64)


@dataclass(frozen=True)
class SearchBank:
    cfos: np.ndarray
    transforms: tuple[np.ndarray, ...]
    length: int
    fft_size: int
    epochs: int


@lru_cache(maxsize=4)
def _bank(configuration_json: str, edge: str, control: bool) -> SearchBank:
    cfg = PartialBandConfigurationV1.model_validate_json(configuration_json)
    cfos = np.arange(-cfg.maximum_cfo_hz, cfg.maximum_cfo_hz + 1, cfg.coarse_step_hz)
    period = cfg.sample_rate_hz / FRAME_RATE_HZ
    epochs = int(np.ceil(period))
    length = round(cfg.symbol_count * OFDM_SYMBOL_DURATION_S * cfg.sample_rate_hz)
    size = fft.next_fast_len(epochs + length - 1)
    transforms = []
    for frame in range(3):
        phase = round(frame * period) - frame * period
        replica = filtered_replicas(
            cfos, edge=edge, configuration=cfg, fractional_sample=phase, control=control
        )
        values = fft.fft(replica, n=size, axis=1).conj()
        values.flags.writeable = False
        transforms.append(values)
    cfos.flags.writeable = False
    return SearchBank(cfos, tuple(transforms), length, size, epochs)


def _search(samples, frames, cfg, edge, control=False):
    bank = _bank(cfg.model_dump_json(), edge, control)
    period = cfg.sample_rate_hz / FRAME_RATE_HZ
    anchor = round(cfg.first_symbol * OFDM_SYMBOL_DURATION_S * cfg.sample_rate_hz)
    scores = np.zeros((len(bank.cfos), bank.epochs), np.float64)
    for frame in frames:
        start = round(frame * period) + anchor
        x = samples[start : start + bank.epochs + bank.length - 1]
        integrals = np.concatenate(([0.0], np.cumsum(np.abs(x.astype(np.complex128)) ** 2)))
        energies = integrals[bank.length :] - integrals[: -bank.length]
        spectrum = fft.fft(x, n=bank.fft_size)
        # Bound intermediate allocations independently of CFO extent.
        for i in range(0, len(bank.cfos), 64):
            corr = fft.ifft(bank.transforms[frame % 3][i : i + 64] * spectrum, axis=1)
            scores[i : i + 64] += np.abs(corr[:, : bank.epochs]) ** 2 / np.maximum(energies, 1e-24)
    scores /= len(frames)
    peaks = []
    for _ in range(1 if control else cfg.maximum_candidates):
        i, epoch = np.unravel_index(np.argmax(scores), scores.shape)
        peaks.append((float(bank.cfos[i]), float(epoch), float(scores[i, epoch])))
        # Keep distinct CFO basins; no assumption that the strongest is unique.
        scores[np.abs(bank.cfos - bank.cfos[i]) < cfg.candidate_separation_hz, :] = -1
    return peaks


def projection_scores(samples, frames, cfos, epoch, cfg, edge, *, control=False, evaluation=False):
    """Direct filtered-template oracle, also used for local refinement."""
    period = cfg.sample_rate_hz / FRAME_RATE_HZ
    first_symbol = cfg.evaluation_first_symbol if evaluation else cfg.first_symbol
    anchor = round(first_symbol * OFDM_SYMBOL_DURATION_S * cfg.sample_rate_hz)
    length = round(cfg.symbol_count * OFDM_SYMBOL_DURATION_S * cfg.sample_rate_hz)
    integer = round(epoch)
    total = np.zeros(len(cfos))
    for phase in range(3):
        selected = [frame for frame in frames if frame % 3 == phase]
        if not selected:
            continue
        delta = round(phase * period) - phase * period + integer - epoch
        replicas = filtered_replicas(
            np.asarray(cfos),
            edge=edge,
            configuration=cfg,
            fractional_sample=delta,
            control=control,
            first_symbol=first_symbol,
        )
        for frame in selected:
            start = integer + round(frame * period) + anchor
            x = samples[start : start + length]
            if len(x) != length:
                raise ValueError("template crosses a probe boundary")
            total += np.abs(replicas.conj() @ x) ** 2 / max(float(np.vdot(x, x).real), 1e-24)
    return total / len(frames)


@dataclass(frozen=True)
class PartialBandResult:
    training_frames: tuple[int, ...]
    evaluation_frames: tuple[int, ...]
    control_training_score: float
    candidates: tuple[PartialBandCandidateV1, ...]
    zero_energy: bool = False


def analyze_partial_band_probe(
    samples,
    *,
    edge: str,
    configuration: PartialBandConfigurationV1 | None = None,
    split_seed: int | None = None,
) -> PartialBandResult:
    cfg = configuration or PartialBandConfigurationV1()
    x = np.asarray(samples, dtype=np.complex64)
    if x.ndim != 1 or x.size != cfg.sample_rate_hz * cfg.probe_ms // 1000:
        raise ValueError("partial-band analysis requires exactly one native 20 ms probe")
    if not np.all(np.isfinite(x)):
        raise ValueError("IQ must be finite")
    if edge not in ("lower", "upper"):
        raise ValueError("unknown pilot edge")
    train, evaluation = frame_partition(cfg.split_seed if split_seed is None else split_seed)
    if np.vdot(x, x).real <= 1e-24:
        return PartialBandResult(train, evaluation, 0.0, (), True)
    peaks = _search(x, train, cfg, edge)
    control_cfo, control_epoch, control_train = _search(x, train, cfg, edge, True)[0]
    control_eval = float(
        projection_scores(
            x, evaluation, [control_cfo], control_epoch, cfg, edge, control=True, evaluation=True
        )[0]
    )
    candidates = []
    for rank, (cfo, epoch, _) in enumerate(peaks):
        grid = np.arange(
            max(-cfg.maximum_cfo_hz, cfo - cfg.coarse_step_hz),
            min(cfg.maximum_cfo_hz, cfo + cfg.coarse_step_hz) + 1,
            cfg.fine_step_hz,
        )
        scores = projection_scores(x, train, grid, epoch, cfg, edge)
        cfo = float(grid[np.argmax(scores)])
        epochs = np.arange(epoch - 1, epoch + 1.001, cfg.timing_step_samples)
        epochs = epochs[(epochs >= 0) & (epochs < cfg.sample_rate_hz / FRAME_RATE_HZ)]
        scores = [projection_scores(x, train, [cfo], float(e), cfg, edge)[0] for e in epochs]
        epoch = float(epochs[np.argmax(scores)])
        train_score = float(max(scores))
        score = float(projection_scores(x, evaluation, [cfo], epoch, cfg, edge, evaluation=True)[0])
        conditioned = float(
            projection_scores(
                x, evaluation, [cfo], epoch, cfg, edge, control=True, evaluation=True
            )[0]
        )
        frequencies = edge_frequencies_hz(edge) + cfo
        visible = np.abs(frequencies) < cfg.filter_cutoff_hz
        clearance = (
            float(np.min(cfg.filter_cutoff_hz - np.abs(frequencies[visible])))
            if visible.any()
            else 0.0
        )
        passed = (
            train_score >= cfg.minimum_training_score
            and score >= cfg.minimum_evaluation_score
            and score >= cfg.minimum_control_ratio * max(conditioned, control_eval)
        )
        candidates.append(
            PartialBandCandidateV1(
                rank=rank,
                cfo_hz=cfo,
                epoch_samples=epoch,
                training_score=train_score,
                evaluation_score=score,
                conditioned_control_score=conditioned,
                searched_control_evaluation_score=control_eval,
                passed=passed,
                observable_tone_centers=int(visible.sum()),
                filter_edge_clearance_hz=clearance,
            )
        )
    return PartialBandResult(train, evaluation, control_train, tuple(candidates))
