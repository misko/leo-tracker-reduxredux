"""Additive, candidate-only partial-band pilot analysis contracts."""

from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, StringConstraints, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest


class PartialBandConfigurationV1(ContractModel):
    schema_version: Literal[1] = 1
    model: Literal["filtered-pilot64-grouped-glrt-v1"] = "filtered-pilot64-grouped-glrt-v1"
    sample_rate_hz: Literal[1_250_000] = 1_250_000
    probe_ms: Literal[20] = 20
    stride_ms: Literal[20] = 20
    synthesis_rate_hz: Literal[5_000_000] = 5_000_000
    filter_cutoff_hz: Annotated[float, Field(ge=450_000, le=590_000)] = 550_000
    filter_taps: Literal[129] = 129
    filter_kaiser_beta: Literal[8.0] = 8.0
    filter_authority: Literal["approximate-receiver-response"] = "approximate-receiver-response"
    first_symbol: Literal[18] = 18
    evaluation_first_symbol: Literal[146] = 146
    symbol_count: Literal[64] = 64
    maximum_cfo_hz: Annotated[int, Field(ge=20_000, le=800_000)] = 800_000
    coarse_step_hz: Annotated[int, Field(ge=500, le=2_000)] = 2_000
    fine_step_hz: Literal[100] = 100
    timing_step_samples: Literal[0.125] = 0.125
    maximum_candidates: Annotated[int, Field(ge=1, le=8)] = 3
    candidate_separation_hz: Literal[10_000] = 10_000
    split_seed: Annotated[int, Field(ge=0, le=2**32 - 1)] = 20261003
    control_seed: Literal[9103] = 9103
    training_frame_count: Literal[7] = 7
    evaluation_frame_count: Literal[7] = 7
    minimum_training_score: Annotated[float, Field(gt=0, le=1)] = 0.025
    minimum_evaluation_score: Annotated[float, Field(gt=0, le=1)] = 0.02
    minimum_control_ratio: Annotated[float, Field(ge=1, le=100)] = 3.0
    candidate_only: Literal[True] = True

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))


class PartialBandCandidateV1(ContractModel):
    rank: Annotated[int, Field(ge=0)]
    cfo_hz: Annotated[float, Field(allow_inf_nan=False)]
    epoch_samples: Annotated[float, Field(allow_inf_nan=False)]
    training_score: Annotated[float, Field(ge=0, le=1.000001)]
    evaluation_score: Annotated[float, Field(ge=0, le=1.000001)]
    conditioned_control_score: Annotated[float, Field(ge=0, le=1.000001)]
    searched_control_evaluation_score: Annotated[float, Field(ge=0, le=1.000001)]
    passed: bool
    observable_tone_centers: Annotated[int, Field(ge=0, le=8)]
    filter_edge_clearance_hz: float
    cfo_grid_resolution_hz: Literal[100] = 100
    candidate_only: Literal[True] = True


class PartialBandProbeV1(ContractModel):
    schema_version: Literal[1] = 1
    visit_index: Annotated[int, Field(ge=0)]
    receiver_id: Literal[0, 1]
    channel: Annotated[int, Field(ge=1, le=4)]
    edge: Literal["lower", "upper"]
    probe_index: Annotated[int, Field(ge=0)]
    sample_start_counter: Annotated[int, Field(ge=0)]
    time_s: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    reported_lo_frequency_hz: Annotated[int, Field(gt=0)]
    configuration_sha256: Sha256Digest
    training_frames: tuple[int, ...]
    evaluation_frames: tuple[int, ...]
    control_training_score: Annotated[float, Field(ge=0, le=1.000001)]
    candidates: tuple[PartialBandCandidateV1, ...]
    state: Literal["candidate", "no_detection", "zero_energy"]

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (
            len(self.training_frames) != 7
            or len(self.evaluation_frames) != 7
            or set(self.training_frames) & set(self.evaluation_frames)
            or set(self.training_frames) | set(self.evaluation_frames) != set(range(14))
        ):
            raise ValueError("invalid grouped frame partition")
        if (self.state == "candidate") != any(c.passed for c in self.candidates):
            raise ValueError("probe state differs from candidate evidence")
        return self


SessionId = Annotated[str, StringConstraints(pattern=r"^scan-fw-[0-9a-f]{16}$")]


class PartialBandVisitPlanV1(ContractModel):
    visit_index: Annotated[int, Field(ge=0)]
    channel: Annotated[int, Field(ge=1, le=4)]
    edge: Literal["lower", "upper"]
    start_counter: Annotated[int, Field(ge=0)]
    sample_count: Annotated[int, Field(ge=25_000)]
    reported_lo_frequency_hz: Annotated[int, Field(gt=0)]

    @property
    def probe_count(self) -> int:
        return self.sample_count // 25_000


