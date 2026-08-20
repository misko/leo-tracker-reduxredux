"""Pinned, no-follow reader for bounded station-authority JSON documents."""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import PurePosixPath
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from leo.contracts.digests import sha256_digest
from leo.station.authority import FixturePathAuthorityV1, StationReceiverTopologyV1

_QNAP = "/mnt/qnap01"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_AUTHORITY_BYTES = 4 * 1024 * 1024
_ModelT = TypeVar("_ModelT", bound=BaseModel)


class AuthorityDocumentError(ValueError):
    """An authority document or its filesystem provenance is invalid."""


class OwnershipValidator(Protocol):
    """Injected ownership policy for an opened inode."""

    def __call__(self, label: str, metadata: os.stat_result) -> None: ...


class StationAuthorityReader(Protocol):
    """Narrow read port for later catalog and reconciliation composition."""

    def read_topology(
        self, relative_path: str, *, expected_file_digest: str
    ) -> StationReceiverTopologyV1: ...

    def read_fixture_authority(
        self, relative_path: str, *, expected_file_digest: str
    ) -> FixturePathAuthorityV1: ...


def require_root_owned(label: str, metadata: os.stat_result) -> None:
    """Production ownership policy for the approved root and its documents."""

    if metadata.st_uid != 0:
        raise AuthorityDocumentError(f"{label} must be owned by root")


def require_owner_uid(owner_uid: int) -> OwnershipValidator:
    """Return an exact-owner policy, primarily for isolated tests."""

    if owner_uid < 0:
        raise ValueError("owner UID must be nonnegative")

    def validate(label: str, metadata: os.stat_result) -> None:
        if metadata.st_uid != owner_uid:
            raise AuthorityDocumentError(f"{label} has an unapproved owner")

    return validate


class PinnedAuthorityJsonLoader:
    """Read immutable JSON beneath one retained, pre-created local root inode."""

    def __init__(
        self,
        approved_root: str | os.PathLike[str],
        *,
        ownership_validator: OwnershipValidator = require_root_owned,
        max_document_bytes: int = 1024 * 1024,
    ) -> None:
        if not 1 <= max_document_bytes <= _MAX_AUTHORITY_BYTES:
            raise ValueError("authority JSON size bound is outside the supported range")
        normalized = _lexical_local_root(os.fspath(approved_root))
        descriptor = _open_directory_chain(normalized)
        try:
            metadata = os.fstat(descriptor)
            _validate_directory("approved authority root", metadata, ownership_validator)
        except Exception:
            os.close(descriptor)
            raise
        self.root = normalized
        self._fd = descriptor
        self._identity = (metadata.st_dev, metadata.st_ino)
        self._ownership_validator = ownership_validator
        self._max_document_bytes = max_document_bytes

    def close(self) -> None:
        if self._fd >= 0:
            descriptor = self._fd
            self._fd = -1
            os.close(descriptor)

    def __enter__(self) -> PinnedAuthorityJsonLoader:
        self._assert_open()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def __del__(self) -> None:
        descriptor = getattr(self, "_fd", -1)
        if descriptor >= 0:
            os.close(descriptor)

    def load_contract(
        self,
        relative_path: str,
        *,
        expected_file_digest: str,
        contract_type: type[_ModelT],
    ) -> _ModelT:
        """Load and validate one digest-pinned contract from the retained root."""

        if _SHA256.fullmatch(expected_file_digest) is None:
            raise ValueError("expected authority file digest is not tagged SHA-256")
        components = _safe_relative_components(relative_path)
        parent = self._open_parent(components[:-1])
        try:
            try:
                descriptor = os.open(
                    components[-1],
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=parent,
                )
            except OSError as error:
                raise AuthorityDocumentError(
                    "authority document is inaccessible or symlinked"
                ) from error
        finally:
            os.close(parent)
        try:
            before = os.fstat(descriptor)
            _validate_file(
                "authority document", before, self._ownership_validator, self._max_document_bytes
            )
            first = _bounded_pread(descriptor, before.st_size)
            middle = os.fstat(descriptor)
            _require_stable_inode(before, middle)
            readback = _bounded_pread(descriptor, before.st_size)
            after_readback = os.fstat(descriptor)
            _require_stable_inode(before, after_readback)
            if first != readback:
                raise AuthorityDocumentError("authority document changed during readback")
            observed_digest = sha256_digest(first)
            if observed_digest != expected_file_digest:
                raise AuthorityDocumentError(
                    f"authority document digest mismatch: {observed_digest}"
                )
            document = _parse_closed_json_object(first)
            try:
                contract = contract_type.model_validate(document)
            except Exception as error:
                raise AuthorityDocumentError("authority contract validation failed") from error
            _require_stable_inode(before, os.fstat(descriptor))
            return contract
        finally:
            os.close(descriptor)

    def _assert_open(self) -> None:
        if self._fd < 0:
            raise RuntimeError("pinned authority root is closed")
        try:
            metadata = os.fstat(self._fd)
        except OSError as error:
            raise RuntimeError("pinned authority root descriptor is invalid") from error
        if (metadata.st_dev, metadata.st_ino) != self._identity:
            raise RuntimeError("pinned authority root descriptor identity changed")
        _validate_directory("approved authority root", metadata, self._ownership_validator)

    def _open_parent(self, components: tuple[str, ...]) -> int:
        self._assert_open()
        descriptor = os.dup(self._fd)
        try:
            for component in components:
                try:
                    child = os.open(
                        component,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                        dir_fd=descriptor,
                    )
                except OSError as error:
                    raise AuthorityDocumentError(
                        "authority document parent is inaccessible or symlinked"
                    ) from error
                try:
                    _validate_directory(
                        f"authority directory {component}",
                        os.fstat(child),
                        self._ownership_validator,
                    )
                except Exception:
                    os.close(child)
                    raise
                os.close(descriptor)
                descriptor = child
            return descriptor
        except Exception:
            os.close(descriptor)
            raise


