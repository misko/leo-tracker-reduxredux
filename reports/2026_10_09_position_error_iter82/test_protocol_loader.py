import hashlib
import sys
import types

import pytest
from protocol_loader import verified_protocol


def test_ignores_unrelated_freeze_module(tmp_path, monkeypatch):
    payload = b'{"membership": ["DS17-001"]}\n'
    (tmp_path / "protocol.json").write_bytes(payload)
    (tmp_path / "protocol.sha256").write_text(
        "sha256:" + hashlib.sha256(payload).hexdigest()
    )
    monkeypatch.setitem(sys.modules, "freeze", types.ModuleType("wrong_freeze"))
    assert verified_protocol(tmp_path) == {"membership": ["DS17-001"]}


def test_rejects_changed_protocol(tmp_path):
    (tmp_path / "protocol.json").write_text("{}")
    (tmp_path / "protocol.sha256").write_text("sha256:wrong")
    with pytest.raises(AssertionError):
        verified_protocol(tmp_path)
