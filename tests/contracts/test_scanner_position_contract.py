import math

import pytest
from pydantic import ValidationError

from leo.contracts.scanner_position import (
    RegionPositionPriorV1,
    SparseScanPositionDiagnosticV1,
)

_DIGEST = "sha256:" + "1" * 64


def prior() -> RegionPositionPriorV1:
    return RegionPositionPriorV1(
        center_latitude_deg=39.7392,
        center_longitude_deg=-104.9903,
        width_km=14_484.096,
        height_km=14_484.096,
        altitude_m=0.0,
    )


def diagnostic(**updates) -> SparseScanPositionDiagnosticV1:
    values = dict(
        state="diagnostic",
        position_prior=prior(),
        source_count=2,
        track_count=2,
        fit_observation_count=2,
        evaluation_observation_count=1,
        selected_observation_ids=("a", "b", "c"),
        selected_observations_digest=_DIGEST,
        configuration_digest=_DIGEST,
        candidate_latitude_deg=40.0,
        candidate_longitude_deg=-105.0,
        training_rms_hz=12.0,
        evaluation_rms_hz=15.0,
        jacobian_rank=2,
        condition_number=12.0,
        boundary_hit=False,
        runtime_ms=3.0,
    )
    values.update(updates)
    return SparseScanPositionDiagnosticV1(**values)


def test_position_diagnostic_is_explicitly_conditional_and_not_a_fix() -> None:
    value = diagnostic()
    assert value.conditional_on_site_assisted_identity is True
    assert value.position_fix_claimed is False


@pytest.mark.parametrize("field", ["runtime_ms", "training_rms_hz", "condition_number"])
def test_position_diagnostic_rejects_non_finite_json_numbers(field: str) -> None:
    with pytest.raises(ValidationError):
        diagnostic(**{field: math.nan})


def test_position_diagnostic_requires_candidate_fields_only_for_diagnostic_state() -> None:
    with pytest.raises(ValidationError, match="incomplete"):
        diagnostic(candidate_latitude_deg=None)
    with pytest.raises(ValidationError, match="cannot publish a candidate"):
        diagnostic(state="insufficient", reasons=("too-few-tracks",))
