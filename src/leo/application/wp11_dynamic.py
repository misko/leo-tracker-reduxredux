"""Campaign-plan-bound dynamic analyzers for the ordinary processing worker."""

from __future__ import annotations

from collections.abc import Callable

from leo.application.frequency_calibration import NativeReleaseCalibrationEvidenceAdapter
from leo.application.trusted_campaign import ImmutableCaptureCampaignAuthority
from leo.application.trusted_matched_recovery import (
    PinnedLegacyOracleAuthority,
    PostgresAuthoritativeCalibrationScope,
    wp11_trusted_matched_registry,
)
from leo.application.wp11_operations import (
    WP11CampaignPlanV1,
    WP11CaptureAuthorityPort,
    validate_authoritative_plan,
    wp11_run_id,
)
from leo.artifacts import AnalysisArtifactStore
from leo.pipeline import (
    AnalysisContext,
    Analyzer,
    AnalyzerRegistry,
    IqReader,
    OutputSink,
    ProductReader,
    StageResult,
)
from leo.qualification.native_execution import ReleaseLocalNativeEvidenceExecutor
from leo.qualification.wp11_plan_store import ImmutableWP11PlanStore
from leo.storage import RecordingStore

AnalyzerFactory = Callable[[WP11CampaignPlanV1, str], Analyzer]


class WP11ProductionDelegateFactory:
    """Cache only analyzer composition; every invocation still resolves plan/run binding."""

    def __init__(
        self,
        *,
        scopes: PostgresAuthoritativeCalibrationScope,
        legacy: PinnedLegacyOracleAuthority,
        releases: NativeReleaseCalibrationEvidenceAdapter,
        executor: ReleaseLocalNativeEvidenceExecutor,
        recordings: RecordingStore,
        artifacts: AnalysisArtifactStore,
    ) -> None:
        self._scopes = scopes
        self._legacy = legacy
        self._releases = releases
        self._executor = executor
        self._recordings = recordings
        self._artifacts = artifacts
        self._registries: dict[str, tuple[str, AnalyzerRegistry]] = {}

    def __call__(self, plan: WP11CampaignPlanV1, stage_key: str) -> Analyzer:
        cached = self._registries.get(plan.campaign_id)
        if cached is not None and cached[0] != plan.plan_digest:
            raise ValueError("WP11 campaign plan changed after analyzer composition")
        registry = None if cached is None else cached[1]
        if registry is None:
            composition = wp11_trusted_matched_registry(
                config=plan.processing_config,
                scopes=self._scopes,
                legacy=self._legacy,
                receipt_names={
                    (item.inventory.session_id, item.inventory.stream_id): item.legacy_receipt_name
                    for item in plan.members
                },
                releases=self._releases,
                executor=self._executor,
                recordings=self._recordings,
                artifacts=self._artifacts,
            )
            registry = composition.registry
            self._registries[plan.campaign_id] = (plan.plan_digest, registry)
        return registry.get(stage_key)


class DynamicWP11Analyzer:
    """Resolve an immutable plan for each claimed job, then delegate exactly once."""

    def __init__(
        self,
        spec,
        plans: ImmutableWP11PlanStore,
        capture: WP11CaptureAuthorityPort,
        factory: AnalyzerFactory,
    ) -> None:
        if type(capture) is not ImmutableCaptureCampaignAuthority:
            raise TypeError("dynamic WP11 analyzer requires concrete capture authority")
        self.spec = spec
        self._plans = plans
        self._capture = capture
        self._factory = factory

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        plan = self._plan_for_context(context)
        delegate = self._factory(plan, self.spec.key)
        if delegate.spec != self.spec:
            raise ValueError("dynamic WP11 delegate has a different frozen stage specification")
        return delegate.analyze(context, iq, products, outputs)

    def _plan_for_context(self, context: AnalysisContext) -> WP11CampaignPlanV1:
        # Plans are bounded at forty members; scanning avoids a mutable reverse index.
        # The run ID itself is content-derived, so unrelated plans cannot claim it.
        plan, _ref = self._plans.load_for_run(context.run_id)
        validate_authoritative_plan(plan, self._capture)
        if not any(
            item.inventory.session_id == context.session_id
            and item.inventory.stream_id == context.scope_key
            for item in plan.members
        ):
            raise ValueError("WP11 analysis scope is absent from its immutable campaign plan")
        if (
            wp11_run_id(plan.campaign_id, context.session_id) != context.run_id
            or plan.pipeline_release_id != context.pipeline_release
        ):
            raise ValueError("WP11 analysis run is retargeted from its immutable campaign plan")
        return plan
