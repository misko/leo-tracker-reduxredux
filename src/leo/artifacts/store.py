"""Crash-safe immutable analysis artifact publication on local bulk storage."""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from pydantic import JsonValue

from leo.artifacts.models import AnalysisRunManifestV1
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.pipeline import OutputSink, ProductRole, ProductSpec, PublishedProduct
from leo.storage import BulkUriResolver
from leo.storage.uri import confined_path

FailureInjector = Callable[[str], None]
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_MAX_JSON_BYTES = 64 * 1024 * 1024


class ArtifactStoreError(RuntimeError):
    pass


class ArtifactConflictError(ArtifactStoreError):
    pass


class ArtifactCorruptionError(ArtifactStoreError):
    pass


class RunSealedError(ArtifactStoreError):
    pass


@dataclass(frozen=True, slots=True)
class PublishedRunManifest:
    manifest: AnalysisRunManifestV1
    logical_uri: str
    digest: str
    byte_size: int
    path: Path


@dataclass(frozen=True, slots=True)
class ProductPublication:
    stage_key: str
    scope_key: str
    published: PublishedProduct


class ArtifactOutputSink(OutputSink):
    """One job's collecting output sink.

    Files are published immediately, but catalog registration is deliberately
    performed by the processing service only after the analyzer returns an
    accepted semantic outcome.
    """

    def __init__(
        self,
        store: AnalysisArtifactStore,
        *,
        session_id: str,
        run_id: str,
        stage_key: str,
        scope_key: str,
    ) -> None:
        self._store = store
        self._session_id = session_id
        self._run_id = run_id
        self._stage_key = stage_key
        self._scope_key = scope_key
        self._publications: list[ProductPublication] = []

    @property
    def publications(self) -> tuple[ProductPublication, ...]:
        return tuple(self._publications)

    def publish_json(
        self,
        product: ProductSpec,
        document: dict[str, JsonValue],
    ) -> PublishedProduct:
        if any(
            publication.published.product.kind == product.kind
            and publication.published.product.schema_version == product.schema_version
            for publication in self._publications
        ):
            raise ArtifactConflictError(
                f"job published product more than once: {product.kind} v{product.schema_version}"
            )
        published = self._store.publish_json(
            session_id=self._session_id,
            run_id=self._run_id,
            stage_key=self._stage_key,
            scope_key=self._scope_key,
            product=product,
            document=document,
        )
        self._publications.append(
            ProductPublication(
                stage_key=self._stage_key,
                scope_key=self._scope_key,
                published=published,
            )
        )
        return published


