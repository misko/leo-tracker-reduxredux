"""Create-only publication store for authoritative trusted-campaign seals."""

from __future__ import annotations

import json
import os
import stat
import time
from contextlib import suppress
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import TypeAdapter

from leo.application.frequency_calibration import ImmutableDocumentRefV1
from leo.application.trusted_campaign import (
    TrustedCampaignFinalizer,
    TrustedCampaignOuterSealV1,
    TrustedCampaignPresentationV1,
    TrustedCampaignPublicationV1,
    TrustedCampaignSealMaterialV1,
    _trusted_finalizer_is_registered,
)
from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.contracts.recording import Identifier
from leo.contracts.trusted_scientific import TrustedMatchedRecoveryCampaignReceiptV2
from leo.storage import PinnedLocalRoot

_SCIENTIFIC_LIMIT = 64 * 1024 * 1024
_PRESENTATION_LIMIT = 256 * 1024
_SEAL_LIMIT = 2 * 1024 * 1024
_IDENTIFIER = TypeAdapter(Identifier)


class TrustedCampaignPublicationError(RuntimeError):
    pass


class TrustedCampaignPublicationConflict(TrustedCampaignPublicationError):
    pass


class PublicationFailureInjector(Protocol):
    def __call__(self, point: str) -> None: ...


