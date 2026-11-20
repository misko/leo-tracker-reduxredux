"""Stop fractional GLRT scoring at a supported capture's original rank prefix."""

from contextlib import contextmanager
from unittest.mock import patch

GATE = 0.025
PRODUCER_FILES = {
    "leo/scanner/fast_scan_detector.py": (
        "3a34612a9ebb4384062d69457b43c4a072ae2b5a40b01f3364ff39292eb09e83"
    ),
    "leo/analysis/starlink/fast_scan_scores.py": (
        "fbefc411d1ec407c90a39a4ea2f823a62b11683c2d0877bdbd1c717acfec12aa"
    ),
}


def prefix(rows, passes, accepted):
    """Keep original rank order, including every rejection before the last pass."""
    remaining = passes
    for row in rows:
        yield row
        if accepted(row):
            remaining -= 1
            if remaining == 0:
                return


def fractional_pass(response):
    value = response.fractional_margin
    return value is not None and value >= GATE


class GateStop:
    def __init__(self, detector, passes):
        if passes is not None and (type(passes) is not int or passes not in (1, 2)):
            raise ValueError("fractional gate stop accepts first or second pass")
        self.detector = detector
        self.passes = passes
        self.full = detector._evaluate_probe
        self.attempts = []

    def responses(self, probe, configuration, edge, retained):
        detector = self.detector
        rate = configuration.sample_rate_hz
        epochs = tuple(row.refined_epoch_sample for row in retained)
        cfos = tuple(row.absolute_cfo_hz for row in retained)
        scores = detector.conditioned_glrt64_scores(
            probe, rate, epoch_samples=epochs, acquired_cfo_hz=cfos, edge=edge
        )
        for index, (row, score) in enumerate(zip(retained, scores, strict=True)):
            arg = slice(index, index + 1)
            (fractional,) = detector.refine_glrt64_epochs(
                probe,
                rate,
                integer_epoch_samples=epochs[arg],
                acquired_cfo_hz=cfos[arg],
                edge=edge,
                expected_integer_scores=scores[arg],
            )
            yield detector.Glrt64CandidateResponse(
                candidate_rank=row.rank,
                epoch_sample=row.refined_epoch_sample,
                acquired_cfo_hz=row.absolute_cfo_hz,
                residual_cfo_hz=score.residual_cfo_hz,
                tracking_cfo_hz=score.tracking_cfo_hz,
                exact_score=score.exact_score,
                control_score=score.control_score or 0.0,
                margin=score.margin,
                passed_margin_gate=score.margin >= GATE,
                fractional_epoch_status=fractional.status.value,
                fractional_epoch_offset_samples=fractional.fractional_epoch_offset_samples,
                fractional_frame_phase_sample=fractional.fractional_frame_phase_sample,
                fractional_exact_score=fractional.fractional_exact_score,
                fractional_control_score=fractional.fractional_control_score,
                fractional_residual_cfo_hz=fractional.fractional_residual_cfo_hz,
                fractional_tracking_cfo_hz=fractional.fractional_tracking_cfo_hz,
                fractional_margin=fractional.fractional_margin,
            )

    def evaluate(
        self,
        probe,
        configuration,
        calibration,
        *,
        edge,
        acquisition_config,
        receiver_id,
        probe_index,
    ):
        detector = self.detector
        if configuration.scheduled_probe_count != 1 or configuration.glrt64_margin_gate != GATE:
            raise ValueError("gate stop requires the original single-probe capture configuration")
        if self.passes is None:
            result = self.full(
                probe,
                configuration,
                calibration,
                edge=edge,
                acquisition_config=acquisition_config,
                receiver_id=receiver_id,
                probe_index=probe_index,
            )
            available = len(result.candidates)
        else:
            acquired = detector.acquire_symbolwise(
                probe,
                configuration.sample_rate_hz,
                calibration,
                edge=edge,
                config=acquisition_config,
            )
            retained = acquired.candidates[: configuration.maximum_acquisition_candidates]
            available = len(retained)
            responses = tuple(
                prefix(
                    self.responses(probe, configuration, edge, retained),
                    self.passes,
                    fractional_pass,
                )
            )
            # With exactly one scheduled probe there can be no earlier probe for
            # the legacy integer confirmation. The production caller uses only
            # these response rows and the original fractional retry predicate.
            result = detector._ProbeEvaluation(responses, ())
        self.attempts.append((receiver_id, probe_index, available, result.candidates))
        return result

    @contextmanager
    def route(self):
        with patch.object(self.detector, "_evaluate_probe", self.evaluate):
            yield self
