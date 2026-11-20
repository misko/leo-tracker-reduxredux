import csv
from collections import Counter

import pytest

from tools.pipeline_eval.qualification import roof_day_sensitivity as study


def test_publication_and_paired_tails_use_their_own_recordings():
    rows = [
        {"baseline_error_km": "0", "router_error_km": "0"},
        {"baseline_error_km": "0.5", "router_error_km": ""},
        {"baseline_error_km": "", "router_error_km": "6"},
        {"baseline_error_km": "0.5", "router_error_km": "1"},
    ]
    value = study.measurements(rows, "router")
    assert (value["offered"], value["published"], value["within_5km"]) == (4, 3, 2)
    assert (value["paired"], value["paired_within_110pct"]) == (2, 1)
    assert (value["median_km"], value["paired_test_p50"], value["paired_original_p50"]) == (
        1.0,
        0.5,
        0.25,
    )


def test_calendar_scores_reproduce_and_keep_the_undated_input_in_every_omission(tmp_path):
    study.publish(tmp_path)
    archived = study.STUDY / "time-sensitivity"
    for name in ("by-date.csv", "receipt.json"):
        assert (tmp_path / name).read_bytes() == (archived / name).read_bytes()
    with (tmp_path / "by-date.csv").open() as stream:
        rows = [r for r in csv.DictReader(stream) if r["arm"] == "c0" and r["method"] == "router"]
    assert Counter(r["scope"] for r in rows) == {"full": 1, "day": 8, "omit": 7}
    full = next(r for r in rows if r["scope"] == "full")
    unknown = next(r for r in rows if r["date_utc"] == "unknown")
    assert (full["offered"], full["published"]) == ("159", "154")
    assert (unknown["offered"], unknown["published"]) == ("1", "0")
    days = {r["date_utc"]: int(r["offered"]) for r in rows if r["scope"] == "day"}
    assert all(int(r["offered"]) == 159 - days[r["date_utc"]] for r in rows if r["scope"] == "omit")


def test_scores_reject_a_roster_with_a_duplicate_in_place_of_a_recording(tmp_path, monkeypatch):
    ids, authority = study.corpus._selection("ds26-all159")
    wrong_ids = [ids[0], *ids[:-1]]
    monkeypatch.setattr(study.corpus, "_selection", lambda panel: (wrong_ids, authority))
    with pytest.raises(ValueError, match="incomplete or duplicated"):
        study.publish(tmp_path)
