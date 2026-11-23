from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def oracle(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("short_floor_raw")


def test_precomputed_rows_must_match_verified_window(oracle):
    acquisition = dict(global_visit=19, actual_if_center_hz=30, sample_start=123456)
    target = dict(channel=3, lnb_lo_hz=79000, edge="lower")
    window = SimpleNamespace(acquisition=acquisition, target=target, receiver_ids=(0, 1), sample_rate_hz=10000)
    rows = [dict(receiver_id=i, visit_index=19, edge="lower", channel=3, actual_rf_hz=79030,
                 valid_start_counter=123456, probe_index=0, probe_start_ms=0, payload_start_sample=3800,
                 candidates=[]) for i in (0, 1)]
    assert oracle.rows_for_window(window, rows) is rows
    for edits in (dict(receiver_id=0), dict(visit_index=18), dict(channel=1), dict(actual_rf_hz=79031),
                  dict(probe_index=1), dict(valid_start_counter=123444), dict(payload_start_sample=0)):
        with pytest.raises(ValueError):
            oracle.rows_for_window(window, [rows[0], dict(rows[1], **edits)])
    with pytest.raises(ValueError):
        oracle.rows_for_window(window, rows[:1])
