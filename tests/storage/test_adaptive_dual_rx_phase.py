import pytest

from leo.storage.adaptive_dual_rx_phase import AdaptiveDualRxPhaseStore
from leo.storage.errors import BundleCorruptionError
from tests.presentation.adaptive_overview_fixtures import rendered_fixture


def digest(letter: str) -> str:
    return "sha256:" + letter * 64


def test_phase_product_is_immutable_digest_bound_and_read_only(tmp_path):
    png = rendered_fixture().artifacts["coverage"]
    store = AdaptiveDualRxPhaseStore(tmp_path)
    manifest = store.publish(
        session_id="scan-hop-phase-test",
        input_manifest_sha256=digest("1"),
        glrt_binding_sha256=digest("2"),
        glrt_metrics_manifest_sha256=digest("3"),
        qualified_phase_count=4,
        association_count=1,
        png=png,
    )
    assert manifest.state == "ready" and manifest.artifact is not None
    assert store.artifact(manifest, expected_sha256=manifest.artifact.sha256) == png
    assert (
        store.publish(
            session_id="scan-hop-phase-test",
            input_manifest_sha256=digest("1"),
            glrt_binding_sha256=digest("2"),
            glrt_metrics_manifest_sha256=digest("3"),
            qualified_phase_count=4,
            association_count=1,
            png=png,
        )
        == manifest
    )
    with pytest.raises(BundleCorruptionError):
        store.publish(
            session_id="scan-hop-phase-test",
            input_manifest_sha256=digest("1"),
            glrt_binding_sha256=digest("2"),
            glrt_metrics_manifest_sha256=digest("3"),
            qualified_phase_count=5,
            association_count=1,
            png=png,
        )
    store.close()
    read_only = AdaptiveDualRxPhaseStore(tmp_path, read_only=True)
    with pytest.raises(BundleCorruptionError):
        read_only.artifact(manifest, expected_sha256=digest("9"))
    read_only.close()


def test_insufficient_signal_has_no_png(tmp_path):
    store = AdaptiveDualRxPhaseStore(tmp_path)
    manifest = store.publish(
        session_id="scan-hop-phase-empty",
        input_manifest_sha256=digest("1"),
        glrt_binding_sha256=digest("2"),
        glrt_metrics_manifest_sha256=digest("3"),
        qualified_phase_count=0,
        association_count=0,
        png=None,
    )
    assert manifest.state == "insufficient_signal" and manifest.artifact is None
    store.close()
