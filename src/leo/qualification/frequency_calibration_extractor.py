"""Bounded WP11 blind-pilot calibration extractor and evidence product."""

from __future__ import annotations

from typing import Protocol

import numpy as np
import numpy.typing as npt

from leo.pipeline import OutputSink, ProductRole, ProductSpec, PublishedProduct
from leo.qualification.frequency_calibration import (
    CANDIDATE_SCORE_THRESHOLD,
    EXTRACTOR_CONFIG_DIGEST,
    EXTRACTOR_IMPLEMENTATION,
    RESIDUAL_SEARCH_HALF_WIDTH_HZ,
    SAMPLE_COUNT,
    SAMPLE_RATE_HZ,
    TEMPLATE_DIGEST,
    WINDOW_COUNT,
    WINDOW_SAMPLE_COUNT,
    WINDOW_STRIDE_SAMPLES,
    CalibrationCaptureEnvelopeV1,
    CalibrationExtractorReceiptV1,
    CalibrationWindowObservationV1,
    FrequencyCalibrationPlanV1,
)

EXTRACTOR_PRODUCT = ProductSpec(
    kind="wp11-frequency-calibration-extractor",
    schema_version=1,
    role=ProductRole.SCIENTIFIC,
)
_TONE_CENTER_HZ = 820_312.5


class ExactWindowIqReader(Protocol):
    @property
    def sample_rate_hz(self) -> int: ...

    @property
    def center_frequency_hz(self) -> int: ...

    @property
    def sample_count(self) -> int: ...

    @property
    def receiver_ids(self) -> tuple[int, ...]: ...

    def read(
        self,
        sample_start: int,
        sample_count: int,
        *,
        receiver_ids: tuple[int, ...] | None = None,
    ) -> npt.NDArray[np.int16]: ...


class BlindPilotCalibrationExtractor:
    """Read only the frozen 10% exposure windows; peak memory is one window."""

    def extract(
        self,
        *,
        plan: FrequencyCalibrationPlanV1,
        capture: CalibrationCaptureEnvelopeV1,
        reader: ExactWindowIqReader,
    ) -> CalibrationExtractorReceiptV1:
        if (
            reader.sample_rate_hz != SAMPLE_RATE_HZ
            or reader.center_frequency_hz != plan.center_frequency_hz
            or reader.sample_count != SAMPLE_COUNT
            or reader.receiver_ids != (1,)
        ):
            raise ValueError("IQ reader does not expose exact frozen WP11 geometry")
        observations: list[CalibrationWindowObservationV1] = []
        for index in range(WINDOW_COUNT):
            sample_start = index * WINDOW_STRIDE_SAMPLES
            values = reader.read(
                sample_start,
                WINDOW_SAMPLE_COUNT,
                receiver_ids=(1,),
            )
            if values.shape != (WINDOW_SAMPLE_COUNT, 1, 2) or values.dtype != np.dtype("<i2"):
                raise ValueError("IQ reader returned wrong CI16 window geometry")
            score, offset_hz = _blind_pair_score(values[:, 0, :])
            candidate = score >= CANDIDATE_SCORE_THRESHOLD
            observations.append(
                CalibrationWindowObservationV1(
                    observation_id=f"{capture.manifest.session_id}:{capture.stream_id}:{index:03d}",
                    window_index=index,
                    sample_start=sample_start,
                    decision="candidate" if candidate else "no_candidate",
                    candidate_score=score,
                    candidate_offset_hz=offset_hz if candidate else None,
                )
            )
        stream = capture.manifest.streams[0]
        return CalibrationExtractorReceiptV1.create(
            envelope_digest=capture.envelope_digest,
            recording_uri=capture.recording_uri,
            manifest_digest=capture.manifest_digest,
            session_id=capture.manifest.session_id,
            stream_id=capture.stream_id,
            radio_id=stream.radio.radio_id,
            radio_serial=stream.radio.serial,
            physical_receiver_id=capture.physical_receiver_id,
            hardware_epoch_id=capture.hardware_epoch_id,
            profile_revision_digest=plan.profile_revision_digest,
            extractor_implementation=EXTRACTOR_IMPLEMENTATION,
            extractor_config_digest=EXTRACTOR_CONFIG_DIGEST,
            template_digest=TEMPLATE_DIGEST,
            git_revision=plan.extractor_git_revision,
            source_tree_digest=plan.extractor_source_tree_digest,
            executable_digest=plan.extractor_executable_digest,
            observations=tuple(observations),
        )

    def publish(
        self,
        *,
        plan: FrequencyCalibrationPlanV1,
        capture: CalibrationCaptureEnvelopeV1,
        reader: ExactWindowIqReader,
        sink: OutputSink,
    ) -> tuple[CalibrationExtractorReceiptV1, PublishedProduct]:
        receipt = self.extract(plan=plan, capture=capture, reader=reader)
        published = sink.publish_json(EXTRACTOR_PRODUCT, receipt.model_dump(mode="json"))
        return receipt, published


def _blind_pair_score(ci16: npt.NDArray[np.int16]) -> tuple[float, float]:
    complex_values = ci16[:, 0].astype(np.float64) + 1j * ci16[:, 1].astype(np.float64)
    complex_values -= np.mean(complex_values)
    power = np.abs(np.fft.fftshift(np.fft.fft(complex_values))) ** 2
    median_power = float(np.median(power))
    if not math_is_positive_finite(median_power):
        return 0.0, 0.0
    frequencies = np.fft.fftshift(np.fft.fftfreq(WINDOW_SAMPLE_COUNT, 1 / SAMPLE_RATE_HZ))
    bin_hz = SAMPLE_RATE_HZ / WINDOW_SAMPLE_COUNT
    maximum_shift = int(RESIDUAL_SEARCH_HALF_WIDTH_HZ / bin_hz)
    lower_base = int(np.argmin(np.abs(frequencies + _TONE_CENTER_HZ)))
    upper_base = int(np.argmin(np.abs(frequencies - _TONE_CENTER_HZ)))
    shifts = np.arange(-maximum_shift, maximum_shift + 1)
    valid = (
        (lower_base + shifts >= 0)
        & (upper_base + shifts >= 0)
        & (lower_base + shifts < power.size)
        & (upper_base + shifts < power.size)
    )
    shifts = shifts[valid]
    pair_power = (power[lower_base + shifts] + power[upper_base + shifts]) / 2
    best = int(np.argmax(pair_power))
    score = float(pair_power[best] / median_power)
    offset_hz = float(shifts[best] * bin_hz)
    if not math_is_positive_finite(score):
        return 0.0, 0.0
    return score, offset_hz


def math_is_positive_finite(value: float) -> bool:
    return bool(np.isfinite(value) and value > 0)
