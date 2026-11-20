"""Gate the rolled-pilot GLRT on a bound from the exact-pilot score.

Both arms use the existing 8-proposal, two-lag blind timing search. The control
scores all epochs, aliases and CFO bins in those proposals. The candidate first
scores the exact hypothesis on the same grid. The exact peak bounds the margin
from above because the maximum rolled score is nonnegative. A rolled search can
only affect the published result if that bound reaches the 0.10 threshold
and can beat the best earlier detection. Grid order breaks ties in both arms.

The experiment uses both receivers in sequences 0 and 1 of each roof case
and one phase-randomized null from the first receiver in sequence 0. Real
positives and negatives are defined by the blind waveform control. No archived
detections or location estimates enter either arm.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median

import numpy as np

from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

RATE = 10_000_000
FRAME_RATE = 750
FRAME_SAMPLES = round(RATE / FRAME_RATE)
WINDOW_SAMPLES = RATE // 50
FFT_SIZE = 512
PROPOSALS = 8
REFINE_SAMPLES = 4
SUPPRESSION_SAMPLES = 12
DETECTION_MARGIN = 0.10
REPEATS = 5
NULL_SEED = 347_227
LAGS = (4, 20)
TAPS = np.arange(2, 66)[:, None] * 44 + np.arange(44)
ALIASES = np.arange(-2, 3)
CFO_PERIOD_HZ = RATE / TAPS.shape[1]
CFO_HZ = np.fft.fftfreq(FFT_SIZE) * CFO_PERIOD_HZ
ALIAS_ROTATIONS = np.exp(-2j * np.pi * ALIASES[:, None] * np.arange(44) / 44)
BOUNDARY = "Decoded 20 ms IQ to Qin pilot decision on the blind proposal grid"


@dataclass(frozen=True)
class Detection:
    epoch_sample: int
    alias: int
    cfo_bin: int
    cfo_hz: float
    absolute_cfo_hz: float
    margin: float


@dataclass(frozen=True)
class Search:
    winner: Detection | None
    epochs: int
    exact_fft_cells: int
    rolled_fft_cells: int


class PilotSearch:
    def __init__(self, edge: str):
        exact = qin_edge_pilot_frame(RATE, edge).astype(np.complex128)
        rolled = qin_edge_pilot_frame(RATE, edge, symbol_roll=CONTROL_SYMBOL_ROLL)
        self.exact = exact[TAPS].conj()[None, :, :] * ALIAS_ROTATIONS[:, None, :]
        self.rolled = rolled[TAPS].conj()[None, :, :] * ALIAS_ROTATIONS[:, None, :]
        self.lags = []
        for lag in LAGS:
            feature = np.roll(exact, -lag) * exact.conj()
            feature -= feature.mean()
            self.lags.append((lag, np.fft.fft(feature).conj(), np.linalg.norm(feature)))

    def epochs(self, samples: np.ndarray) -> list[int]:
        frame_count = math.floor(samples.size * FRAME_RATE / RATE) - 1
        folds = np.rint(np.arange(frame_count) * RATE / FRAME_RATE).astype(int)
        indexes = folds[:, None] + np.arange(FRAME_SAMPLES)
        scores = np.zeros(FRAME_SAMPLES)
        for lag, template_fft, template_norm in self.lags:
            feature = (samples[indexes + lag] * samples[indexes].conj()).mean(axis=0)
            feature -= feature.mean()
            scale = np.linalg.norm(feature) * template_norm
            if scale > 0:
                scores += np.abs(np.fft.ifft(np.fft.fft(feature) * template_fft)) / scale

        epochs = set()
        for _ in range(PROPOSALS):
            peak = int(np.argmax(scores))
            neighbours = peak + np.arange(-REFINE_SAMPLES, REFINE_SAMPLES + 1)
            epochs.update(neighbours % FRAME_SAMPLES)
            suppressed = peak + np.arange(-SUPPRESSION_SAMPLES, SUPPRESSION_SAMPLES + 1)
            scores[suppressed % FRAME_SAMPLES] = -np.inf
        return sorted(epochs)

    @staticmethod
    def peak_scores(samples: np.ndarray, reference: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        matched = np.einsum("fst,ast->afs", samples, reference, optimize=False)
        ceiling = np.sum(np.sum(np.abs(matched), axis=-1) ** 2, axis=-1)
        spectrum = np.fft.fft(matched, n=FFT_SIZE, axis=-1)
        power = np.sum(np.abs(spectrum) ** 2, axis=-2)
        bins = np.argmax(power, axis=-1)
        peak = power[np.arange(len(bins)), bins]
        score = np.divide(peak, ceiling, out=np.zeros_like(peak), where=ceiling > 0)
        return bins, score

    def search(self, samples: np.ndarray, *, gated: bool) -> Search:
        if samples.shape != (WINDOW_SAMPLES,):
            raise ValueError("pilot search requires one complete 20 ms receiver window")
        winner = None
        rolled_aliases = 0
        epochs = self.epochs(samples)
        frame_starts = np.rint(np.arange(15) * RATE / FRAME_RATE).astype(int)
        for epoch in epochs:
            starts = frame_starts[frame_starts + epoch + TAPS[-1, -1] < samples.size]
            taps = samples[starts[:, None, None] + epoch + TAPS[None, :, :]]
            bins, exact = self.peak_scores(taps, self.exact)
            aliases = np.arange(ALIASES.size)
            if gated:
                useful = exact >= DETECTION_MARGIN
                if winner is not None:
                    useful &= exact > winner.margin
                aliases = aliases[useful]
                if aliases.size == 0:
                    continue
            _, rolled = self.peak_scores(taps, self.rolled[aliases])
            rolled_aliases += aliases.size
            margins = exact[aliases] - rolled
            best = int(np.argmax(margins))
            margin = float(margins[best])
            if margin >= DETECTION_MARGIN and (winner is None or margin > winner.margin):
                alias_index = aliases[best]
                alias = int(ALIASES[alias_index])
                cfo_bin = int(bins[alias_index])
                cfo_hz = float(CFO_HZ[cfo_bin])
                winner = Detection(
                    int(epoch),
                    alias,
                    cfo_bin,
                    cfo_hz,
                    cfo_hz + alias * CFO_PERIOD_HZ,
                    margin,
                )
        return Search(
            winner,
            len(epochs),
            len(epochs) * ALIASES.size * FFT_SIZE,
            int(rolled_aliases) * FFT_SIZE,
        )


@dataclass(frozen=True)
class Probe:
    sequence: int
    receiver: int
    iq_sha256: str
    samples: np.ndarray
    bank: PilotSearch


def phase_randomized_null(samples: np.ndarray) -> np.ndarray:
    rng = np.random.default_rng(NULL_SEED)
    phase = rng.uniform(-np.pi, np.pi, len(samples))
    return np.fft.ifft(np.abs(np.fft.fft(samples)) * np.exp(1j * phase))


def measure(probes: list[Probe]) -> tuple[dict, list[dict]]:
    for gated in (False, True):
        probes[0].bank.search(probes[0].samples, gated=gated)

    elapsed: dict[bool, list[float]] = {False: [], True: []}
    outcomes: dict[bool, list[Search]] = {}
    for repeat in range(REPEATS):
        for gated in (False, True) if repeat % 2 == 0 else (True, False):
            start = time.perf_counter()
            result = [p.bank.search(p.samples, gated=gated) for p in probes]
            elapsed[gated].append(time.perf_counter() - start)
            if gated in outcomes and outcomes[gated] != result:
                raise ValueError("pilot decisions changed across repeated identical inputs")
            outcomes[gated] = result

    control, candidate = outcomes[False], outcomes[True]
    pairs = list(zip(control, candidate, strict=True))
    both = [(a.winner, b.winner) for a, b in pairs if a.winner and b.winner]
    metrics = {
        "windows": len(probes),
        "complex_samples": sum(len(p.samples) for p in probes),
        "control_s": median(elapsed[False]),
        "candidate_s": median(elapsed[True]),
        "control_repeats_s": elapsed[False],
        "candidate_repeats_s": elapsed[True],
        "control_positive": sum(a.winner is not None for a in control),
        "candidate_positive": sum(b.winner is not None for b in candidate),
        "control_negative": sum(a.winner is None for a in control),
        "missed_detections": sum(a.winner is not None and b.winner is None for a, b in pairs),
        "false_promotions": sum(a.winner is None and b.winner is not None for a, b in pairs),
        "changed_winners": sum(
            (a.epoch_sample, a.alias, a.cfo_bin) != (b.epoch_sample, b.alias, b.cfo_bin)
            for a, b in both
        ),
        "changed_cfo": sum(a.absolute_cfo_hz != b.absolute_cfo_hz for a, b in both),
        "max_absolute_cfo_change_hz": max(
            (abs(a.absolute_cfo_hz - b.absolute_cfo_hz) for a, b in both),
            default=0.0,
        ),
        "max_margin_change": max((abs(a.margin - b.margin) for a, b in both), default=0.0),
        "control_epochs": sum(a.epochs for a in control),
        "candidate_epochs": sum(b.epochs for b in candidate),
        "control_exact_fft_cells": sum(a.exact_fft_cells for a in control),
        "candidate_exact_fft_cells": sum(b.exact_fft_cells for b in candidate),
        "control_rolled_fft_cells": sum(a.rolled_fft_cells for a in control),
        "candidate_rolled_fft_cells": sum(b.rolled_fft_cells for b in candidate),
    }
    evidence = [
        dict(
            sequence=p.sequence,
            receiver=p.receiver,
            iq_sha256=p.iq_sha256,
            control=asdict(a),
            candidate=asdict(b),
        )
        for p, (a, b) in zip(probes, pairs, strict=True)
    ]
    return metrics, evidence


def run(case: dict, work_dir: Path) -> dict:
    from tools.pipeline_eval.variants.iq_stream import IQReadError, load_windows

    if case.get("panel") not in {"DS26", "DS29"}:
        return {
            "status": "unavailable",
            "boundary": BOUNDARY,
            "metrics": {},
            "reason": "requires original dual-receiver roof IQ",
        }
    try:
        windows = load_windows(case, sequences=(0, 1))
    except IQReadError as exc:
        return {"status": "unavailable", "boundary": BOUNDARY, "metrics": {}, "reason": str(exc)}

    probes = []
    banks = {}
    for window in windows:
        edge = window.target.get("edge")
        if (
            edge not in {"lower", "upper"}
            or window.sample_rate_hz != RATE
            or window.samples.shape != (WINDOW_SAMPLES, 2, 2)
            or len(window.receiver_ids) != 2
        ):
            return {
                "status": "unavailable",
                "boundary": BOUNDARY,
                "metrics": {},
                "reason": "requires Qin lower/upper 10 Msps dual-receiver 20 ms IQ",
            }
        if edge not in banks:
            banks[edge] = PilotSearch(edge)
        for index, receiver_id in enumerate(window.receiver_ids):
            iq = window.samples[:, index, :].astype(np.float64)
            samples = iq[:, 0] + 1j * iq[:, 1]
            probes.append(
                Probe(window.sequence, receiver_id, window.iq_sha256, samples, banks[edge])
            )

    real, evidence = measure(probes)
    source = probes[0]
    null = Probe(
        source.sequence,
        source.receiver,
        source.iq_sha256,
        phase_randomized_null(source.samples),
        source.bank,
    )
    null_metrics, null_evidence = measure([null])
    work_dir.joinpath("waveform-comparison.json").write_text(
        json.dumps(
            {"real": evidence, "phase_randomized_null": null_evidence}, indent=2, allow_nan=False
        )
        + "\n",
    )
    metrics = dict(real, **{f"null_{name}": value for name, value in null_metrics.items()})
    return {"status": "ok", "boundary": BOUNDARY, "metrics": metrics}