class PinnedStationAuthorityReader:
    """Typed station-authority reader over the generic hardened JSON loader."""

    def __init__(self, loader: PinnedAuthorityJsonLoader) -> None:
        self._loader = loader

    def read_topology(
        self, relative_path: str, *, expected_file_digest: str
    ) -> StationReceiverTopologyV1:
        return self._loader.load_contract(
            relative_path,
            expected_file_digest=expected_file_digest,
            contract_type=StationReceiverTopologyV1,
        )

    def read_fixture_authority(
        self, relative_path: str, *, expected_file_digest: str
    ) -> FixturePathAuthorityV1:
        return self._loader.load_contract(
            relative_path,
            expected_file_digest=expected_file_digest,
            contract_type=FixturePathAuthorityV1,
        )


def _lexical_local_root(raw_path: str) -> str:
    """Normalize without filesystem access and reject QNAP before any syscall."""

    if not raw_path or "\x00" in raw_path or not raw_path.startswith("/"):
        raise ValueError("approved authority root must be an absolute local path")
    collapsed = "/" + raw_path.lstrip("/")
    normalized = os.path.normpath(collapsed)
    if normalized == _QNAP or normalized.startswith(f"{_QNAP}/"):
        raise ValueError("QNAP cannot be an authority document root")
    return normalized


def _safe_relative_components(relative_path: str) -> tuple[str, ...]:
    if (
        not relative_path
        or "\x00" in relative_path
        or "\\" in relative_path
        or relative_path.startswith("/")
    ):
        raise ValueError("authority document path must be normalized and relative")
    pure = PurePosixPath(relative_path)
    components = pure.parts
    if (
        not components
        or any(item in {"", ".", ".."} for item in components)
        or "/".join(components) != relative_path
    ):
        raise ValueError("authority document path must use safe canonical components")
    return components


def _open_directory_chain(path: str) -> int:
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for component in PurePosixPath(path).parts[1:]:
            try:
                child = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=descriptor,
                )
            except OSError as error:
                raise AuthorityDocumentError(
                    "approved authority root contains an inaccessible or symlinked component"
                ) from error
            os.close(descriptor)
            descriptor = child
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _validate_directory(
    label: str, metadata: os.stat_result, ownership_validator: OwnershipValidator
) -> None:
    if not stat.S_ISDIR(metadata.st_mode):
        raise AuthorityDocumentError(f"{label} is not a directory")
    if metadata.st_nlink < 1:
        raise AuthorityDocumentError(f"{label} has an invalid link count")
    permissions = stat.S_IMODE(metadata.st_mode)
    if (
        permissions & 0o7000
        or permissions & 0o022
        or permissions & 0o007
        or permissions & 0o500 != 0o500
    ):
        raise AuthorityDocumentError(f"{label} has unsafe permissions")
    ownership_validator(label, metadata)


def _validate_file(
    label: str,
    metadata: os.stat_result,
    ownership_validator: OwnershipValidator,
    maximum_size: int,
) -> None:
    if not stat.S_ISREG(metadata.st_mode):
        raise AuthorityDocumentError(f"{label} is not a regular file")
    if metadata.st_nlink != 1:
        raise AuthorityDocumentError(f"{label} must have exactly one hard link")
    permissions = stat.S_IMODE(metadata.st_mode)
    if (
        permissions & 0o7000
        or permissions & 0o333
        or permissions & 0o007
        or permissions & 0o400 == 0
    ):
        raise AuthorityDocumentError(f"{label} has unsafe permissions")
    if not 1 <= metadata.st_size <= maximum_size:
        raise AuthorityDocumentError(f"{label} exceeds the bounded JSON size")
    ownership_validator(label, metadata)


def _bounded_pread(descriptor: int, expected_size: int) -> bytes:
    data = os.pread(descriptor, expected_size + 1, 0)
    if len(data) != expected_size:
        raise AuthorityDocumentError("authority document size changed while reading")
    return data


def _stable_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _require_stable_inode(before: os.stat_result, after: os.stat_result) -> None:
    if _stable_identity(before) != _stable_identity(after):
        raise AuthorityDocumentError("authority document metadata changed while reading")


def _parse_closed_json_object(payload: bytes) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise AuthorityDocumentError(f"authority JSON repeats key {key!r}")
            result[key] = value
        return result

    try:
        decoded = payload.decode("utf-8")
        value = json.loads(
            decoded,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=lambda token: (_ for _ in ()).throw(
                AuthorityDocumentError(f"authority JSON contains {token}")
            ),
        )
    except AuthorityDocumentError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AuthorityDocumentError("authority document is not strict UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise AuthorityDocumentError("authority JSON root must be an object")
    return value
