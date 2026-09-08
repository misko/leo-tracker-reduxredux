"""Small synthetic capture fixtures; never opens hardware or existing archives."""

from leo.contracts.scanner_glrt_frame import ScannerGlrtClassificationV1
from leo.contracts.scanner_glrt_publication import ScannerGlrtPublicationV1
from leo.contracts.scanner_glrt_session import ScannerGlrtSessionEvidenceV1
from leo.scanner.fake_persistent_hop import FakePersistentHopRadio
from leo.scanner.persistent_hop import (
    compile_persistent_hop_plan_v1,
    persistent_hop_wire_session_id,
)
from leo.storage.persistent_hop import PersistentHopIqStore

ALGORITHM = "a" * 64
CONFIGURATION = "b" * 64


def make_evidence(receipt):
    visit = receipt.visits[0]
    start, rate = visit.valid_device_sample_counter, receipt.plan.sample_rate_hz
    result = ScannerGlrtClassificationV1(
        sequence=0,
        visit=0,
        valid_start=start,
        valid_end=start + rate * 120 // 1000,
        search_start=start,
        search_end=start + rate * 120 // 1000,
        confirmation_start=start,
        confirmation_end=start + rate // 50,
        rate_hz=rate,
        channel=visit.target.channel,
        edge=visit.target.edge,
        rx=1,
        verdict="unavailable",
        reason="unqualified_classifier",
        search_window_mask=63,
        exact_score=0.25,
        control_score=0.06,
        margin=0.19,
        cfo_hz=173123.0,
        epoch_sample_counter=start + 317,
        fractional_offset_samples=0.375,
        cpu_ms=64.0,
        wall_ms=70.0,
    )
    return ScannerGlrtSessionEvidenceV1(
        session=persistent_hop_wire_session_id(receipt.session_id),
        generation=2**53 + 31,
        algorithm_sha256=ALGORITHM,
        configuration_sha256=CONFIGURATION,
        negotiated=True,
        mode="unqualified-evidence",
        source_terminal_attested=True,
        final_received=True,
        expected_results=1,
        dropped_results=0,
        result_sequence_limit=1,
        results=(result,),
        delivery_complete=True,
        classification_complete=False,
        error=None,
    )


def make_capture(root, *, session_id="scan-hop-glrt-test", rate=2500000):
    store = PersistentHopIqStore(root)
    radio = FakePersistentHopRadio(first_device_sample_counter=2**53 + 19)
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=rate)
    radio.open()
    session = radio.begin_session(plan, session_id=session_id)
    block = session.read_visit()
    session.request_cancel()
    receipt = session.finish()
    radio.close()
    writer = store.begin(session_id, plan)
    writer.append(block)
    capture = writer.finish(receipt)
    return store, capture


def make_publication(capture):
    return ScannerGlrtPublicationV1(
        session_id=capture.session_id,
        input_manifest_sha256=capture.manifest_sha256,
        algorithm_sha256=ALGORITHM,
        configuration_sha256=CONFIGURATION,
        published_utc_ns=1788870000000000001,
        evidence=make_evidence(capture.manifest.receipt),
        error=None,
    )
