"""Pure fractional GLRT analysis of actual adaptive visits, without sweep aliases."""

from __future__ import annotations

import math
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Annotated, Any, ClassVar, Literal, Protocol, Self, cast

import numpy as np
import numpy.typing as npt
from pydantic import Field, TypeAdapter, field_validator, model_validator

from leo.contracts.digests import Sha256Digest
from leo.contracts.scanner_glrt_frame import U64
from leo.scanner.adaptive_hop import (
    AdaptiveHopReceiptV1,
    AdaptiveHopReceiptV2,
    AdaptiveHopReceiptV3,
    AdaptiveHopReceiptV4,
    AdaptiveHopReceiptV5,
    AdaptiveHopReceiptV6,
    AdaptiveHopReceiptV7,
    AdaptiveHopVisitV1,
    AdaptiveModel,
    SessionId,
)
from leo.scanner.detector import (
    Glrt64CandidateResponse,
    Glrt64DwellConfiguration,
    analyze_glrt64_dwell,
)
from leo.scanner.models import ScanTarget

Finite = Annotated[float, Field(allow_inf_nan=False)]
Nonnegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Rank = Annotated[int, Field(strict=True, ge=0, le=15)]


class AdaptiveHopAnalysisConfigurationV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    analyzer_id: Literal["adaptive-hop-fractional-glrt64-cfo-v1"] = (
        "adaptive-hop-fractional-glrt64-cfo-v1"
    )
    sample_rate_hz: Literal[2_500_000, 5_000_000]
    valid_visit_ms: Literal[120] = 120
    probe_ms: Literal[20] = 20
    probe_stride_ms: Annotated[int, Field(strict=True, ge=10, le=120)] = 10
    glrt64_margin_gate: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 0.025
    maximum_acquisition_candidates: Annotated[int, Field(strict=True, ge=1, le=16)] = 8
    receiver_ids: tuple[Literal[0], Literal[1]] = (0, 1)
    timing_refinement: Literal["circular-five-cell-log-parabola-plus-lanczos16-v1"] = (
        "circular-five-cell-log-parabola-plus-lanczos16-v1"
    )
    decision_score: Literal["fractional-epoch-conditioned-glrt64-v1"] = (
        "fractional-epoch-conditioned-glrt64-v1"
    )

    @field_validator("receiver_ids", mode="before")
    @classmethod
    def _exact_receivers(cls, value: object) -> object:
        if (
            not isinstance(value, (tuple, list))
            or len(value) != 2
            or any(type(item) is not int for item in value)
            or tuple(value) != (0, 1)
        ):
            raise ValueError("adaptive offline analysis requires exact dual-RX identity")
        return value

    @property
    def dwell_samples(self) -> int:
        return self.sample_rate_hz * self.valid_visit_ms // 1000

    @property
    def probe_samples(self) -> int:
        return self.sample_rate_hz * self.probe_ms // 1000

    @property
    def probe_stride_samples(self) -> int:
        return self.sample_rate_hz * self.probe_stride_ms // 1000

    @property
    def scheduled_probe_count(self) -> int:
        return (self.dwell_samples - self.probe_samples) // self.probe_stride_samples + 1

    @property
    def scheduled_probe_counts(self) -> tuple[int, ...]:
        return (len(self.receiver_ids) * self.scheduled_probe_count,)


