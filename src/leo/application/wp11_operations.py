"""Typed application boundary for the operational WP11 campaign workflow."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, StringConstraints, model_validator

from leo.application.frequency_calibration import ImmutableDocumentRefV1
from leo.application.trusted_campaign import TrustedCampaignPublicationV1
from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.recording import Identifier
from leo.contracts.scientific import (
    AcceptedCaptureStreamInventoryV1,
    MatchedPilotAcceptanceConfigV1,
)
from leo.qualification.capture_modes import CaptureModeCampaignAcceptanceReceiptV2
from leo.qualification.scientific_campaign import campaign_config_from_accepted_capture


def wp11_run_id(campaign_id: str, session_id: str) -> str:
    digest = hashlib.sha256(f"{campaign_id}\0{session_id}".encode()).hexdigest()[:32]
    return f"wp11-{digest}"


def wp11_legacy_receipt_name(campaign_id: str, ordinal: int) -> str:
    campaign_digest = hashlib.sha256(campaign_id.encode()).hexdigest()[:16]
    return f"legacy-{campaign_digest}-{ordinal:02d}.json"


class WP11CaptureAuthorityPort(Protocol):
    def resolve(
        self, ref: ImmutableDocumentRefV1
    ) -> CaptureModeCampaignAcceptanceReceiptV2: ...


def validate_authoritative_plan(
    plan: WP11CampaignPlanV1,
    capture: WP11CaptureAuthorityPort,
) -> None:
    receipt = capture.resolve(plan.capture)
    reconstructed = campaign_config_from_accepted_capture(
        campaign_id=plan.campaign_id,
        capture_receipt=receipt,
        detector_binding=plan.processing_config.detector_binding,
    )
    expected = tuple(
        (
            ordinal,
            inventory,
            wp11_legacy_receipt_name(plan.campaign_id, ordinal),
        )
        for ordinal, inventory in enumerate(reconstructed.capture_inventory)
    )
    observed = tuple(
        (member.ordinal, member.inventory, member.legacy_receipt_name)
        for member in plan.members
    )
    if observed != expected:
        raise ValueError("WP11 plan differs from authoritative accepted-capture reconstruction")


class WP11PlanMemberV1(ContractModel):
    schema_version: Literal[1] = 1
    ordinal: Annotated[int, Field(ge=0, lt=40)]
    inventory: AcceptedCaptureStreamInventoryV1
    legacy_receipt_name: Annotated[
        str,
        StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$"),
    ]


class WP11CampaignPlanV1(ContractModel):
    schema_version: Literal[1] = 1
    campaign_id: Identifier
    capture: ImmutableDocumentRefV1
    pipeline_release_id: Identifier
    processing_config: MatchedPilotAcceptanceConfigV1
    members: tuple[WP11PlanMemberV1, ...]
    plan_digest: Sha256Digest

    @classmethod
    def create(
        cls,
        *,
        campaign_id: str,
        capture: ImmutableDocumentRefV1,
        pipeline_release_id: str,
        processing_config: MatchedPilotAcceptanceConfigV1,
        members: tuple[WP11PlanMemberV1, ...],
    ) -> Self:
        values = {
            "schema_version": 1,
            "campaign_id": campaign_id,
            "capture": capture.model_dump(mode="json"),
            "pipeline_release_id": pipeline_release_id,
            "processing_config": processing_config.model_dump(mode="json"),
            "members": [item.model_dump(mode="json") for item in members],
        }
        return cls(
            campaign_id=campaign_id,
            capture=capture,
            pipeline_release_id=pipeline_release_id,
            processing_config=processing_config,
            members=members,
            plan_digest=canonical_digest(values),
        )

    @model_validator(mode="after")
    def _exact_inventory(self) -> Self:
        if len(self.members) != 40 or tuple(item.ordinal for item in self.members) != tuple(
            range(40)
        ):
            raise ValueError("WP11 plan requires exactly 40 ordered streams")
        identities = tuple(
            (item.inventory.session_id, item.inventory.stream_id) for item in self.members
        )
        if len(set(identities)) != 40 or len({item[0] for item in identities}) != 30:
            raise ValueError("WP11 plan requires exact 30-session/40-stream inventory")
        expected = canonical_digest(self.model_dump(mode="json", exclude={"plan_digest"}))
        if self.plan_digest != expected:
            raise ValueError("WP11 plan digest differs from immutable content")
        return self


@dataclass(frozen=True, slots=True)
class WP11CreateResult:
    campaign_id: str
    plan: ImmutableDocumentRefV1
    capture: ImmutableDocumentRefV1
    session_count: int
    stream_count: int
    pipeline_release_id: str


@dataclass(frozen=True, slots=True)
class WP11QueueResult:
    campaign_id: str
    run_ids: tuple[str, ...]
    session_count: int
    stream_count: int
    already_queued_count: int


@dataclass(frozen=True, slots=True)
class WP11CampaignSummary:
    campaign_id: str
    state: str
    result_status: str | None
    mathematical_eligible: bool | None
    production_accepted: bool | None
    session_count: int
    stream_count: int
    scientific: ImmutableDocumentRefV1 | None = None
    presentation: ImmutableDocumentRefV1 | None = None
    outer_seal: ImmutableDocumentRefV1 | None = None


class WP11WorkflowPort(Protocol):
    def create(
        self,
        *,
        campaign_id: str,
        capture: ImmutableDocumentRefV1,
        processing_config: MatchedPilotAcceptanceConfigV1,
    ) -> WP11CreateResult: ...

    def queue(self, campaign_id: str) -> WP11QueueResult: ...

    def finalize(self, campaign_id: str) -> TrustedCampaignPublicationV1: ...

    def show(self, campaign_id: str) -> WP11CampaignSummary: ...


class WP11Operations:
    """Keep CLI concerns outside the trusted production facade."""

    def __init__(self, workflow: WP11WorkflowPort) -> None:
        self._workflow = workflow

    def create(
        self,
        *,
        campaign_id: str,
        capture: ImmutableDocumentRefV1,
        processing_config: MatchedPilotAcceptanceConfigV1,
    ) -> WP11CreateResult:
        return self._workflow.create(
            campaign_id=campaign_id,
            capture=capture,
            processing_config=processing_config,
        )

    def queue(self, campaign_id: str) -> WP11QueueResult:
        return self._workflow.queue(campaign_id)

    def finalize(self, campaign_id: str) -> TrustedCampaignPublicationV1:
        return self._workflow.finalize(campaign_id)

    def show(self, campaign_id: str) -> WP11CampaignSummary:
        return self._workflow.show(campaign_id)


def summary_from_publication(publication: TrustedCampaignPublicationV1) -> WP11CampaignSummary:
    seal = publication.seal
    return WP11CampaignSummary(
        campaign_id=seal.campaign_id,
        state="sealed",
        result_status=seal.result_status.value,
        mathematical_eligible=seal.mathematical_eligible,
        production_accepted=seal.production_accepted,
        session_count=len({item.session_id for item in seal.members}),
        stream_count=len(seal.members),
        scientific=publication.scientific,
        presentation=publication.presentation,
        outer_seal=publication.outer_seal,
    )
