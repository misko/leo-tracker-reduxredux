"""Explicit runtime opt-in and post-capture publication of GLRT evidence."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from leo.contracts.scanner_glrt_publication import ScannerGlrtPublicationV1
from leo.contracts.scanner_glrt_session import ScannerGlrtSessionEvidenceV1
from leo.radio.scanner_glrt_metadata import ScannerGlrtOptions
from leo.scanner.glrt_publication import (
    ScannerGlrtEvidenceSource,
    validate_glrt_adaptive_binding,
    validate_glrt_capture_binding,
)
from leo.storage.adaptive_hop import PublishedAdaptiveHopIqSession
from leo.storage.persistent_hop import PublishedPersistentHopIqSession
from leo.storage.scanner_glrt import ScannerGlrtStore


def scanner_glrt_options(values: Mapping[str, str]) -> ScannerGlrtOptions | None:
    mode = values.get("LEO_SCANNER_GLRT_MODE", "disabled")
    keys = (
        "LEO_SCANNER_GLRT_ALGORITHM_SHA256",
        "LEO_SCANNER_GLRT_CONFIGURATION_SHA256",
        "LEO_SCANNER_GLRT_DRAIN_BUDGET_SECONDS",
    )
    if mode == "disabled":
        if any(key in values for key in keys):
            raise ValueError("GLRT parameters require an explicit detector opt-in")
        return None
    if mode not in ("unqualified-evidence", "positive-only-v1"):
        raise ValueError("GLRT mode must be disabled, unqualified-evidence or positive-only-v1")
    return ScannerGlrtOptions(
        algorithm_sha256=values.get(keys[0], ""),
        configuration_sha256=values.get(keys[1], ""),
        drain_budget_seconds=float(values.get(keys[2], "5")),
        mode=mode,
    )


def publish_scanner_glrt(
    source: ScannerGlrtEvidenceSource,
    capture: PublishedPersistentHopIqSession | PublishedAdaptiveHopIqSession,
    options: ScannerGlrtOptions,
    *,
    store_factory: Callable[[Path], ScannerGlrtStore],
    bulk_root: Path,
    realtime_ns: Callable[[], int] = time.time_ns,
) -> str | None:
    """Called only after immutable IQ publication and radio/lifecycle cleanup.

    Result failures must not make a good IQ recording fail or trigger another
    capture. Missing/invalid metadata gets an explicit error product when the
    independent store is available. Storage failures remain observable warnings.
    """
    try:
        error = getattr(source, "classification_error", None)
        evidence = getattr(source, "classification_evidence", None)
        if evidence is not None and not isinstance(evidence, ScannerGlrtSessionEvidenceV1):
            raise ValueError("radio returned an invalid GLRT evidence type")
        if evidence is not None:
            evidence = ScannerGlrtSessionEvidenceV1.model_validate(evidence.model_dump())
        if evidence is None and error is None:
            error = "radio supplied no GLRT evidence after capture"
        publication = ScannerGlrtPublicationV1(
            session_id=capture.session_id,
            input_manifest_sha256=capture.manifest_sha256,
            algorithm_sha256=options.algorithm_sha256,
            configuration_sha256=options.configuration_sha256,
            published_utc_ns=realtime_ns(),
            evidence=evidence,
            error=error,
        )
        _validate_binding(publication, capture)
    except Exception as failure:
        publication = ScannerGlrtPublicationV1(
            session_id=capture.session_id,
            input_manifest_sha256=capture.manifest_sha256,
            algorithm_sha256=options.algorithm_sha256,
            configuration_sha256=options.configuration_sha256,
            published_utc_ns=time.time_ns(),
            evidence=None,
            error=f"GLRT evidence rejected: {type(failure).__name__}: {failure}"[:2048],
        )
    warning: str | None
    try:
        store_factory(bulk_root).publish(publication)
    except Exception as failure:
        warning = f"GLRT result publication failed: {type(failure).__name__}: {failure}"[:2048]
    else:
        warning = publication.error or (
            publication.evidence.error if publication.evidence is not None else None
        )
        if (
            warning is None
            and publication.evidence is not None
            and not publication.evidence.delivery_complete
        ):
            warning = "GLRT result delivery is incomplete"
    if warning is not None:
        logging.getLogger(__name__).warning(
            "%s: %s; IQ capture preserved", capture.session_id, warning
        )
    return warning


def existing_scanner_glrt_warning(
    capture: PublishedPersistentHopIqSession | PublishedAdaptiveHopIqSession,
    options: ScannerGlrtOptions,
    *,
    store_factory: Callable[[Path], ScannerGlrtStore],
    bulk_root: Path,
) -> str | None:
    """A capture retry reads old evidence; it never reuses a radio's last result."""
    try:
        publication = store_factory(bulk_root).read(capture.session_id)
        if publication is None:
            return "no GLRT evidence recorded for this existing capture; radio was not reopened"
        _validate_binding(publication, capture)
        if (
            publication.algorithm_sha256 != options.algorithm_sha256
            or publication.configuration_sha256 != options.configuration_sha256
        ):
            return "existing capture has different GLRT identities; original evidence retained"
        if publication.error is not None:
            return publication.error
        evidence = publication.evidence
        if evidence is not None:
            if evidence.error is not None:
                return evidence.error
            if not evidence.delivery_complete:
                return "GLRT result delivery is incomplete"
        return None
    except Exception as failure:
        return f"existing GLRT evidence unavailable: {type(failure).__name__}: {failure}"[:2048]


def _validate_binding(
    publication: ScannerGlrtPublicationV1,
    capture: PublishedPersistentHopIqSession | PublishedAdaptiveHopIqSession,
) -> None:
    if isinstance(capture, PublishedAdaptiveHopIqSession):
        validate_glrt_adaptive_binding(
            publication, capture.manifest.receipt, input_manifest_sha256=capture.manifest_sha256
        )
    else:
        validate_glrt_capture_binding(
            publication, capture.manifest.receipt, input_manifest_sha256=capture.manifest_sha256
        )
