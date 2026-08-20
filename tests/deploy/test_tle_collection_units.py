from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_tle_collection_uses_local_state_and_named_credentials() -> None:
    service = (PROJECT_ROOT / "deploy/systemd/leo-tle-collection.service").read_text()
    timer = (PROJECT_ROOT / "deploy/systemd/leo-tle-collection.timer").read_text()

    assert "StateDirectory=leo/tle" in service
    assert "--root /var/lib/leo/tle" in service
    assert "/opt/leo-tracker/current/.venv/bin/python" in service
    assert "LoadCredential=space-track-identity:" in service
    assert "LoadCredential=space-track-password:" in service
    assert "InaccessiblePaths=/mnt/qnap01" in service
    assert "OnCalendar=hourly" in timer
    assert "Persistent=true" in timer
