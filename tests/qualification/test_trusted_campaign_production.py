from pathlib import Path

import pytest

from leo.application import (
    TrustedCampaignProductionSettings,
    open_trusted_campaign_service,
)


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
