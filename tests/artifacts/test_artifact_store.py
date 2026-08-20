from __future__ import annotations

import json
from pathlib import Path

import pytest

from leo.artifacts import (
    AnalysisArtifactStore,
    AnalysisJobReceiptV1,
    AnalysisProductReceiptV1,
    AnalysisRunManifestV1,
    ArtifactConflictError,
    ArtifactCorruptionError,
    RunSealedError,
)
from leo.pipeline import ProductRole, ProductSpec, PublishedProduct
from leo.storage import PinnedLocalRoot

DIGEST_A = "sha256:" + "a" * 64


def _product_receipt(product_id: int, published: PublishedProduct) -> AnalysisProductReceiptV1:
    return AnalysisProductReceiptV1(
        product_id=product_id,
        stage_key="quality",
        scope_key="stream-a",
        kind=published.product.kind,
        product_schema_version=published.product.schema_version,
        role=published.product.role.value,
        status="complete",
        media_type=published.product.media_type,
        logical_uri=published.logical_uri,
        digest=published.digest,
        byte_size=published.byte_size,
        coverage=1.0,
    )


def _manifest(product: PublishedProduct) -> AnalysisRunManifestV1:
    return AnalysisRunManifestV1(
        session_id="session-a",
        run_id="run-a",
        pipeline_release_id="release-a",
        input_manifest_digest=DIGEST_A,
        trigger="new_capture",
        jobs=(
            AnalysisJobReceiptV1(
                job_id=1,
                stage_key="quality",
                scope_key="stream-a",
                outcome="complete",
            ),
        ),
        products=(_product_receipt(1, product),),
    )


def test_scientific_and_presentation_products_use_stable_bulk_layout(
    tmp_path: Path,
) -> None:
    store = AnalysisArtifactStore(tmp_path / "bulk")
    scientific = store.publish_json(
        session_id="session-a",
        run_id="run-a",
        stage_key="quality",
        scope_key="stream-a",
        product=ProductSpec(kind="quality.summary"),
        document={"coverage_fraction": 1.0},
    )
    presentation = store.publish_json(
        session_id="session-a",
        run_id="run-a",
        stage_key="quality",
        scope_key="stream-a",
        product=ProductSpec(
            kind="quality.presentation",
            role=ProductRole.PRESENTATION,
        ),
        document={"points": []},
    )
    png = store.publish_bytes(
        session_id="session-a",
        run_id="run-a",
        stage_key="quality",
        scope_key="stream-a",
        product=ProductSpec(
            kind="quality.plot",
            role=ProductRole.PRESENTATION,
            media_type="image/png",
        ),
        payload=b"\x89PNG\r\n\x1a\nfixture",
    )

    assert scientific.logical_uri == (
        "bulk://analysis/session-a/run-a/scientific/quality/stream-a/quality.summary.v1.json"
    )
    assert presentation.logical_uri == (
        "bulk://analysis/session-a/run-a/presentation/quality/stream-a/quality.presentation.v1.json"
    )
    assert png.logical_uri == (
        "bulk://analysis/session-a/run-a/presentation/quality/stream-a/quality.plot.v1.png"
    )
    assert store.read_json(scientific.logical_uri, scientific.digest) == {"coverage_fraction": 1.0}
    assert store.read_bytes(png.logical_uri, png.digest) == b"\x89PNG\r\n\x1a\nfixture"


def test_product_publication_is_idempotent_and_never_overwrites(tmp_path: Path) -> None:
    store = AnalysisArtifactStore(tmp_path / "bulk")

    def publish(value: int) -> PublishedProduct:
        return store.publish_json(
            session_id="session-a",
            run_id="run-a",
            stage_key="quality",
            scope_key="stream-a",
            product=ProductSpec(kind="quality.summary"),
            document={"value": value},
        )

    first = publish(1)
    duplicate = publish(1)
    assert duplicate == first

    with pytest.raises(ArtifactConflictError, match="already differs"):
        publish(2)
    assert store.read_json(first.logical_uri, first.digest) == {"value": 1}


