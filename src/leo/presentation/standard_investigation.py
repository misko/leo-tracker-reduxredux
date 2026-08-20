"""Digest-verified local PNGs produced by bounded Standard investigations."""

from __future__ import annotations

import hashlib
import re
import stat
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_MAX_PNG_BYTES = 32 * 1024 * 1024


class StandardInvestigationImageV1(ContractModel):
    image_id: str
    subject_id: str
    label: Annotated[str, Field(min_length=1, max_length=160)]
    analysis_variant: Literal["wide-fine-upper-edge"]
    relative_path: Annotated[str, Field(min_length=1, max_length=200)]
    byte_size: Annotated[int, Field(gt=0, le=_MAX_PNG_BYTES)]
    digest: Sha256Digest

    @model_validator(mode="after")
    def _identities_are_safe(self) -> StandardInvestigationImageV1:
        if _IDENTIFIER.fullmatch(self.image_id) is None:
            raise ValueError("investigation image ID is invalid")
        if _IDENTIFIER.fullmatch(self.subject_id) is None:
            raise ValueError("investigation subject ID is invalid")
        path = Path(self.relative_path)
        if path.is_absolute() or len(path.parts) != 1 or path.suffix.lower() != ".png":
            raise ValueError("investigation image path must be one relative PNG leaf")
        return self


class StandardInvestigationGalleryV1(ContractModel):
    schema_version: Literal[1] = 1
    session_id: str
    title: Annotated[str, Field(min_length=1, max_length=200)]
    status: Literal["exploratory"] = "exploratory"
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    images: Annotated[tuple[StandardInvestigationImageV1, ...], Field(min_length=1, max_length=16)]

    @model_validator(mode="after")
    def _gallery_is_canonical(self) -> StandardInvestigationGalleryV1:
        if _IDENTIFIER.fullmatch(self.session_id) is None:
            raise ValueError("investigation session ID is invalid")
        keys = tuple((item.subject_id, item.image_id) for item in self.images)
        if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
            raise ValueError("investigation images must be unique and canonically ordered")
        return self


class StandardInvestigationStore:
    """Read explicit, digest-bound local investigations without touching raw IQ."""

    def __init__(self, bulk_root: Path) -> None:
        if not bulk_root.is_absolute() or str(bulk_root).startswith("/mnt/qnap01"):
            raise ValueError("investigation store requires an approved local bulk root")
        self._root = bulk_root / "investigations"

    def gallery(self, session_id: str) -> StandardInvestigationGalleryV1 | None:
        try:
            directory = self._session_directory(session_id)
        except FileNotFoundError:
            return None
        manifest = directory / "manifest.json"
        try:
            payload = self._read_regular(manifest, maximum_bytes=256 * 1024)
        except FileNotFoundError:
            return None
        gallery = StandardInvestigationGalleryV1.model_validate_json(payload)
        if gallery.session_id != session_id:
            raise ValueError("investigation manifest session does not match request")
        for image in gallery.images:
            self._verified_image(directory, image)
        return gallery

    def image(self, session_id: str, image_id: str) -> bytes | None:
        gallery = self.gallery(session_id)
        if gallery is None:
            return None
        selected = next((item for item in gallery.images if item.image_id == image_id), None)
        if selected is None:
            return None
        return self._verified_image(self._session_directory(session_id), selected)

    def _session_directory(self, session_id: str) -> Path:
        if _IDENTIFIER.fullmatch(session_id) is None:
            raise ValueError("investigation session ID is invalid")
        for path in (self._root, self._root / session_id):
            metadata = path.lstat()
            if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
                raise ValueError("investigation path must be a real directory")
        return self._root / session_id

    def _verified_image(self, directory: Path, image: StandardInvestigationImageV1) -> bytes:
        payload = self._read_regular(directory / image.relative_path, maximum_bytes=_MAX_PNG_BYTES)
        if (
            len(payload) != image.byte_size
            or not payload.startswith(_PNG_SIGNATURE)
            or f"sha256:{hashlib.sha256(payload).hexdigest()}" != image.digest
        ):
            raise ValueError("investigation PNG does not match its reviewed manifest")
        return payload

    @staticmethod
    def _read_regular(path: Path, *, maximum_bytes: int) -> bytes:
        metadata = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or not 0 < metadata.st_size <= maximum_bytes
        ):
            raise ValueError("investigation artifact inode is invalid")
        payload = path.read_bytes()
        after = path.stat(follow_symlinks=False)
        if len(payload) != metadata.st_size or (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError("investigation artifact changed while it was read")
        return payload
