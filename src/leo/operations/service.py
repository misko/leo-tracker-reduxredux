"""Catalog-backed retention, durable holds, and committed-bundle reconciliation."""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from leo.catalog import (
    CatalogRepository,
    RadioStreamRegistration,
    RecordingChunkRegistration,
    SessionState,
)
from leo.catalog.errors import InvalidStateError
from leo.contracts.recording import (
    RecordingManifestV1,
    RecordingManifestV3,
    RecordingManifestV4,
    RecordingStreamV1,
    RecordingStreamV3,
)
from leo.operations.retention import (
    HIGH_WATERMARK,
    HoldReceipt,
    HoldReceiptStore,
    PersistentHopPurgeTombstone,
    PersistentHopPurgeTombstoneStore,
    PurgeExecutor,
    PurgeReceipt,
    RetentionCandidate,
    RetentionDecision,
    ScannerPurgeTombstone,
    ScannerPurgeTombstoneStore,
    StorageUsage,
    allocated_bytes,
    plan_retention,
)
from leo.station.resolver import ResolvedCaptureAuthority, UnreviewedTestFixtureAuthorityError
from leo.storage import (
    PersistentHopIqStore,
    PublishedBundle,
    ReconcileIssueKind,
    RecordingStore,
    ScannerAnalysisStore,
    ScannerIqStore,
    ScannerRunStore,
)

FailureInjector = Callable[[str], None]


class CaptureAuthorityResolver(Protocol):
    def resolve(
        self,
        manifest: RecordingManifestV1 | RecordingManifestV3 | RecordingManifestV4,
        *,
        observed_manifest_file_digest: str,
    ) -> ResolvedCaptureAuthority: ...


@dataclass(frozen=True, slots=True)
class RetentionRunResult:
    decision: RetentionDecision
    committed: tuple[str, ...]
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    restored: tuple[str, ...]
    discarded: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CatalogReconcileReport:
    registered: tuple[str, ...]
    existing: tuple[str, ...]
    issues: tuple[str, ...]
    historical_incompatibilities: tuple[str, ...] = ()


class CatalogHoldService:
    """Preserve the fail-safe ordering between durable evidence and catalog state."""

    def __init__(
        self,
        catalog: CatalogRepository,
        receipts: HoldReceiptStore,
        *,
        failure_injector: FailureInjector | None = None,
    ) -> None:
        self._catalog = catalog
        self._receipts = receipts
        self._failure_injector = failure_injector

    def add(self, *, session_id: str, reason: str, actor: str) -> int:
        self._receipts.put(
            HoldReceipt(
                session_id=session_id,
                reason=reason,
                actor=actor,
                created_utc_ns=time.time_ns(),
            )
        )
        self._inject("hold:after_receipt")
        return self._catalog.add_retention_hold(
            session_id=session_id,
            reason=reason,
            created_by=actor,
        )

    def release(self, *, session_id: str) -> bool:
        released = self._catalog.release_retention_hold(session_id=session_id)
        self._inject("hold:after_catalog_release")
        self._receipts.remove_after_catalog_deactivation(session_id)
        return released

    def _inject(self, point: str) -> None:
        if self._failure_injector is not None:
            self._failure_injector(point)


