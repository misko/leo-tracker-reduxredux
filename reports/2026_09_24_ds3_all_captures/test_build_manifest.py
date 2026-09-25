from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ds3_manifest", HERE / "build_manifest.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["ds3_manifest"] = module
spec.loader.exec_module(module)


def test_assemble_requires_the_frozen_56_sessions(monkeypatch) -> None:
    rows = [
        {
            "session_id": f"scan-fw-{index:016x}",
            "recording_complete": True,
            "qualified_utc_timing": True,
            "admission_status": "included",
        }
        for index in range(56)
    ]
    monkeypatch.setattr(module, "discover", lambda _root, _cutoff: rows)
    ds2 = {"sessions": [{"session_id": row["session_id"]} for row in rows[:22]]}
    document = module.assemble(Path("/read-only"), ds2)
    assert document["counts"]["new_since_ds2_22"] == 34
    assert document["counts"]["ds2_22_missing_from_cutoff"] == 0
