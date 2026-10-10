import pytest
from freeze import forbid_evaluation, selected_identity


def test_identity_whitelist_omits_all_historical_outcomes():
    member = dict(
        dataset="DS16",
        inventory_label="DS16-020",
        session_id="session",
        recording_manifest_sha256="recording",
        uncompressed_sha256="iq",
        research_errors={"fitted-c": {"error_km": 999.0}},
        reference_latitude_deg=5.0,
    )
    selected = selected_identity(dict(member=member))
    assert set(selected) == {
        "dataset",
        "inventory_label",
        "session_id",
        "recording_manifest_sha256",
        "uncompressed_sha256",
    }
    assert "research_errors" not in selected
    with pytest.raises(ValueError, match="evaluation"):
        forbid_evaluation({"nested": [{"reference_latitude_deg": 1.0}]})
    forbid_evaluation({"session_id": "session", "configuration": {"prior": {"latitude_deg": 1.0}}})
