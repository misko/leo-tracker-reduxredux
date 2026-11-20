"""Evaluate the same blind Qin pilot-bank grid with short frame FFTs."""

from __future__ import annotations

import json
import time
from hashlib import sha256
from pathlib import Path
from statistics import median
from types import ModuleType

import numpy as np

BOUNDARY = (
    "Decoded 20 ms IQ through blind Qin folded proposals and full pilot-bank GLRT. "
    "Archive reads, decoding and bank setup are outside the paired timings."
)
REPEATS = 6
SCORE_TOLERANCE = 1e-12
ERROR_KEYS = (
    "wrapped_cfo_error_hz",
    "wrapped_phase_error_us",
    "exact_error",
    "control_error",
    "margin_error",
)


def summed_grid_power(symbols: np.ndarray, size: int) -> np.ndarray:
    """Sum incoherent frame power on the requested DFT grid."""
    count = symbols.shape[-1]
    short_size = 1 << (2 * count - 2).bit_length()
    short = np.fft.fft(symbols, n=short_size, axis=-1)
    correlation = np.fft.ifft(np.sum(np.abs(short) ** 2, axis=-2), axis=-1)
    # The unaliased positive lags determine the full Hermitian autocorrelation.
    return np.fft.hfft(correlation[..., :count], n=size, axis=-1)


class BatchedPilotBank:
    """Share the reference proposals and precompute the alias-weighted templates."""

    def __init__(self, bank, reference: ModuleType):
        self.coarse = bank.coarse
        self.reference = reference
        weighted = bank.reference[:, None, :, :] * reference.ALIAS_ROTATION[None, :, None, :]
        symbol_count, taps_per_symbol = reference.TAPS.shape
        self.kernel = np.ascontiguousarray(
            weighted.reshape(-1, symbol_count, taps_per_symbol).transpose(1, 2, 0)
        )
        self.frame_starts = np.rint(np.arange(15) * reference.RATE / 750).astype(int)
        self.refine = np.arange(-reference.REFINE_SAMPLES, reference.REFINE_SAMPLES + 1)
        self.suppress = np.arange(-12, 13)

    def search(self, samples: np.ndarray, counter: int) -> dict:
        ref = self.reference
        proposal = self.coarse(samples)
        epochs = set()
        for _ in range(ref.PROPOSALS):
            peak = int(proposal.argmax())
            if not np.isfinite(proposal[peak]):
                break
            epochs.update((peak + self.refine) % ref.FRAME_SAMPLES)
            proposal[(peak + self.suppress) % ref.FRAME_SAMPLES] = -np.inf

        block_size = ref.TAPS.size
        first_tap = ref.TAPS[0, 0]
        blocks = np.lib.stride_tricks.sliding_window_view(samples, block_size)
        best = None
        tested_epochs = 0
        for epoch in sorted(epochs):
            starts = self.frame_starts + epoch + first_tap
            starts = starts[starts < len(blocks)]
            if starts.size < 2:
                continue
            taps = blocks[starts].reshape(starts.size, *ref.TAPS.shape)
            products = taps.swapaxes(0, 1) @ self.kernel
            symbols = products.transpose(2, 1, 0).reshape(2, ref.ALIASES.size, starts.size, -1)
            ceiling = np.sum(np.sum(np.abs(symbols), axis=-1) ** 2, axis=-1)
            power = summed_grid_power(symbols, ref.FFT_SIZE)
            normalized = np.divide(
                power, ceiling[..., None], out=np.zeros_like(power), where=ceiling[..., None] > 0
            )
            bins = np.argmax(normalized[0], axis=1)
            exact = normalized[0, np.arange(ref.ALIASES.size), bins]
            controls = np.max(normalized[1], axis=1)
            margins = exact - controls
            alias = int(np.argmax(margins))
            tested_epochs += 1
            if best is None or margins[alias] > best["margin"]:
                cfo = ref.BINS_HZ[bins[alias]]
                best = {
                    "epoch_sample": int(epoch),
                    "phase_us": float(ref.phase_at(epoch, counter)),
                    "cfo_hz": float(cfo),
                    "alias_cfo_hz": float(cfo + ref.ALIASES[alias] * ref.FREQUENCY_PERIOD),
                    "exact": float(exact[alias]),
                    "control": float(controls[alias]),
                    "margin": float(margins[alias]),
                    "frames": int(starts.size),
                    "passed": bool(margins[alias] >= ref.MARGIN),
                }
        return {
            "winner": best,
            "tested_epochs": tested_epochs,
            "scored_epoch_alias_cfo_cells": tested_epochs * 2 * ref.ALIASES.size * ref.FFT_SIZE,
        }


