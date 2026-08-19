"""Confined reads for presentation artifacts registered by product ID."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

from leo.presentation.models import AnalysisProductV1, ProductContentV1
from leo.presentation.projectors import decimate_product_points_v1

_MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
_MAX_METADATA_BYTES = 32 * 1024
_MAX_METADATA_KEYS = 128
_ARTIFACT_KEYS = {"schema_version", "kind", "metadata", "points"}


class RegisteredArtifactError(RuntimeError):
    """A registered product does not resolve to its declared confined bytes."""


class RegisteredArtifactResolver:
    def __init__(self, artifact_root: Path) -> None:
        if not artifact_root.is_absolute():
            raise ValueError("artifact root must be absolute")
        self._root = artifact_root.resolve(strict=True)
        if not self._root.is_dir() or artifact_root.is_symlink():
            raise ValueError("artifact root must be a real directory")

    def content(self, product: AnalysisProductV1, maximum_points: int) -> ProductContentV1:
        path = Path(product.artifact_path)
        if not path.is_absolute():
            raise RegisteredArtifactError("registered artifact path is not absolute")
        try:
            unresolved_relative = path.relative_to(self._root)
            resolved = path.resolve(strict=True)
            resolved.relative_to(self._root)
        except (FileNotFoundError, ValueError) as exc:
            raise RegisteredArtifactError("registered artifact escapes its root") from exc
        cursor = self._root
        for component in unresolved_relative.parts:
            cursor = cursor / component
            if cursor.is_symlink():
                raise RegisteredArtifactError("registered artifact path contains a symlink")
        file_stat = resolved.stat()
        if not stat.S_ISREG(file_stat.st_mode):
            raise RegisteredArtifactError("registered artifact is not a regular file")
        if file_stat.st_size != product.byte_count:
            raise RegisteredArtifactError("registered artifact byte count changed")
        if file_stat.st_size > _MAX_ARTIFACT_BYTES:
            raise RegisteredArtifactError("registered artifact exceeds the read bound")
        payload = resolved.read_bytes()
        if hashlib.sha256(payload).hexdigest() != product.sha256:
            raise RegisteredArtifactError("registered artifact digest changed")
        try:
            document = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RegisteredArtifactError("registered artifact is not valid JSON") from exc
        if not isinstance(document, dict) or set(document) != _ARTIFACT_KEYS:
            raise RegisteredArtifactError("registered artifact contract is invalid")
        if document["schema_version"] != 1 or document["kind"] != product.kind:
            raise RegisteredArtifactError("registered artifact identity is invalid")
        if not isinstance(document["metadata"], dict) or not isinstance(document["points"], list):
            raise RegisteredArtifactError("registered artifact payload shape is invalid")
        encoded_metadata = json.dumps(
            document["metadata"], sort_keys=True, separators=(",", ":")
        ).encode()
        if (
            len(document["metadata"]) > _MAX_METADATA_KEYS
            or len(encoded_metadata) > _MAX_METADATA_BYTES
        ):
            raise RegisteredArtifactError("registered artifact metadata exceeds the read bound")
        try:
            content = decimate_product_points_v1(
                product.product_id,
                product.kind,
                document["points"],
                document["metadata"],
                maximum_points,
            )
            if content.analysis_run_id != product.analysis_run_id:
                raise RegisteredArtifactError(
                    "registered artifact belongs to a different analysis run"
                )
            return content
        except (TypeError, ValueError) as exc:
            raise RegisteredArtifactError("registered plot points are invalid") from exc