class CatalogRetentionService:
    """Run watermarked retention as small, fenced session/artifact transactions."""

    def __init__(
        self,
        catalog: CatalogRepository,
        recordings: RecordingStore,
        holds: HoldReceiptStore,
        executor: PurgeExecutor,
        *,
        scanner_iq: ScannerIqStore | None = None,
        scanner_analysis: ScannerAnalysisStore | None = None,
        scanner_runs: ScannerRunStore | None = None,
        scanner_tombstones: ScannerPurgeTombstoneStore | None = None,
        scanner_analysis_ids: tuple[str, ...] = (),
        persistent_hop_iq: PersistentHopIqStore | None = None,
        persistent_hop_tombstones: PersistentHopPurgeTombstoneStore | None = None,
        lease_for: timedelta = timedelta(minutes=10),
        failure_injector: FailureInjector | None = None,
    ) -> None:
        if recordings.root != executor.bulk_root or holds.bulk_root != executor.bulk_root:
            raise ValueError("retention components must share one local bulk root")
        scanner_components = (scanner_iq, scanner_analysis, scanner_runs, scanner_tombstones)
        if any(item is not None for item in scanner_components) != all(
            item is not None for item in scanner_components
        ):
            raise ValueError("scanner retention components must be configured together")
        if scanner_iq is not None:
            assert (
                scanner_analysis is not None
                and scanner_runs is not None
                and scanner_tombstones is not None
            )
            if (
                scanner_iq.root != executor.bulk_root
                or scanner_analysis.root != executor.bulk_root
                or scanner_runs.root != executor.bulk_root
                or scanner_tombstones.bulk_root != executor.bulk_root
            ):
                raise ValueError("scanner retention components must share one local bulk root")
            if not scanner_analysis_ids:
                raise ValueError("scanner retention requires allowed analysis IDs")
        persistent_hop_components = (persistent_hop_iq, persistent_hop_tombstones)
        if any(item is not None for item in persistent_hop_components) != all(
            item is not None for item in persistent_hop_components
        ):
            raise ValueError("persistent-hop retention components must be configured together")
        if persistent_hop_iq is not None:
            assert persistent_hop_tombstones is not None
            if (
                persistent_hop_iq.root != executor.bulk_root
                or persistent_hop_tombstones.bulk_root != executor.bulk_root
            ):
                raise ValueError(
                    "persistent-hop retention components must share one local bulk root"
                )
        self._catalog = catalog
        self._recordings = recordings
        self._holds = holds
        self._executor = executor
        self._scanner_iq = scanner_iq
        self._scanner_analysis = scanner_analysis
        self._scanner_runs = scanner_runs
        self._scanner_tombstones = scanner_tombstones
        self._scanner_analysis_ids = scanner_analysis_ids
        self._persistent_hop_iq = persistent_hop_iq
        self._persistent_hop_tombstones = persistent_hop_tombstones
        self._lease_for = lease_for
        self._failure_injector = failure_injector

    def storage_usage(self) -> StorageUsage:
        status = os.statvfs(self._executor.bulk_root)
        total = status.f_frsize * status.f_blocks
        available = status.f_frsize * status.f_bavail
        return StorageUsage(total_bytes=total, used_bytes=total - available)

    def run(
        self, usage: StorageUsage | None = None, *, dry_run: bool = False
    ) -> RetentionRunResult:
        selected_usage = self.storage_usage() if usage is None else usage
        catalog_candidates = self._catalog.retention_candidates()
        candidates = [
            RetentionCandidate(
                session_id=f"{item.kind}:{item.item_id}",
                created_utc_ns=int(item.created_at.timestamp() * 1_000_000_000),
                allocated_bytes=item.allocated_bytes,
            )
            for item in catalog_candidates
        ]
        scanner_inputs: dict[str, tuple[str, str]] = {}
        persistent_hop_inputs: dict[str, tuple[str, str]] = {}
        if selected_usage.fraction >= HIGH_WATERMARK:
            scanner_candidates, scanner_inputs = self._scanner_retention_candidates()
            candidates.extend(scanner_candidates)
            persistent_hop_candidates, persistent_hop_inputs = (
                self._persistent_hop_retention_candidates()
            )
            candidates.extend(persistent_hop_candidates)
        decision = plan_retention(selected_usage, tuple(candidates))
        if dry_run or not decision.should_run:
            return RetentionRunResult(decision=decision, committed=(), failures=())

        committed: list[str] = []
        failures: list[str] = []
        for work_id in decision.selected_session_ids:
            kind, item_id = work_id.split(":", 1)
            try:
                if kind == "session":
                    accepted = self._purge_session(item_id)
                elif kind == "artifact":
                    accepted = self._purge_artifact(int(item_id))
                elif kind == "scanner":
                    expected_input = scanner_inputs.get(item_id)
                    if expected_input is None:
                        raise InvalidStateError(
                            "scanner retention candidate lost its completed-run fence"
                        )
                    accepted = self._purge_scanner(item_id, expected_input=expected_input)
                elif kind == "persistent-hop":
                    expected_input = persistent_hop_inputs.get(item_id)
                    if expected_input is None:
                        raise InvalidStateError(
                            "persistent-hop retention candidate lost its qualification fence"
                        )
                    accepted = self._purge_persistent_hop(
                        item_id,
                        expected_input=expected_input,
                    )
                else:
                    raise ValueError(f"unknown retention candidate kind: {kind}")
            except Exception as error:
                failures.append(f"{work_id}: {type(error).__name__}: {error}")
            else:
                if accepted:
                    committed.append(work_id)
        return RetentionRunResult(
            decision=decision,
            committed=tuple(committed),
            failures=tuple(failures),
        )

    def recover(self) -> RecoveryResult:
        restored: list[str] = []
        discarded: list[str] = []
        for receipt in self._executor.pending():
            if receipt.kind == "persistent-hop":
                if self._persistent_hop_tombstones is None:
                    raise RuntimeError("persistent-hop purge recovery is not configured")
                identity = f"persistent-hop:{receipt.item_id}"
                if self._persistent_hop_tombstones.commits(receipt):
                    self._executor.discard_staged(receipt)
                    discarded.append(identity)
                else:
                    self._executor.restore(receipt)
                    restored.append(identity)
                continue
            if receipt.kind == "scanner":
                if self._scanner_tombstones is None:
                    raise RuntimeError("scanner purge recovery is not configured")
                identity = f"scanner:{receipt.item_id}"
                if self._scanner_tombstones.commits(receipt):
                    self._executor.discard_staged(receipt)
                    discarded.append(identity)
                else:
                    self._executor.restore(receipt)
                    restored.append(identity)
                continue
            disposition = self._catalog.purge_disposition(
                kind=receipt.kind,
                item_id=receipt.item_id,
                claim_token=receipt.claim_token,
            )
            identity = f"{receipt.kind}:{receipt.item_id}"
            if disposition == "discard":
                reclaimed = self._executor.discard_staged(receipt)
                self._catalog.record_purge_discarded(
                    session_id=receipt.session_id,
                    kind=receipt.kind,
                    item_id=receipt.item_id,
                    claim_token=receipt.claim_token,
                    bytes_reclaimed=reclaimed,
                )
                discarded.append(identity)
                continue
            self._executor.restore(receipt)
            if receipt.kind == "session":
                self._catalog.release_session_purge_claim(
                    session_id=receipt.item_id,
                    claim_token=receipt.claim_token,
                )
            else:
                self._catalog.release_product_purge_claim(
                    product_id=int(receipt.item_id),
                    claim_token=receipt.claim_token,
                )
            restored.append(identity)
        return RecoveryResult(restored=tuple(restored), discarded=tuple(discarded))

    def _scanner_retention_candidates(
        self,
    ) -> tuple[tuple[RetentionCandidate, ...], dict[str, tuple[str, str]]]:
        if self._scanner_iq is None or self._scanner_analysis is None or self._scanner_runs is None:
            return (), {}
        completed_inputs: dict[str, tuple[str, str]] = {}
        for run_id in self._scanner_runs.run_ids():
            run = self._scanner_runs.inspect(run_id)
            if run.manifest.status != "complete":
                continue
            for sweep in run.manifest.sweeps:
                if sweep.iq_bundle_uri is None or sweep.iq_manifest_sha256 is None:
                    continue
                reference = (sweep.iq_bundle_uri, sweep.iq_manifest_sha256)
                previous = completed_inputs.setdefault(sweep.scan_id, reference)
                if previous != reference:
                    raise InvalidStateError("completed scanner runs disagree about one IQ bundle")
        candidates: list[RetentionCandidate] = []
        for scan_id in self._scanner_iq.recording_ids():
            bundle = self._scanner_iq.inspect(scan_id)
            if completed_inputs.get(scan_id) != (bundle.uri, bundle.manifest_sha256):
                continue
            if not self._scanner_analysis.has_matching_input(
                scan_id,
                self._scanner_analysis_ids,
                input_uri=bundle.uri,
                input_manifest_sha256=bundle.manifest_sha256,
                verify_products=False,
            ):
                continue
            candidates.append(
                RetentionCandidate(
                    session_id=f"scanner:{scan_id}",
                    created_utc_ns=bundle.manifest.created_utc_ns,
                    allocated_bytes=allocated_bytes(bundle.path),
                )
            )
        return tuple(candidates), completed_inputs

    def _persistent_hop_retention_candidates(
        self,
    ) -> tuple[tuple[RetentionCandidate, ...], dict[str, tuple[str, str]]]:
        if self._persistent_hop_iq is None:
            return (), {}
        candidates: list[RetentionCandidate] = []
        qualified_inputs: dict[str, tuple[str, str]] = {}
        for session_id in self._persistent_hop_iq.session_ids():
            bundle = self._persistent_hop_iq.inspect(session_id)
            if not bundle.manifest.receipt.qualified:
                continue
            qualified_inputs[session_id] = (bundle.uri, bundle.manifest_sha256)
            candidates.append(
                RetentionCandidate(
                    session_id=f"persistent-hop:{session_id}",
                    created_utc_ns=bundle.manifest.created_utc_ns,
                    allocated_bytes=allocated_bytes(bundle.path),
                    held=self._holds.contains(session_id),
                )
            )
        return tuple(candidates), qualified_inputs

    def _purge_session(self, session_id: str) -> bool:
        token = uuid.uuid4().hex
        claim = self._catalog.claim_session_for_purge(
            session_id=session_id,
            claim_token=token,
            lease_for=self._lease_for,
        )
        if claim is None:
            return False
        receipt: PurgeReceipt | None = None
        try:
            bundle = self._recordings.inspect_uri(claim.bundle_uri)
            if bundle.session_id != session_id:
                raise InvalidStateError("recording identity changed after purge claim")
            receipt = self._executor.stage(bundle.path, session_id, token)
            self._inject("session:after_stage")
            self._catalog.commit_session_purge(
                session_id=session_id,
                claim_token=token,
                staged_bytes=receipt.staged_bytes,
                recording_manifest=bundle.manifest.model_dump(mode="json"),
                recording_root=receipt.original_path,
                durable_hold_present=self._holds.contains,
            )
            self._inject("session:after_commit")
            return True
        except Exception:
            self._restore_if_uncommitted(receipt, kind="session", item_id=session_id, token=token)
            raise

    def _purge_artifact(self, product_id: int) -> bool:
        token = uuid.uuid4().hex
        claim = self._catalog.claim_product_for_purge(
            product_id=product_id,
            claim_token=token,
            lease_for=self._lease_for,
        )
        if claim is None:
            return False
        receipt: PurgeReceipt | None = None
        try:
            path = self._recordings.resolver.resolve(claim.product.logical_uri, must_exist=True)
            receipt = self._executor.stage_artifact(
                path,
                product_id=product_id,
                session_id=claim.session_id,
                claim_token=token,
            )
            self._inject("artifact:after_stage")
            self._catalog.commit_product_purge(
                product_id=product_id,
                claim_token=token,
                staged_bytes=receipt.staged_bytes,
            )
            self._inject("artifact:after_commit")
            return True
        except Exception:
            self._restore_if_uncommitted(
                receipt,
                kind="artifact",
                item_id=str(product_id),
                token=token,
            )
            raise

    def _purge_scanner(
        self,
        scan_id: str,
        *,
        expected_input: tuple[str, str],
    ) -> bool:
        if (
            self._scanner_iq is None
            or self._scanner_analysis is None
            or self._scanner_tombstones is None
        ):
            raise RuntimeError("scanner retention is not configured")
        token = uuid.uuid4().hex
        bundle = self._scanner_iq.inspect(scan_id)
        if (bundle.uri, bundle.manifest_sha256) != expected_input:
            raise InvalidStateError("scanner IQ changed after retention selection")
        if not self._scanner_analysis.has_matching_input(
            scan_id,
            self._scanner_analysis_ids,
            input_uri=bundle.uri,
            input_manifest_sha256=bundle.manifest_sha256,
            verify_products=True,
        ):
            return False
        receipt: PurgeReceipt | None = None
        try:
            receipt = self._executor.stage_scanner(
                bundle.path,
                scan_id=scan_id,
                claim_token=token,
            )
            self._inject("scanner:after_stage")
            self._scanner_tombstones.put(
                ScannerPurgeTombstone(
                    schema_version=1,
                    scan_id=scan_id,
                    claim_token=token,
                    iq_bundle_uri=bundle.uri,
                    iq_manifest_sha256=bundle.manifest_sha256,
                    iq_manifest=bundle.manifest.model_dump(mode="json"),
                    original_path=receipt.original_path,
                    staged_bytes=receipt.staged_bytes,
                    purged_utc_ns=time.time_ns(),
                )
            )
            self._inject("scanner:after_commit")
            return True
        except Exception:
            if receipt is not None and not self._scanner_tombstones.commits(receipt):
                self._executor.restore(receipt)
            raise

    def _purge_persistent_hop(
        self,
        session_id: str,
        *,
        expected_input: tuple[str, str],
    ) -> bool:
        if self._persistent_hop_iq is None or self._persistent_hop_tombstones is None:
            raise RuntimeError("persistent-hop retention is not configured")
        token = uuid.uuid4().hex
        bundle = self._persistent_hop_iq.inspect(session_id)
        if (bundle.uri, bundle.manifest_sha256) != expected_input:
            raise InvalidStateError("persistent-hop IQ changed after retention selection")
        if not bundle.manifest.receipt.qualified or self._holds.contains(session_id):
            return False
        receipt: PurgeReceipt | None = None
        try:
            receipt = self._executor.stage_persistent_hop(
                bundle.path,
                session_id=session_id,
                claim_token=token,
            )
            self._inject("persistent-hop:after_stage")
            if self._holds.contains(session_id):
                raise InvalidStateError("durable hold won the persistent-hop purge fence")
            self._persistent_hop_tombstones.put(
                PersistentHopPurgeTombstone(
                    schema_version=1,
                    session_id=session_id,
                    claim_token=token,
                    iq_bundle_uri=bundle.uri,
                    iq_manifest_sha256=bundle.manifest_sha256,
                    iq_manifest=bundle.manifest.model_dump(mode="json"),
                    original_path=receipt.original_path,
                    staged_bytes=receipt.staged_bytes,
                    purged_utc_ns=time.time_ns(),
                )
            )
            self._inject("persistent-hop:after_commit")
            return True
        except Exception:
            if receipt is not None and not self._persistent_hop_tombstones.commits(receipt):
                self._executor.restore(receipt)
            raise

    def _restore_if_uncommitted(
        self,
        receipt: PurgeReceipt | None,
        *,
        kind: str,
        item_id: str,
        token: str,
    ) -> None:
        disposition = self._catalog.purge_disposition(
            kind=kind,
            item_id=item_id,
            claim_token=token,
        )
        if disposition == "discard":
            return
        if receipt is not None:
            self._executor.restore(receipt)
        if kind == "session":
            self._catalog.release_session_purge_claim(session_id=item_id, claim_token=token)
        else:
            self._catalog.release_product_purge_claim(product_id=int(item_id), claim_token=token)

    def _inject(self, point: str) -> None:
        if self._failure_injector is not None:
            self._failure_injector(point)


