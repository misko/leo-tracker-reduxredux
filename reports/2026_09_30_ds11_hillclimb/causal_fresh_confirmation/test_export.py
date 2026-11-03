from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("causal_fresh_confirmation_export", HERE / "export.py")
export = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = export
SPEC.loader.exec_module(export)


def test_export_plan_membership_is_exact_and_ordered(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.write_text("bound")
    plan = {
        "schema": "ds11-causal-fresh-confirmation-export-plan/v1",
        "captures": [{"full_manifest_index": value} for value in (10, 18, 35, 60, 75)],
        "source_sha256": {str(source): export.digest(source)},
    }
    export.validate_export_plan(plan)
    plan["captures"][0]["full_manifest_index"] = 11
    with pytest.raises(ValueError, match="membership"):
        export.validate_export_plan(plan)
    plan["captures"][0]["full_manifest_index"] = 10
    source.write_text("changed")
    with pytest.raises(ValueError, match="source digest"):
        export.validate_export_plan(plan)
