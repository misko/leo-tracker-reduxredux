from pathlib import Path
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3.exact_solver_0057 import archive_plan


def snapshot(name, size):
    return SimpleNamespace(path=Path("/original/archive") / name, byte_size=size)


def test_archival_view_plans_exact_signed_aliases_from_existing_regular_files(tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    (first / "100-signed.tle").write_bytes(b"body")
    (first / "200-signed.tle").write_bytes(b"wrong length")
    (second / "200-signed.tle").write_bytes(b"body")
    planned = archive_plan([snapshot("100-signed.tle", 4), snapshot("200-signed.tle", 4)],
                           (first, second), tmp_path.stat().st_dev)
    assert planned == {"100-signed.tle": first / "100-signed.tle", "200-signed.tle": second / "200-signed.tle"}


def test_archival_view_refuses_symlink_wrong_device_and_missing_timestamp(tmp_path):
    (tmp_path / "100-signed.tle").write_bytes(b"body")
    (tmp_path / "200-signed.tle").symlink_to(tmp_path / "100-signed.tle")
    dev = tmp_path.stat().st_dev
    for name, device in (("100-signed.tle", dev+1), ("200-signed.tle", dev), ("300-signed.tle", dev)):
        with pytest.raises(ValueError, match="No existing exact tmpfs snapshot"):
            archive_plan([snapshot(name, 4)], (tmp_path,), device)
