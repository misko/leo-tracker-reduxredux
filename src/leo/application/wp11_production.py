"""Operational WP11 workflow over trusted composition and the processing catalog."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.exc import IntegrityError

from leo.analysis.starlink.acceptance import NATIVE_KNOWN_PILOT_EVIDENCE_STAGE
from leo.application.frequency_calibration import ImmutableDocumentRefV1
from leo.application.trusted_campaign import (
    ImmutableCaptureCampaignAuthority,
    TrustedCampaignMemberInput,
    TrustedCampaignPublicationV1,
)
from leo.application.trusted_campaign_production import TrustedCampaignService
from leo.application.wp11_operations import (
    WP11CampaignPlanV1,
    WP11CampaignSummary,
    WP11CreateResult,
    WP11PlanMemberV1,
    WP11QueueResult,
    summary_from_publication,
    validate_authoritative_plan,
    wp11_legacy_receipt_name,
    wp11_run_id,
)
from leo.catalog import (
    ActiveRunExistsError,
    CatalogNotFoundError,
    CatalogRepository,
    PromotionPolicy,
)
from leo.contracts.scientific import MatchedPilotAcceptanceConfigV1
from leo.processing import ProcessingService
from leo.qualification.scientific_campaign import campaign_config_from_accepted_capture
from leo.qualification.trusted_matched_recovery_stage import TRUSTED_MATCHED_RECOVERY_STAGE
from leo.qualification.wp11_plan_store import ImmutableWP11PlanStore

_STAGES = (NATIVE_KNOWN_PILOT_EVIDENCE_STAGE.key, TRUSTED_MATCHED_RECOVERY_STAGE.key)


class WP11RunConflict(RuntimeError):
    pass


class WP11ProductionWorkflow:
    """No raw authority leaves this application facade."""

    def __init__(
        self,
        *,
        plans: ImmutableWP11PlanStore,
        capture,
        catalog: CatalogRepository,
        processing: ProcessingService,
        trusted: TrustedCampaignService,
        pipeline_release_id: str,
    ) -> None:
        if type(capture) is not ImmutableCaptureCampaignAuthority:
            raise TypeError("WP11 workflow requires concrete accepted-capture authority")
        self._plans = plans
        self._capture = capture
        self._catalog = catalog
        self._processing = processing
        self._trusted = trusted
        self._pipeline_release_id = pipeline_release_id
        self._plan_authority = plans._bind_production_workflow(self)

    def create(
        self,
        *,
        campaign_id: str,
        capture: ImmutableDocumentRefV1,
        processing_config: MatchedPilotAcceptanceConfigV1,
    ) -> WP11CreateResult:
        receipt = self._capture.resolve(capture)
        campaign = campaign_config_from_accepted_capture(
            campaign_id=campaign_id,
            capture_receipt=receipt,
            detector_binding=processing_config.detector_binding,
        )
        if processing_config.detector_binding.pipeline_release != self._pipeline_release_id:
            raise ValueError("WP11 processing config differs from the deployed pipeline release")
        plan = WP11CampaignPlanV1.create(
            campaign_id=campaign_id,
            capture=capture,
            pipeline_release_id=self._pipeline_release_id,
            processing_config=processing_config,
            members=tuple(
                WP11PlanMemberV1(
                    ordinal=index,
                    inventory=item,
                    legacy_receipt_name=wp11_legacy_receipt_name(campaign_id, index),
                )
                for index, item in enumerate(campaign.capture_inventory)
            ),
        )
        ref = self._plans._publish_authoritative(self._plan_authority, self, plan)
        return WP11CreateResult(
            campaign_id=campaign_id,
            plan=ref,
            capture=capture,
            session_count=30,
            stream_count=40,
            pipeline_release_id=self._pipeline_release_id,
        )

    def queue(self, campaign_id: str) -> WP11QueueResult:
        plan, _ref = self._plans.load(campaign_id)
        validate_authoritative_plan(plan, self._capture)
        by_session: dict[str, list[WP11PlanMemberV1]] = defaultdict(list)
        for member in plan.members:
            by_session[member.inventory.session_id].append(member)
        run_ids: list[str] = []
        existing = 0
        for session_id, members in sorted(by_session.items()):
            run_id = wp11_run_id(campaign_id, session_id)
            run_ids.append(run_id)
            try:
                snapshot = self._catalog.run_seal_snapshot(run_id)
            except CatalogNotFoundError:
                try:
                    self._processing.create_reprocess_run(
                        run_id=run_id,
                        session_id=session_id,
                        pipeline_release_id=plan.pipeline_release_id,
                        input_manifest_digest=members[0].inventory.manifest_digest,
                        scope_keys=tuple(item.inventory.stream_id for item in members),
                        promotion_policy=PromotionPolicy.EVIDENCE_ONLY,
                        stage_keys=_STAGES,
                    )
                except (ActiveRunExistsError, IntegrityError) as error:
                    try:
                        winner = self._catalog.run_seal_snapshot(run_id)
                    except CatalogNotFoundError:
                        raise WP11RunConflict(
                            "another analysis run conflicts with deterministic WP11 queueing"
                        ) from error
                    self._validate_existing_run(winner, plan, members)
                    existing += 1
            else:
                self._validate_existing_run(snapshot, plan, members)
                existing += 1
        return WP11QueueResult(
            campaign_id=campaign_id,
            run_ids=tuple(run_ids),
            session_count=len(by_session),
            stream_count=len(plan.members),
            already_queued_count=existing,
        )

    def finalize(self, campaign_id: str) -> TrustedCampaignPublicationV1:
        plan, _ref = self._plans.load(campaign_id)
        validate_authoritative_plan(plan, self._capture)
        members: list[TrustedCampaignMemberInput] = []
        for item in plan.members:
            run_id = wp11_run_id(campaign_id, item.inventory.session_id)
            snapshot = self._catalog.run_seal_snapshot(run_id)
            products = tuple(
                product
                for product in snapshot.products
                if product.stage_key == TRUSTED_MATCHED_RECOVERY_STAGE.key
                and product.scope_key == item.inventory.stream_id
                and product.kind == "starlink.trusted-matched-recovery"
                and product.schema_version == 2
                and product.role == "scientific"
                and product.status == "complete"
                and product.available
            )
            if len(products) != 1:
                raise ValueError("WP11 finalization requires one sealed matched product per stream")
            members.append(
                TrustedCampaignMemberInput(
                    analysis_run_id=run_id,
                    analysis_product_id=products[0].product_id,
                    legacy_receipt_name=item.legacy_receipt_name,
                )
            )
        return self._trusted.finalize(
            campaign_id=campaign_id,
            capture_ref=plan.capture,
            members=tuple(members),
        )

    def show(self, campaign_id: str) -> WP11CampaignSummary:
        record = self._catalog.scientific_campaign(campaign_id)
        if record is not None and record.state == "sealed":
            return summary_from_publication(self._trusted.resolve(campaign_id))
        plan, _ref = self._plans.load(campaign_id)
        validate_authoritative_plan(plan, self._capture)
        queued = sum(
            1
            for session_id in {item.inventory.session_id for item in plan.members}
            if self._run_exists(wp11_run_id(campaign_id, session_id))
        )
        return WP11CampaignSummary(
            campaign_id=campaign_id,
            state="created" if queued == 0 else "processing",
            result_status=None,
            mathematical_eligible=None,
            production_accepted=None,
            session_count=30,
            stream_count=40,
        )

    def _run_exists(self, run_id: str) -> bool:
        try:
            self._catalog.run_seal_snapshot(run_id)
        except CatalogNotFoundError:
            return False
        return True

    @staticmethod
    def _validate_existing_run(snapshot, plan, members: list[WP11PlanMemberV1]) -> None:
        expected_jobs = {
            (stage, member.inventory.stream_id)
            for member in members
            for stage in _STAGES
        }
        execution = snapshot.execution
        if (
            execution.session_id != members[0].inventory.session_id
            or execution.pipeline_release_id != plan.pipeline_release_id
            or execution.input_manifest_digest != members[0].inventory.manifest_digest
            or execution.promotion_policy != PromotionPolicy.EVIDENCE_ONLY.value
            or {(job.stage_key, job.scope_key) for job in snapshot.jobs} != expected_jobs
        ):
            raise WP11RunConflict("existing WP11 run conflicts with immutable campaign plan")
