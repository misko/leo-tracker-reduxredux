"""Additive fast-scan products. Existing recording and Standard schemas stay fixed."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest


class FastScanPolicyV1(ContractModel):
    schema_version: Literal[1] = 1
    mode: Literal["gated", "ungated", "shadow"] = "gated"
    threshold: Annotated[float, Field(ge=0, le=1)] = 0.013219531315217865
    margin_gate: Literal[0.025] = 0.025
    strong_margin: Literal[0.1] = 0.1
    sample_rate_hz: Literal[2500000] = 2500000
    window_samples: Literal[50000] = 50000
    gate: Literal["either_receiver"] = "either_receiver"


class FastScanScoreV1(ContractModel):
    model_config = ConfigDict(allow_inf_nan=False)
    receiver_id: int
    margin: float
    exact: float
    control: float
    epoch_sample: Annotated[int, Field(ge=0, lt=10000)]


class FastScanCandidateV1(ContractModel):
    model_config = ConfigDict(allow_inf_nan=False)
    candidate_rank: Annotated[int, Field(ge=0, lt=8)]
    epoch_sample: Annotated[int, Field(ge=0)]
    acquired_cfo_hz: float
    residual_cfo_hz: float
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float
    passed_margin_gate: bool
    fractional_epoch_status: str
    fractional_epoch_offset_samples: float | None
    fractional_frame_phase_sample: float | None
    fractional_exact_score: float | None
    fractional_control_score: float | None
    fractional_residual_cfo_hz: float | None
    fractional_tracking_cfo_hz: float | None
    fractional_margin: float | None


class FastScanReceiverV1(ContractModel):
    receiver_id: int
    candidates: tuple[FastScanCandidateV1, ...]


class FastScanWindowResultV1(ContractModel):
    schema_version: Literal[1] = 1
    visit: Annotated[int, Field(ge=0)]
    segment_sequence: Annotated[int, Field(ge=0)]
    iq_sha256: Sha256Digest
    sample_start: int | None
    sample_end: int | None
    sample_start_utc_ns: int | None
    generation: int | None
    channel: Annotated[int, Field(ge=1, le=8)]
    edge: Literal["lower", "upper"]
    actual_if_hz: int | None
    lnb_reference_hz: int
    rf_mapping_authority: Literal["hypothesis", "known", "unknown"]
    status: Literal["processed", "skipped_fast_score", "invalid_capture"]
    reason: str
    scores: tuple[FastScanScoreV1, ...] = ()
    receivers: tuple[FastScanReceiverV1, ...] = ()
    qualified_tracking: Literal[False] = False

    @model_validator(mode="after")
    def coherent_status(self):
        scored = [s.receiver_id for s in self.scores]
        measured = [r.receiver_id for r in self.receivers]
        if len(set(scored)) != len(scored) or len(set(measured)) != len(measured):
            raise ValueError("duplicate receiver results")
        if self.status == "processed" and (not scored or set(scored) != set(measured)):
            raise ValueError("processed windows require every scored receiver")
        if self.status != "processed" and self.receivers:
            raise ValueError("unprocessed windows cannot contain GLRT results")
        if self.status == "skipped_fast_score" and not self.scores:
            raise ValueError("skipped windows require predictor evidence")
        return self


class FastScanSegmentResultV1(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["fast-scan.glrt"] = "fast-scan.glrt"
    manifest_digest: Sha256Digest
    policy: FastScanPolicyV1
    windows: tuple[FastScanWindowResultV1, ...]
