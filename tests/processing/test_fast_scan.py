from datetime import timedelta

import pytest

from leo.contracts.fast_scan import FastScanPolicyV1
from leo.processing.fast_scan import FastScanProcessing
from tests.fast_scan_support import detector, predictor, recording

pytestmark = pytest.mark.postgres


def test_segment_jobs_are_isolated_resumable_and_publishable(processing_database, tmp_path):
    catalog = processing_database.catalog
    app = FastScanProcessing(catalog, tmp_path / "bulk", predictor=predictor, detector=detector)
    path = recording(tmp_path / "raw")
    run = app.queue(path, FastScanPolicyV1())
    assert app.queue(path, FastScanPolicyV1()) == run
    assert (
        catalog.claim_job(worker_id="other", lease_for=timedelta(minutes=1), run_ids=("other",))
        is None
    )
    worker = FastScanProcessing(
        catalog, tmp_path / "bulk", run_ids=(run,), predictor=predictor, detector=detector
    )
    assert worker.service.run_once(worker_id="test") is not None
    assert worker.service.run_once(worker_id="test") is None
    report = app.publish(run)
    assert report["counts"] == {"processed": 2, "skipped_fast_score": 1, "invalid_capture": 0}
    assert app.publish(run) == report
    assert app.queue(path, FastScanPolicyV1()) == run
    assert not report["qualified_tracking"]
    exported = app.tracking_input(run)
    assert exported["source"]["timing"] is None
    assert exported["clock_anchor"] is None
    assert exported["provenance"]["skipped_fast_score"] == 1
    assert exported["provenance"]["rf_mapping_authorities"] == ["hypothesis"]
    probes = exported["source"]["probes"]
    assert [(p["visit_index"], p["receiver_id"]) for p in probes] == [
        (1, 0), (1, 1), (2, 0), (2, 1)]
    assert probes[0]["valid_start_counter"] == 100000
    assert probes[0]["payload_start_sample"] == 50000
    assert probes[0]["actual_rf_hz"] == 10709687500
    published = app.store.publish_tracking_input(run, exported)
    assert app.store.publish_tracking_input(run, exported) == published
    with pytest.raises(ValueError, match="immutable"):
        app.store.publish_tracking_input(run, {**exported, "clock_anchor": {}})


def test_tracking_adapter_preserves_fractional_candidate_and_refuses_unsealed_run(
    processing_database, tmp_path
):
    from leo.contracts.fast_scan import FastScanCandidateV1, FastScanReceiverV1
    candidate = FastScanCandidateV1(
        candidate_rank=0, epoch_sample=123, acquired_cfo_hz=200,
        residual_cfo_hz=3, tracking_cfo_hz=203, exact_score=.3,
        control_score=.01, margin=.29, passed_margin_gate=True,
        fractional_epoch_status="complete", fractional_epoch_offset_samples=-.2,
        fractional_frame_phase_sample=122.8, fractional_exact_score=.31,
        fractional_control_score=.02, fractional_residual_cfo_hz=3.1,
        fractional_tracking_cfo_hz=203.1, fractional_margin=.29,
    )
    def measured(window, receivers):
        return tuple(FastScanReceiverV1(receiver_id=rx, candidates=(candidate,))
                     for rx in receivers)
    app = FastScanProcessing(processing_database.catalog, tmp_path / "bulk",
                             predictor=predictor, detector=measured)
    run = app.queue(recording(tmp_path / "raw"), FastScanPolicyV1())
    with pytest.raises(ValueError, match="sealed"):
        app.tracking_input(run)
    app.service.run_once(worker_id="test")
    app.publish(run)
    exported = app.tracking_input(run)
    c = exported["source"]["probes"][0]["candidates"][0]
    assert c["integer_epoch_sample"] == 123
    assert c["fractional_epoch_offset_samples"] == -.2
    assert c["fractional_tracking_cfo_hz"] == 203.1
    assert c["passed_fractional_margin_gate"] is True
    from tools.fast_scan_standard_pipeline import load_tracking_input

    tracking = load_tracking_input(exported)
    assert tracking.probes[0].candidates[0].fractional_tracking_cfo_hz == 203.1
    assert tracking.timing is None
