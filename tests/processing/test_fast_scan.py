from datetime import timedelta

import pytest

from leo.contracts.fast_scan import FastScanPolicyV1
from leo.processing.fast_scan import FastScanProcessing
from tests.fast_scan_support import detector, predictor, recording

pytestmark = pytest.mark.postgres


@pytest.mark.parametrize('excluded', [(), (0, 63, 66)])
def test_native_scopes_resume_and_publish_complete_cross_boundary_coverage(processing_database, tmp_path, excluded):
    import numpy as np
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.processing.service import RunNotReadyError
    from leo.storage.short_window import ShortWindowWriter
    from tests.fast_scan_support import TARGET
    writer = ShortWindowWriter(tmp_path / 'raw', 'native-bounded', schema_version=2,
        configuration={'sample_rate_hz': 10_000_000, 'window_ms': 20, 'targets': [TARGET]},
        radio={'serial': 'synthetic'}, receiver_ids=(0, 1))
    for visit in range(67):
        writer.append(sequence=visit, target_id='ch1',
            samples=np.zeros((200_000, 2, 2), dtype='<i2'), powers=({}, {}),
            acquisition=dict(global_visit=visit, sample_start=visit * 400_000,
                sample_end=visit * 400_000 + 200_000, generation=1,
                actual_if_center_hz=959687500, complete=True,
                validity_authority='provider_attested', validity_includes_guard=True,
                quality_flags=['adc12_clipping'] if visit in excluded else []))
    path = writer.finish(stop_reason='test')
    app = FastScanProcessing(processing_database.catalog, tmp_path / 'bulk',
                            predictor=predictor, detector=detector)
    run = app.queue(path, FastScanPolicyV2())
    assert app.service.run_once(worker_id='first-scope') is not None
    with pytest.raises(RunNotReadyError, match='unfinished jobs'):app.publish(run)
    assert app.queue(path, FastScanPolicyV2()) == run
    assert app.service.run_once(worker_id='second-scope') is not None
    assert app.service.run_once(worker_id='empty') is None
    report = app.publish(run)
    assert report['counts'] == dict(processed=67-len(excluded), skipped_fast_score=0, invalid_capture=len(excluded))
    assert report['window_count'] == 67
    exported = app.tracking_input(run)
    valid = [i for i in range(67) if i not in excluded]
    assert exported['schema_version'] == 2
    assert exported['provenance']['invalid_capture'] == len(excluded)
    assert [w['visit'] for w in exported['provenance']['excluded_windows']] == list(excluded)
    assert [p['visit_index'] for p in exported['source']['probes']][::2] == valid
    assert [p['valid_start_counter'] for p in exported['source']['probes']][::2] == [i * 400_000 for i in valid]
    assert [p['payload_start_sample'] for p in exported['source']['probes']][::2] == [i * 200_000 for i in valid]


def test_native_10m_queue_publication_and_tracking_keep_source_coordinates(processing_database, tmp_path):
    import numpy as np
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.storage.short_window import ShortWindowWriter
    from tests.fast_scan_support import TARGET

    writer = ShortWindowWriter(tmp_path / "raw", "native", schema_version=2,
        configuration={"sample_rate_hz": 10_000_000, "window_ms": 20, "targets": [TARGET]},
        radio={"serial": "synthetic"}, receiver_ids=(0, 1))
    for visit in range(2):
        writer.append(sequence=visit, target_id="ch1",
            samples=np.zeros((200_000, 2, 2), dtype="<i2"), powers=({}, {}),
            acquisition=dict(global_visit=visit, sample_start=visit * 400_000,
                sample_end=visit * 400_000 + 200_000, generation=1,
                actual_if_center_hz=959687500, complete=True,
                validity_authority="provider_attested", validity_includes_guard=True,
                quality_flags=[]))
    path = writer.finish(stop_reason="test")
    def forbidden(*args):
        raise AssertionError("unqualified fast predictor must be disabled")
    app = FastScanProcessing(processing_database.catalog, tmp_path / "bulk",
                            predictor=forbidden, detector=detector)
    run = app.queue(path, FastScanPolicyV2())
    assert app.service.run_once(worker_id="native-test") is not None
    report = app.publish(run)
    assert report["counts"] == dict(processed=2, skipped_fast_score=0, invalid_capture=0)
    assert report["policy"]["sample_rate_hz"] == 10_000_000
    exported = app.tracking_input(run)
    assert exported["source"]["sample_rate_hz"] == 10_000_000
    probes = exported["source"]["probes"]
    assert [p["payload_start_sample"] for p in probes] == [0, 0, 200_000, 200_000]
    assert [p["valid_start_counter"] for p in probes] == [0, 0, 400_000, 400_000]


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
