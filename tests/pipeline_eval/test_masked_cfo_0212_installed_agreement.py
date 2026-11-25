from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def study(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("masked_cfo_0212_installed_agreement")


def test_lost_owners_keep_original_satellite_and_only_count_actual_cfo_changes(study):
    before = {key: dict(norad=norad, role=role) for key, norad, role in (
        ("retained", 100, "conditional"), ("unedited", 100, "conditional"),
        ("null", 100, "conditional"), ("changed", 200, "predictive"),
        ("conditional", 200, "conditional"))}
    after = {"retained": dict(norad=101, role="predictive"), "added": dict(norad=100, role="conditional")}
    edits = {"null": dict(original_hz=-5., updated_hz=-5.), "changed": dict(original_hz=-5., updated_hz=-7.)}
    group = study.lost_groups(before, after, edits)
    assert group["total"] == 4 and group["changed"] == 1
    assert group["groups"] == [
        dict(cfo_changed=False, ordinary_norad=100, ordinary_role="conditional", n=2),
        dict(cfo_changed=False, ordinary_norad=200, ordinary_role="conditional", n=1),
        dict(cfo_changed=True, ordinary_norad=200, ordinary_role="predictive", n=1)]
    assert group["owner_rows_sha256"] == study.residual.digest([
        ["changed", True, 200, "predictive"], ["conditional", False, 200, "conditional"],
        ["null", False, 100, "conditional"], ["unedited", False, 100, "conditional"]])
