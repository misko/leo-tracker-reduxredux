from leo.application.partial_band import replay_partial_band
from leo.cli.partial_band_position import publish_partial_band_positions
from leo.contracts.digests import canonical_digest
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStoreV3
from leo.storage.partial_band import PartialBandStore
from leo.storage.regional_position_v2 import Hard60Store
from tests.storage.test_partial_band_store import Captures


def test_unqualified_partial_band_has_baseline_and_hard60_explicit_diagnostic_figures(tmp_path):
    captures = Captures()
    session, capture = captures.capture.session_id, captures.capture.manifest_sha256
    products = PartialBandStore(tmp_path, read_only=False)
    replay_partial_band(captures=captures, products=products, session_id=session, maximum_workers=1)
    manifest = products.status(session, capture).manifest
    publish_partial_band_positions(tmp_path, manifest)
    # Restart must be idempotent, without new RF or re-analysis.
    publish_partial_band_positions(tmp_path, manifest)
    baseline = AdaptiveTlePositionStoreV3(tmp_path)
    regional = Hard60Store(tmp_path)
    doc = baseline.status(session).manifest.document
    assert doc.state == "insufficient" and "candidate-only" in doc.reasons[0]
    assert doc.analysis_manifest_sha256 == canonical_digest(manifest.model_dump(mode="json"))
    assert baseline.artifact(session).startswith(b"\x89PNG")
    regional_doc = regional.status(session).manifest.document
    assert all(method.state == "insufficient" for method in regional_doc.methods)
    assert all(arm.selected is None for method in regional_doc.methods for arm in method.arms)
    for method in ("V16",):
        assert regional.artifact(session, method).startswith(b"\x89PNG")