class AnalysisArtifactStore:
    """Own ``bulk://analysis`` and private analysis spool namespaces."""

    def __init__(self, root: Path, *, failure_injector: FailureInjector | None = None) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve(strict=True)
        self.analysis_root = self.root / "analysis"
        self.spool_root = self.root / "spool" / "analysis"
        self.analysis_root.mkdir(parents=True, exist_ok=True)
        self.spool_root.mkdir(parents=True, exist_ok=True)
        if os.stat(self.analysis_root).st_dev != os.stat(self.spool_root).st_dev:
            raise ValueError("analysis spool and public roots must share one filesystem")
        self.resolver = BulkUriResolver(self.root)
        self._failure_injector = failure_injector

    def output_sink(
        self,
        *,
        session_id: str,
        run_id: str,
        stage_key: str,
        scope_key: str,
    ) -> ArtifactOutputSink:
        return ArtifactOutputSink(
            self,
            session_id=session_id,
            run_id=run_id,
            stage_key=stage_key,
            scope_key=scope_key,
        )

    def publish_json(
        self,
        *,
        session_id: str,
        run_id: str,
        stage_key: str,
        scope_key: str,
        product: ProductSpec,
        document: dict[str, JsonValue],
    ) -> PublishedProduct:
        session_id, run_id, stage_key, scope_key = _safe_components(
            session_id, run_id, stage_key, scope_key
        )
        run_directory = self._run_directory(session_id, run_id)
        if (run_directory / "manifest.json").exists():
            raise RunSealedError(f"analysis run is already sealed: {run_id}")
        role_directory = "scientific" if product.role is ProductRole.SCIENTIFIC else "presentation"
        filename = f"{_safe_component(product.kind)}.v{product.schema_version}.json"
        final_path = run_directory / role_directory / stage_key / scope_key / filename
        payload = canonical_json_bytes(document)
        published_path, digest = self._publish_bytes(
            session_id=session_id,
            run_id=run_id,
            final_path=final_path,
            payload=payload,
            kind="product",
        )
        return PublishedProduct(
            product=product,
            logical_uri=self.resolver.uri_for(published_path),
            digest=digest,
            byte_size=len(payload),
        )

    def read_json(self, logical_uri: str, digest: str) -> dict[str, JsonValue]:
        path = self.resolver.resolve(logical_uri, must_exist=True)
        try:
            size = path.stat().st_size
            if size > _MAX_JSON_BYTES:
                raise ArtifactCorruptionError(f"JSON artifact exceeds size limit: {path}")
            payload = path.read_bytes()
        except OSError as error:
            raise ArtifactCorruptionError(
                f"cannot read analysis artifact {path}: {error}"
            ) from error
        if sha256_digest(payload) != digest:
            raise ArtifactCorruptionError(f"analysis artifact digest mismatch: {path}")
        try:
            document = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ArtifactCorruptionError(f"analysis artifact is not valid JSON: {path}") from error
        if not isinstance(document, dict):
            raise ArtifactCorruptionError(f"analysis JSON artifact is not an object: {path}")
        return document

    def seal_run(self, manifest: AnalysisRunManifestV1) -> PublishedRunManifest:
        session_id, run_id = _safe_components(manifest.session_id, manifest.run_id)
        run_directory = self._run_directory(session_id, run_id)
        for product in manifest.products:
            path = self.resolver.resolve(product.logical_uri, must_exist=True)
            try:
                path.relative_to(run_directory)
            except ValueError as error:
                raise ArtifactConflictError(
                    f"product does not belong to run directory: {product.logical_uri}"
                ) from error
            if path.stat().st_size != product.byte_size:
                raise ArtifactCorruptionError(f"product size changed before run seal: {path}")
            if sha256_digest(path.read_bytes()) != product.digest:
                raise ArtifactCorruptionError(f"product digest changed before run seal: {path}")

        payload = canonical_json_bytes(manifest.model_dump(mode="json"))
        final_path = run_directory / "manifest.json"
        published_path, digest = self._publish_bytes(
            session_id=session_id,
            run_id=run_id,
            final_path=final_path,
            payload=payload,
            kind="manifest",
        )
        return PublishedRunManifest(
            manifest=manifest,
            logical_uri=self.resolver.uri_for(published_path),
            digest=digest,
            byte_size=len(payload),
            path=published_path,
        )

    def _run_directory(self, session_id: str, run_id: str) -> Path:
        return confined_path(
            self.root,
            self.analysis_root / session_id / run_id,
            must_exist=False,
        )

    def _publish_bytes(
        self,
        *,
        session_id: str,
        run_id: str,
        final_path: Path,
        payload: bytes,
        kind: str,
    ) -> tuple[Path, str]:
        final_path = confined_path(self.root, final_path, must_exist=False)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        spool_directory = confined_path(
            self.root,
            self.spool_root / session_id / run_id,
            must_exist=False,
        )
        spool_directory.mkdir(parents=True, exist_ok=True)
        partial_path = spool_directory / f"{uuid.uuid4().hex}.{kind}.partial"
        digest = sha256_digest(payload)
        try:
            with partial_path.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            self._inject(f"{kind}:after_temp_fsync")
            try:
                os.link(partial_path, final_path)
            except FileExistsError:
                existing = final_path.read_bytes()
                if len(existing) != len(payload) or sha256_digest(existing) != digest:
                    raise ArtifactConflictError(
                        f"immutable artifact already differs: {final_path}"
                    ) from None
            else:
                os.chmod(final_path, 0o440)
                _fsync_directory(final_path.parent)
                self._inject(f"{kind}:after_publish")
            return final_path, digest
        finally:
            with suppress(FileNotFoundError):
                partial_path.unlink()

    def _inject(self, point: str) -> None:
        if self._failure_injector is not None:
            self._failure_injector(point)


def _safe_component(value: str) -> str:
    if not _SAFE_COMPONENT.fullmatch(value):
        raise ValueError(f"unsafe analysis path component: {value!r}")
    return value


def _safe_components(*values: str) -> tuple[str, ...]:
    return tuple(_safe_component(value) for value in values)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
