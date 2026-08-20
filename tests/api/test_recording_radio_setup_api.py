from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from leo.api import create_app
from leo.presentation.fixtures import build_fixture_repository, write_fixture_artifacts
from leo.presentation.models import RadioSetupV2, RecordingRadioSetupV2
from leo.presentation.repository import FixturePresentationRepository


class _InvalidRadioSetupRepository:
    def __init__(self, delegate: FixturePresentationRepository) -> None:
        self._delegate = delegate

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    def recording_radio_setup(self, session_id: str) -> RecordingRadioSetupV2 | None:
        raise ValueError("malformed authoritative tuning tags")


def test_v2_radio_setup_get_and_head_are_bounded_and_session_scoped(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    write_fixture_artifacts(artifact_root)
    source = build_fixture_repository(artifact_root)
    detail = source.recording_detail("retro-positive-68p7")
    assert detail is not None
    setup = RecordingRadioSetupV2(
        session_id=detail.session_id,
        radios=(
            RadioSetupV2(
                radio_id=detail.radios[0].radio_id,
                radio_index=0,
                applied_if_center_frequency_hz=1_440_312_500,
                target_rf_center_frequency_hz=11_190_312_500,
                applied_bandwidth_hz=2_500_000,
                applied_sample_rate_hz=2_500_000,
                starlink_channel="ch2",
                starlink_edge="upper",
                firmware_version="0.39-test",
            ),
        ),
    )
    repository = FixturePresentationRepository(
        (detail,), source.status(), radio_setups=(setup,)
    )
    client = TestClient(create_app(repository, artifact_root=artifact_root))

    response = client.get(f"/api/v2/recordings/{detail.session_id}/radio-setup")

    assert response.status_code == 200
    assert response.json() == setup.model_dump(mode="json")
    assert client.head(f"/api/v2/recordings/{detail.session_id}/radio-setup").status_code == 200
    assert client.get("/api/v2/recordings/missing/radio-setup").status_code == 404


def test_invalid_authoritative_radio_setup_projection_is_typed_unavailable(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    write_fixture_artifacts(artifact_root)
    source = build_fixture_repository(artifact_root)
    client = TestClient(
        create_app(_InvalidRadioSetupRepository(source), artifact_root=artifact_root)
    )

    for name, method in (("GET", client.get), ("HEAD", client.head)):
        response = method("/api/v2/recordings/retro-positive-68p7/radio-setup")
        assert response.status_code == 503
        if name == "GET":
            assert response.json()["detail"] == "recording setup projection is invalid"