class PartialBandBindingV1(ContractModel):
    schema_version: Literal[1] = 1
    session_id: SessionId
    input_manifest_sha256: Sha256Digest
    configuration: PartialBandConfigurationV1
    first_counter: Annotated[int, Field(ge=0)]
    visits: Annotated[tuple[PartialBandVisitPlanV1, ...], Field(min_length=1, max_length=3000)]

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if tuple(v.visit_index for v in self.visits) != tuple(range(len(self.visits))):
            raise ValueError("visit inventory is not complete and ordered")
        if any(
            v.start_counter < self.first_counter or v.sample_count % 25_000 for v in self.visits
        ):
            raise ValueError("visit cannot be completely covered by native 20 ms probes")
        return self

    @property
    def digest(self) -> Sha256Digest:
        return partial_band_identity(
            self.session_id, self.input_manifest_sha256, self.configuration
        )

    @property
    def expected_probes(self) -> int:
        return 2 * sum(v.probe_count for v in self.visits)


def partial_band_identity(session_id, input_manifest_sha256, configuration):
    return canonical_digest(
        dict(
            session_id=session_id,
            input_manifest_sha256=input_manifest_sha256,
            configuration=configuration.model_dump(mode="json"),
        )
    )


class PartialBandVisitV1(ContractModel):
    schema_version: Literal[1] = 1
    binding_sha256: Sha256Digest
    visit_index: Annotated[int, Field(ge=0)]
    raw_ci16_sha256: Sha256Digest
    probes: tuple[PartialBandProbeV1, ...]

    def validate_binding(self, binding: PartialBandBindingV1) -> None:
        if self.binding_sha256 != binding.digest or self.visit_index >= len(binding.visits):
            raise ValueError("checkpoint source/configuration differs")
        visit = binding.visits[self.visit_index]
        expected = [(rx, p) for rx in (0, 1) for p in range(visit.probe_count)]
        if [(p.receiver_id, p.probe_index) for p in self.probes] != expected:
            raise ValueError("checkpoint probe inventory is incomplete or duplicated")
        for p in self.probes:
            start = visit.start_counter + p.probe_index * 25_000
            if (
                p.visit_index != self.visit_index
                or p.channel != visit.channel
                or p.edge != visit.edge
                or p.configuration_sha256 != binding.configuration.digest
                or p.reported_lo_frequency_hz != visit.reported_lo_frequency_hz
                or p.sample_start_counter != start
                or abs(p.time_s - (start - binding.first_counter) / 1_250_000) > 1e-9
            ):
                raise ValueError("checkpoint probe coordinates changed")


PARTIAL_BAND_ARTIFACTS = (
    "coverage.png",
    "glrt64-response.png",
    "cfo-trajectories.png",
    "bandwidth.png",
    "probes.jsonl.gz",
    "segments.json",
)


class PartialBandArtifactV1(ContractModel):
    name: Literal[
        "coverage.png",
        "glrt64-response.png",
        "cfo-trajectories.png",
        "bandwidth.png",
        "probes.jsonl.gz",
        "segments.json",
    ]
    sha256: Sha256Digest
    byte_count: Annotated[int, Field(gt=0, le=128 * 1024 * 1024)]


class PartialBandManifestV1(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["experimental-partial-band-glrt"] = "experimental-partial-band-glrt"
    binding_sha256: Sha256Digest
    binding: PartialBandBindingV1
    checkpoint_sha256: tuple[Sha256Digest, ...]
    probe_count: Annotated[int, Field(ge=0)]
    candidate_probe_count: Annotated[int, Field(ge=0)]
    artifacts: tuple[PartialBandArtifactV1, ...]
    scientific_status: Literal["candidate_only"] = "candidate_only"
    phase_and_position_status: Literal["not_qualified_for_partial_band"] = (
        "not_qualified_for_partial_band"
    )

    @model_validator(mode="after")
    def complete(self) -> Self:
        if (
            self.binding_sha256 != self.binding.digest
            or len(self.checkpoint_sha256) != len(self.binding.visits)
            or self.probe_count != self.binding.expected_probes
            or self.candidate_probe_count > self.probe_count
            or tuple(a.name for a in self.artifacts) != PARTIAL_BAND_ARTIFACTS
        ):
            raise ValueError("partial-band publication inventory is incomplete")
        return self


class PartialBandStatusV1(ContractModel):
    schema_version: Literal[1] = 1
    session_id: SessionId
    binding_sha256: Sha256Digest
    state: Literal["not_started", "partial", "figures_ready"]
    completed_visits: int
    manifest: PartialBandManifestV1 | None = None


class PartialBandReader(Protocol):
    def status(self, session_id: str, input_manifest_sha256: str) -> PartialBandStatusV1: ...
    def artifact(
        self, session_id: str, input_manifest_sha256: str, name: str, expected_sha256: str
    ) -> bytes | None: ...
