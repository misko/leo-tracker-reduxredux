import importlib.util
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("confirmation_selection", HERE / "selection.py")
SELECTION = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = SELECTION
SPEC.loader.exec_module(SELECTION)


def _row(session_id, start, end):
    return {
        "session_id": session_id,
        "manifest_sha256": "sha256:" + "0" * 64,
        "capture_start_utc_ns": start,
        "capture_start_earliest_utc_ns": start,
        "capture_end_utc_ns": end,
        "utc_qualified": True,
        "exclusion_reasons": [],
    }


def test_closed_interval_overlap_includes_shared_endpoint():
    assert SELECTION.overlaps((10, 20), (20, 30))
    assert SELECTION.overlaps((10, 20), (11, 19))
    assert not SELECTION.overlaps((10, 19), (20, 30))


def test_fake_cohort_excludes_interval_overlap_and_is_deterministic(tmp_path, monkeypatch):
    prior = tmp_path / "prior.json"
    authority = tmp_path / "authority.json"
    prior.write_text(json.dumps({"selected": {"DX": [_row("old", 20, 30)]}}))
    rows = [_row(f"s{i}", i * 10, i * 10 + 5) for i in range(5)]
    rows.insert(2, _row("overlap-with-different-id", 25, 35))
    authority.write_text(json.dumps({"captures": rows}))
    monkeypatch.setattr(SELECTION, "PRIOR", prior)
    monkeypatch.setattr(SELECTION, "AUTHORITIES", {"DX": authority})
    monkeypatch.setattr(SELECTION, "COUNTS", {"DX": 2})
    first = SELECTION.build()
    second = SELECTION.build()
    assert first == second
    assert first["eligibility"]["DX"]["excluded_interval_overlap_session_ids"] == [
        "overlap-with-different-id",
        "s2",
        "s3",
    ]
    assert [row["session_id"] for row in first["selected"]["DX"]] == ["s0", "s4"]


def test_frozen_panel_rebuilds_exactly_and_has_no_prior_interval_overlap():
    frozen = json.loads((HERE / "selection.json").read_text())
    assert SELECTION.build() == frozen
    assert {dataset: len(rows) for dataset, rows in frozen["selected"].items()} == {
        "DS9": 11,
        "DS10": 11,
        "DS11": 10,
    }
    prior = json.loads(SELECTION.PRIOR.read_text())
    prior_intervals = [
        SELECTION.interval(row)
        for rows in prior["selected"].values()
        for row in rows
    ]
    selected = [row for rows in frozen["selected"].values() for row in rows]
    assert len({row["session_id"] for row in selected}) == 32
    assert all(
        not SELECTION.overlaps(SELECTION.interval(row), prior_interval)
        for row in selected
        for prior_interval in prior_intervals
    )
    assert all(
        row["unit_id"] == f"{dataset}-F{row['authority_index'] + 1:03d}"
        for dataset, rows in frozen["selected"].items()
        for row in rows
    )
