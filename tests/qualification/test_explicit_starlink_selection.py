from __future__ import annotations

import pytest
from pydantic import ValidationError

from leo.qualification.capture_modes import CaptureModeExpectationV1
from leo.qualification.frequency_calibration import FrequencyCalibrationPlanV1
from leo.qualification.legacy_oracle import LegacyOracleConfigV1


@pytest.mark.parametrize(
    ("model", "field_names"),
    (
        (FrequencyCalibrationPlanV1, ("starlink_channel", "starlink_edge")),
        (CaptureModeExpectationV1, ("starlink_channel", "starlink_edge")),
        (LegacyOracleConfigV1, ("edge",)),
    ),
)
def test_qualification_contracts_require_explicit_starlink_selection(
    model: type,
    field_names: tuple[str, ...],
) -> None:
    schema = model.model_json_schema()

    assert set(field_names) <= set(schema["required"])
    for field_name in field_names:
        assert model.model_fields[field_name].is_required()


def test_missing_capture_mode_channel_and_edge_fail_validation() -> None:
    with pytest.raises(ValidationError) as error:
        CaptureModeExpectationV1.model_validate(
            {
                "profile_name": "test",
                "profile_revision_digest": "sha256:" + "0" * 64,
                "radio_ids": ("radio-a", "radio-b"),
                "receiver_id": 0,
                "center_frequency_hz": 1,
                "rf_center_frequency_hz": 1,
                "sample_rate_hz": 1,
                "bandwidth_hz": 1,
                "gain_db": 40.0,
                "sample_count": 1,
            }
        )

    assert {item["loc"] for item in error.value.errors()} >= {
        ("starlink_channel",),
        ("starlink_edge",),
    }