class ImmutableTrustedCampaignStore:
    """Own immutable scientific, presentation, and outer-seal documents."""

    def __init__(
        self,
        root: PinnedLocalRoot,
        *,
        failure_injector: PublicationFailureInjector | None = None,
    ) -> None:
        self._root = root.clone()
        self._campaign_capability = self._root.child("trusted-campaigns", create=True)
        self.root = self._root.io_root
        self.campaign_root = self._campaign_capability.io_root
        self._failure_injector = failure_injector
        self._bound_finalizer: TrustedCampaignFinalizer | None = None
        self._bound_sentinel: object | None = None
        self._authority = object()

    def close(self) -> None:
        self._campaign_capability.close()
        self._root.close()

    def _bind_trusted_finalizer(self, finalizer: object, sentinel: object) -> object:
        if type(finalizer) is not TrustedCampaignFinalizer:
            raise TypeError("trusted campaign store binds only the production finalizer")
        if not _trusted_finalizer_is_registered(finalizer, sentinel):
            raise TypeError("trusted campaign finalizer is not fully initialized")
        if self._bound_finalizer is not None and self._bound_finalizer is not finalizer:
            raise RuntimeError("trusted campaign store is already bound")
        self._bound_finalizer = finalizer
        self._bound_sentinel = sentinel
        return self._authority

    def _publish_verified(
        self,
        authority: object,
        finalizer: object,
        sentinel: object,
        campaign_id: str,
        scientific: TrustedMatchedRecoveryCampaignReceiptV2,
        presentation: TrustedCampaignPresentationV1,
        material: TrustedCampaignSealMaterialV1,
    ) -> TrustedCampaignPublicationV1:
        if (
            authority is not self._authority
            or finalizer is not self._bound_finalizer
            or sentinel is not self._bound_sentinel
            or not _trusted_finalizer_is_registered(finalizer, sentinel)
            or type(finalizer) is not TrustedCampaignFinalizer
        ):
            raise PermissionError("trusted campaign publication requires bound authority")
        _IDENTIFIER.validate_python(campaign_id)
        if scientific.acceptance_eligible or scientific.production_accepted:
            raise ValueError("inner trusted campaign evidence must remain non-authoritative")
        if self._campaign_exists(campaign_id):
            return self._load_and_compare(campaign_id, scientific, presentation, material)
        temporary_name = f".{campaign_id}.{uuid4().hex}.partial"
        os.mkdir(temporary_name, mode=0o750, dir_fd=self._campaign_capability.fileno())
        temporary_capability = self._campaign_capability.child(temporary_name)
        temporary = temporary_capability.io_root
        try:
            scientific_payload = _bounded_payload(scientific, _SCIENTIFIC_LIMIT)
            presentation_payload = _bounded_payload(presentation, _PRESENTATION_LIMIT)
            scientific_ref = _document_ref(campaign_id, "scientific.json", scientific_payload)
            presentation_ref = _document_ref(campaign_id, "presentation.json", presentation_payload)
            seal = _seal(material, scientific_ref, presentation_ref, time.time_ns())
            seal_payload = _bounded_payload(seal, _SEAL_LIMIT)
            _write_file(temporary / "scientific.json", scientific_payload)
            self._fail("after_scientific")
            _write_file(temporary / "presentation.json", presentation_payload)
            self._fail("after_presentation")
            _write_file(temporary / "seal.json", seal_payload)
            self._fail("after_seal")
            _fsync_directory(temporary)
            self._fail("before_publish")
            try:
                os.rename(
                    temporary_name,
                    campaign_id,
                    src_dir_fd=self._campaign_capability.fileno(),
                    dst_dir_fd=self._campaign_capability.fileno(),
                )
            except OSError as error:
                if not self._campaign_exists(campaign_id):
                    raise TrustedCampaignPublicationError(
                        f"cannot publish trusted campaign: {error}"
                    ) from error
                return self._load_and_compare(campaign_id, scientific, presentation, material)
            _fsync_directory(self.campaign_root)
            self._fail("after_publish")
            return self._load_confined(campaign_id)
        finally:
            if _entry_exists(self._campaign_capability, temporary_name):
                for name in ("scientific.json", "presentation.json", "seal.json"):
                    with suppress(FileNotFoundError):
                        os.unlink(name, dir_fd=temporary_capability.fileno())
                os.rmdir(temporary_name, dir_fd=self._campaign_capability.fileno())
            temporary_capability.close()

    def _load_confined(self, campaign_id: str) -> TrustedCampaignPublicationV1:
        _IDENTIFIER.validate_python(campaign_id)
        try:
            directory = self._campaign_capability.child(campaign_id)
        except ValueError as error:
            raise TrustedCampaignPublicationError(
                f"trusted campaign is absent or symlinked: {campaign_id}"
            ) from error
        try:
            scientific_payload = _read_bounded_at(directory, "scientific.json", _SCIENTIFIC_LIMIT)
            presentation_payload = _read_bounded_at(
                directory, "presentation.json", _PRESENTATION_LIMIT
            )
            seal_payload = _read_bounded_at(directory, "seal.json", _SEAL_LIMIT)
        finally:
            directory.close()
        scientific_ref = _document_ref(campaign_id, "scientific.json", scientific_payload)
        presentation_ref = _document_ref(campaign_id, "presentation.json", presentation_payload)
        seal_ref = _document_ref(campaign_id, "seal.json", seal_payload)
        scientific = TrustedMatchedRecoveryCampaignReceiptV2.model_validate_json(scientific_payload)
        presentation = TrustedCampaignPresentationV1.model_validate_json(presentation_payload)
        seal = TrustedCampaignOuterSealV1.model_validate_json(seal_payload)
        if (
            seal.campaign_id != campaign_id
            or seal.scientific != scientific_ref
            or seal.presentation != presentation_ref
            or scientific.config.campaign_id != campaign_id
            or presentation.campaign_id != campaign_id
        ):
            raise TrustedCampaignPublicationError(
                "trusted campaign publication has inconsistent identity"
            )
        return TrustedCampaignPublicationV1(
            scientific=scientific_ref,
            presentation=presentation_ref,
            outer_seal=seal_ref,
            seal=seal,
        )

    def _load_verified(
        self,
        authority: object,
        finalizer: object,
        sentinel: object,
        campaign_id: str,
    ) -> tuple[
        TrustedCampaignPublicationV1,
        TrustedMatchedRecoveryCampaignReceiptV2,
        TrustedCampaignPresentationV1,
    ]:
        if (
            authority is not self._authority
            or finalizer is not self._bound_finalizer
            or sentinel is not self._bound_sentinel
            or not _trusted_finalizer_is_registered(finalizer, sentinel)
        ):
            raise PermissionError("trusted campaign read requires bound authority")
        publication = self._load_confined(campaign_id)
        directory = self._campaign_capability.child(campaign_id)
        try:
            scientific = TrustedMatchedRecoveryCampaignReceiptV2.model_validate_json(
                _read_bounded_at(directory, "scientific.json", _SCIENTIFIC_LIMIT)
            )
            presentation = TrustedCampaignPresentationV1.model_validate_json(
                _read_bounded_at(directory, "presentation.json", _PRESENTATION_LIMIT)
            )
        finally:
            directory.close()
        return publication, scientific, presentation

    def _load_and_compare(
        self,
        campaign_id: str,
        scientific: TrustedMatchedRecoveryCampaignReceiptV2,
        presentation: TrustedCampaignPresentationV1,
        material: TrustedCampaignSealMaterialV1,
    ) -> TrustedCampaignPublicationV1:
        existing = self._load_confined(campaign_id)
        scientific_payload = canonical_json_bytes(scientific.model_dump(mode="json"))
        presentation_payload = canonical_json_bytes(presentation.model_dump(mode="json"))
        expected_seal = _seal(
            material,
            _document_ref(campaign_id, "scientific.json", scientific_payload),
            _document_ref(campaign_id, "presentation.json", presentation_payload),
            existing.seal.sealed_utc_ns,
        )
        if (
            existing.scientific.digest != sha256_digest(scientific_payload)
            or existing.presentation.digest != sha256_digest(presentation_payload)
            or existing.seal != expected_seal
        ):
            raise TrustedCampaignPublicationConflict(
                f"trusted campaign identity conflicts: {campaign_id}"
            )
        return existing

    def _fail(self, point: str) -> None:
        if self._failure_injector is not None:
            self._failure_injector(point)

    def _campaign_exists(self, campaign_id: str) -> bool:
        try:
            info = os.stat(
                campaign_id,
                dir_fd=self._campaign_capability.fileno(),
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return False
        if not stat.S_ISDIR(info.st_mode):
            raise TrustedCampaignPublicationConflict(
                f"trusted campaign path is not a real directory: {campaign_id}"
            )
        return True


def _bounded_payload(value: object, limit: int) -> bytes:
    if not hasattr(value, "model_dump"):
        raise TypeError("trusted campaign document is not a contract")
    payload = canonical_json_bytes(value.model_dump(mode="json"))
    if len(payload) > limit:
        raise ValueError("trusted campaign document exceeds its bounded size")
    return payload


def _seal(
    material: TrustedCampaignSealMaterialV1,
    scientific: ImmutableDocumentRefV1,
    presentation: ImmutableDocumentRefV1,
    sealed_utc_ns: int,
) -> TrustedCampaignOuterSealV1:
    values = {
        "schema_version": 1,
        "kind": "trusted-campaign-outer-seal",
        "campaign_id": material.campaign_id,
        "capture": material.capture.model_dump(mode="json"),
        "scientific": scientific.model_dump(mode="json"),
        "presentation": presentation.model_dump(mode="json"),
        "current_release_evidence_digest": material.current_release_evidence_digest,
        "members": tuple(item.model_dump(mode="json") for item in material.members),
        "result_status": material.result_status.value,
        "mathematical_eligible": material.mathematical_eligible,
        "authoritative_evidence": True,
        "production_accepted": material.production_accepted,
        "sealed_utc_ns": sealed_utc_ns,
    }
    return TrustedCampaignOuterSealV1.model_validate(
        {**values, "seal_digest": canonical_digest(values)}
    )


def _document_ref(campaign_id: str, name: str, payload: bytes) -> ImmutableDocumentRefV1:
    return ImmutableDocumentRefV1(
        logical_uri=f"qualification://trusted-campaigns/{campaign_id}/{name}",
        digest=sha256_digest(payload),
    )


def _write_file(path: Path, payload: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o440,
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_bounded_at(root: PinnedLocalRoot, name: str, limit: int) -> bytes:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root.fileno())
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit or info.st_nlink != 1:
            raise TrustedCampaignPublicationError(f"invalid trusted campaign artifact: {name}")
        payload = bytearray()
        while len(payload) <= limit:
            block = os.read(descriptor, min(64 * 1024, limit + 1 - len(payload)))
            if not block:
                break
            payload.extend(block)
        if len(payload) != info.st_size:
            raise TrustedCampaignPublicationError(
                f"trusted campaign artifact changed while reading: {name}"
            )
    finally:
        os.close(descriptor)
    try:
        parsed = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TrustedCampaignPublicationError(f"invalid trusted campaign JSON: {name}") from error
    if not isinstance(parsed, dict):
        raise TrustedCampaignPublicationError(f"trusted campaign JSON is not an object: {name}")
    return bytes(payload)


def _entry_exists(root: PinnedLocalRoot, name: str) -> bool:
    try:
        os.stat(name, dir_fd=root.fileno(), follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _reject_qnap(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    qnap = Path("/mnt/qnap01")
    if absolute == qnap or qnap in absolute.parents:
        raise ValueError("trusted campaign store cannot use QNAP")
