import importlib
from collections import Counter
from pathlib import Path

import pytest

from test_selector_occupancy import packet


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return importlib.import_module("selector_occupancy_position")


def test_two_projections_keep_same_measured_source_and_explicit_erasure_ledger(runner):
    source = packet("radio")
    source["source"]["session_id"] = "session"
    source["source"]["probes"][0]["candidates"] = []
    source["source"]["probes"][64]["candidates"] = []
    original = source["source"]["probes"]

    masked_a, unfiltered, rows_a = runner.projection(source, "unfiltered")
    masked_b, history, rows_b = runner.projection(source, "history")
    assert masked_a == masked_b
    assert set(rows_a) == set(rows_b)
    assert source["source"]["qualified"]
    assert all(not item["source"]["qualified"] and item["provenance"]["detector_sha256"] is None
               for item in [unfiltered, history])
    assert Counter(row["state"] for row in rows_a.values()) == Counter(
        native_empty=1, erased_empty=1, erased_positive=63, observed=191,
    )
    assert any(row["state"] == "history_rejected" for row in rows_b.values())
    for index, (old, kept) in enumerate(zip(original, history["source"]["probes"], strict=True)):
        assert dict(old, candidates=[]) == dict(kept, candidates=[])
        assert kept["candidates"] in ([], unfiltered["source"]["probes"][index]["candidates"])
