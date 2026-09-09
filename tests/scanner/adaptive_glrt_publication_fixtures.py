"""Source-bound synthetic positives plus an explicit cancelled last event."""

from leo.contracts.scanner_glrt_frame import ScannerGlrtClassificationV1
from leo.contracts.scanner_glrt_publication import ScannerGlrtPublicationV1
from leo.contracts.scanner_glrt_session import ScannerGlrtSessionEvidenceV1

ALGORITHM = "a" * 64
CONFIGURATION = "b" * 64
MANIFEST = "sha256:" + "c" * 64


def evidence_fixture(receipt):
    rate = receipt.plan.geometry.sample_rate_hz
    results = []
    for index, event in enumerate(receipt.events):
        start = event.valid_start_counter
        retained = index < receipt.complete_visit_count
        results.append(
            ScannerGlrtClassificationV1(
                sequence=index,
                visit=index,
                valid_start=start,
                valid_end=start + rate * 120 // 1000,
                search_start=start,
                search_end=start + rate * 120 // 1000 if retained else start,
                confirmation_start=start,
                confirmation_end=start + rate // 50 if retained else start,
                rate_hz=rate,
                channel=event.target.channel,
                edge=event.target.edge,
                rx=1,
                verdict="starlink" if retained else "unavailable",
                reason="complete" if retained else "cancelled",
                search_window_mask=63 if retained else 0,
                exact_score=0.25 if retained else 0.0,
                control_score=0.06 if retained else 0.0,
                margin=0.19 if retained else 0.0,
                cfo_hz=173123.0 if retained else 0.0,
                epoch_sample_counter=start + 317 if retained else 0,
                fractional_offset_samples=0.375 if retained else 0.0,
                cpu_ms=64.0 if retained else 0.0,
                wall_ms=70.0 if retained else 0.0,
            )
        )
    return ScannerGlrtSessionEvidenceV1(
        session=receipt.terminal.session_id,
        generation=receipt.plan.policy.generation,
        algorithm_sha256=ALGORITHM,
        configuration_sha256=CONFIGURATION,
        negotiated=True,
        mode="positive-only-v1",
        source_terminal_attested=True,
        final_received=True,
        expected_results=len(results),
        dropped_results=0,
        result_sequence_limit=len(results),
        results=tuple(results),
        delivery_complete=True,
        classification_complete=bool(results) and receipt.terminal.state == "completed",
        error=None,
    )


def publication_fixture(receipt, manifest=MANIFEST):
    return ScannerGlrtPublicationV1(
        session_id=receipt.session_id,
        input_manifest_sha256=manifest,
        algorithm_sha256=ALGORITHM,
        configuration_sha256=CONFIGURATION,
        published_utc_ns=1_780_000_000_000_000_001,
        evidence=evidence_fixture(receipt),
        error=None,
    )
