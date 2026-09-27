"""Report-owned exact decision-only early-exit scanner prototype.

The full ``analyze_glrt64_dwell`` contract deliberately remains untouched.  This
module implements only the narrower ``DwellDetection`` result returned by
``detect_first_glrt64`` and stops after the complete confirming probe.
"""

from __future__ import annotations

import numpy as np

from leo.analysis.starlink import ReceiverFrequencyCalibration, StarlinkEdge, SymbolwiseAcquisitionConfig
from leo.analysis.starlink.acquisition import acquire_symbolwise
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
from leo.scanner.detector import (
    DwellDetection,
    STANDARD_SCANNER_CANDIDATE_CFO_SEPARATION_HZ,
    STANDARD_SCANNER_CANDIDATE_EPOCH_SEPARATION_SAMPLES,
    _CONFIRMATION_CFO_GATE_HZ,
    _ZERO_CALIBRATION_SHA256,
)
from leo.scanner.models import Glrt64FirstDetection, ScannerConfiguration


def detect_first_glrt64_early(
    samples: np.ndarray,
    configuration: ScannerConfiguration,
    *,
    edge: StarlinkEdge | str,
) -> DwellDetection:
    """Return the oracle decision after finishing the confirming probe.

    Receiver order, candidate order, hit sorting, history association, gates,
    and reductions intentionally mirror ``leo.scanner.detector``.  No work in a
    probe is skipped: both receivers and every retained candidate finish before
    this function considers an early return.
    """

    values = np.asarray(samples)
    expected = (configuration.dwell_samples, len(configuration.receiver_ids))
    if values.ndim != 2 or values.shape != expected:
        raise ValueError(f"scanner dwell has shape {values.shape}, expected {expected}")
    acquisition_config = SymbolwiseAcquisitionConfig(
        maximum_probe_samples=configuration.probe_samples,
        retained_candidate_count=configuration.maximum_acquisition_candidates,
        candidate_epoch_separation_samples=(
            STANDARD_SCANNER_CANDIDATE_EPOCH_SEPARATION_SAMPLES
        ),
        candidate_cfo_separation_hz=STANDARD_SCANNER_CANDIDATE_CFO_SEPARATION_HZ,
    )
    best: float | None = None
    history: dict[int, list[Glrt64FirstDetection]] = {
        receiver_id: [] for receiver_id in configuration.receiver_ids
    }
    for probe_index in range(configuration.scheduled_probe_count):
        start = probe_index * configuration.probe_stride_samples
        stop = start + configuration.probe_samples
        hits: list[Glrt64FirstDetection] = []
        for column, receiver_id in enumerate(configuration.receiver_ids):
            probe = np.ascontiguousarray(values[start:stop, column], dtype=np.complex128)
            calibration = ReceiverFrequencyCalibration(
                receiver_id=str(receiver_id),
                center_hz=0.0,
                calibration_sha256=_ZERO_CALIBRATION_SHA256,
            )
            acquired = acquire_symbolwise(
                probe,
                configuration.sample_rate_hz,
                calibration,
                edge=edge,
                config=acquisition_config,
            )
            for candidate in acquired.candidates[: configuration.maximum_acquisition_candidates]:
                score = conditioned_glrt64_score(
                    probe,
                    configuration.sample_rate_hz,
                    epoch_sample=candidate.refined_epoch_sample,
                    acquired_cfo_hz=candidate.absolute_cfo_hz,
                    edge=edge,
                )
                best = score.margin if best is None else max(best, score.margin)
                if score.margin >= configuration.glrt64_margin_gate:
                    hits.append(
                        Glrt64FirstDetection(
                            receiver_id=receiver_id,
                            probe_index=probe_index,
                            probe_start_ms=probe_index * configuration.probe_stride_ms,
                            candidate_rank=candidate.rank,
                            epoch_sample=candidate.refined_epoch_sample,
                            acquired_cfo_hz=candidate.absolute_cfo_hz,
                            residual_cfo_hz=score.residual_cfo_hz,
                            tracking_cfo_hz=score.tracking_cfo_hz,
                            exact_score=score.exact_score,
                            control_score=score.control_score or 0.0,
                            margin=score.margin,
                        )
                    )
        first_detection: Glrt64FirstDetection | None = None
        for hit in sorted(hits, key=lambda item: (item.receiver_id, -item.margin)):
            compatible = tuple(
                prior
                for prior in history[hit.receiver_id]
                if hit.probe_start_ms - prior.probe_start_ms >= configuration.probe_ms
                and abs(hit.tracking_cfo_hz - prior.tracking_cfo_hz)
                <= _CONFIRMATION_CFO_GATE_HZ
            )
            if compatible and first_detection is None:
                first_detection = min(
                    compatible,
                    key=lambda item: (item.probe_index, -item.margin),
                )
        if first_detection is not None:
            return DwellDetection(
                first=first_detection,
                best_margin=best,
                reason=(
                    "two same-receiver non-overlapping 20 ms GLRT-64 probes "
                    "passed the margin gate within 8 kHz CFO"
                ),
            )
        for hit in hits:
            history[hit.receiver_id].append(hit)
    return DwellDetection(
        first=None,
        best_margin=best,
        reason=(
            f"all {configuration.scheduled_probe_count} overlapping "
            f"{configuration.probe_ms} ms probes completed without a confirmed "
            "same-receiver CFO-consistent pair"
        ),
    )
