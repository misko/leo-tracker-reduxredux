from __future__ import annotations

from pathlib import Path

import pytest

import leo.scanner.persistent_hop_analysis as persistent_source_module
from leo.application.persistent_hop_analysis import PersistentHopAnalysisService
from leo.presentation.persistent_hop_analysis import render_persistent_hop_analysis_pngs
from leo.scanner.detector import DwellGlrt64Analysis, Glrt64ProbeResponse
from leo.scanner.fake_persistent_hop import FakePersistentHopRadio
from leo.scanner.persistent_hop import compile_persistent_hop_plan_v1
from leo.storage.errors import BundleCorruptionError
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.persistent_hop_analysis import (
    PersistentHopAnalysisStore,
    PersistentHopPresentationStore,
)
from leo.storage.persistent_hop_analysis_source import PersistentHopAnalysisInputStore


def _capture(root: Path, *, visit_count: int = 9) -> PersistentHopIqStore:
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)
    radio = FakePersistentHopRadio()
    radio.open()
    session = radio.begin_session(plan, session_id="hop-analysis-store")
    captures = PersistentHopIqStore(root)
    writer = captures.begin("hop-analysis-store", plan)
    for _ in range(visit_count):
        block = session.read_visit()
        writer.append(block)
    session.request_cancel()
    receipt = session.finish()
    writer.finish(receipt)
    radio.close()
    return captures


def _empty_dwell(_samples, configuration, *, edge) -> DwellGlrt64Analysis:
    return DwellGlrt64Analysis(
        first=None,
        decision_best_margin=None,
        full_best_margin=None,
        reason=f"no candidates at {edge}",
        probes=tuple(
            Glrt64ProbeResponse(
                receiver_id=receiver_id,
                probe_index=probe_index,
                probe_start_ms=probe_index * configuration.probe_stride_ms,
                candidates=(),
            )
            for probe_index in range(configuration.scheduled_probe_count)
            for receiver_id in configuration.receiver_ids
        ),
    )


def test_worker_resumes_at_sweep_boundary_and_publishes_verified_ui_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captures = _capture(tmp_path)
    products = PersistentHopAnalysisStore(tmp_path)
    service = PersistentHopAnalysisService(
        inputs=PersistentHopAnalysisInputStore(captures),
        products=products,
        renderer=render_persistent_hop_analysis_pngs,
    )
    calls = 0

    def fail_on_ninth_visit(samples, configuration, *, edge):
        nonlocal calls
        calls += 1
        if calls == 9:
            raise RuntimeError("injected second-sweep interruption")
        return _empty_dwell(samples, configuration, edge=edge)

    monkeypatch.setattr(
        persistent_source_module,
        "analyze_glrt64_dwell",
        fail_on_ninth_visit,
    )
    failed = service.run_pending(maximum_sessions=1)

    assert failed.completed_session_ids == ()
    assert "injected second-sweep interruption" in failed.failures[0]
    assert products.completed_sweeps("hop-analysis-store") == (0,)
    failed_status = products.status("hop-analysis-store", total_visits=9)
    assert failed_status.state == "failed"
    assert failed_status.analyzed_visits == 8

    calls = 0
    monkeypatch.setattr(
        persistent_source_module,
        "analyze_glrt64_dwell",
        _empty_dwell,
    )
    original_write = products._write_new_regular
    interrupted = False

    def interrupt_first_presentation_write(path: Path, payload: bytes) -> None:
        nonlocal interrupted
        original_write(path, payload)
        if path.parent.name == "presentation" and not interrupted:
            interrupted = True
            raise RuntimeError("injected publication interruption")

    monkeypatch.setattr(products, "_write_new_regular", interrupt_first_presentation_write)
    publication_failed = service.run_pending(maximum_sessions=1)

    assert "injected publication interruption" in publication_failed.failures[0]
    assert products.completed_sweeps("hop-analysis-store") == (0, 1)
    assert products.status("hop-analysis-store", total_visits=9).state == "failed"

    monkeypatch.setattr(products, "_write_new_regular", original_write)
    completed = service.run_pending(maximum_sessions=1)

    assert completed.completed_session_ids == ("hop-analysis-store",)
    assert completed.failures == ()
    assert products.is_complete("hop-analysis-store")
    published = products.inspect("hop-analysis-store")
    assert published.manifest.visit_count == 9
    assert published.manifest.sweep_count == 2
    assert published.manifest.probe_count == 9 * 2 * 11
    assert published.manifest.passed_best_count == 0
    assert published.manifest.checkpoint_binding_relative_path == "work-manifest.v1.json"
    assert published.manifest.checkpoint_binding_sha256.startswith("sha256:")
    assert sorted(item.name for item in published.path.iterdir()) == [
        "manifest.json",
        "metrics-sweep-000000.v1.json.zst",
        "metrics-sweep-000001.v1.json.zst",
        "presentation",
        "work-manifest.v1.json",
    ]
    assert sorted(item.name for item in (published.path / "presentation").iterdir()) == [
        "persistent-hop-cfo-trajectories.v1.png",
        "persistent-hop-coverage.v1.png",
        "persistent-hop-glrt64-response.v1.png",
    ]
    assert (
        not (tmp_path / "scanner-hop-analysis-work" / "hop-analysis-store")
        .joinpath("persistent-hop-glrt64-cfo-v1")
        .exists()
    )
    for artifact in ("coverage", "glrt64-response", "cfo-trajectories"):
        payload = products.artifact("hop-analysis-store", artifact)
        assert payload is not None
        assert payload.startswith(b"\x89PNG\r\n\x1a\n")

    presentation = PersistentHopPresentationStore(captures, products)
    page = presentation.page_v2(cursor=0, limit=5)
    assert page.items[0].analysis.state == "complete"
    assert set(page.items[0].available_artifacts) == {
        "coverage",
        "glrt64-response",
        "cfo-trajectories",
    }
    detail = presentation.detail("hop-analysis-store")
    assert detail is not None
    assert detail.product == published.manifest


def test_analysis_store_read_only_open_does_not_create_namespaces(tmp_path: Path) -> None:
    PersistentHopAnalysisStore.open_read_only(tmp_path)

    assert not (tmp_path / "scanner-hop-analysis").exists()
    assert not (tmp_path / "scanner-hop-analysis-work").exists()
    assert not (tmp_path / "control").exists()


def test_analysis_store_rejects_tampered_published_checkpoint_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captures = _capture(tmp_path, visit_count=1)
    products = PersistentHopAnalysisStore(tmp_path)
    monkeypatch.setattr(persistent_source_module, "analyze_glrt64_dwell", _empty_dwell)
    service = PersistentHopAnalysisService(
        inputs=PersistentHopAnalysisInputStore(captures),
        products=products,
        renderer=render_persistent_hop_analysis_pngs,
    )
    assert service.run_pending(maximum_sessions=1).failures == ()
    published = products.inspect("hop-analysis-store")
    binding = published.path / published.manifest.checkpoint_binding_relative_path
    binding.write_bytes(binding.read_bytes() + b"\n")

    with pytest.raises(BundleCorruptionError, match="checkpoint binding digest mismatch"):
        products.inspect("hop-analysis-store")