class CatalogReconciliationService:
    """Register valid public bundles that committed before their catalog transaction."""

    def __init__(
        self,
        catalog: CatalogRepository,
        recordings: RecordingStore,
        holds: HoldReceiptStore,
        authority_resolver: CaptureAuthorityResolver | None = None,
        require_authority: bool = False,
    ) -> None:
        if recordings.root != holds.bulk_root:
            raise ValueError("reconciliation components must share one bulk root")
        self._catalog = catalog
        self._recordings = recordings
        self._holds = holds
        self._authority_resolver = authority_resolver
        self._require_authority = require_authority

    def run(self) -> CatalogReconcileReport:
        report = self._recordings.reconcile()
        registered: list[str] = []
        existing: list[str] = []
        issues = [
            f"{item.path}: {item.error}"
            for item in report.issues
            if item.kind is ReconcileIssueKind.INSPECTION_FAILURE
        ]
        historical_incompatibilities = [
            f"{item.path}: {item.error}"
            for item in report.issues
            if item.kind is ReconcileIssueKind.INCOMPATIBLE_MANIFEST
        ]
        for bundle in report.committed:
            inserted, error = self._register_bundle(bundle)
            if error is not None:
                destination = (
                    historical_incompatibilities
                    if isinstance(error, UnreviewedTestFixtureAuthorityError)
                    or self._is_exact_cataloged_legacy_manifest(bundle, error)
                    else issues
                )
                destination.append(_registration_error(bundle, error))
                continue
            (registered if inserted else existing).append(bundle.session_id)
        return CatalogReconcileReport(
            registered=tuple(registered),
            existing=tuple(existing),
            issues=tuple(issues),
            historical_incompatibilities=tuple(historical_incompatibilities),
        )

    def _is_exact_cataloged_legacy_manifest(
        self, bundle: PublishedBundle, error: Exception
    ) -> bool:
        """Classify only an exact cataloged pre-canonical manifest as historical."""

        if not (
            isinstance(error, ValueError)
            and str(error)
            == "observed manifest-file digest does not match canonical RecordingManifestV1"
        ):
            return False
        try:
            identity = self._catalog.capture_recording_identity(bundle.session_id)
        except Exception:
            return False
        return (
            identity.bundle_uri == bundle.uri and identity.manifest_digest == bundle.manifest_sha256
        )

    def run_session(self, session_id: str) -> CatalogReconcileReport:
        """Register one newly committed bundle without rescanning the archive."""

        try:
            bundle = self._recordings.inspect(session_id)
        except Exception as error:
            return CatalogReconcileReport(
                registered=(),
                existing=(),
                issues=(f"{session_id}: {type(error).__name__}: {error}",),
            )
        inserted, registration_error = self._register_bundle(bundle)
        if registration_error is not None:
            return CatalogReconcileReport(
                registered=(),
                existing=(),
                issues=(_registration_error(bundle, registration_error),),
            )
        return CatalogReconcileReport(
            registered=(session_id,) if inserted else (),
            existing=() if inserted else (session_id,),
            issues=(),
        )

    def _register_bundle(self, bundle: PublishedBundle) -> tuple[bool, Exception | None]:
        manifest = bundle.manifest
        source_type = manifest.source_type.value
        protected_evidence_tags = {"CALIBRATION", "ACCEPTANCE"}.intersection(manifest.tags)
        hold_reason = (
            "automatic TEST corpus hold"
            if source_type == "test"
            else "automatic selected qualification evidence hold"
        )
        if (source_type == "test" or protected_evidence_tags) and not self._holds.contains(
            bundle.session_id
        ):
            self._holds.put(
                HoldReceipt(
                    session_id=bundle.session_id,
                    reason=hold_reason,
                    actor="reconciliation",
                    created_utc_ns=time.time_ns(),
                )
            )
        try:
            if self._authority_resolver is None and self._require_authority:
                raise InvalidStateError("capture path authority resolver is not configured")
            resolved_authority = (
                None
                if self._authority_resolver is None
                else self._authority_resolver.resolve(
                    manifest,
                    observed_manifest_file_digest=bundle.manifest_sha256,
                )
            )
            if resolved_authority is not None and resolved_authority.topology is not None:
                self._catalog.register_station_topology(resolved_authority.topology)
            inserted = self._catalog.reconcile_capture_session(
                session_id=bundle.session_id,
                source_type=source_type,
                bundle_uri=bundle.uri,
                manifest_digest=bundle.manifest_sha256,
                allocated_bytes=allocated_bytes(bundle.path),
                attributes={
                    "reconciled": True,
                    "presentation": _manifest_presentation(manifest),
                },
                tags=manifest.tags,
                observed_start_at=_manifest_time(manifest, first=True),
                observed_end_at=_manifest_time(manifest, first=False),
                state=SessionState(manifest.state.value),
                streams=_stream_registrations(bundle),
                path_authority=(
                    None if resolved_authority is None else resolved_authority.path_authority
                ),
            )
        except Exception as error:
            return False, error
        return inserted, None


