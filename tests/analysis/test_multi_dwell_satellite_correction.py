from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from pydantic import ValidationError

from leo.analysis.joint_frequency_calibration import JointFrequencyCalibrationConfig
from leo.analysis.multi_dwell_joint_frequency_calibration import (
    calibrate_multi_dwell_history_frequencies,
)
from leo.analysis.multi_dwell_satellite_correction import (
    build_sequential_history_satellite_correction,
)
from leo.analysis.satellite_correction_replay import SatelliteCorrectionInputError
from leo.contracts.digests import canonical_digest
from leo.contracts.satellite_pnt import CalibrationSourceSpanV1
from leo.contracts.satellite_pnt_multi_dwell_correction import (
    KnownPositionSequentialHistoryCalibrationReceiptV1,
    SequentialHistoryCorrectionModeV1,
    SequentialHistorySatelliteCorrectionProductV1,
)
from tests.analysis.test_multi_dwell_joint_frequency_calibration import _inputs


def _calibration_and_spans(*, gauge_resolved: bool = True) -> tuple[Any, ...]:
    graphs, banks, _adapted, posterior, component_priors, hardware_priors = _inputs()
    calibration = calibrate_multi_dwell_history_frequencies(
        posterior=posterior,
        graphs=graphs,
        prediction_banks=banks,
        component_priors=component_priors,
        hardware_priors=hardware_priors,
        receiver_frequency_reference_authority_digest=canonical_digest(
            {"receiver-frequency": "synthetic"}
        ),
        receiver_frequency_gauge_resolved=gauge_resolved,
        calibration_config=JointFrequencyCalibrationConfig(
            minimum_observations_per_satellite=4,
            minimum_span_s_per_satellite=1.0,
        ),
    )
    source_authority = canonical_digest({"source-authority": "synthetic"})
    spans = tuple(
        CalibrationSourceSpanV1(
            source_fingerprint_authority_digest=source_authority,
            source_recording_fingerprint=canonical_digest({"recording": index}),
            source_stream_index=0,
            source_sample_start=min(item.source_sample_start for item in graph.observations),
            source_sample_stop=max(item.source_sample_end for item in graph.observations),
            start_utc_ns=min(item.support_start_utc_ns for item in graph.observations),
            end_utc_ns=max(item.support_end_utc_ns for item in graph.observations),
        )
        for index, graph in enumerate(graphs)
    )
    return graphs, banks, posterior, calibration, spans


def _receipt(*, gauge_resolved: bool = True) -> KnownPositionSequentialHistoryCalibrationReceiptV1:
    _graphs, banks, posterior, calibration, spans = _calibration_and_spans(
        gauge_resolved=gauge_resolved
    )
    end_utc_ns = max(item.end_utc_ns for item in spans)
    return build_sequential_history_satellite_correction(
        posterior=posterior,
        calibration=calibration,
        prediction_banks=banks,
        calibration_source_spans=spans,
        calibration_site=banks[0].observer_site,
        calibration_site_authority_digest=canonical_digest({"site-authority": "synthetic"}),
        calibration_protocol_digest=canonical_digest({"protocol": "sequential-calibration"}),
        frequency_calibration_authority_digest=canonical_digest(
            {"frequency-authority": "synthetic"}
        ),
        produced_utc_ns=end_utc_ns + 1_000_000_000,
        sealed_utc_ns=end_utc_ns + 2_000_000_000,
    )


def test_sequential_correction_transfers_states_without_future_activity_claim() -> None:
    receipt = _receipt()
    product = receipt.correction_product

    assert product.status.value == "partial"
    assert product.receiver_local_state_excluded
    assert product.sequential_history_semantics_preserved
    assert product.future_activity_selection_required
    assert product.simultaneous_activity_inferred_from_history is False
    assert product.navigation_eligible is False
    assert product.identity_claimed is False
    assert product.modes
    assert any(item.calibration_transferable for item in product.modes)
    assert all(not item.navigation_eligible for item in product.modes)
    serialized = product.model_dump_json()
    assert "synthetic-known-site" not in serialized
    assert "receiver_local_state_digest" not in serialized
    assert "receiver_drift_hz_s" not in serialized
    assert receipt.calibration_site.label == "synthetic-known-site"


def test_unresolved_gauge_preserves_modes_but_transfers_no_calibration() -> None:
    product = _receipt(gauge_resolved=False).correction_product

    assert all(not item.calibration_transferable for item in product.modes)
    assert all(not item.receiver_frequency_gauge_resolved for item in product.modes)


