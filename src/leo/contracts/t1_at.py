"""Versioned, storage-independent evidence for the T1-AT association baseline.

Orbit-blind refinement and receiver calibration are upstream inputs, not
silently recomputed by selection. Support is conditional on those inputs.
"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest

Finite = Annotated[float, Field(allow_inf_nan=False)]


class T1AtCandidateV1(ContractModel):
    candidate_id: Annotated[int, Field(ge=0)]
    window_id: Annotated[str, Field(min_length=1)]
    receiver_id: Annotated[int, Field(ge=0)]
    channel: Annotated[int, Field(ge=0)]
    receive_time_s: Finite
    refined_cfo_hz: Finite
    refined_margin: Finite
    refinement_state: Literal["refined", "failed-original-retained"] = "refined"


class T1AtModeV1(ContractModel):
    catalog_number: Annotated[int, Field(gt=0)]
    absolute_timing_s: Annotated[Finite, Field(ge=-20, le=20)]
    candidate_ids: tuple[int, ...]
    residual_hz: tuple[Finite, ...]

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if len(self.candidate_ids) != len(self.residual_hz):
            raise ValueError("mode residuals do not match candidate IDs")
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("mode repeats a candidate")
        if any(abs(e) > 600 for e in self.residual_hz):
            raise ValueError("mode evidence exceeds the v1 600 Hz visibility/residual gate")
        return self


class T1AtInputV1(ContractModel):
    schema_version: Literal[1] = 1
    baseline_id: Literal["t1_at_v1"] = "t1_at_v1"
    session_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
    capture_mode: Literal["adaptive"] = "adaptive"
    input_manifest_sha256: Sha256Digest
    analysis_manifest_sha256: Sha256Digest
    refinement_sha256: Sha256Digest
    calibration_sha256: Sha256Digest
    orbit_bank_sha256: Sha256Digest
    calibration_qualified: Literal[True] = True
    timing_convention: Literal["absolute-no-fold-reference"] = "absolute-no-fold-reference"
    position_scope: Literal["known-site-conditional"] = "known-site-conditional"
    candidates: tuple[T1AtCandidateV1, ...]
    fitted_c_modes: tuple[T1AtModeV1, ...]
    zero_c_modes: tuple[T1AtModeV1, ...]

    @model_validator(mode="after")
    def coherent(self) -> Self:
        ids = {c.candidate_id for c in self.candidates}
        if len(ids) != len(self.candidates):
            raise ValueError("duplicate candidate ID")
        windows: dict[str, tuple[int, int]] = {}
        for candidate in self.candidates:
            lane = candidate.receiver_id, candidate.channel
            if windows.setdefault(candidate.window_id, lane) != lane:
                raise ValueError("window crosses receiver/channel lanes")

        def key(modes):
            return [(m.catalog_number, m.absolute_timing_s) for m in modes]

        if key(self.fitted_c_modes) != key(self.zero_c_modes):
            raise ValueError("RF ablation requires identical satellite/timing hypotheses")
        for mode in (*self.fitted_c_modes, *self.zero_c_modes):
            if not set(mode.candidate_ids) <= ids:
                raise ValueError("mode references missing candidate")
        return self


class T1AtAssignmentV1(ContractModel):
    candidate_id: Annotated[int, Field(ge=0)]
    window_id: str
    catalog_number: Annotated[int, Field(gt=0)]
    mode_index: Annotated[int, Field(ge=0)]
    residual_hz: Annotated[Finite, Field(ge=-600, le=600)]


class T1AtSelectedV1(ContractModel):
    catalog_number: Annotated[int, Field(gt=0)]
    absolute_timing_s: Annotated[Finite, Field(ge=-20, le=20)]
    mode_index: Annotated[int, Field(ge=0)]
    count: Annotated[int, Field(gt=10)]


class T1AtSelectionV1(ContractModel):
    assigned: Annotated[int, Field(ge=0)]
    denominator: Annotated[int, Field(ge=0)]
    unassigned: Annotated[int, Field(ge=0)]
    objective: int
    satellites: tuple[T1AtSelectedV1, ...]
    assignments: tuple[T1AtAssignmentV1, ...]

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (
            self.assigned != len(self.assignments)
            or self.assigned + self.unassigned != self.denominator
        ):
            raise ValueError("window coverage accounting differs")
        if len({a.window_id for a in self.assignments}) != self.assigned:
            raise ValueError("window assigned twice")
        if len({a.candidate_id for a in self.assignments}) != self.assigned:
            raise ValueError("candidate assigned twice")
        if len({s.catalog_number for s in self.satellites}) != len(self.satellites):
            raise ValueError("satellite has multiple selected timing modes")
        if self.objective != self.assigned - 10 * len(self.satellites):
            raise ValueError("v1 count-minus-penalty objective differs")
        for satellite in self.satellites:
            members = [a for a in self.assignments if a.catalog_number == satellite.catalog_number]
            if len(members) != satellite.count or any(
                a.mode_index != satellite.mode_index for a in members
            ):
                raise ValueError("satellite assignment accounting differs")
        if sum(s.count for s in self.satellites) != self.assigned:
            raise ValueError("assignments include unselected satellites")
        return self


class T1AtPassV1(ContractModel):
    pass_index: Annotated[int, Field(ge=1, le=3)]
    accepted: Annotated[int, Field(ge=0)]
    objective: int


class T1AtArmV1(ContractModel):
    initial: T1AtSelectionV1
    final: T1AtSelectionV1
    passes: tuple[T1AtPassV1, ...]
    termination: Literal["no_improving_greedy_repair", "pass_limit"]

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (
            self.final.denominator != self.initial.denominator
            or self.final.objective < self.initial.objective
        ):
            raise ValueError("replacement accounting differs")
        return self


class T1AtProductV1(ContractModel):
    schema_version: Literal[1] = 1
    baseline_id: Literal["t1_at_v1"] = "t1_at_v1"
    session_id: str
    input_manifest_sha256: Sha256Digest
    analysis_manifest_sha256: Sha256Digest
    prepared_input_sha256: Sha256Digest
    arms: dict[Literal["fitted-c", "zero-c"], T1AtArmV1]
    candidate_only: Literal[True] = True
    identity_claimed: Literal[False] = False
    scope: Literal[
        "Known-site conditional association; not blind localization or held-out validation"
    ] = "Known-site conditional association; not blind localization or held-out validation"

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if set(self.arms) != {"fitted-c", "zero-c"}:
            raise ValueError("both RF ablation arms are required")
        if len({a.final.denominator for a in self.arms.values()}) != 1:
            raise ValueError("RF ablation denominators differ")
        return self
