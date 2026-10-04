"""Explicit prepared-evidence file and immutable local T1-AT product namespace."""

import io
import os
import zipfile
from pathlib import Path
from uuid import uuid4

import numpy as np
from pydantic import TypeAdapter

from leo.contracts.digests import Sha256Digest, canonical_json_bytes, sha256_digest
from leo.contracts.t1_at import T1AtInputV1, T1AtProductV1
from leo.contracts.t1_at_prediction import T1AtDiscoveryData, T1AtDiscoveryManifestV1
from leo.storage.pinned import PinnedLocalRoot


class T1AtInputFile:
    def __init__(self, path: Path):
        self.path = path

    def load(self, session_id: str) -> T1AtInputV1:
        with self.path.open("rb") as stream:
            payload = stream.read(256 * 1024 * 1024 + 1)
        if len(payload) > 256 * 1024 * 1024:
            raise ValueError("T1-AT input exceeds 256 MiB bound")
        value = T1AtInputV1.model_validate_json(payload)
        if value.session_id != session_id:
            raise ValueError("T1-AT input session differs")
        return value


class T1AtDiscoveryFile:
    def __init__(self, path: Path):
        self.path = path

    def load(self, session_id: str) -> T1AtDiscoveryData:
        with self.path.open("rb") as stream:
            payload = stream.read(32 * 1024 * 1024 + 1)
        if len(payload) > 32 * 1024 * 1024:
            raise ValueError("discovery manifest exceeds 32 MiB bound")
        manifest = T1AtDiscoveryManifestV1.model_validate_json(payload)
        if manifest.evidence.session_id != session_id:
            raise ValueError("discovery input session differs")
        with (self.path.parent / manifest.array_file).open("rb") as stream:
            payload = stream.read(256 * 1024 * 1024 + 1)
        if len(payload) > 256 * 1024 * 1024 or sha256_digest(payload) != manifest.bank_sha256:
            raise ValueError("discovery bank byte bound or digest mismatch")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 512 * 1024 * 1024:
                raise ValueError("discovery bank expands beyond 512 MiB bound")
        with np.load(io.BytesIO(payload), allow_pickle=False) as arrays:
            expected = set(T1AtDiscoveryData.__dataclass_fields__) - {"manifest"}
            if set(arrays.files) != expected:
                raise ValueError("discovery bank array inventory differs")
            values = {name: arrays[name].copy() for name in expected}
        return T1AtDiscoveryData(manifest=manifest, **values)


class T1AtProductStore:
    def __init__(self, root: Path):
        resolved = root.resolve()
        protected = Path("/mnt/qnap01")
        if resolved == protected or protected in resolved.parents:
            raise ValueError("QNAP is read-only")
        self.root = root

    def load(self, prepared_input_sha256: str) -> T1AtProductV1 | None:
        TypeAdapter(Sha256Digest).validate_python(prepared_input_sha256)
        root = PinnedLocalRoot(self.root)
        directory = None
        try:
            try:
                directory = root.child("t1-at-v1", prepared_input_sha256.removeprefix("sha256:"))
            except ValueError as error:
                if isinstance(error.__cause__, FileNotFoundError):
                    return None
                raise
            try:
                fd = os.open("product.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory.fileno())
            except FileNotFoundError:
                return None
            with os.fdopen(fd, "rb") as stream:
                payload = stream.read(32 * 1024 * 1024 + 1)
            if len(payload) > 32 * 1024 * 1024:
                raise ValueError("T1-AT product exceeds 32 MiB bound")
            product = T1AtProductV1.model_validate_json(payload)
            if product.prepared_input_sha256 != prepared_input_sha256:
                raise ValueError("T1-AT cached product input digest differs")
            return product
        finally:
            if directory is not None:
                directory.close()
            root.close()

    def save(self, product: T1AtProductV1) -> None:
        # Digest is the directory key; user-supplied session text is never a path.
        directory = None
        root = PinnedLocalRoot(self.root)
        try:
            directory = root.child(
                "t1-at-v1", product.prepared_input_sha256.removeprefix("sha256:"), create=True
            )
            payload = canonical_json_bytes(product.model_dump(mode="json"))
            temporary = f".{uuid4().hex}.partial"
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o640,
                dir_fd=directory.fileno(),
            )
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(
                        temporary,
                        "product.json",
                        src_dir_fd=directory.fileno(),
                        dst_dir_fd=directory.fileno(),
                        follow_symlinks=False,
                    )
                except FileExistsError as error:
                    current = os.open(
                        "product.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory.fileno()
                    )
                    with os.fdopen(current, "rb") as stream:
                        if stream.read(len(payload) + 1) != payload:
                            raise ValueError(
                                "immutable T1-AT product conflicts with existing evidence"
                            ) from error
                os.fsync(directory.fileno())
            finally:
                os.unlink(temporary, dir_fd=directory.fileno())
        finally:
            if directory is not None:
                directory.close()
            root.close()
