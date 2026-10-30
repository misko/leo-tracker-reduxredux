"""The candidate stager packages all frozen source bytes without activation."""

import hashlib
import json
from pathlib import Path

import pytest
import stage_algo03_release as staging


def fake_git(monkeypatch, *, corrupt=None):
    name = "reports/frozen/README.md"
    data = b"frozen scientific evidence\n"
    manifest = json.dumps(dict(sha256={name: hashlib.sha256(data).hexdigest()})).encode()
    monkeypatch.setattr(staging, "MANIFEST_SHA256", hashlib.sha256(manifest).hexdigest())
    files = {staging.MANIFEST: manifest, name: data}
    if corrupt:
        files[corrupt] = b"changed"

    def git(source, *arguments):
        if arguments[0] == "rev-parse":
            return b"a" * 40
        assert arguments[0] == "show"
        return files[arguments[1].split(":", 1)[1]]

    monkeypatch.setattr(staging, "_git", git)
    return files


def test_stage_plan_contains_scientific_reports_and_cannot_touch_services(tmp_path, monkeypatch):
    files = fake_git(monkeypatch)
    (tmp_path / "runtime/bin").mkdir(parents=True)
    (tmp_path / "runtime/bin/python3.12").touch()
    (tmp_path / "uv").touch()
    result = staging.stage(tmp_path, "a" * 40, tmp_path / "runtime", tmp_path / "uv")
    assert set(files) <= set(result["archive_paths"])
    assert result["service_mutation"] is False
    assert result["recording_or_database_mutation"] is False
    assert not Path(result["release"]).exists()


@pytest.mark.parametrize("name", [staging.MANIFEST, "reports/frozen/README.md"])
def test_changed_frozen_members_rejected_before_staging(monkeypatch, name):
    fake_git(monkeypatch, corrupt=name)
    with pytest.raises(ValueError, match="frozen r1|scientific source changed"):
        staging.scientific_inventory(Path("."), "a" * 40)


def test_committed_r1_inventory_can_be_packaged():
    source = Path(__file__).resolve().parents[2]
    revision = staging._git(source, "rev-parse", "HEAD").decode().strip()
    files = staging.scientific_inventory(source, revision)
    assert staging.MANIFEST in files
    assert any(name.startswith("tests/") for name in files)
    assert any(name.startswith("reports/") and name != staging.MANIFEST for name in files)
