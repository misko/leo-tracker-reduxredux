"""Durable create-only storage and authoritative resolution of WP11 promotions."""

from __future__ import annotations

import errno
import os
import re
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
    TrustedFrequencyCalibrationPromoter,
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
        if not root.is_absolute():
            raise ValueError("calibration promotion store root must be absolute")
        normalized_text = os.path.normpath(os.fspath(root))
        # POSIX permits a special meaning for exactly two leading slashes.
        # Collapse every absolute spelling to the single local root namespace.
        normalized = Path(f"/{normalized_text.lstrip('/')}")
        # This lexical gate deliberately precedes every filesystem syscall. It
        # prevents even probing the protected QNAP namespace.
        if normalized == _QNAP or _QNAP in normalized.parents:
            raise ValueError("calibration promotion store cannot be beneath QNAP")
        self.__root_fd = _open_precreated_directory_chain(normalized)
        root_info = os.fstat(self.__root_fd)
        self.__root_identity = (root_info.st_dev, root_info.st_ino)
        self.__promoter: TrustedFrequencyCalibrationPromoter | None = None
        self.__authority: object | None = None
        self.root = normalized
        self._clock_ns = clock_ns

    def close(self) -> None:
        descriptor = self.__root_fd
        if descriptor >= 0:
            self.__root_fd = -1
            os.close(descriptor)

    def __del__(self) -> None:
        descriptor = getattr(self, "_ImmutableCalibrationPromotionStore__root_fd", -1)
        if descriptor >= 0:
            os.close(descriptor)

    def _bind_trusted_promoter(self, promoter: object) -> object:
        if type(promoter) is not TrustedFrequencyCalibrationPromoter:
            raise TypeError("publication authority is reserved for the trusted promoter")
        if self.__promoter is not None:
            raise RuntimeError("calibration promotion store already has an authority owner")
        authority = object()
        self.__promoter = promoter
        self.__authority = authority
        return authority

    def _publish_verified(
        self,
        authority: object,
        promoter: object,
        promotion_id: str,
        builder: PromotionBuilder,
    ) -> DurableCalibrationPublicationRefV1:
        if (
            authority is not self.__authority
            or promoter is not self.__promoter
            or type(promoter) is not TrustedFrequencyCalibrationPromoter
        ):
            raise PermissionError("calibration publication authority is invalid")
        return self.__publish(promotion_id, builder)

    def __publish(
        self,
        promotion_id: str,
        builder: PromotionBuilder,
    ) -> DurableCalibrationPublicationRefV1:
        self._assert_root_identity()
        _require_identifier(promotion_id)
        if _entry_exists(self.__root_fd, promotion_id):
            stored = self._load_name(promotion_id)
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
        temporary = f".tmp-{promotion_id}-{uuid.uuid4().hex}"
        os.mkdir(temporary, mode=0o750, dir_fd=self.__root_fd)
        temporary_fd = _open_directory_at(self.__root_fd, temporary)
        try:
            for name in _FILES:
                _write_new_durable_at(temporary_fd, name, payloads[name])
            _write_new_durable_at(temporary_fd, "manifest.json", manifest_payload)
            os.fsync(temporary_fd)
            try:
                os.rename(
                    temporary,
                    promotion_id,
                    src_dir_fd=self.__root_fd,
                    dst_dir_fd=self.__root_fd,
                )
            except OSError as error:
                if error.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                    raise
                os.close(temporary_fd)
                temporary_fd = -1
                _remove_temporary_at(self.__root_fd, temporary)
                stored = self._load_name(promotion_id)
                replay = builder(
                    stored.manifest.sealed_utc_ns,
                    _receipt_uri(promotion_id),
                )
                if replay != stored.result:
                    raise CalibrationPublicationConflict(
                        "concurrent promotion published different immutable content"
                    ) from error
                return stored.publication
            os.fsync(self.__root_fd)
        except BaseException:
            if temporary_fd >= 0:
                os.close(temporary_fd)
                temporary_fd = -1
            if _entry_exists(self.__root_fd, temporary):
                _remove_temporary_at(self.__root_fd, temporary)
            raise
        finally:
            if temporary_fd >= 0:
                os.close(temporary_fd)
        stored = self._load_name(promotion_id)
        if stored.result != result:
            raise RuntimeError("promotion readback differs from published content")
        return stored.publication

    def load(self, ref: DurableCalibrationPublicationRefV1) -> StoredCalibrationPromotionV1:
        self._assert_root_identity()
        if ref.bundle_uri != _bundle_uri(ref.promotion_id):
            raise ValueError("publication reference URI is noncanonical")
        stored = self._load_name(ref.promotion_id)
        if stored.publication != ref:
            raise ValueError("publication reference does not match durable store content")
        return stored

    def _load_name(self, promotion_id: str) -> StoredCalibrationPromotionV1:
        _require_identifier(promotion_id)
        directory_fd = _open_directory_at(self.__root_fd, promotion_id)
        try:
            manifest_payload = _read_regular_at(directory_fd, "manifest.json")
            manifest = CalibrationPromotionBundleManifestV1.model_validate_json(
                manifest_payload
            )
            if promotion_id != manifest.promotion_id:
                raise ValueError("promotion directory name differs from manifest")
            documents: dict[str, dict[str, object]] = {}
            for name, expected_digest in manifest.file_digests:
                payload = _read_regular_at(directory_fd, name)
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
            publication = DurableCalibrationPublicationRefV1(
                promotion_id=manifest.promotion_id,
                bundle_uri=manifest.bundle_uri,
                manifest_digest=sha256_digest(manifest_payload),
                sealed_utc_ns=manifest.sealed_utc_ns,
            )
            return StoredCalibrationPromotionV1(
                publication=publication,
                manifest=manifest,
                result=result,
            )
        finally:
            os.close(directory_fd)

    def _assert_root_identity(self) -> None:
        info = os.fstat(self.__root_fd)
        if (info.st_dev, info.st_ino) != self.__root_identity or not stat.S_ISDIR(info.st_mode):
            raise RuntimeError("calibration promotion store root identity changed")


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


def _entry_exists(directory_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def _open_precreated_directory_chain(path: Path) -> int:
    """Return the retained final dirfd after no-follow opening every component."""

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(path.anchor, flags)
    try:
        for component in path.parts[1:]:
            next_descriptor = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except OSError as error:
        os.close(descriptor)
        raise ValueError(
            "calibration promotion store requires a precreated real directory chain"
        ) from error


def _open_directory_at(parent_fd: int, name: str) -> int:
    try:
        return os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
    except FileNotFoundError:
        raise
    except OSError as error:
        raise ValueError("promotion entry is not one real direct child directory") from error


def _write_new_durable_at(directory_fd: int, name: str, payload: bytes) -> None:
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o440,
        dir_fd=directory_fd,
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _read_regular_at(directory_fd: int, name: str) -> bytes:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"promotion file is not regular: {name}")
        if info.st_size > _MAX_FILE_BYTES:
            raise ValueError(f"promotion file exceeds size limit: {name}")
        return stream.read(_MAX_FILE_BYTES + 1)


def _remove_temporary_at(root_fd: int, name: str) -> None:
    directory_fd = _open_directory_at(root_fd, name)
    try:
        for child in os.listdir(directory_fd):
            os.unlink(child, dir_fd=directory_fd)
    finally:
        os.close(directory_fd)
    os.rmdir(name, dir_fd=root_fd)


def _digest_without(value: ContractModel, field: str) -> str:
    return canonical_digest(value.model_dump(mode="json", exclude={field}))
