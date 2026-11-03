from __future__ import annotations

import hashlib
from pathlib import Path

import finite_set_rf_cohort_provenance as wrapper


def test_prevalidation_snapshot_includes_frozen_runner_and_missing_helper(tmp_path):
    inherited = tmp_path / "inherited.py"
    inherited.write_text("frozen")
    source_path = tmp_path / "fit.json"
    source_path.write_text("{}")
    source = {
        "source_hashes": {
            str(inherited.resolve()): hashlib.sha256(inherited.read_bytes()).hexdigest()
        }
    }
    paths = wrapper.prevalidation_snapshot_paths(source_path, source, "DS10-S01")
    names = {Path(path).name for path in paths}
    assert "finite_set_rf_cohort.py" in names
    assert "finite_set_tau_continue.py" in names
    assert "finite_set_rf_cohort_provenance.py" in names
    assert str(source_path.resolve()) in paths
    assert str(inherited.resolve()) in paths


def test_snapshot_occurs_before_frozen_validation(tmp_path):
    source_path = tmp_path / "fit.json"
    source_path.write_text("{}")
    source = {"source_hashes": {}}
    events = []

    def snapshotter(paths):
        assert str(source_path.resolve()) in paths
        events.append("snapshot")
        return {"snapshot": "complete"}

    def validator(value, unit_id):
        assert unit_id == "DS10-S01"
        events.append("validate")
        return value

    validated, snapshot = wrapper.snapshot_then_validate(
        source_path,
        source,
        "DS10-S01",
        snapshotter=snapshotter,
        validator=validator,
    )
    assert validated is source
    assert snapshot == {"snapshot": "complete"}
    assert events == ["snapshot", "validate"]


def test_core_fit_is_delegated_once_without_argument_changes():
    data = object()
    source_fit = {"banks": "frozen"}
    calls = []

    def fitter(received_data, received_fit):
        calls.append((received_data, received_fit))
        return {"fit": "unchanged"}

    result = wrapper.invoke_core_fit(data, source_fit, fitter=fitter)
    assert result == {"fit": "unchanged"}
    assert calls == [(data, source_fit)]


def test_legacy_receipt_is_recorded_read_only(tmp_path, monkeypatch):
    root = tmp_path / "experiment"
    path = root / "runs" / wrapper.core.RUN_ID / "DS10-S01" / "fit.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"frozen": true}')
    before = path.read_bytes()
    monkeypatch.setattr(wrapper, "ROOT", root)
    receipt = wrapper.legacy_receipt("DS10-S01")
    assert receipt["path"] == str(path.resolve())
    assert receipt["sha256"] == hashlib.sha256(before).hexdigest()
    assert receipt["preserved_in_place"] is True
    assert receipt["used_as_fit_input"] is False
    assert path.read_bytes() == before


def test_new_run_scope_and_budget_are_distinct_from_provisional():
    assert wrapper.RUN_ID == "finite-set-rf-cohort-provenance-v1"
    assert wrapper.RUN_ID != wrapper.core.RUN_ID
    assert wrapper.SUPPORTED_UNITS == wrapper.core.SUPPORTED_UNITS
    assert len(wrapper.SUPPORTED_UNITS) == 32
    assert wrapper.core.fit_rf_cohort_branches.__module__ == "finite_set_rf_cohort"