class DualRx10mAdaptiveHopAnalysisConfigurationV2(AdaptiveHopAnalysisConfigurationV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    analyzer_id: Literal["adaptive-hop-fractional-glrt64-cfo-10m-v1"] = (  # type: ignore[assignment]
        cast(  # type: ignore[assignment]
            Literal["adaptive-hop-fractional-glrt64-cfo-10m-v1"],
            "adaptive-hop-fractional-glrt64-cfo-10m-v1",
        )
    )
    sample_rate_hz: Literal[10_000_000] = 10_000_000  # type: ignore[assignment]


class AdaptiveHopFractionalCandidateV1(AdaptiveModel):
    candidate_rank: Rank
    integer_epoch_sample: Annotated[int, Field(strict=True, ge=0)]
    integer_device_sample_counter: U64
    integer_session_sample: U64
    fractional_epoch_offset_samples: Annotated[float, Field(ge=-2, le=2, allow_inf_nan=False)]
    fractional_time_s: Nonnegative
    acquired_cfo_hz: Finite
    integer_residual_cfo_hz: Finite
    integer_tracking_cfo_hz: Finite
    integer_exact_score: Nonnegative
    integer_control_score: Nonnegative
    integer_margin: Finite
    fractional_residual_cfo_hz: Finite
    fractional_tracking_cfo_hz: Finite
    fractional_exact_score: Nonnegative
    fractional_control_score: Nonnegative
    fractional_margin: Finite
    passed_fractional_margin_gate: bool

    @model_validator(mode="after")
    def _scores_close(self) -> Self:
        for margin, exact, control in (
            (self.integer_margin, self.integer_exact_score, self.integer_control_score),
            (self.fractional_margin, self.fractional_exact_score, self.fractional_control_score),
        ):
            if not math.isclose(margin, exact - control, rel_tol=0, abs_tol=1e-12):
                raise ValueError("adaptive fractional candidate margin does not close")
        return self


class AdaptiveHopUnavailableCandidateV1(AdaptiveModel):
    candidate_rank: Rank
    fractional_epoch_status: Annotated[str, Field(min_length=1, max_length=64)]
    reason: Literal["fractional_incomplete", "outside_retained_interval"]


class AdaptiveHopProbeAnalysisV1(AdaptiveModel):
    receiver_id: Annotated[int, Field(strict=True, ge=0, le=1)]
    probe_index: Annotated[int, Field(strict=True, ge=0, le=10)]
    probe_start_ms: Annotated[int, Field(strict=True, ge=0, le=100)]
    candidate_count: Annotated[int, Field(strict=True, ge=0, le=16)]
    candidates: Annotated[tuple[AdaptiveHopFractionalCandidateV1, ...], Field(max_length=16)]
    unavailable_candidates: Annotated[
        tuple[AdaptiveHopUnavailableCandidateV1, ...], Field(max_length=16)
    ]
    winning_candidate_rank: Rank | None

    @model_validator(mode="after")
    def _inventory_closes(self) -> Self:
        ranks = [c.candidate_rank for c in self.candidates] + [
            c.candidate_rank for c in self.unavailable_candidates
        ]
        winner = max(
            self.candidates, key=lambda c: (c.fractional_margin, -c.candidate_rank), default=None
        )
        if (
            len(ranks) != self.candidate_count
            or len(set(ranks)) != len(ranks)
            or self.winning_candidate_rank != (winner.candidate_rank if winner else None)
        ):
            raise ValueError("adaptive fractional probe candidate inventory or winner differs")
        return self


class AdaptiveHopVisitAnalysisV1(AdaptiveModel):
    """One checkpointable complete visit; no absolute floating epoch or sweep field."""

    _allow_zero_gap: ClassVar[bool] = False
    schema_version: Literal[1] = 1
    kind: Literal["adaptive_hop_fractional_visit_analysis"] = (
        "adaptive_hop_fractional_visit_analysis"
    )
    session_id: SessionId
    input_manifest_sha256: Sha256Digest
    configuration: AdaptiveHopAnalysisConfigurationV1
    policy_generation: U64
    source_origin_counter: U64
    visit_index: Annotated[int, Field(strict=True, ge=0, lt=2500)]
    target_index: Annotated[int, Field(strict=True, ge=0, le=7)]
    target: ScanTarget
    invalid_start_counter: U64
    valid_start_counter: U64
    valid_end_counter: U64
    actual_if_center_hz: Annotated[int, Field(strict=True, gt=0)]
    probes: Annotated[tuple[AdaptiveHopProbeAnalysisV1, ...], Field(min_length=2, max_length=22)]
    phase_continuity_across_retunes: Literal[False] = False

    @model_validator(mode="after")
    def _source_and_coverage_close(self) -> Self:
        cfg = self.configuration
        dwell_samples = self.valid_end_counter - self.valid_start_counter
        scheduled_probe_count = (
            cfg.scheduled_probe_count(dwell_samples)
            if isinstance(cfg, VariableDwellAnalysisConfigurationV5)
            else cfg.scheduled_probe_count
        )
        keys = [(p.probe_index, p.receiver_id) for p in self.probes]
        expected = [(p, rx) for p in range(scheduled_probe_count) for rx in cfg.receiver_ids]
        if (
            keys != expected
            or not self.policy_generation
            or (
                not isinstance(cfg, VariableDwellAnalysisConfigurationV5)
                and dwell_samples != cfg.dwell_samples
            )
            or not self.source_origin_counter
            <= self.invalid_start_counter
            <= self.valid_start_counter
            or (self.invalid_start_counter == self.valid_start_counter and not self._allow_zero_gap)
            or self.actual_if_center_hz != self.target.if_center_hz
            or self.target.channel != self.target_index % 4 + 1
            or self.target.edge != ("lower" if self.target_index < 4 else "upper")
        ):
            raise ValueError("adaptive fractional visit source or probe inventory differs")
        for probe in self.probes:
            if (
                probe.probe_start_ms != probe.probe_index * cfg.probe_stride_ms
                or probe.candidate_count > cfg.maximum_acquisition_candidates
            ):
                raise ValueError("adaptive probe differs from numerical configuration")
            for candidate in probe.candidates:
                local = (
                    probe.probe_start_ms * cfg.sample_rate_hz // 1000
                    + candidate.integer_epoch_sample
                )
                anchor = self.valid_start_counter + local
                relative = anchor - self.source_origin_counter
                offset = candidate.fractional_epoch_offset_samples
                if (
                    not 0 <= candidate.integer_epoch_sample < cfg.probe_samples
                    or not 0 <= local + offset < dwell_samples
                    or candidate.integer_device_sample_counter != anchor
                    or candidate.integer_session_sample != relative
                    or candidate.fractional_time_s != (relative + offset) / cfg.sample_rate_hz
                    or candidate.passed_fractional_margin_gate
                    != (candidate.fractional_margin >= cfg.glrt64_margin_gate)
                ):
                    raise ValueError("adaptive fractional candidate differs from retained source")
        return self


class DualRx10mAdaptiveHopVisitAnalysisV2(AdaptiveHopVisitAnalysisV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    configuration: DualRx10mAdaptiveHopAnalysisConfigurationV2  # type: ignore[assignment]


class Feature103AnalysisConfigurationV3(AdaptiveHopAnalysisConfigurationV1):
    schema_version: Literal[3] = 3  # type: ignore[assignment]
    sample_rate_hz: Literal[2_500_000, 5_000_000, 10_000_000]  # type: ignore[assignment]


class Feature103VisitAnalysisV3(AdaptiveHopVisitAnalysisV1):
    schema_version: Literal[3] = 3  # type: ignore[assignment]
    _allow_zero_gap: ClassVar[bool] = True
    configuration: Feature103AnalysisConfigurationV3  # type: ignore[assignment]


class Feature104AnalysisConfigurationV4(AdaptiveHopAnalysisConfigurationV1):
    schema_version: Literal[4] = 4  # type: ignore[assignment]
    sample_rate_hz: Literal[2_500_000, 10_000_000, 15_000_000]  # type: ignore[assignment]


class VariableDwellAnalysisConfigurationV5(AdaptiveModel):
    """One configuration whose probe inventory follows each attested event span."""

    schema_version: Literal[5] = 5
    analyzer_id: Literal["adaptive-hop-variable-dwell-fractional-glrt64-cfo-v1"] = (
        "adaptive-hop-variable-dwell-fractional-glrt64-cfo-v1"
    )
    sample_rate_hz: Literal[2_500_000, 10_000_000]
    allowed_valid_visit_ms: tuple[Literal[120], Literal[240], Literal[360]] = (
        120,
        240,
        360,
    )
    probe_ms: Literal[20] = 20
    probe_stride_ms: Annotated[int, Field(strict=True, ge=10, le=120)] = 10
    glrt64_margin_gate: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 0.025
    maximum_acquisition_candidates: Annotated[int, Field(strict=True, ge=1, le=16)] = 8
    receiver_ids: tuple[Literal[0], Literal[1]] = (0, 1)
    timing_refinement: Literal["circular-five-cell-log-parabola-plus-lanczos16-v1"] = (
        "circular-five-cell-log-parabola-plus-lanczos16-v1"
    )
    decision_score: Literal["fractional-epoch-conditioned-glrt64-v1"] = (
        "fractional-epoch-conditioned-glrt64-v1"
    )

    @field_validator("receiver_ids", mode="before")
    @classmethod
    def _exact_receivers(cls, value: object) -> object:
        return AdaptiveHopAnalysisConfigurationV1._exact_receivers(value)

    @field_validator("allowed_valid_visit_ms", mode="before")
    @classmethod
    def _exact_durations(cls, value: object) -> object:
        if not isinstance(value, (tuple, list)) or tuple(value) != (120, 240, 360):
            raise ValueError("variable adaptive analysis requires exact attested durations")
        return value

    @property
    def probe_samples(self) -> int:
        return self.sample_rate_hz * self.probe_ms // 1000

    @property
    def probe_stride_samples(self) -> int:
        return self.sample_rate_hz * self.probe_stride_ms // 1000

    def valid_visit_ms(self, sample_count: int) -> int:
        numerator = sample_count * 1000
        if numerator % self.sample_rate_hz:
            raise ValueError("adaptive event span is not an exact millisecond duration")
        duration = numerator // self.sample_rate_hz
        if duration not in self.allowed_valid_visit_ms:
            raise ValueError("adaptive event span is outside the analysis contract")
        return duration

    def scheduled_probe_count(self, sample_count: int) -> int:
        self.valid_visit_ms(sample_count)
        return (sample_count - self.probe_samples) // self.probe_stride_samples + 1

    @property
    def scheduled_probe_counts(self) -> tuple[int, ...]:
        return tuple(
            len(self.receiver_ids)
            * self.scheduled_probe_count(self.sample_rate_hz * duration // 1000)
            for duration in self.allowed_valid_visit_ms
        )


class FourRateVariableDwellAnalysisConfigurationV6(VariableDwellAnalysisConfigurationV5):
    """Variable-dwell analysis for every qualified v0.58 source rate."""

    schema_version: Literal[6] = 6  # type: ignore[assignment]
    sample_rate_hz: Literal[2_500_000, 5_000_000, 7_500_000, 10_000_000]  # type: ignore[assignment]


class Feature104VisitAnalysisV4(AdaptiveHopVisitAnalysisV1):
    schema_version: Literal[4] = 4  # type: ignore[assignment]
    _allow_zero_gap: ClassVar[bool] = True
    configuration: Feature104AnalysisConfigurationV4  # type: ignore[assignment]


class AdaptiveHopProbeAnalysisV2(AdaptiveHopProbeAnalysisV1):
    """Probe coordinates for an event span of up to 360 milliseconds."""

    schema_version: Literal[2] = 2
    probe_index: Annotated[int, Field(strict=True, ge=0, le=34)]  # type: ignore[assignment]
    probe_start_ms: Annotated[int, Field(strict=True, ge=0, le=340)]  # type: ignore[assignment]


class VariableDwellVisitAnalysisV5(AdaptiveHopVisitAnalysisV1):
    """Receipt-V6 analysis whose per-visit probe layout follows the event end."""

    schema_version: Literal[5] = 5  # type: ignore[assignment]
    _allow_zero_gap: ClassVar[bool] = True
    configuration: VariableDwellAnalysisConfigurationV5  # type: ignore[assignment]
    probes: Annotated[tuple[AdaptiveHopProbeAnalysisV2, ...], Field(min_length=2, max_length=70)]  # type: ignore[assignment]


class FourRateVariableDwellVisitAnalysisV6(VariableDwellVisitAnalysisV5):
    schema_version: Literal[6] = 6  # type: ignore[assignment]
    configuration: FourRateVariableDwellAnalysisConfigurationV6  # type: ignore[assignment]


class AdaptiveHopAnalysisReader(Protocol):
    """A manifest-bound, lazy, dual-RX reader. Its caller owns closure."""

    @property
    def session_id(self) -> str: ...
    @property
    def input_manifest_sha256(self) -> str: ...
    @property
    def receipt(self) -> AdaptiveHopReceiptV1: ...
    def read_visit_ci16(self, index: int) -> tuple[AdaptiveHopVisitV1, npt.NDArray[np.int16]]: ...


@dataclass(frozen=True, slots=True)
class AdaptiveHopAnalysisSource:
    _receipt_model: ClassVar[type[AdaptiveHopReceiptV1]] = AdaptiveHopReceiptV1
    reader: AdaptiveHopAnalysisReader = field(repr=False, compare=False)
    receipt: AdaptiveHopReceiptV1 = field(init=False)
    visits: tuple[AdaptiveHopVisitV1, ...] = field(init=False)
    input_manifest_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        receipt = self._receipt_model.model_validate(self.reader.receipt.model_dump())
        if self.reader.session_id != receipt.session_id:
            raise ValueError("adaptive analysis reader changed session identity")
        # Validate the digest at admission, not after expensive scientific work.
        TypeAdapter(Sha256Digest).validate_python(self.reader.input_manifest_sha256)
        object.__setattr__(self, "input_manifest_sha256", self.reader.input_manifest_sha256)
        object.__setattr__(self, "receipt", receipt)
        object.__setattr__(self, "visits", receipt.visits)

    def read_visit(self, index: int) -> npt.NDArray[np.complex64]:
        if type(index) is not int or not 0 <= index < len(self.visits):
            raise ValueError("adaptive analysis visit is not a complete retained visit")
        if (
            self.reader.session_id != self.receipt.session_id
            or self.reader.input_manifest_sha256 != self.input_manifest_sha256
        ):
            raise ValueError("adaptive analysis reader changed manifest binding")
        evidence, values = self.reader.read_visit_ci16(index)
        if evidence != self.visits[index]:
            raise ValueError("adaptive analysis reader changed actual visit evidence")
        expected = (
            self.visits[index].valid_sample_count,
            len(self.receipt.plan.geometry.receiver_ids),
            2,
        )
        if (
            not isinstance(values, np.ndarray)
            or values.dtype != np.dtype("<i2")
            or values.shape != expected
            or not values.flags.c_contiguous
        ):
            raise ValueError("adaptive analysis reader did not supply complete source-bound CI16")
        output = np.empty(expected[:2], dtype=np.complex64)
        output.real = values[:, :, 0]
        output.imag = values[:, :, 1]
        output.setflags(write=False)
        return output


class EdgeAdaptiveHopAnalysisSourceV2(AdaptiveHopAnalysisSource):
    _receipt_model: ClassVar[type[AdaptiveHopReceiptV2]] = AdaptiveHopReceiptV2
    receipt: AdaptiveHopReceiptV2 = field(init=False)


class DualRx10mAdaptiveHopAnalysisSourceV3(AdaptiveHopAnalysisSource):
    _receipt_model: ClassVar[type[AdaptiveHopReceiptV3]] = AdaptiveHopReceiptV3
    receipt: AdaptiveHopReceiptV3 = field(init=False)


class Feature103AnalysisSourceV4(AdaptiveHopAnalysisSource):
    _receipt_model: ClassVar[type[AdaptiveHopReceiptV4]] = AdaptiveHopReceiptV4
    receipt: AdaptiveHopReceiptV4 = field(init=False)


class Feature104AnalysisSourceV5(AdaptiveHopAnalysisSource):
    _receipt_model: ClassVar[type[AdaptiveHopReceiptV5]] = AdaptiveHopReceiptV5
    receipt: AdaptiveHopReceiptV5 = field(init=False)


class VariableDwellAnalysisSourceV6(AdaptiveHopAnalysisSource):
    _receipt_model: ClassVar[type[AdaptiveHopReceiptV6]] = AdaptiveHopReceiptV6
    receipt: AdaptiveHopReceiptV6 = field(init=False)


class FourRateVariableDwellAnalysisSourceV7(AdaptiveHopAnalysisSource):
    _receipt_model: ClassVar[type[AdaptiveHopReceiptV7]] = AdaptiveHopReceiptV7
    receipt: AdaptiveHopReceiptV7 = field(init=False)


@dataclass(frozen=True, slots=True)
class _VariableDwellDetectorConfiguration:
    persisted: VariableDwellAnalysisConfigurationV5 | FourRateVariableDwellAnalysisConfigurationV6
    dwell_samples: int
    scheduled_probe_count: int

    def __getattr__(self, name: str) -> Any:
        return getattr(self.persisted, name)


def _analysis_models(source):
    if isinstance(source, FourRateVariableDwellAnalysisSourceV7):
        return FourRateVariableDwellAnalysisConfigurationV6, FourRateVariableDwellVisitAnalysisV6
    if isinstance(source, VariableDwellAnalysisSourceV6):
        return VariableDwellAnalysisConfigurationV5, VariableDwellVisitAnalysisV5
    if isinstance(source, Feature104AnalysisSourceV5):
        return Feature104AnalysisConfigurationV4, Feature104VisitAnalysisV4
    if isinstance(source, Feature103AnalysisSourceV4):
        return Feature103AnalysisConfigurationV3, Feature103VisitAnalysisV3
    if isinstance(source, DualRx10mAdaptiveHopAnalysisSourceV3):
        return DualRx10mAdaptiveHopAnalysisConfigurationV2, DualRx10mAdaptiveHopVisitAnalysisV2
    return AdaptiveHopAnalysisConfigurationV1, AdaptiveHopVisitAnalysisV1


def _fractional_candidate(
    response: Glrt64CandidateResponse,
    *,
    probe_start: int,
    visit_start: int,
    source_origin: int,
    cfg,
) -> AdaptiveHopFractionalCandidateV1 | AdaptiveHopUnavailableCandidateV1:
    fractional = (
        response.fractional_epoch_offset_samples,
        response.fractional_residual_cfo_hz,
        response.fractional_tracking_cfo_hz,
        response.fractional_exact_score,
        response.fractional_control_score,
        response.fractional_margin,
    )
    if response.fractional_epoch_status != "complete" or any(v is None for v in fractional):
        return AdaptiveHopUnavailableCandidateV1(
            candidate_rank=response.candidate_rank,
            fractional_epoch_status=response.fractional_epoch_status,
            reason="fractional_incomplete",
        )
    offset = response.fractional_epoch_offset_samples
    assert offset is not None
    assert response.fractional_residual_cfo_hz is not None
    assert response.fractional_tracking_cfo_hz is not None
    assert response.fractional_exact_score is not None
    assert response.fractional_control_score is not None
    assert response.fractional_margin is not None
    if not math.isfinite(offset) or abs(offset) > 2:
        raise ValueError("adaptive detector returned invalid fractional refinement")
    if type(response.epoch_sample) is not int or not 0 <= response.epoch_sample < cfg.probe_samples:
        raise ValueError("adaptive detector returned an epoch outside its probe")
    local = probe_start + response.epoch_sample
    if not 0 <= local + offset < cfg.dwell_samples:
        return AdaptiveHopUnavailableCandidateV1(
            candidate_rank=response.candidate_rank,
            fractional_epoch_status=response.fractional_epoch_status,
            reason="outside_retained_interval",
        )
    anchor = visit_start + local
    relative = anchor - source_origin
    return AdaptiveHopFractionalCandidateV1(
        candidate_rank=response.candidate_rank,
        integer_epoch_sample=response.epoch_sample,
        integer_device_sample_counter=anchor,
        integer_session_sample=relative,
        fractional_epoch_offset_samples=offset,
        fractional_time_s=(relative + offset) / cfg.sample_rate_hz,
        acquired_cfo_hz=response.acquired_cfo_hz,
        integer_residual_cfo_hz=response.residual_cfo_hz,
        integer_tracking_cfo_hz=response.tracking_cfo_hz,
        integer_exact_score=response.exact_score,
        integer_control_score=response.control_score,
        integer_margin=response.margin,
        fractional_residual_cfo_hz=response.fractional_residual_cfo_hz,
        fractional_tracking_cfo_hz=response.fractional_tracking_cfo_hz,
        fractional_exact_score=response.fractional_exact_score,
        fractional_control_score=response.fractional_control_score,
        fractional_margin=response.fractional_margin,
        passed_fractional_margin_gate=response.fractional_margin >= cfg.glrt64_margin_gate,
    )


def analyze_adaptive_hop_visit(
    source: AdaptiveHopAnalysisSource,
    visit_index: int,
    *,
    configuration: AdaptiveHopAnalysisConfigurationV1
    | VariableDwellAnalysisConfigurationV5
    | FourRateVariableDwellAnalysisConfigurationV6
    | None = None,
) -> AdaptiveHopVisitAnalysisV1:
    """Reuse the existing detector, keeping only complete fractional decisions."""
    model, product_model = _analysis_models(source)
    cfg = configuration or model.model_validate(
        {"sample_rate_hz": source.receipt.plan.geometry.sample_rate_hz}
    )
    cfg = model.model_validate(cfg.model_dump())
    if cfg.sample_rate_hz != source.receipt.plan.geometry.sample_rate_hz:
        raise ValueError("adaptive analysis configuration changed source sample rate")
    samples = source.read_visit(visit_index)
    return _analyze_loaded_visit(source, visit_index, samples, cfg, product_model)


def analyze_adaptive_hop_visit_batch(
    source: AdaptiveHopAnalysisSource,
    visit_indexes: tuple[int, ...],
    *,
    configuration: AdaptiveHopAnalysisConfigurationV1
    | VariableDwellAnalysisConfigurationV5
    | FourRateVariableDwellAnalysisConfigurationV6,
) -> Iterator[AdaptiveHopVisitAnalysisV1]:
    """At most two independent visits; only the owning thread reads stored IQ.

    Yield in source order so each successful visit can be checkpointed even if
    the next fails. Worker threads see immutable arrays, never the reader cache.
    """
    if not 1 <= len(visit_indexes) <= 2 or len(set(visit_indexes)) != len(visit_indexes):
        raise ValueError("adaptive analysis batch must contain one or two distinct visits")
    config_model, product_model = _analysis_models(source)
    cfg = config_model.model_validate(configuration.model_dump())
    if cfg.sample_rate_hz != source.receipt.plan.geometry.sample_rate_hz:
        raise ValueError("adaptive analysis configuration changed source sample rate")
    samples = tuple(source.read_visit(index) for index in visit_indexes)
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="leo-adaptive-glrt") as executor:
        futures = [
            executor.submit(
                _analyze_loaded_visit,
                source,
                index,
                values,
                cfg,
                product_model,
            )
            for index, values in zip(visit_indexes, samples, strict=True)
        ]
        for future in futures:
            yield future.result()


def _analyze_loaded_visit(
    source: AdaptiveHopAnalysisSource,
    visit_index: int,
    samples: npt.NDArray[np.complex64],
    cfg: AdaptiveHopAnalysisConfigurationV1
    | VariableDwellAnalysisConfigurationV5
    | FourRateVariableDwellAnalysisConfigurationV6,
    product_model: type[AdaptiveHopVisitAnalysisV1] = AdaptiveHopVisitAnalysisV1,
) -> AdaptiveHopVisitAnalysisV1:
    visit = source.visits[visit_index]
    event = visit.event
    if isinstance(
        cfg, (VariableDwellAnalysisConfigurationV5, FourRateVariableDwellAnalysisConfigurationV6)
    ):
        detector_cfg: Glrt64DwellConfiguration = _VariableDwellDetectorConfiguration(
            persisted=cfg,
            dwell_samples=visit.valid_sample_count,
            scheduled_probe_count=cfg.scheduled_probe_count(visit.valid_sample_count),
        )
    else:
        detector_cfg = cfg
    analysis = analyze_glrt64_dwell(samples, detector_cfg, edge=event.target.edge)
    rows = []
    for probe in analysis.probes:
        converted = tuple(
            _fractional_candidate(
                response,
                probe_start=probe.probe_start_ms * cfg.sample_rate_hz // 1000,
                visit_start=event.valid_start_counter,
                source_origin=source.receipt.terminal.first_counter,
                cfg=detector_cfg,
            )
            for response in probe.candidates
        )
        candidates = tuple(c for c in converted if isinstance(c, AdaptiveHopFractionalCandidateV1))
        unavailable = tuple(
            c for c in converted if isinstance(c, AdaptiveHopUnavailableCandidateV1)
        )
        winner = max(
            candidates, key=lambda c: (c.fractional_margin, -c.candidate_rank), default=None
        )
        rows.append(
            (
                AdaptiveHopProbeAnalysisV2
                if isinstance(
                    cfg,
                    (
                        VariableDwellAnalysisConfigurationV5,
                        FourRateVariableDwellAnalysisConfigurationV6,
                    ),
                )
                else AdaptiveHopProbeAnalysisV1
            )(
                receiver_id=probe.receiver_id,
                probe_index=probe.probe_index,
                probe_start_ms=probe.probe_start_ms,
                candidate_count=len(probe.candidates),
                candidates=candidates,
                unavailable_candidates=unavailable,
                winning_candidate_rank=winner.candidate_rank if winner else None,
            )
        )
    return product_model(
        session_id=source.receipt.session_id,
        input_manifest_sha256=source.input_manifest_sha256,
        configuration=cast(Any, cfg),
        policy_generation=source.receipt.plan.policy.generation,
        source_origin_counter=source.receipt.terminal.first_counter,
        visit_index=event.visit_index,
        target_index=event.target_index,
        target=event.target,
        invalid_start_counter=event.invalid_start_counter,
        valid_start_counter=event.valid_start_counter,
        valid_end_counter=visit.valid_end_counter_exclusive,
        actual_if_center_hz=event.actual_lo_frequency_hz + event.actual_if_offset_hz,
        probes=tuple(rows),
    )


def validate_adaptive_analysis_binding(
    product: AdaptiveHopVisitAnalysisV1,
    receipt: AdaptiveHopReceiptV1
    | AdaptiveHopReceiptV2
    | AdaptiveHopReceiptV3
    | AdaptiveHopReceiptV6,
    *,
    input_manifest_sha256: str,
) -> None:
    product_model = (
        VariableDwellVisitAnalysisV5
        if isinstance(product, VariableDwellVisitAnalysisV5)
        else AdaptiveHopVisitAnalysisV1
    )
    product = product_model.model_validate(product.model_dump())
    receipt_model = (
        AdaptiveHopReceiptV6
        if isinstance(receipt, AdaptiveHopReceiptV6)
        else AdaptiveHopReceiptV3
        if isinstance(receipt, AdaptiveHopReceiptV3)
        else AdaptiveHopReceiptV2
        if isinstance(receipt, AdaptiveHopReceiptV2)
        else AdaptiveHopReceiptV1
    )
    receipt = receipt_model.model_validate(receipt.model_dump())
    _compare_source_fields(product, receipt, input_manifest_sha256)


def _compare_source_fields(
    product: AdaptiveHopVisitAnalysisV1, receipt: AdaptiveHopReceiptV1, input_manifest_sha256: str
) -> None:
    """Scanner-internal comparison of fully validated immutable snapshots.

    A retained binding validates its receipt once, avoiding an O(visits²)
    full-receipt parse during checkpointing. Public standalone ingress above
    still revalidates both models, including unchecked model_copy instances.
    """
    retained = tuple(
        getattr(receipt, "retained_visit_indices", range(receipt.complete_visit_count))
    )
    if product.visit_index not in retained:
        raise ValueError("adaptive analysis claims a non-retained visit")
    event = receipt.events[product.visit_index]
    if (
        product.session_id != receipt.session_id
        or product.input_manifest_sha256 != input_manifest_sha256
        or product.configuration.sample_rate_hz != receipt.plan.geometry.sample_rate_hz
        or product.configuration.receiver_ids != receipt.plan.geometry.receiver_ids
        or product.policy_generation != receipt.plan.policy.generation
        or product.source_origin_counter != receipt.terminal.first_counter
        or product.target_index != event.target_index
        or product.target != event.target
        or product.invalid_start_counter != event.invalid_start_counter
        or product.valid_start_counter != event.valid_start_counter
        or product.valid_end_counter
        != getattr(
            event,
            "valid_end_counter_exclusive",
            event.valid_start_counter + receipt.plan.geometry.valid_visit_samples,
        )
        or product.actual_if_center_hz != event.actual_lo_frequency_hz + event.actual_if_offset_hz
    ):
        raise ValueError("adaptive analysis product differs from source manifest")