def _compare(control: dict, candidate: dict, reference: ModuleType) -> dict:
    first, second = control["winner"], candidate["winner"]
    result = {
        "control_passed": bool(first and first["passed"]),
        "candidate_passed": bool(second and second["passed"]),
        "work_equal": all(
            control[key] == candidate[key]
            for key in ("tested_epochs", "scored_epoch_alias_cfo_cells")
        ),
        "peak_equal": first is second,
        **dict.fromkeys(ERROR_KEYS, 0.0),
    }
    if first is not None and second is not None:
        result.update(
            peak_equal=all(
                first[key] == second[key]
                for key in ("epoch_sample", "cfo_hz", "alias_cfo_hz", "frames")
            ),
            wrapped_cfo_error_hz=abs(
                reference.wrap(first["cfo_hz"] - second["cfo_hz"], reference.FREQUENCY_PERIOD)
            ),
            wrapped_phase_error_us=abs(
                reference.wrap(first["phase_us"] - second["phase_us"], reference.PHASE_PERIOD_US)
            ),
            **{
                f"{key}_error": abs(first[key] - second[key])
                for key in ("exact", "control", "margin")
            },
        )
    return result


def run(case: dict, work_dir: Path) -> dict:
    from tools.pipeline_eval.variants.iq_stream import IQReadError, load_windows

    try:
        from tools.pipeline_eval.reference import waveform as reference

        windows = load_windows(case, sequences=(0, 1))
        for window in windows:
            if (
                window.sample_rate_hz != reference.RATE
                or len(window.samples) != reference.PROBE_SAMPLES
                or window.target.get("edge") not in ("lower", "upper")
            ):
                raise IQReadError("The waveform control requires 20 ms windows at 10 Msps.")
    except (ImportError, IQReadError) as exc:
        return {"status": "unavailable", "reason": str(exc), "boundary": BOUNDARY, "metrics": {}}

    banks_by_edge = {}
    scans = []
    counter_zero = windows[0].acquisition["sample_start"]
    for window in windows:
        edge = window.target["edge"]
        counter = window.acquisition["sample_start"] - counter_zero
        if edge not in banks_by_edge:
            control = reference.PilotBank(edge)
            banks_by_edge[edge] = control, BatchedPilotBank(control, reference)
        for index, receiver in enumerate(window.receiver_ids):
            values = window.samples[:, index, :]
            samples = values[:, 0].astype(float) + 1j * values[:, 1]
            scans.append((window, receiver, banks_by_edge[edge], samples, counter))

    times = {"control": [], "candidate": []}
    measurements = []
    for repeat in range(REPEATS):
        outputs = [None, None]
        order = (0, 1) if repeat % 2 == 0 else (1, 0)
        for arm in order:
            started = time.perf_counter()
            outputs[arm] = [
                banks[arm].search(samples, counter) for _, _, banks, samples, counter in scans
            ]
            times[("control", "candidate")[arm]].append(time.perf_counter() - started)
        measurements.append([_compare(a, b, reference) for a, b in zip(*outputs, strict=True)])

    comparisons = [row for repetition in measurements for row in repetition]
    first = measurements[0]
    control_positive = sum(row["control_passed"] for row in first)
    candidate_positive = sum(row["candidate_passed"] for row in first)
    document = {
        "waveform_control_sha256": sha256(Path(reference.__file__).read_bytes()).hexdigest(),
        "phase_counter_zero": counter_zero,
        "scans": [
            {
                "sequence": window.sequence,
                "iq_sha256": window.iq_sha256,
                "target_id": window.target_id,
                "receiver": receiver,
                "counter": counter,
                "control": control,
                "candidate": candidate,
            }
            for (window, receiver, _, _, counter), control, candidate in zip(
                scans, *outputs, strict=True
            )
        ],
        "comparisons": measurements,
    }
    (work_dir / "waveform-parity.json").write_text(json.dumps(document, indent=2, allow_nan=False))
    return {
        "status": "ok",
        "boundary": BOUNDARY,
        "metrics": {
            "windows": len(windows),
            "receiver_windows": len(scans),
            "complex_samples": sum(samples.size for _, _, _, samples, _ in scans),
            "paired_repeats": REPEATS,
            "control_s": median(times["control"]),
            "candidate_s": median(times["candidate"]),
            "control_s_repeats": times["control"],
            "candidate_s_repeats": times["candidate"],
            "control_positives": control_positive,
            "control_negatives": len(scans) - control_positive,
            "candidate_positives": candidate_positive,
            "candidate_negatives": len(scans) - candidate_positive,
            "decision_disagreements": sum(
                row["control_passed"] != row["candidate_passed"] for row in comparisons
            ),
            "peak_disagreements": sum(not row["peak_equal"] for row in comparisons),
            "work_disagreements": sum(not row["work_equal"] for row in comparisons),
            "score_tolerance_violations": sum(
                max(row[key] for key in ERROR_KEYS[2:]) > SCORE_TOLERANCE for row in comparisons
            ),
            "cells": sum(row["scored_epoch_alias_cfo_cells"] for row in outputs[0]),
            "score_tolerance": SCORE_TOLERANCE,
            **{f"max_{key}": max(row[key] for row in comparisons) for key in ERROR_KEYS},
        },
    }
