"""The new opportunity starts only from the pinned old extent and inode."""

from pathlib import Path
import stat
import sys
from types import SimpleNamespace

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports" / "ALGO08" / "v3"))
import first_member_0163_resume as resume


def test_first_member_resume_requires_exact_committed_prefix(monkeypatch):
    inode = 123
    source = Path("/srv/bulk/recording/first/iq-000000.ci16.zst")
    info = SimpleNamespace(st_dev=resume.DEVICE, st_ino=inode, st_size=resume.SIZE,
                          st_mtime_ns=44, st_ctime_ns=55, st_mode=stat.S_IFREG)
    monkeypatch.setattr(Path, "lstat", lambda _: info)
    digest = "sha256:" + "a" * 64
    first = {"compressed_sha256": digest}
    saved = dict(verified_partial_bytes=resume.PREFIX_BYTES, verified_partial_sha256=resume.PREFIX_SHA,
                 checkpoint_sha256=resume.OLD_JOURNAL_PIN, permit_analysis=False)
    journal = dict(source_identity=resume.identity(info), relative="first/iq-000000.ci16.zst",
                   size=resume.SIZE, sha256=digest, prefixes=[(resume.PREFIX_BYTES, resume.PREFIX_SHA)])
    assert resume.extent_and_checkpoint(source, first, inode, saved, journal).size - resume.PREFIX_BYTES == 43_068_882
    with pytest.raises(ValueError, match="inode"):
        resume.extent_and_checkpoint(source, first, inode + 1, saved, journal)
    with pytest.raises(ValueError, match="committed prefix"):
        resume.extent_and_checkpoint(source, first, inode, dict(saved, verified_partial_bytes=0), journal)