def _registration_error(bundle: PublishedBundle, error: Exception) -> str:
    return f"{bundle.path}: {type(error).__name__}: {error}"


def _manifest_time(
    manifest: RecordingManifestV1 | RecordingManifestV3 | RecordingManifestV4,
    *,
    first: bool,
) -> datetime | None:
    estimates = tuple(
        (
            stream.timing.first_sample.estimate_utc_ns
            if first
            else stream.timing.last_sample.estimate_utc_ns
        )
        for stream in manifest.streams
        if stream.timing is not None
    )
    if not estimates:
        return None
    nanoseconds = min(estimates) if first else max(estimates)
    seconds, remainder = divmod(nanoseconds, 1_000_000_000)
    return datetime.fromtimestamp(seconds, UTC) + timedelta(microseconds=remainder // 1000)


def _stream_registrations(bundle: PublishedBundle) -> tuple[RadioStreamRegistration, ...]:
    values: list[RadioStreamRegistration] = []
    ordered_streams = _ordered_manifest_streams(bundle.manifest)
    for manifest_ordinal, stream in enumerate(ordered_streams):
        timing = stream.timing
        applied = stream.applied_settings
        sample_rate_hz = (
            applied.sample_rate_hz
            if applied is not None
            else stream.requested_settings.sample_rate_hz
        )
        receiver_ids = (
            applied.receiver_ids if applied is not None else stream.requested_settings.receiver_ids
        )
        sample_ns = (1_000_000_000 + sample_rate_hz - 1) // sample_rate_hz
        attributes: dict[str, Any] = {
            "requested_settings": stream.requested_settings.model_dump(mode="json"),
            "applied_settings": None if applied is None else applied.model_dump(mode="json"),
            "timing": None if timing is None else timing.model_dump(mode="json"),
            "capture_start_utc_ns": (
                None if timing is None else timing.first_sample.earliest_utc_ns
            ),
            "capture_end_utc_ns": (
                None if timing is None else timing.last_sample.latest_utc_ns + sample_ns
            ),
            "continuity": stream.continuity.model_dump(mode="json"),
            "timeline_relative_path": stream.timeline_relative_path,
            "timeline_sha256": stream.timeline_sha256,
        }
        if isinstance(stream, RecordingStreamV3):
            captured_sample_count = stream.observed_sample_count
            attributes.update(
                {
                    "logical_sample_count": stream.logical_sample_count,
                    "observed_sample_count": stream.observed_sample_count,
                    "zero_fill_sample_count": stream.zero_fill_sample_count,
                    "observed_iq_sha256": stream.observed_iq_sha256,
                    "logical_iq_sha256": stream.logical_iq_sha256,
                    "gap_map_relative_path": stream.gap_map_relative_path,
                    "gap_map_sha256": stream.gap_map_sha256,
                    "validity_inventory_relative_path": (stream.validity_inventory_relative_path),
                    "validity_inventory_sha256": stream.validity_inventory_sha256,
                }
            )
            chunks = tuple(
                RecordingChunkRegistration(
                    chunk_index=chunk.chunk_index,
                    sample_start=chunk.device_sample_start,
                    sample_count=chunk.sample_count,
                    logical_uri=f"{bundle.uri.rstrip('/')}/{chunk.relative_path}",
                    compressed_digest=chunk.compressed_sha256,
                    uncompressed_digest=chunk.uncompressed_sha256,
                    compressed_bytes=chunk.compressed_bytes,
                    uncompressed_bytes=chunk.uncompressed_bytes,
                )
                for chunk in stream.chunks
            )
        else:
            captured_sample_count = stream.captured_sample_count
            chunks = tuple(
                RecordingChunkRegistration(
                    chunk_index=chunk.chunk_index,
                    sample_start=chunk.sample_start,
                    sample_count=chunk.sample_count,
                    logical_uri=f"{bundle.uri.rstrip('/')}/{chunk.relative_path}",
                    compressed_digest=chunk.compressed_sha256,
                    uncompressed_digest=chunk.uncompressed_sha256,
                    compressed_bytes=chunk.compressed_bytes,
                    uncompressed_bytes=chunk.uncompressed_bytes,
                )
                for chunk in stream.chunks
            )
        values.append(
            RadioStreamRegistration(
                stream_id=stream.stream_id,
                manifest_ordinal=manifest_ordinal,
                radio_id=stream.radio.radio_id,
                radio_serial=stream.radio.serial,
                radio_uri=stream.radio.uri,
                radio_transport=stream.radio.transport.value,
                state=stream.state.value,
                receiver_ids=receiver_ids,
                sample_rate_hz=sample_rate_hz,
                captured_sample_count=captured_sample_count,
                observed_start_at=(
                    None if timing is None else _utc_datetime(timing.first_sample.estimate_utc_ns)
                ),
                observed_end_at=(
                    None if timing is None else _utc_datetime(timing.last_sample.estimate_utc_ns)
                ),
                attributes=attributes,
                chunks=chunks,
            )
        )
    return tuple(values)


def _ordered_manifest_streams(
    manifest: RecordingManifestV1 | RecordingManifestV3 | RecordingManifestV4,
) -> tuple[RecordingStreamV1 | RecordingStreamV3, ...]:
    if isinstance(manifest, (RecordingManifestV3, RecordingManifestV4)):
        return tuple(
            sorted(
                manifest.streams,
                key=lambda item: (item.stream_id, item.radio.radio_id),
            )
        )
    return tuple(
        sorted(
            manifest.streams,
            key=lambda item: (item.stream_id, item.radio.radio_id),
        )
    )


def _manifest_presentation(
    manifest: RecordingManifestV1 | RecordingManifestV3 | RecordingManifestV4,
) -> dict[str, object]:
    if isinstance(manifest, RecordingManifestV4):
        rates = tuple(item.requested_settings.sample_rate_hz for item in manifest.streams)
        rate_label = "/".join(f"{rate / 1_000_000:g}M" for rate in rates)
        return {
            "title": f"Mixed-rate {rate_label} native dwell",
            "profile_name": manifest.capture_plan.dwell_class.value,
            "duration_seconds": float(manifest.capture_plan.duration_seconds),
        }
    profile = manifest.capture_plan.profile_revision.profile
    return {
        "title": profile.description or profile.name,
        "profile_name": profile.name,
        "duration_seconds": manifest.capture_plan.resolved_sample_count / profile.sample_rate_hz,
    }


def _utc_datetime(utc_ns: int) -> datetime:
    seconds, remainder = divmod(utc_ns, 1_000_000_000)
    return datetime.fromtimestamp(seconds, UTC) + timedelta(microseconds=remainder // 1_000)
