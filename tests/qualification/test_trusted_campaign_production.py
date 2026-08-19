from pathlib import Path

import pytest

from leo.application import (
    TrustedCampaignProductionSettings,
    open_trusted_campaign_service,
)
from leo.application.trusted_campaign_production import _close_all


def test_production_factory_rejects_non_postgresql_before_filesystem_access(
    tmp_path: Path,
) -> None:
    settings = TrustedCampaignProductionSettings(
        database_url="sqlite+pysqlite:///:memory:",
        bulk_root=tmp_path / "absent-bulk",
        qualification_root=tmp_path / "absent-qualification",
        capture_evidence_root=tmp_path / "absent-capture",
        legacy_evidence_root=tmp_path / "absent-legacy",
        pipeline_release_id="trusted-release",
    )
    with pytest.raises(ValueError, match="PostgreSQL"):
        open_trusted_campaign_service(settings)
    assert not any(tmp_path.iterdir())


def test_resource_cleanup_attempts_every_close_and_reports_all_failures() -> None:
    calls: list[str] = []

    def close(name: str, *, fail: bool = False) -> None:
        calls.append(name)
        if fail:
            raise RuntimeError(name)

    with pytest.raises(BaseExceptionGroup) as caught:
        _close_all(
            lambda: close("outputs", fail=True),
            lambda: close("recordings"),
            lambda: close("engine", fail=True),
        )

    assert calls == ["outputs", "recordings", "engine"]
    assert [str(error) for error in caught.value.exceptions] == ["outputs", "engine"]
