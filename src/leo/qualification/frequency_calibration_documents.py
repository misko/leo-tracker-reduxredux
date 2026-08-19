"""Immutable local predeclaration and analysis-product document adapters."""

from __future__ import annotations

import os
import re
import stat
import time
from collections.abc import Callable
from pathlib import Path

from leo.application.frequency_calibration import (
    ImmutableDocumentRefV1,
    TrustedImmutableDocumentV1,
)
from leo.artifacts import AnalysisArtifactStore
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.qualification.frequency_calibration import FrequencyCalibrationPlanV1
from leo.qualification.native_release import _beneath_qnap, _open_absolute_directory

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_BYTES = 64 * 1024 * 1024


class ImmutableCalibrationPlanStore:
    """Create-only local plan store whose seal time is part of stored evidence."""

    def __init__(self, root: Path, *, clock_ns=time.time_ns) -> None:
        if not root.is_absolute() or _beneath_qnap(root):
            raise ValueError("calibration plan root must be absolute local storage")
        self._root_fd = _open_absolute_directory(root)
        self.root = root
        self._clock_ns = clock_ns

    def publish(
        self,
        plan: FrequencyCalibrationPlanV1,
    ) -> ImmutableDocumentRefV1:
        sealed_utc_ns = self._clock_ns()
        if sealed_utc_ns > plan.declared_utc_ns:
            raise ValueError("calibration plan store seal must be no later than declaration")
        return self._publish(plan, sealed_utc_ns)

    def publish_builder(
        self,
        plan_id: str,
        builder: Callable[[int], FrequencyCalibrationPlanV1],
    ) -> ImmutableDocumentRefV1:
        if _SAFE_ID.fullmatch(plan_id) is None:
            raise ValueError("calibration plan id is unsafe")
        try:
            existing = self._load_id(plan_id)
        except FileNotFoundError:
            sealed_utc_ns = self._clock_ns()
            plan = builder(sealed_utc_ns)
            if plan.plan_id != plan_id or plan.declared_utc_ns != sealed_utc_ns:
                raise ValueError(
                    "predeclaration builder differs from store identity/time"
                ) from None
            return self._publish(plan, sealed_utc_ns)
        proposed = builder(existing.sealed_utc_ns)
        if proposed.model_dump(mode="json") != existing.document:
            raise ValueError("calibration plan id already contains different content")
        return ImmutableDocumentRefV1(logical_uri=existing.logical_uri, digest=existing.digest)

    def _publish(
        self,
        plan: FrequencyCalibrationPlanV1,
        sealed_utc_ns: int,
    ) -> ImmutableDocumentRefV1:
        if _SAFE_ID.fullmatch(plan.plan_id) is None:
            raise ValueError("calibration plan id is unsafe")
        filename = f"{plan.plan_id}.json"
        document = plan.model_dump(mode="json")
        digest = sha256_digest(canonical_json_bytes(document))
        envelope = {
            "schema_version": 1,
            "logical_uri": self._uri(plan.plan_id),
            "digest": digest,
            "sealed_utc_ns": sealed_utc_ns,
            "document": document,
        }
        payload = canonical_json_bytes(envelope)
        try:
            descriptor = os.open(
                filename,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o440,
                dir_fd=self._root_fd,
            )
        except FileExistsError:
            stored = self.load(
                ImmutableDocumentRefV1(logical_uri=self._uri(plan.plan_id), digest=digest)
            )
            if stored.document != document:
                raise ValueError(
                    "calibration plan id already contains different content"
                ) from None
            return ImmutableDocumentRefV1(logical_uri=stored.logical_uri, digest=stored.digest)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(self._root_fd)
        return ImmutableDocumentRefV1(logical_uri=self._uri(plan.plan_id), digest=digest)

    def load(self, ref: ImmutableDocumentRefV1) -> TrustedImmutableDocumentV1:
        plan_id = self._id_from_uri(ref.logical_uri)
        stored = self._load_id(plan_id)
        if stored.logical_uri != ref.logical_uri or stored.digest != ref.digest:
            raise ValueError("calibration plan reference differs from immutable content")
        FrequencyCalibrationPlanV1.model_validate(stored.document)
        return stored

    def _load_id(self, plan_id: str) -> TrustedImmutableDocumentV1:
        descriptor = os.open(
            f"{plan_id}.json",
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=self._root_fd,
        )
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_BYTES:
                raise ValueError("calibration plan document is not one bounded regular file")
            payload = stream.read(_MAX_BYTES + 1)
        stored = TrustedImmutableDocumentV1.model_validate_json(payload)
        return stored

    @staticmethod
    def _uri(plan_id: str) -> str:
        return f"qualification://frequency-calibration-predeclarations/{plan_id}"

    @classmethod
    def _id_from_uri(cls, uri: str) -> str:
        prefix = "qualification://frequency-calibration-predeclarations/"
        plan_id = uri.removeprefix(prefix)
        if uri != cls._uri(plan_id) or _SAFE_ID.fullmatch(plan_id) is None:
            raise ValueError("calibration plan URI is noncanonical")
        return plan_id


class AnalysisArtifactTrustedDocumentAdapter:
    """Digest-verifying adapter over the ordinary immutable analysis store."""

    def __init__(self, store: AnalysisArtifactStore) -> None:
        self._store = store

    def load(self, ref: ImmutableDocumentRefV1) -> TrustedImmutableDocumentV1:
        document = self._store.read_json(ref.logical_uri, ref.digest)
        path = self._store.resolver.resolve(ref.logical_uri, must_exist=True)
        return TrustedImmutableDocumentV1(
            logical_uri=ref.logical_uri,
            digest=ref.digest,
            sealed_utc_ns=path.stat(follow_symlinks=False).st_ctime_ns,
            document=dict(document),
        )
