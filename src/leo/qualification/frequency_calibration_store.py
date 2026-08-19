"""Durable create-only storage and authoritative resolution of WP11 promotions."""

from __future__ import annotations

import errno
import os
import re
import shutil
import stat
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal, Self
from urllib.parse import quote

from pydantic import Field, StringConstraints, model_validator

from leo.application.frequency_calibration import (
    DurableCalibrationPublicationRefV1,
    PromotionBuilder,
    TrustedCalibrationPromotionResultV1,
    TrustedReleaseEvidencePort,
)
from leo.contracts.base import ContractModel
from leo.contracts.calibration import ReceiverFrequencyCalibrationSetV1
from leo.contracts.digests import (
    Sha256Digest,
    canonical_digest,
    canonical_json_bytes,
    sha256_digest,
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_FILES = ("receipt.json", "draft.json", "calibration.json", "calibration-set.json")
_MAX_FILE_BYTES = 64 * 1024 * 1024
_QNAP = Path("/mnt/qnap01")


class CalibrationPromotionBundleManifestV1(ContractModel):
    schema_version: Literal[1] = 1
    promotion_id: Annotated[
        str,
        StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
    ]
    bundle_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    sealed_utc_ns: Annotated[int, Field(ge=0)]
    file_digests: tuple[tuple[str, Sha256Digest], ...]
    receipt_semantic_digest: Sha256Digest
    bundle_digest: Sha256Digest

    @model_validator(mode="after")
    def _canonical(self) -> Self:
        if tuple(name for name, _ in self.file_digests) != _FILES:
            raise ValueError("promotion bundle file inventory is not canonical")
        if self.bundle_uri != _bundle_uri(self.promotion_id):
            raise ValueError("promotion bundle URI does not match promotion id")
        if self.bundle_digest != _digest_without(self, "bundle_digest"):
            raise ValueError("promotion bundle digest does not match content")
        return self


class StoredCalibrationPromotionV1(ContractModel):
    schema_version: Literal[1] = 1
    publication: DurableCalibrationPublicationRefV1
    manifest: CalibrationPromotionBundleManifestV1
    result: TrustedCalibrationPromotionResultV1

    @model_validator(mode="after")
    def _bound(self) -> Self:
        if (
            self.publication.promotion_id != self.manifest.promotion_id
            or self.publication.bundle_uri != self.manifest.bundle_uri
            or self.publication.sealed_utc_ns != self.manifest.sealed_utc_ns
            or self.result.receipt.promotion_id != self.manifest.promotion_id
            or self.result.receipt.promoted_utc_ns != self.manifest.sealed_utc_ns
            or self.result.receipt.promotion_uri != f"{self.manifest.bundle_uri}/receipt.json"
            or self.result.receipt.promotion_digest != self.manifest.receipt_semantic_digest
        ):
            raise ValueError("stored promotion identities are inconsistent")
        return self


class CalibrationPublicationConflict(RuntimeError):
    pass


class ImmutableCalibrationPromotionStore:
    """One fsync-durable directory per promotion; existing content is immutable."""

    def __init__(self, root: Path, *, clock_ns: Callable[[], int] = time.time_ns) -> None:
        root.mkdir(parents=True, exist_ok=True)
        root_info = root.lstat()
        if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
            raise ValueError("calibration promotion store root must be a real directory")
        self.root = root.resolve(strict=True)
        if self.root == _QNAP or _QNAP in self.root.parents:
            raise ValueError("calibration promotion store cannot be beneath QNAP")
        self._clock_ns = clock_ns

    def publish(
        self,
        promotion_id: str,
        builder: PromotionBuilder,
    ) -> DurableCalibrationPublicationRefV1:
        _require_identifier(promotion_id)
        target = self.root / promotion_id
        if _lexists(target):
            stored = self._load_path(target)
            proposed = builder(stored.manifest.sealed_utc_ns, _receipt_uri(promotion_id))
            if proposed != stored.result:
                raise CalibrationPublicationConflict(
                    "promotion id already contains different immutable content"
                )
            return stored.publication

        sealed_utc_ns = self._clock_ns()
        result = builder(sealed_utc_ns, _receipt_uri(promotion_id))
        _validate_result_identity(result, promotion_id, sealed_utc_ns)
        documents = _result_documents(result)
        payloads = {name: canonical_json_bytes(document) for name, document in documents.items()}
        file_digests = tuple((name, sha256_digest(payloads[name])) for name in _FILES)
        manifest_values: dict[str, Any] = {
            "schema_version": 1,
            "promotion_id": promotion_id,
            "bundle_uri": _bundle_uri(promotion_id),
            "sealed_utc_ns": sealed_utc_ns,
            "file_digests": file_digests,
            "receipt_semantic_digest": result.receipt.promotion_digest,
        }
        manifest = CalibrationPromotionBundleManifestV1(
            **manifest_values,
            bundle_digest=canonical_digest(manifest_values),
        )
        manifest_payload = canonical_json_bytes(manifest.model_dump(mode="json"))
        temporary = self.root / f".tmp-{promotion_id}-{uuid.uuid4().hex}"
        temporary.mkdir(mode=0o750)
        try:
            for name in _FILES:
                _write_new_durable(temporary / name, payloads[name])
            _write_new_durable(temporary / "manifest.json", manifest_payload)
            _fsync_directory(temporary)
            try:
                os.rename(temporary, target)
            except OSError as error:
                if error.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                    raise
                shutil.rmtree(temporary)
                stored = self._load_path(target)
                if result != stored.result:
                    raise CalibrationPublicationConflict(
                        "concurrent promotion published different immutable content"
                    ) from error
                return stored.publication
            _fsync_directory(self.root)
        except BaseException:
            if _lexists(temporary):
                shutil.rmtree(temporary)
            raise
        stored = self._load_path(target)
        if stored.result != result:
            raise RuntimeError("promotion readback differs from published content")
        return stored.publication

    def load(self, ref: DurableCalibrationPublicationRefV1) -> StoredCalibrationPromotionV1:
        if ref.bundle_uri != _bundle_uri(ref.promotion_id):
            raise ValueError("publication reference URI is noncanonical")
        stored = self._load_path(self.root / ref.promotion_id)
        if stored.publication != ref:
            raise ValueError("publication reference does not match durable store content")
        return stored

    def _load_path(self, path: Path) -> StoredCalibrationPromotionV1:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or path.parent != self.root:
            raise ValueError("promotion path is not one real direct child directory")
        manifest_payload = _read_regular(path / "manifest.json")
        manifest = CalibrationPromotionBundleManifestV1.model_validate_json(manifest_payload)
        if path.name != manifest.promotion_id:
            raise ValueError("promotion directory name differs from manifest")
        documents: dict[str, dict[str, object]] = {}
        for name, expected_digest in manifest.file_digests:
            payload = _read_regular(path / name)
            if sha256_digest(payload) != expected_digest:
                raise ValueError(f"promotion file digest mismatch: {name}")
            import json

            parsed = json.loads(payload)
            if not isinstance(parsed, dict):
                raise ValueError("promotion document must contain one JSON object")
            documents[name] = parsed
        result = TrustedCalibrationPromotionResultV1.model_validate(
            {
                "receipt": documents["receipt.json"],
                "draft": documents["draft.json"],
                "calibration": documents["calibration.json"],
                "calibration_set": documents["calibration-set.json"],
            }
        )
        manifest_file_digest = sha256_digest(manifest_payload)
        publication = DurableCalibrationPublicationRefV1(
            promotion_id=manifest.promotion_id,
            bundle_uri=manifest.bundle_uri,
            manifest_digest=manifest_file_digest,
            sealed_utc_ns=manifest.sealed_utc_ns,
        )
        return StoredCalibrationPromotionV1(
            publication=publication,
            manifest=manifest,
            result=result,
        )


class AuthoritativeCalibrationResolver:
    """Only durable store readback plus a currently validated release can resolve."""

    def __init__(
        self,
        store: ImmutableCalibrationPromotionStore,
        releases: TrustedReleaseEvidencePort,
        *,
        allowed_release_ids: tuple[str, ...],
    ) -> None:
        if not allowed_release_ids or len(set(allowed_release_ids)) != len(allowed_release_ids):
            raise ValueError("allowed release ids must be nonempty and unique")
        if type(store) is not ImmutableCalibrationPromotionStore:
            raise TypeError("authoritative resolution requires the concrete immutable store")
        self._store = store
        self._releases = releases
        self._allowed = allowed_release_ids

    def resolve(
        self,
        ref: DurableCalibrationPublicationRefV1,
    ) -> ReceiverFrequencyCalibrationSetV1:
        stored = self._store.load(ref)
        current = self._releases.current_release()
        receipt = stored.result.receipt
        if current.release_id not in self._allowed:
            raise ValueError("current deployed release is not allowed for calibration resolution")
        if (
            current.git_revision != receipt.promoter_git_revision
            or current.source_tree_digest != receipt.promoter_source_tree_digest
            or current.executable_digest != receipt.promoter_executable_digest
            or current.evidence_digest != receipt.release_evidence_digest
            or current.attestation_uri != receipt.release_attestation_uri
        ):
            raise ValueError("current deployed release differs from promotion attestation")
        return stored.result.calibration_set


def _result_documents(result: TrustedCalibrationPromotionResultV1) -> dict[str, dict[str, object]]:
    return {
        "receipt.json": result.receipt.model_dump(mode="json"),
        "draft.json": result.draft.model_dump(mode="json"),
        "calibration.json": result.calibration.model_dump(mode="json"),
        "calibration-set.json": result.calibration_set.model_dump(mode="json"),
    }


def _validate_result_identity(
    result: TrustedCalibrationPromotionResultV1,
    promotion_id: str,
    sealed_utc_ns: int,
) -> None:
    if (
        result.receipt.promotion_id != promotion_id
        or result.receipt.promotion_uri != _receipt_uri(promotion_id)
        or result.receipt.promoted_utc_ns != sealed_utc_ns
        or result.calibration.created_utc_ns != sealed_utc_ns
    ):
        raise ValueError("promotion result is not bound to authoritative store identity/time")


def _bundle_uri(promotion_id: str) -> str:
    _require_identifier(promotion_id)
    return f"qualification://frequency-calibration-promotions/{quote(promotion_id, safe='._-:')}"


def _receipt_uri(promotion_id: str) -> str:
    return f"{_bundle_uri(promotion_id)}/receipt.json"


def _require_identifier(value: str) -> None:
    if _IDENTIFIER.fullmatch(value) is None:
        raise ValueError("promotion id is unsafe")


def _lexists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _write_new_durable(path: Path, payload: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o440,
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _read_regular(path: Path) -> bytes:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError(f"promotion file is not regular: {path.name}")
    if info.st_size > _MAX_FILE_BYTES:
        raise ValueError(f"promotion file exceeds size limit: {path.name}")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        return stream.read(_MAX_FILE_BYTES + 1)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _digest_without(value: ContractModel, field: str) -> str:
    return canonical_digest(value.model_dump(mode="json", exclude={field}))
