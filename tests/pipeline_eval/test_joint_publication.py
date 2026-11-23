from importlib import import_module
from pathlib import Path

import pytest

from leo.contracts.digests import canonical_digest


@pytest.mark.parametrize("wrong", [None, "digest", "session", "inventory", "receiver"])
def test_replay_requires_all_saved_input_bindings(wrong, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    verified_saved = import_module("joint_publication").verified_saved
    native = dict(source=dict(session_id="session", input_manifest_sha256="inventory"),
                  provenance=dict(detector_sha256="sha256:receiver"))
    args = dict(expected=canonical_digest(native), session="session", inventory_digest="inventory", receiver="receiver")
    if wrong:
        args[{"digest": "expected", "inventory": "inventory_digest"}.get(wrong, wrong)] = "wrong"
        with pytest.raises(ValueError):
            verified_saved(native, **args)
    else:
        assert verified_saved(native, **args) is native