def test_product_probabilities_and_history_assignments_match_posterior() -> None:
    _graphs, _banks, posterior, _calibration, _spans = _calibration_and_spans()
    product = _receipt().correction_product
    product_by_history = {item.history_mode_digest: item for item in product.modes}

    assert set(product_by_history) == {item.mode_digest for item in posterior.modes}
    for history in posterior.modes:
        mode = product_by_history[history.mode_digest]
        assert mode.posterior_probability == history.posterior_probability
        assert mode.assignments == history.assignments
        assert mode.active_catalog_numbers == history.active_catalog_numbers


def test_navigation_eligibility_cannot_be_resealed_true() -> None:
    mode = next(item for item in _receipt().correction_product.modes if item.satellite_states)
    payload = mode.model_dump(mode="json", exclude={"mode_digest"})
    payload["navigation_eligible"] = True

    with pytest.raises(ValidationError):
        SequentialHistoryCorrectionModeV1.model_validate(
            {**payload, "mode_digest": canonical_digest(payload)}
        )


def test_product_rejects_receiver_local_field_and_probability_tamper() -> None:
    product = _receipt().correction_product
    payload = product.model_dump(mode="json", exclude={"content_digest"})
    payload["receiver_drift_hz_s"] = 1.0
    with pytest.raises(ValidationError):
        SequentialHistorySatelliteCorrectionProductV1.model_validate(
            {**payload, "content_digest": canonical_digest(payload)}
        )

    payload = product.model_dump(mode="json", exclude={"content_digest"})
    payload["modes"][0]["posterior_probability"] *= 0.5
    with pytest.raises(ValidationError):
        SequentialHistorySatelliteCorrectionProductV1.model_validate(
            {**payload, "content_digest": canonical_digest(payload)}
        )


def test_receipt_rejects_a_different_calibration_site() -> None:
    receipt = _receipt()
    payload = receipt.model_dump(mode="json", exclude={"content_digest"})
    payload["calibration_site"]["latitude_deg"] += 0.25

    with pytest.raises(ValidationError, match="opaque commitment"):
        type(receipt).model_validate({**payload, "content_digest": canonical_digest(payload)})


def test_builder_rejects_another_history_posterior() -> None:
    _graphs, banks, posterior, calibration, spans = _calibration_and_spans()
    poisoned = posterior.model_copy(
        update={"content_digest": canonical_digest({"posterior": "different"})}
    )
    end_utc_ns = max(item.end_utc_ns for item in spans)

    with pytest.raises(ValidationError, match="digest"):
        build_sequential_history_satellite_correction(
            posterior=poisoned,
            calibration=calibration,
            prediction_banks=banks,
            calibration_source_spans=spans,
            calibration_site=banks[0].observer_site,
            calibration_site_authority_digest=canonical_digest({"site": "authority"}),
            calibration_protocol_digest=canonical_digest({"protocol": "sequential"}),
            frequency_calibration_authority_digest=canonical_digest({"frequency": "authority"}),
            produced_utc_ns=end_utc_ns + 1_000_000_000,
            sealed_utc_ns=end_utc_ns + 2_000_000_000,
        )


def test_builder_rejects_a_mutated_frequency_calibration_receipt() -> None:
    _graphs, banks, posterior, calibration, spans = _calibration_and_spans()
    poisoned = replace(calibration, identity_claimed=True)
    end_utc_ns = max(item.end_utc_ns for item in spans)

    with pytest.raises(SatelliteCorrectionInputError, match="digest"):
        build_sequential_history_satellite_correction(
            posterior=posterior,
            calibration=poisoned,
            prediction_banks=banks,
            calibration_source_spans=spans,
            calibration_site=banks[0].observer_site,
            calibration_site_authority_digest=canonical_digest({"site": "authority"}),
            calibration_protocol_digest=canonical_digest({"protocol": "sequential"}),
            frequency_calibration_authority_digest=canonical_digest({"frequency": "authority"}),
            produced_utc_ns=end_utc_ns + 1_000_000_000,
            sealed_utc_ns=end_utc_ns + 2_000_000_000,
        )


def test_builder_rejects_early_production() -> None:
    _graphs, banks, posterior, calibration, spans = _calibration_and_spans()

    with pytest.raises(SatelliteCorrectionInputError, match="chronology"):
        build_sequential_history_satellite_correction(
            posterior=posterior,
            calibration=calibration,
            prediction_banks=banks,
            calibration_source_spans=spans,
            calibration_site=banks[0].observer_site,
            calibration_site_authority_digest=canonical_digest({"site": "authority"}),
            calibration_protocol_digest=canonical_digest({"protocol": "sequential"}),
            frequency_calibration_authority_digest=canonical_digest({"frequency": "authority"}),
            produced_utc_ns=min(item.end_utc_ns for item in spans),
            sealed_utc_ns=max(item.end_utc_ns for item in spans) + 1,
        )
