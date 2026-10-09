import pytest
from pydantic import ValidationError

from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position_v3 import RegionalPositionDocumentV3
from tests.contracts.test_regional_position_v2 import document as old_document


def document():
    payload = old_document().model_dump(mode="json")
    payload.update(schema_version=3, analysis_id="scanner-regional-position-v3")
    payload["configuration"]["protocol"] = "sacramento-hard60-b7-v1"
    payload["configuration_sha256"] = canonical_digest(payload["configuration"])
    payload["windows"] = 10
    payload["methods"][0]["state"] = "diagnostic"
    for arm in payload["methods"][0]["arms"]:
        arm.update(
            completed_starts=1,
            reasons=[],
            selected=dict(
                accepted_stage="B1",
                joint_state=None,
                latitude_deg=38.58,
                longitude_deg=-121.49,
                east_km=0,
                north_km=0,
                objective=100,
                calibration_penalty=1,
                selection_score=101,
                posterior_rms_hz=10,
                signal_windows=9,
                stationarity=0.0001,
                converged=True,
                boundary=False,
                coefficient_hz_per_ghz=0,
                horizontal_error_m=100,
                satellites=[1, 2, 3, 4],
                associated_windows=9,
                source_basin="point:0:0",
                stop_reason="stationary",
            ),
        )
    return RegionalPositionDocumentV3.model_validate(payload)


def test_b7_contract_roundtrip_and_historical_contract_unchanged():
    doc = document()
    assert RegionalPositionDocumentV3.model_validate_json(doc.model_dump_json()) == doc
    assert old_document().schema_version == 2


def test_joint_stage_cannot_omit_its_model_state():
    value = document().model_dump(mode="json")
    value["methods"][0]["arms"][0]["selected"]["accepted_stage"] = "B7"
    with pytest.raises(ValidationError, match="model state"):
        RegionalPositionDocumentV3.model_validate(value)


def joint_document():
    payload = document().model_dump(mode="json")
    for arm in payload["methods"][0]["arms"]:
        selected = arm["selected"]
        selected.update(
            accepted_stage="B7",
            calibration_penalty=0,
            selection_score=100,
            joint_state=dict(
                stage="B7",
                vector=[0.0] * 11,
                clock_coefficients=[0.0] * 9,
                clock_nodes_s=[0.0, 30.0, 60.0, 90.0],
                clock_knots_hz=[[0.0] * 4] * 2,
                receiver_baseline_hz=[0.0] * 10,
                rf_time_coefficients=[0.0, 0.0],
                satellite_centers_s=[45.0] * 4,
                satellite_offsets_hz=[0.0] * 4,
                satellite_slopes_hz_s=[0.0] * 4,
                likelihood_nll=99.0,
                timing_penalty=0.5,
                nuisance_penalty=0.5,
                total_objective=100.0,
            ),
        )
    return RegionalPositionDocumentV3.model_validate(payload)


@pytest.mark.parametrize("mutation", ["penalty", "total", "position", "rf-lock"])
def test_joint_publication_rejects_inconsistent_state(mutation):
    value = joint_document().model_dump(mode="json")
    selected = value["methods"][0]["arms"][1]["selected"]
    if mutation == "penalty":
        selected["calibration_penalty"] = 0.5
        selected["selection_score"] += 0.5
    elif mutation == "total":
        selected["joint_state"]["nuisance_penalty"] += 1
    elif mutation == "position":
        selected["joint_state"]["vector"][0] = 1
    else:
        selected["joint_state"]["rf_time_coefficients"][0] = 1
    with pytest.raises(ValidationError):
        RegionalPositionDocumentV3.model_validate(value)
