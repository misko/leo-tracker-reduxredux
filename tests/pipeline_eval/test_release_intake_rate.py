import json
from pathlib import Path

import pytest

from reports.ALGO08.v3.release_intake_rate import byte_bounds, rate_gates, required_rate, summarize


def test_rounding_is_per_member():
    assert byte_bounds(4, 2, 4096) == (8194, 16384)
    with pytest.raises(ValueError):
        byte_bounds(1, 2, 4096)


def test_failed_job_and_setup_remain_charged_even_at_infinite_bandwidth():
    rows = [dict(elapsed_s=8, post_s=3, size=3_000_000), dict(elapsed_s=2, post_s=None, size=1_000_000)]
    assert rate_gates(rows, "size", 2, 2, .5) == pytest.approx(
        dict(median_ratio=(3.5/8 + 1)/2, sum_ratio=5.5/10))
    assert required_rate(rows, "size", 2, .5) is None


def test_observed_ledger_and_gate_thresholds():
    base = Path(__file__).resolve().parents[2]/"reports/ALGO08/v3/measurements"
    data = json.loads((base/"release-intake-rate.json").read_bytes())
    rows = data["rows"]
    assert len(rows) == len({r["case"] for r in rows}) == 100
    assert sum(r["post_s"] is None for r in rows) == 5
    assert all(r["byte_high"] >= r["byte_low"] > 0 for r in rows)
    assert summarize(rows) == data["summary"]
    threshold = required_rate(rows, "byte_high", 1.5, .5)
    assert .49 < max(threshold["sum_ratio"], threshold["median_ratio"]) <= .5
    assert max(rate_gates(rows, "byte_high", threshold["required_MB_s"]-.01, 1.5, .5).values()) > .5