def test_pinned_read_rejects_rename_to_symlink_race_without_reading_outside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "bulk"
    (root / "spool").mkdir(parents=True)
    (root / "recordings").mkdir()
    pin = PinnedLocalRoot(root)
    store = AnalysisArtifactStore.open_pinned(pin)
    pin.close()
    published = store.publish_json(
        session_id="session-a",
        run_id="run-a",
        stage_key="quality",
        scope_key="stream-a",
        product=ProductSpec(kind="quality.summary"),
        document={"source": "inside"},
    )
    outside = tmp_path / "outside.json"
    outside.write_text('{"source":"outside"}', encoding="utf-8")
    outside.chmod(0o440)
    original_resolve = store.resolver.resolve
    raced = False

    def resolve_then_swap(uri: str, *, must_exist: bool = True) -> Path:
        nonlocal raced
        resolved = original_resolve(uri, must_exist=must_exist)
        if not raced:
            raced = True
            resolved.rename(resolved.with_suffix(".saved"))
            resolved.symlink_to(outside)
        return resolved

    monkeypatch.setattr(store.resolver, "resolve", resolve_then_swap)
    with pytest.raises(ArtifactCorruptionError, match="safely read pinned"):
        store.read_json(published.logical_uri, published.digest)
    assert outside.read_text(encoding="utf-8") == '{"source":"outside"}'
    store.close()


def test_verified_json_size_is_the_actual_safely_read_payload_size(tmp_path: Path) -> None:
    root = tmp_path / "bulk"
    (root / "spool").mkdir(parents=True)
    (root / "recordings").mkdir()
    pin = PinnedLocalRoot(root)
    store = AnalysisArtifactStore.open_pinned(pin)
    pin.close()
    published = store.publish_json(
        session_id="session-a",
        run_id="run-a",
        stage_key="quality",
        scope_key="stream-a",
        product=ProductSpec(kind="quality.summary"),
        document={"source": "inside"},
    )
    document, byte_size = store.read_json_with_size(published.logical_uri, published.digest)
    assert document == {"source": "inside"}
    assert byte_size == published.byte_size
    store.close()


@pytest.mark.parametrize(
    ("failure_point", "published"),
    [
        ("product:after_temp_fsync", False),
        ("product:after_publish", True),
    ],
)
def test_product_kill_points_are_unambiguously_absent_or_complete(
    tmp_path: Path,
    failure_point: str,
    published: bool,
) -> None:
    class InjectedFailure(RuntimeError):
        pass

    def inject(point: str) -> None:
        if point == failure_point:
            raise InjectedFailure(point)

    root = tmp_path / "bulk"
    store = AnalysisArtifactStore(root, failure_injector=inject)
    with pytest.raises(InjectedFailure, match=failure_point):
        store.publish_json(
            session_id="session-a",
            run_id="run-a",
            stage_key="quality",
            scope_key="stream-a",
            product=ProductSpec(kind="quality.summary"),
            document={"value": 1},
        )

    final = root / "analysis/session-a/run-a/scientific/quality/stream-a/quality.summary.v1.json"
    assert final.exists() is published
    if published:
        retry = AnalysisArtifactStore(root).publish_json(
            session_id="session-a",
            run_id="run-a",
            stage_key="quality",
            scope_key="stream-a",
            product=ProductSpec(kind="quality.summary"),
            document={"value": 1},
        )
        assert retry.logical_uri.startswith("bulk://analysis/")
        assert json.loads(final.read_bytes()) == {"value": 1}


def test_manifest_is_published_last_and_seals_run(tmp_path: Path) -> None:
    store = AnalysisArtifactStore(tmp_path / "bulk")
    product = store.publish_json(
        session_id="session-a",
        run_id="run-a",
        stage_key="quality",
        scope_key="stream-a",
        product=ProductSpec(kind="quality.summary"),
        document={"coverage_fraction": 1.0},
    )
    manifest = _manifest(product)

    published = store.seal_run(manifest)
    duplicate = store.seal_run(manifest)

    assert published == duplicate
    assert published.path.name == "manifest.json"
    assert published.path.is_file()
    with pytest.raises(RunSealedError, match="already sealed"):
        store.publish_json(
            session_id="session-a",
            run_id="run-a",
            stage_key="power",
            scope_key="stream-a",
            product=ProductSpec(kind="power.summary"),
            document={"coverage_fraction": 1.0},
        )


def test_manifest_publish_is_retryable_after_post_publish_failure(tmp_path: Path) -> None:
    class InjectedFailure(RuntimeError):
        pass

    def inject(point: str) -> None:
        if point == "manifest:after_publish":
            raise InjectedFailure(point)

    root = tmp_path / "bulk"
    store = AnalysisArtifactStore(root, failure_injector=inject)
    product = store.publish_json(
        session_id="session-a",
        run_id="run-a",
        stage_key="quality",
        scope_key="stream-a",
        product=ProductSpec(kind="quality.summary"),
        document={"coverage_fraction": 1.0},
    )
    manifest = _manifest(product)

    with pytest.raises(InjectedFailure, match="manifest:after_publish"):
        store.seal_run(manifest)

    final = root / "analysis/session-a/run-a/manifest.json"
    assert final.is_file()
    recovered = AnalysisArtifactStore(root).seal_run(manifest)
    assert recovered.path == final
    assert recovered.manifest == manifest
