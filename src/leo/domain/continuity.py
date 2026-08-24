"""Counter-authoritative IQ continuity validation shared across components."""

from __future__ import annotations

from leo.contracts.radio import IqBlockMetadataV1, IqBlockMetadataV2
from leo.contracts.states import ContinuityStatus

_MAX_COUNTER = (1 << 64) - 1


class ContinuityValidationError(RuntimeError):
    """IQ metadata cannot form one unambiguous counter/sequence chain."""


class ContinuityChainValidator:
    """Validate one capture generation and derive exact gap classifications.

    A new instance (or ``reset``) establishes a new capture baseline. It never
    joins independent captures and never infers continuity from host time.
    """

    def __init__(
        self,
        *,
        require_metadata: bool = True,
        require_generation: bool | None = None,
        validate_declared: bool = False,
    ) -> None:
        self.require_metadata = require_metadata
        self.require_generation = require_generation
        self.validate_declared = validate_declared
        self.reset()

    def reset(self) -> None:
        self._previous: IqBlockMetadataV1 | None = None
        self._generation: str | None = None
        self._validated_refills = 0
        self._metadata_complete = True
        self.gap_count = 0
        self.missing_sample_count = 0
        self.overflow_count = 0

    @property
    def validated(self) -> bool:
        return self._validated_refills > 0 and self._metadata_complete

    @property
    def stream_generation(self) -> str | None:
        return self._generation

    def observe(self, metadata: IqBlockMetadataV1) -> IqBlockMetadataV1:
        counter = metadata.device_sample_counter
        sequence = metadata.source_sequence
        generation = getattr(metadata, "stream_generation", None)
        generation_required = (
            isinstance(metadata, IqBlockMetadataV2)
            if self.require_generation is None
            else self.require_generation
        )
        if (counter is None) != (sequence is None):
            if self.require_metadata or isinstance(metadata, IqBlockMetadataV2):
                raise ContinuityValidationError(
                    "device counter and source sequence must appear together"
                )
            # Published V1 metadata allowed either field independently. Such a
            # block stays readable/writable, but it breaks the validated chain
            # and can never support a sample-loss-observable claim.
            self._metadata_complete = False
            self._previous = None
            self._generation = None
            return metadata
        if counter is None:
            self._metadata_complete = False
            if self.require_metadata:
                raise ContinuityValidationError(
                    "counter-authoritative capture requires device counter and source sequence"
                )
            if generation_required and generation is None:
                raise ContinuityValidationError("capture metadata omits stream generation")
            self._previous = metadata
            return metadata
        assert sequence is not None
        if counter > _MAX_COUNTER or sequence > _MAX_COUNTER:
            raise ContinuityValidationError("capture counter or sequence exceeds uint64")
        if generation_required and generation is None:
            raise ContinuityValidationError("capture metadata omits stream generation")

        previous = self._previous
        if previous is None:
            self._generation = generation
            status = (
                ContinuityStatus.OVERFLOW
                if metadata.overflow_observed
                else ContinuityStatus.CONTIGUOUS
            )
            missing = 0
        else:
            if metadata.radio_id != previous.radio_id:
                raise ContinuityValidationError("radio identity changed within capture chain")
            if metadata.receiver_ids != previous.receiver_ids:
                raise ContinuityValidationError("receiver geometry changed within capture chain")
            if generation != self._generation:
                raise ContinuityValidationError(
                    "metadata stream generation changed without validator reset"
                )
            assert previous.device_sample_counter is not None
            assert previous.source_sequence is not None
            expected_counter = previous.device_sample_counter + previous.sample_count
            if expected_counter > _MAX_COUNTER:
                raise ContinuityValidationError("device sample counter wrapped within capture")
            if counter < expected_counter:
                raise ContinuityValidationError(
                    "device sample counter duplicated, regressed, or overlapped: "
                    f"expected {expected_counter}, got {counter}"
                )
            missing = counter - expected_counter
            if isinstance(metadata, IqBlockMetadataV2):
                if missing % previous.sample_count:
                    raise ContinuityValidationError(
                        "counter gap is not an integer number of fixed refills"
                    )
                skipped_refills = missing // previous.sample_count
            else:
                # Historical V1 sources did not define sequence advancement
                # through gaps; retain their one-returned-block semantics.
                skipped_refills = 0
            expected_sequence = previous.source_sequence + 1 + skipped_refills
            if expected_sequence > _MAX_COUNTER:
                raise ContinuityValidationError("source sequence wrapped within capture")
            if sequence != expected_sequence:
                relation = "regressed/duplicated" if sequence < expected_sequence else "jumped"
                raise ContinuityValidationError(
                    f"source sequence {relation}: expected {expected_sequence}, got {sequence}"
                )
            status = (
                ContinuityStatus.GAP_BEFORE
                if missing
                else (
                    ContinuityStatus.OVERFLOW
                    if metadata.overflow_observed
                    else ContinuityStatus.CONTIGUOUS
                )
            )

        if (
            self.validate_declared
            and metadata.continuity is not ContinuityStatus.UNKNOWN
            and (metadata.continuity is not status or metadata.missing_samples_before != missing)
        ):
            raise ContinuityValidationError(
                "declared continuity disagrees with counter-authoritative classification"
            )
        document = metadata.model_dump(mode="json")
        document.update(
            {
                "continuity": status.value,
                "missing_samples_before": missing,
            }
        )
        validated = type(metadata).model_validate(document)
        self._previous = validated
        self._validated_refills += 1
        if status is ContinuityStatus.GAP_BEFORE:
            self.gap_count += 1
            self.missing_sample_count += missing
        if metadata.overflow_observed:
            self.overflow_count += 1
        return validated
