"""The native cost transfer must not absorb scan or callback time."""

from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports" / "ALGO08" / "v3"))
from attested_sparse_budget import factors_only, predicted_slices


def test_preserve_preheld_signed_fields_and_remove_durations_only():
    row = {"callback_timing": {"mixed": {"cpu_ns": 4}}, "iq_sha256": "original", "lanes": [
        {"named_native": {"cpu_ns": 1, "receiver_id": 0},
         "mixed_native": {"elapsed_ns": 2, "raw_candidates": [{"cfo": -123, "epoch": 917}]},
         "named_20ms": {"candidates": []}}
    ]}
    result = factors_only(row)
    assert result == {"iq_sha256": "original", "lanes": [
        {"named_native": {"receiver_id": 0}, "mixed_native": {"raw_candidates": [{"cfo": -123, "epoch": 917}]},
         "named_20ms": {"candidates": []}}
    ]}
    assert row["lanes"][0]["mixed_native"]["elapsed_ns"] == 2


def test_transfer_only_prices_two_direct_native_roles():
    model = {"one": {"full": 0.003, "short_primary": 0.0008}}
    costs = {"native": {"full": {"calls": 4, "cpu_ns": 12_000_000},
                        "short_primary": {"calls": 10, "cpu_ns": 10_000_000}},
             "callback_total_ns": {"cpu_ns": 75_000_000}}
    estimate = predicted_slices(model, costs)["one"]
    assert estimate["predicted_cpu_s"] == {"full": 0.012, "short_primary": 0.008, "native_sum": 0.02}
    assert estimate["actual_cpu_s"]["native_sum"] == pytest.approx(0.022)
    assert estimate["relative_error"]["short_primary"] == pytest.approx(-0.2)
