"""Catalog-backed retention, durable holds, and committed-bundle reconciliation."""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from leo.catalog import CatalogRepository, SessionState
from leo.catalog.errors import InvalidStateError
from leo.contracts.recording import RecordingManifestV1
from leo.operations.retention import (
    HoldReceipt,
    HoldReceiptStore,
    PurgeExecutor,
    PurgeReceipt,
    RetentionCandidate,
    RetentionDecision,
    StorageUsage,
    allocated_bytes,
    plan_retention,
)
from leo.storage import PublishedBundle, RecordingStore

FailureInjector = Callable[[str], None]


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
        lease_for: timedelta = timedelta(minutes=10),
        failure_injector: FailureInjector | None = None,
    ) -> None:
        if recordings.root != executor.bulk_root or holds.bulk_root != executor.bulk_root:
            raise ValueError("retention components must share one local bulk root")
        self._catalog = catalog
        self._recordings = recordings
        self._holds = holds
        self._executor = executor
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
        catalog_candidates = self._catalog.retention_candidates()
        candidates = tuple(
            RetentionCandidate(
                session_id=f"{item.kind}:{item.item_id}",
                created_utc_ns=int(item.created_at.timestamp() * 1_000_000_000),
                allocated_bytes=item.allocated_bytes,
            )
            for item in catalog_candidates
        )
        decision = plan_retention(self.storage_usage() if usage is None else usage, candidates)
        if dry_run or not decision.should_run:
            return RetentionRunResult(decision=decision, committed=(), failures=())

        committed: list[str] = []
        failures: list[str] = []
        for work_id in decision.selected_session_ids:
            kind, item_id = work_id.split(":", 1)
            try:
                accepted = (
                    self._purge_session(item_id)
                    if kind == "session"
                    else self._purge_artifact(int(item_id))
                )
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
    ) -> None:
        if recordings.root != holds.bulk_root:
            raise ValueError("reconciliation components must share one bulk root")
        self._catalog = catalog
        self._recordings = recordings
        self._holds = holds

    def run(self) -> CatalogReconcileReport:
        report = self._recordings.reconcile()
        registered: list[str] = []
        existing: list[str] = []
        issues = [f"{item.path}: {item.error}" for item in report.issues]
        for bundle in report.committed:
            inserted, error = self._register_bundle(bundle)
            if error is not None:
                issues.append(error)
                continue
            (registered if inserted else existing).append(bundle.session_id)
        return CatalogReconcileReport(
            registered=tuple(registered),
            existing=tuple(existing),
            issues=tuple(issues),
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
            return CatalogReconcileReport(registered=(), existing=(), issues=(registration_error,))
        return CatalogReconcileReport(
            registered=(session_id,) if inserted else (),
            existing=() if inserted else (session_id,),
            issues=(),
        )

    def _register_bundle(self, bundle: PublishedBundle) -> tuple[bool, str | None]:
        manifest = bundle.manifest
        source_type = manifest.source_type.value
        if source_type == "test" and not self._holds.contains(bundle.session_id):
            self._holds.put(
                HoldReceipt(
                    session_id=bundle.session_id,
                    reason="automatic TEST corpus hold",
                    actor="reconciliation",
                    created_utc_ns=time.time_ns(),
                )
            )
        try:
            inserted = self._catalog.reconcile_capture_session(
                session_id=bundle.session_id,
                source_type=source_type,
                bundle_uri=bundle.uri,
                manifest_digest=bundle.manifest_sha256,
                allocated_bytes=allocated_bytes(bundle.path),
                attributes={"reconciled": True},
                tags=manifest.tags,
                observed_start_at=_manifest_time(manifest, first=True),
                observed_end_at=_manifest_time(manifest, first=False),
                state=SessionState(manifest.state.value),
            )
        except Exception as error:
            return False, f"{bundle.path}: {type(error).__name__}: {error}"
        return inserted, None


def _manifest_time(
    manifest: RecordingManifestV1,
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
