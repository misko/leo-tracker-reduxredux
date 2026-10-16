from pathlib import Path


def test_base_service_and_upgrade_prepare_orbit_namespace_for_service_user():
    root = Path(__file__).resolve().parents[2]
    required = (
        "ExecStartPre=+/usr/bin/install -d -o leo -g leo -m 0750 /srv/bulk/leo/fast-scan-orbits-v1"
    )
    for name in ("leo-fast-scan-analysis.service", "leo-fast-scan-orbits.conf"):
        text = (root / "deploy/systemd" / name).read_text()
        assert required in text
    service = (root / "deploy/systemd/leo-fast-scan-analysis.service").read_text()
    assert "User=leo\n" in service
    assert "ReadWritePaths=/srv/bulk/leo\n" in service
