"""Publish explicit positioning exclusions required by the partial-band contract."""

from pydantic import JsonValue

from leo.application.regional_position_report import regional_position_document
from leo.cli.adaptive_tle_position import configuration as baseline_configuration
from leo.cli.regional_position import REFERENCE, configuration
from leo.contracts.adaptive_tle_position import AdaptiveTlePositionDocumentV3
from leo.contracts.digests import canonical_digest
from leo.contracts.partial_band import PartialBandManifestV1
from leo.presentation.adaptive_tle_position import render_adaptive_tle_position
from leo.presentation.regional_position import render_regional_position
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStoreV3
from leo.storage.regional_position import RegionalPositionStore


def publish_partial_band_positions(root, manifest: PartialBandManifestV1):
    """The verified source declares phase_and_position_status=not_qualified_for_partial_band."""
    manifest = PartialBandManifestV1.model_validate(manifest.model_dump(mode="json"))
    session = manifest.binding.session_id
    capture = manifest.binding.input_manifest_sha256
    analysis = canonical_digest(manifest.model_dump(mode="json"))
    reason = (
        "partial-band filtered-pilot evidence is candidate-only and not qualified for positioning"
    )
    evidence = canonical_digest(
        {"analysis": analysis, "position_status": manifest.phase_and_position_status}
    )
    diagnostics: dict[str, JsonValue] = {
        "partial_band_analysis_sha256": analysis,
        "candidate_probe_count": manifest.candidate_probe_count,
        "probe_count": manifest.probe_count,
        "phase_and_position_status": manifest.phase_and_position_status,
    }
    baseline = AdaptiveTlePositionDocumentV3(
        session_id=session,
        input_manifest_sha256=capture,
        analysis_manifest_sha256=analysis,
        configuration_sha256=canonical_digest(baseline_configuration()),
        evidence_sha256=evidence,
        state="insufficient",
        priors=(),
        reasons=(reason,),
        diagnostics=diagnostics,
    )
    store = AdaptiveTlePositionStoreV3(root, read_only=False)
    with store.writer(session):
        store.publish(baseline, render_adaptive_tle_position(baseline))
    result = {
        "searches": {
            name: {
                "evaluations": [],
                "deferred_cells": 0,
                "stop_reason": "partial-band-not-qualified",
            }
            for name in ("T1AT", "V16")
        },
        "points": {},
        "finals": [],
        "failures": [{"reason": reason}],
    }
    document = regional_position_document(
        result,
        session_id=session,
        input_digest=capture,
        analysis_digest=analysis,
        evidence_digest=evidence,
        configuration=configuration(),
        windows=0,
        reference=REFERENCE,
        reference_evidence="Configured baseline receiver reference; evaluation only",
        diagnostics=diagnostics,
    )
    RegionalPositionStore(root, read_only=False).publish(
        document, {name: render_regional_position(document, name) for name in ("T1AT", "V16")}
    )
