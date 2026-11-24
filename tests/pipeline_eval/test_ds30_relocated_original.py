import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
import ds30_relocated_original as relocation
import ds30_relocation_ledger as ledger


def test_only_literal_same_basename_direct_archive_target_is_admitted(tmp_path, monkeypatch):
    old, current = (tmp_path / name for name in ("old", "current"))
    old.mkdir()
    current.mkdir()
    source, wrong = current / "capture", current / "similar-capture"
    source.mkdir()
    wrong.mkdir()
    monkeypatch.setattr(relocation, "LOGICAL", old)
    monkeypatch.setattr(relocation, "PHYSICAL", current)
    alias = old / "capture"
    alias.symlink_to(source, target_is_directory=True)
    assert relocation.spelling(alias) == source
    alias.unlink()
    alias.symlink_to(wrong, target_is_directory=True)
    with pytest.raises(ValueError, match="Unbound relocation"):
        relocation.spelling(alias)


def test_descriptor_authentication_detects_hash_mismatch_and_symlink(tmp_path):
    path = tmp_path / "expected"
    path.write_bytes(b"retained")
    (tmp_path / "alias").symlink_to(path)
    with relocation.directory(tmp_path) as handle:
        assert relocation.regular(handle, "expected", 8, relocation.digest(b"retained"))[1] == b"retained"
        with pytest.raises(ValueError, match="bytes changed"):
            relocation.regular(handle, "expected", 8, relocation.digest(b"modified"))
        with pytest.raises(ValueError, match="size/type"):
            relocation.regular(handle, "alias")


def test_payload_metadata_checks_never_open_same_sized_payload(tmp_path, monkeypatch):
    (tmp_path / "iq-000000.ci16.zst").write_bytes(b"test")
    with relocation.directory(tmp_path) as handle:
        monkeypatch.setattr(os, "open", lambda *a, **k: pytest.fail("payload metadata must only stat"))
        identity, payload = relocation.regular(handle, "iq-000000.ci16.zst", 4)
    assert identity[3] == 4 and payload is None


def test_only_exact_member_relative_path_is_supported():
    with pytest.raises(ValueError, match="one literal segment"):
        relocation.relative("/approved/record/segment/../file", Path("/approved/record"))
    with pytest.raises(ValueError):
        relocation.relative("/unrelated/record/segment/file", Path("/approved/record"))


def test_ledger_import_resumes_same_inode_and_refuses_to_replace(tmp_path):
    source, target = tmp_path / "proof", tmp_path / "retained"
    source.write_bytes(b"verified")
    assert ledger.link_immutable(source, target) == target
    assert ledger.link_immutable(source, target) == target
    assert source.samefile(target)
    wrong = tmp_path / "changed"
    wrong.write_bytes(b"verified")
    with pytest.raises(ValueError, match="cannot overwrite"):
        ledger.link_immutable(wrong, target)
