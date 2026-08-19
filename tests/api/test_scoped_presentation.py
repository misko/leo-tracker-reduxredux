from __future__ import annotations

from datetime import UTC, datetime

from leo.application.presentation import _detection
from leo.catalog import CatalogRunReadSnapshot
from leo.presentation.models import AnalysisProductV1


def _product(product_id: str, scope_key: str) -> AnalysisProductV1:
    return AnalysisProductV1(
        product_id=product_id,
        session_id="paired-session",
        analysis_run_id="paired-run",
        kind="detection",
        status="complete",
        content_type="application/json",
        artifact_path=f"/srv/bulk/leo/analysis/paired-session/paired-run/{scope_key}.json",
        byte_count=100,
        sha256="a" * 64,
        coverage=None,
        summary={"scope_key": scope_key},
    )


def test_detection_projection_selects_each_stream_instead_of_first_product() -> None:
    now = datetime.now(UTC)
    run = CatalogRunReadSnapshot(
        run_id="paired-run",
        pipeline_release_id="standard-v1",
        pipeline_configuration={},
        state="succeeded",
        created_at=now,
        started_at=now,
        sealed_at=now,
        failure=None,
        input_manifest_digest="sha256:" + "b" * 64,
        manifest_uri=None,
        manifest_digest=None,
        is_current=True,
        summary=None,
        jobs=(),
        products=(),
    )
    products = (_product("ap-1", "stream-0"), _product("ap-2", "stream-1"))
    documents = {
        "ap-1": {
            "run_id": "paired-run",
            "candidate_count": 1,
            "known_pilot_candidate": True,
            "calibrated_detection": False,
            "confidence_reason": "stream zero evidence",
            "candidates": [{"margin": 0.4, "verify_score": 0.5, "control_score": 0.1}],
        },
        "ap-2": {
            "run_id": "paired-run",
            "candidate_count": 0,
            "known_pilot_candidate": False,
            "calibrated_detection": False,
            "confidence_reason": "stream one has no candidate",
            "candidates": [],
        },
    }

    first = _detection(run, (), products, documents, scope_key="stream-0")
    second = _detection(run, (), products, documents, scope_key="stream-1")

    assert first.known_pilot_candidate is True
    assert first.qin_score == 0.5
    assert first.reason == "stream zero evidence"
    assert second.known_pilot_candidate is False
    assert second.qin_score is None
    assert second.reason == "stream one has no candidate"


def test_missing_scoped_document_never_inherits_another_stream_result() -> None:
    now = datetime.now(UTC)
    run = CatalogRunReadSnapshot(
        run_id="paired-run",
        pipeline_release_id="standard-v1",
        pipeline_configuration={},
        state="succeeded",
        created_at=now,
        started_at=now,
        sealed_at=now,
        failure=None,
        input_manifest_digest="sha256:" + "b" * 64,
        manifest_uri=None,
        manifest_digest=None,
        is_current=True,
        summary=None,
        jobs=(),
        products=(),
    )
    products = (_product("ap-1", "stream-0"),)
    documents = {
        "ap-1": {
            "run_id": "paired-run",
            "candidate_count": 1,
            "known_pilot_candidate": True,
            "calibrated_detection": False,
            "confidence_reason": "stream zero evidence",
            "candidates": [],
        }
    }

    absent = _detection(run, (), products, documents, scope_key="stream-1")

    assert absent.known_pilot_candidate is False
    assert absent.state.value == "not_run"
